"""
Unified Video Client — Single interface for generating video from any registered model.

Routes requests to the correct provider (Gemini API or fal.ai) based
on the model registry. Handles retries, cost tracking, and model fallback.
Only models with a `verified` record in registry.json are ever called (review B8).

Billing safety (review B6): a generation is split into submit, wait and download.
Only the submit starts a paid job, so it is retried only when the error proves the
request never reached the provider (connection refused, DNS failure). Once a submit
succeeded, waiting and downloading are retried on their own and never re-submit.
Every attempt is recorded in `attempts`; `on_attempt(event, attempt)` is called with
"submitted" (billed), "succeeded" or "failed" so callers can keep a spend ledger.
A submit that fails in a way that may have reached the provider (a timeout after
sending, a 5xx, a dropped connection) is never retried and is counted as billed with
`attempt["uncertain"] = True`, so the ledger never under-counts.
"""

import logging
import mimetypes
import os
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import Config
from src.video_models import (
    VideoModelConfig,
    TIER_FALLBACK_ORDER,
    clip_duration,
    get_model,
    estimate_cost,
)

logger = logging.getLogger(__name__)


class VideoGenerationError(Exception):
    """Raised when video generation fails after all retries."""
    pass


# Errors that prove a submit never reached the provider: safe to retry the submit.
_SUBMIT_NOT_STARTED_ERRORS = (ConnectionRefusedError, socket.gaierror)
# Transient errors while waiting for or downloading an already-submitted job.
# Retrying these never starts a new (paid) generation.
_TRANSIENT_ERRORS = (ConnectionError, TimeoutError, OSError)
try:
    # fal_client and google-genai talk through httpx: ConnectError means the TCP/TLS
    # connection never opened (nothing was sent); TransportError covers read timeouts too.
    import httpx
    _SUBMIT_NOT_STARTED_ERRORS += (httpx.ConnectError,)
    _TRANSIENT_ERRORS += (httpx.TransportError,)
except ImportError:
    pass
try:
    from fal_client.auth import MissingCredentialsError  # raised before any request is made
    _SUBMIT_NOT_STARTED_ERRORS += (MissingCredentialsError,)
except ImportError:
    pass


def _submit_may_have_reached_provider(exc: BaseException) -> bool:
    """
    True when a failed submit may still have started a paid job (count it, never retry). Only a
    request that provably never left (connection refused, DNS failure, missing credentials) or a
    4xx rejection other than 408 counts as not started; anything else is counted.
    """
    if isinstance(exc, _SUBMIT_NOT_STARTED_ERRORS):
        return False
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return not (400 <= status < 500 and status != 408)
    return True


_FAL_SUBMIT_LOCK = threading.Lock()


_RETRY_ATTEMPTS = 3
_RETRY_WAIT = wait_exponential(multiplier=2, min=5, max=60)


def _retrying(errors: tuple, label: str) -> Retrying:
    """A tenacity Retrying for one phase of a generation (submit, wait or download)."""
    return Retrying(
        retry=retry_if_exception_type(errors),
        stop=stop_after_attempt(_RETRY_ATTEMPTS),
        wait=_RETRY_WAIT,
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            f"[video_client] {label} failed (attempt {rs.attempt_number}), retrying: {rs.outcome.exception()}"
        ),
    )


class UnifiedVideoClient:
    """
    Generates video clips through a single interface, routing to the correct
    provider (fal.ai or the Gemini API) based on the active model.

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
        # One dict per generation attempt: model_id, duration, include_audio, cost,
        # submitted (billed), ok, error. on_attempt(event, attempt) is notified.
        self.attempts: List[dict] = []
        self.on_attempt: Optional[Callable[[str, dict], None]] = None

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
        """Return cumulative estimated cost across all billed attempts (failed ones included)."""
        return round(self._total_cost, 4)

    def _notify(self, event: str, attempt: dict) -> None:
        if self.on_attempt:
            self.on_attempt(event, attempt)

    def _mark_submitted(self, attempt: dict, uncertain: bool = False) -> None:
        """The provider accepted the job (or may have): from here on it is billed."""
        attempt["submitted"] = True
        attempt["uncertain"] = uncertain
        self._total_cost += attempt["cost"]
        self._notify("submitted", attempt)

    def _submit_paid(self, label: str, fn: Callable, *args, on_submitted: Optional[Callable[..., None]] = None):
        """Start a paid job: retried only when it provably never started; counted when it may have."""
        try:
            result = _retrying(_SUBMIT_NOT_STARTED_ERRORS, label)(fn, *args)
        except Exception as exc:
            if on_submitted and _submit_may_have_reached_provider(exc):
                logger.error(f"[video_client] {label} may have reached the provider ({exc}); counted as billed, not retried")
                on_submitted(uncertain=True)
            raise
        if on_submitted:
            on_submitted()
        return result

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
            image_path: Local path to an input image (uploaded for fal.ai, sent inline to the Gemini API).
            reference_images: List of image URLs/paths for reference-to-video (Seedance 2.0).
            dialogue: Character dialogue (Veo lip-sync; added to fal.ai prompts when audio is on).
            voice_profile: Voice description (Veo).
            on_poll: Callback for polling progress updates.

        Returns:
            Path to the saved video file, or None on failure.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        self._last_error = None
        self._fallback_errors = []

        logger.info(
            f"[video_client] Generating video with {self._model.display_name} "
            f"({self._model.model_id}) — {duration}s @ {resolution}, audio={include_audio}"
        )

        include_audio = include_audio and self._model.has_audio
        attempt = {
            "model_id": self._model.model_id,
            "duration": duration,
            "include_audio": include_audio,
            "cost": estimate_cost(self._model.model_id, duration, include_audio),
            "submitted": False,
            "uncertain": False,
            "ok": False,
            "error": None,
        }
        self.attempts.append(attempt)

        try:
            if not self._model.available:
                raise VideoGenerationError(
                    f"{self._model.display_name}: endpoints and price not verified (registry.json); not called"
                )
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
                    on_submitted=lambda uncertain=False: self._mark_submitted(attempt, uncertain),
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
                    dialogue=dialogue or "",
                    on_submitted=lambda uncertain=False: self._mark_submitted(attempt, uncertain),
                )
        except Exception as e:
            self._last_error = str(e)
            attempt["error"] = str(e)
            billed = (" (counted as billed: the submit may have reached the provider)" if attempt["uncertain"]
                      else " (billed: the job was accepted)" if attempt["submitted"] else "")
            logger.error(f"[video_client] Generation failed ({self._model.model_id}){billed}: {e}")
            self._notify("failed", attempt)
            return None

        attempt["ok"] = True
        self._generation_count += 1
        logger.info(
            f"[video_client] Generation #{self._generation_count} complete — "
            f"estimated cost: ${attempt['cost']:.4f} (total: ${self._total_cost:.4f})"
        )
        self._notify("succeeded", attempt)

        return result_path

    # ── fal.ai provider ─────────────────────────────────────────────────────

    def _get_fal_client(self):
        """Lazy-import fal_client to avoid import errors when not installed."""
        if self._fal_client is None:
            import fal_client
            self._fal_client = fal_client
        return self._fal_client

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
        dialogue: str = "",
        on_submitted: Optional[Callable[..., None]] = None,
    ) -> str:
        """Generate video via fal.ai and download to output_path."""
        model = self._model
        endpoint, arguments, uploads = self._fal_request(
            prompt, duration, include_audio, image_url, image_path, reference_images, dialogue,
        )
        logger.info(f"[video_client] fal.ai call: {endpoint} — {sorted(arguments)}")

        # Submit (paid): retried only when the request provably never started
        request_id = self._submit_paid(
            "fal.ai submit", self._fal_submit, endpoint, arguments, on_submitted=on_submitted,
        )

        # Wait for the result of the already-submitted job (never re-submits)
        result = _retrying(_TRANSIENT_ERRORS, "fal.ai result")(self._fal_wait, endpoint, request_id)

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

        # Download to local path (retried on its own)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        _retrying(_TRANSIENT_ERRORS, "fal.ai download")(self._fal_download, video_url, output_path)
        size_kb = Path(output_path).stat().st_size // 1024
        logger.info(f"[video_client] Downloaded {model.display_name} video: {output_path} ({size_kb} KB)")

        return output_path

    def _fal_request(
        self,
        prompt: str,
        duration: int,
        include_audio: bool,
        image_url: Optional[str],
        image_path: Optional[str],
        reference_images: Optional[List[str]],
        dialogue: str,
    ) -> tuple:
        """(endpoint, arguments, uploads) shaped by the model's verified input schema (registry params)."""
        model = self._model
        params = model.params
        if params is None:
            raise VideoGenerationError(f"{model.model_id}: no fal.ai parameter map in registry.json")
        upload = _retrying(_TRANSIENT_ERRORS, "fal.ai upload")  # uploads are free and safe to retry
        uploads = 0

        if reference_images and model.endpoint_ref2v and params.references:
            mode, endpoint = "ref2v", model.endpoint_ref2v
        elif (image_url or image_path) and model.endpoint_i2v and params.image:
            mode, endpoint = "i2v", model.endpoint_i2v
        else:
            mode, endpoint = "t2v", model.endpoint_t2v

        full_prompt = prompt
        if include_audio and dialogue:
            full_prompt += f'\n\nThe character says: "{dialogue}"'
        arguments: dict = {"prompt": full_prompt}
        if params.durations:
            arguments["duration"] = str(clip_duration(model.model_id, duration))
        if params.resolution:
            arguments["resolution"] = model.max_resolution
        if mode in params.aspect_ratio:
            arguments["aspect_ratio"] = "9:16"
        if params.audio:
            arguments[params.audio] = bool(include_audio)
        if mode == "i2v":
            if image_path and not image_url:
                image_url = upload(self._fal_upload, image_path)
                uploads += 1
            arguments[params.image] = image_url
        elif mode == "ref2v":
            urls = []
            for ref in reference_images:
                if ref.startswith("http"):
                    urls.append(ref)
                else:
                    urls.append(upload(self._fal_upload, ref))
                    uploads += 1
            arguments[params.references] = urls
        return endpoint, arguments, uploads

    # fal.ai network primitives (one request each; the smoke test stubs these)

    def _fal_upload(self, path: str) -> str:
        return self._get_fal_client().upload_file(path)

    def _fal_submit(self, endpoint: str, arguments: dict) -> str:
        """
        Start a paid fal.ai job and return its request id: exactly one POST. fal_client retries
        its requests internally (timeouts, dropped connections, 408/409/429, up to MAX_ATTEMPTS),
        which could queue and bill the same job several times; the submit runs with that set to 1,
        and _submit_paid decides what a failure means.
        """
        fal = self._get_fal_client()
        sdk = getattr(fal, "client", None)
        if not isinstance(getattr(sdk, "MAX_ATTEMPTS", None), int):
            raise VideoGenerationError("fal_client changed: cannot switch off its submit retries; not submitting")
        with _FAL_SUBMIT_LOCK:
            saved, sdk.MAX_ATTEMPTS = sdk.MAX_ATTEMPTS, 1
            try:
                handle = fal.submit(endpoint, arguments=arguments)
            finally:
                sdk.MAX_ATTEMPTS = saved
        return handle.request_id

    def _fal_wait(self, endpoint: str, request_id: str):
        """Block until the submitted job finishes and return its result (no new job)."""
        return self._get_fal_client().result(endpoint, request_id)

    def _fal_download(self, url: str, output_path: str) -> None:
        urllib.request.urlretrieve(url, output_path)

    # ── Gemini API provider (direct google.genai SDK) ────────────────────────

    _gemini_client = None  # lazy init

    def _get_gemini_client(self):
        """Lazy-import and cache the Gemini API client."""
        if self._gemini_client is None:
            from google import genai
            self._gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
        return self._gemini_client

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
        on_submitted: Optional[Callable[..., None]] = None,
    ) -> str:
        """Generate video via the Gemini API (google.genai SDK)."""
        from google.genai import types

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

        # Submit (paid): retried only when the request provably never started
        operation = self._submit_paid("Gemini API submit", self._gemini_submit, kwargs, on_submitted=on_submitted)

        # Wait for the already-submitted operation (each poll retried on its own)
        operation = self._gemini_wait(operation, on_poll)

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

        out = Path(output_path)
        _retrying(_TRANSIENT_ERRORS, "Gemini API download")(self._gemini_download, video.video, out)
        logger.info(
            f"[video_client] Gemini API video saved: {out} ({out.stat().st_size // 1024} KB)"
        )
        return str(out)

    # Gemini API network primitives (the smoke test stubs these)

    def _gemini_submit(self, kwargs: dict):
        """Start a paid Veo generation and return the operation."""
        return self._get_gemini_client().models.generate_videos(**kwargs)

    def _gemini_wait(self, operation, on_poll: Optional[Callable[[int], None]] = None):
        """Poll an already-submitted operation until done (never re-submits)."""
        client = self._get_gemini_client()
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
            operation = _retrying(_TRANSIENT_ERRORS, "Gemini API poll")(client.operations.get, operation)
        return operation

    def _gemini_download(self, raw, out: Path) -> None:
        if raw.video_bytes:
            out.write_bytes(raw.video_bytes)
        elif raw.uri:
            # The API key goes in a header, never in the URL (review B10)
            request = urllib.request.Request(raw.uri, headers={"x-goog-api-key": Config.GEMINI_API_KEY})
            with urllib.request.urlopen(request) as response, open(out, "wb") as f:
                f.write(response.read())
        else:
            raise VideoGenerationError("Gemini API: no video_bytes or uri in response")

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
        budget_check: Optional[Callable[[str, float], bool]] = None,
    ) -> Optional[str]:
        """
        Try generating with the active model, then the tier's other available
        models from the cheapest up (registry fallbackOrder, review B8).

        budget_check(model_id, estimated_cost) is asked before every attempt
        (spend from earlier, billed attempts already counted by the caller);
        a model it refuses is skipped, never switched to.
        """
        self._fallback_errors = []
        tier = self._model.tier
        fallback_order = TIER_FALLBACK_ORDER.get(tier, [])

        # The current model first, then the others cheapest first
        current_id = self._model.model_id
        models_to_try = [current_id] + [m for m in fallback_order if m != current_id]

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

            if not model_cfg.available:
                errors.append(f"{model_cfg.display_name}: not verified, never called")
                continue

            # Skip models whose provider SDK isn't installed
            available, reason = self._is_provider_available(model_cfg.provider)
            if not available:
                msg = f"{model_cfg.display_name}: {reason}"
                errors.append(msg)
                logger.warning(f"[video_client] Skipping {model_id} — {reason}")
                continue

            # Snap duration and resolution to the fallback model's capabilities
            effective_duration = clip_duration(model_id, duration)
            effective_resolution = model_cfg.max_resolution
            # Only pass reference_images if this model supports them
            effective_refs = reference_images if model_cfg.has_reference_images else None

            # Re-check the budget before every attempt (review B6)
            estimated = estimate_cost(model_id, effective_duration, include_audio and model_cfg.has_audio)
            if budget_check is not None and not budget_check(model_id, estimated):
                msg = f"{model_cfg.display_name}: skipped, ${estimated:.2f} exceeds the remaining budget"
                errors.append(msg)
                logger.warning(f"[video_client] {msg}")
                continue

            if model_id != self._model.model_id:
                logger.warning(f"[video_client] Falling back to model: {model_id}")
                self.switch_model(model_id)

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
