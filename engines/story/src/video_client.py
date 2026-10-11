"""
Unified Video Client — Single interface for generating video from any registered model.

Routes requests to the correct provider (Gemini API, fal.ai, or Vertex AI) based
on the model registry. Handles retries, cost tracking, and model fallback.
"""

import logging
import mimetypes
import os
import time
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import Config
from src.video_models import (
    VideoModelConfig,
    VIDEO_MODEL_REGISTRY,
    TIER_FALLBACK_ORDER,
    get_model,
    estimate_cost,
)

logger = logging.getLogger(__name__)


class VideoGenerationError(Exception):
    """Raised when video generation fails after all retries."""
    pass


class UnifiedVideoClient:
    """
    Generates video clips through a single interface, routing to the correct
    provider (fal.ai or Vertex AI) based on the active model.

    Usage:
        client = UnifiedVideoClient("kling-2.5-turbo-pro")
        video_path = client.generate_video(
            prompt="A cat walking through a garden",
            output_dir=Path("output/temp/my_project"),
            filename="scene_1.mp4",
        )
    """

    def __init__(self, model_id: Optional[str] = None):
        if model_id is None:
            model_id = "kling-2.5-turbo-pro"
        self._model = get_model(model_id)
        self._total_cost: float = 0.0
        self._generation_count: int = 0
        self._fal_client = None  # lazy import
        self._last_error: Optional[str] = None
        self._fallback_errors: List[str] = []

    @property
    def model(self) -> VideoModelConfig:
        return self._model

    @property
    def model_id(self) -> str:
        return self._model.model_id

    def switch_model(self, model_id: str) -> None:
        """Switch to a different model mid-run."""
        old_id = self._model.model_id
        self._model = get_model(model_id)
        logger.info(f"[video_client] Switched model: {old_id} -> {model_id}")

    def get_total_cost(self) -> float:
        """Return cumulative estimated cost across all generations."""
        return round(self._total_cost, 4)

    def get_generation_count(self) -> int:
        return self._generation_count

    def generate_video(
        self,
        prompt: str,
        output_dir: Path,
        filename: str = "output.mp4",
        duration: int = 5,
        resolution: str = "720p",
        include_audio: bool = False,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        dialogue: Optional[str] = None,
        voice_profile: Optional[str] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[str]:
        """
        Generate a video clip and save it locally.

        Args:
            prompt: Text prompt describing the scene.
            output_dir: Directory to save the output file.
            filename: Output filename (default: output.mp4).
            duration: Clip duration in seconds.
            resolution: Target resolution (e.g. "720p", "1080p").
            include_audio: Whether to request native audio from the model.
            image_url: URL of an input image for image-to-video.
            image_path: Local path to an input image (uploaded for fal.ai, used directly for Vertex).
            reference_images: List of image URLs/paths for reference-to-video (Seedance 2.0).
            dialogue: Character dialogue (used for Vertex AI Veo lip-sync).
            voice_profile: Voice description (used for Vertex AI Veo).
            on_poll: Callback for polling progress updates.

        Returns:
            Path to the saved video file, or None on failure.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename

        logger.info(
            f"[video_client] Generating video with {self._model.display_name} "
            f"({self._model.model_id}) — {duration}s @ {resolution}, audio={include_audio}"
        )

        try:
            if self._model.provider == "gemini_api":
                result_path = self._generate_gemini_api(
                    prompt=prompt,
                    output_path=str(output_path),
                    duration=duration,
                    resolution=resolution,
                    image_path=image_path,
                    reference_images=reference_images,
                    dialogue=dialogue or "",
                    voice_profile=voice_profile or "",
                    on_poll=on_poll,
                )
            else:
                result_path = self._generate_fal(
                    prompt=prompt,
                    output_path=str(output_path),
                    duration=duration,
                    resolution=resolution,
                    include_audio=include_audio,
                    image_url=image_url,
                    image_path=image_path,
                    reference_images=reference_images,
                )
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[video_client] Generation failed ({self._model.model_id}): {e}")
            return None

        # Track cost
        cost = estimate_cost(self._model.model_id, duration, include_audio)
        self._total_cost += cost
        self._generation_count += 1
        logger.info(
            f"[video_client] Generation #{self._generation_count} complete — "
            f"estimated cost: ${cost:.4f} (total: ${self._total_cost:.4f})"
        )

        return result_path

    # ── fal.ai provider ─────────────────────────────────────────────────────

    def _get_fal_client(self):
        """Lazy-import fal_client to avoid import errors when not installed."""
        if self._fal_client is None:
            import fal_client
            self._fal_client = fal_client
        return self._fal_client

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        before_sleep=lambda rs: logger.warning(
            f"fal.ai request failed (attempt {rs.attempt_number}), retrying: {rs.outcome.exception()}"
        ),
    )
    def _generate_fal(
        self,
        prompt: str,
        output_path: str,
        duration: int = 5,
        resolution: str = "720p",
        include_audio: bool = False,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
    ) -> str:
        """Generate video via fal.ai and download to output_path."""
        fal = self._get_fal_client()
        model = self._model

        # Determine endpoint
        if reference_images and model.endpoint_ref2v:
            endpoint = model.endpoint_ref2v
        elif (image_url or image_path) and model.endpoint_i2v:
            endpoint = model.endpoint_i2v
        else:
            endpoint = model.endpoint_t2v

        # Build arguments
        arguments: dict = {"prompt": prompt}

        if duration:
            arguments["duration"] = str(duration)
        if resolution:
            arguments["resolution"] = resolution

        # Image-to-video: upload local file or pass URL
        if image_path and not image_url:
            image_url = fal.upload_file(image_path)
        if image_url and not reference_images:
            arguments["image_url"] = image_url

        # Reference-to-video (Seedance 2.0)
        if reference_images and model.endpoint_ref2v:
            ref_urls = []
            for ref in reference_images:
                if ref.startswith("http"):
                    ref_urls.append(ref)
                else:
                    ref_urls.append(fal.upload_file(ref))
            arguments["reference_images"] = [{"url": u} for u in ref_urls]

        # Audio control — disable by default (use our own TTS pipeline)
        if not include_audio and model.has_audio:
            arguments["enable_audio"] = False

        logger.info(f"[video_client] fal.ai call: {endpoint} — {list(arguments.keys())}")

        def _on_queue_update(update):
            logger.debug(f"[video_client] fal queue: {update}")

        result = fal.subscribe(
            endpoint,
            arguments=arguments,
            with_logs=True,
            on_queue_update=_on_queue_update,
        )

        # Extract video URL from result
        video_url = None
        if isinstance(result, dict):
            video = result.get("video", {})
            if isinstance(video, dict):
                video_url = video.get("url")
            if not video_url:
                # Some models return at top level
                video_url = result.get("url")

        if not video_url:
            raise VideoGenerationError(
                f"fal.ai returned no video URL. Response keys: {list(result.keys()) if isinstance(result, dict) else type(result)}"
            )

        # Download to local path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(video_url, output_path)
        size_kb = Path(output_path).stat().st_size // 1024
        logger.info(f"[video_client] Downloaded fal.ai video: {output_path} ({size_kb} KB)")

        return output_path

    # ── Gemini API provider (direct google.genai SDK) ────────────────────────

    _gemini_client = None  # lazy init

    def _get_gemini_client(self):
        """Lazy-import and cache the Gemini API client."""
        if self._gemini_client is None:
            from google import genai
            self._gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
        return self._gemini_client

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=10, max=60),
        before_sleep=lambda rs: logger.warning(
            f"Gemini API request failed (attempt {rs.attempt_number}), retrying: {rs.outcome.exception()}"
        ),
    )
    def _generate_gemini_api(
        self,
        prompt: str,
        output_path: str,
        duration: int = 8,
        resolution: str = "720p",
        image_path: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        dialogue: str = "",
        voice_profile: str = "",
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> str:
        """Generate video via the Gemini API (google.genai SDK)."""
        from google.genai import types

        client = self._get_gemini_client()
        model_name = self._model.endpoint_t2v

        # Append dialogue/voice to prompt for native lip-sync and audio
        full_prompt = prompt
        if dialogue:
            full_prompt += (
                f"\n\nThe character speaks the following dialogue with natural "
                f"lip-sync and expressive body language: \"{dialogue}\""
            )
        if voice_profile:
            full_prompt += f"\nVoice style: {voice_profile}."

        # Build config
        config = types.GenerateVideosConfig(
            aspect_ratio="9:16",
        )

        # Reference images (veo-3.1 and veo-3.1-fast, up to 3)
        # Checked first because image + reference_images cannot be combined —
        # the Veo API rejects the request with 400 INVALID_ARGUMENT.
        use_refs = bool(reference_images and self._model.has_reference_images)
        if use_refs:
            ref_imgs = []
            for ref_path in reference_images[:3]:
                ref_file = Path(ref_path)
                if ref_file.exists():
                    mime = mimetypes.guess_type(ref_path)[0] or "image/png"
                    ref_imgs.append(types.VideoGenerationReferenceImage(
                        image=types.Image(
                            image_bytes=ref_file.read_bytes(),
                            mime_type=mime,
                        ),
                        reference_type="asset",
                    ))
            if ref_imgs:
                config.reference_images = ref_imgs

        # Image input for image-to-video (only when NOT using reference_images)
        image_input = None
        if image_path and not use_refs:
            img_file = Path(image_path)
            if img_file.exists():
                mime = mimetypes.guess_type(image_path)[0] or "image/png"
                image_input = types.Image(
                    image_bytes=img_file.read_bytes(),
                    mime_type=mime,
                )

        # Submit generation
        kwargs = {"model": model_name, "prompt": full_prompt, "config": config}
        if image_input:
            kwargs["image"] = image_input

        logger.info(
            f"[video_client] Gemini API call: {model_name} — "
            f"prompt={len(full_prompt)} chars, image={'yes' if image_input else 'no'}, "
            f"refs={len(config.reference_images) if hasattr(config, 'reference_images') and config.reference_images else 0}"
        )

        operation = client.models.generate_videos(**kwargs)

        # Poll until completion
        poll_max = 300
        deadline = time.time() + poll_max
        while not operation.done:
            if time.time() > deadline:
                raise VideoGenerationError(
                    f"Gemini API video generation timed out after {poll_max}s"
                )
            elapsed = int(time.time() - (deadline - poll_max))
            logger.info(f"[video_client] Gemini API polling... ({elapsed}s)")
            if on_poll:
                on_poll(elapsed)
            time.sleep(10)
            operation = client.operations.get(operation)

        if operation.error:
            raise VideoGenerationError(f"Gemini API error: {operation.error}")

        # Extract and save video
        response = operation.response
        if not response:
            raise VideoGenerationError(
                "Gemini API: operation completed but response is empty"
            )

        if not response.generated_videos:
            # Possible content filtering — inspect response for clues
            reason = getattr(response, "filter_reason", None) or getattr(response, "blocked_reason", None)
            if reason:
                raise VideoGenerationError(
                    f"Gemini API: video blocked by safety filter — {reason}"
                )
            raise VideoGenerationError(
                "Gemini API: no videos in response (prompt may have been filtered)"
            )

        video = response.generated_videos[0]
        if not hasattr(video, "video") or not video.video:
            reject = getattr(video, "rejection_reason", None) or getattr(video, "filter_reason", None)
            if reject:
                raise VideoGenerationError(
                    f"Gemini API: video rejected — {reject}"
                )
            raise VideoGenerationError(
                "Gemini API: video entry empty (content may have been filtered)"
            )

        raw = video.video
        out = Path(output_path)
        if raw.video_bytes:
            out.write_bytes(raw.video_bytes)
        elif raw.uri:
            uri = raw.uri
            if "key=" not in uri:
                uri = f"{uri}&key={Config.GEMINI_API_KEY}"
            urllib.request.urlretrieve(uri, str(out))
        else:
            raise VideoGenerationError("Gemini API: no video_bytes or uri in response")
        logger.info(
            f"[video_client] Gemini API video saved: {out} ({out.stat().st_size // 1024} KB)"
        )
        return str(out)

    # ── Provider availability ──────────────────────────────────────────────

    @staticmethod
    def _is_provider_available(provider: str) -> tuple:
        """Check if a provider's SDK is installed. Returns (available, reason)."""
        if provider == "fal.ai":
            try:
                import fal_client  # noqa: F401
                return True, ""
            except ImportError:
                return False, "fal_client not installed (pip install fal-client)"
        return True, ""

    def get_fallback_errors(self) -> List[str]:
        """Return the per-model error list from the last generate_with_fallback call."""
        return list(self._fallback_errors)

    # ── Fallback logic ──────────────────────────────────────────────────────

    def generate_with_fallback(
        self,
        prompt: str,
        output_dir: Path,
        filename: str = "output.mp4",
        duration: int = 5,
        resolution: str = "720p",
        include_audio: bool = False,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        dialogue: Optional[str] = None,
        voice_profile: Optional[str] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[str]:
        """
        Try generating with the active model, falling back to other models
        in the same tier on failure.
        """
        tier = self._model.tier
        fallback_order = TIER_FALLBACK_ORDER.get(tier, [])

        # Start from the current model's position in the fallback order
        current_id = self._model.model_id
        if current_id in fallback_order:
            start_idx = fallback_order.index(current_id)
            models_to_try = fallback_order[start_idx:] + fallback_order[:start_idx]
        else:
            models_to_try = [current_id] + fallback_order

        # Deduplicate while preserving order
        seen = set()
        unique_models = []
        for mid in models_to_try:
            if mid not in seen:
                seen.add(mid)
                unique_models.append(mid)

        errors: List[str] = []

        for model_id in unique_models:
            model_cfg = get_model(model_id)

            # Skip models whose provider SDK isn't installed
            available, reason = self._is_provider_available(model_cfg.provider)
            if not available:
                msg = f"{model_cfg.display_name}: {reason}"
                errors.append(msg)
                logger.warning(f"[video_client] Skipping {model_id} — {reason}")
                continue

            if model_id != self._model.model_id:
                logger.warning(f"[video_client] Falling back to model: {model_id}")
                self.switch_model(model_id)

            # Clamp duration and resolution to the fallback model's capabilities
            effective_duration = min(duration, model_cfg.max_duration_sec)
            effective_resolution = model_cfg.max_resolution
            # Only pass reference_images if this model supports them
            effective_refs = reference_images if model_cfg.has_reference_images else None

            result = self.generate_video(
                prompt=prompt,
                output_dir=output_dir,
                filename=filename,
                duration=effective_duration,
                resolution=effective_resolution,
                include_audio=include_audio,
                image_url=image_url,
                image_path=image_path,
                reference_images=effective_refs,
                dialogue=dialogue,
                voice_profile=voice_profile,
                on_poll=on_poll,
            )
            if result:
                return result

            errors.append(f"{model_cfg.display_name}: {self._last_error or 'unknown error'}")
            logger.warning(f"[video_client] Model {model_id} failed, trying next...")

        self._fallback_errors = errors
        logger.error("[video_client] All fallback models exhausted")
        return None
