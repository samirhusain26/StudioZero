"""
Step 7 (per episode): Scene Generator — Render each director shot as a video clip.

Input:  director_shots.json + scene_starts/{char}_{loc}.png (from set_designer)
        Falls back to characters/{character_id}_reference.png if no scene start exists.
Output: episodes/episode_N/clips/scene_N.mp4
Persists: project_dir/episodes/episode_N/clips/

Supports multiple video generation providers via UnifiedVideoClient:
  - fal.ai models (Kling, Seedance, Wan, Sora, Veo via fal)
  - Vertex AI Veo (legacy, direct Google API)

The active model is read from config (ACTIVE_VIDEO_MODEL from settings.json).
When the active model is a Gemini API Veo model (e.g. "veo-3.1-fast"),
generation uses the google.genai SDK directly.

Rate limits are enforced between requests (35s for Vertex AI, lower for fal.ai).

Retry / override mechanism:
  - Before sending, the generator checks for clips/scene_X_override.txt.
    If present, its contents replace the default veo_prompt.
  - A skip marker at clips/scene_X.skip causes the scene to be skipped entirely.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

from src.config import Config
from src.video_models import get_model
from src.video_client import UnifiedVideoClient
from src.budget_guard import BudgetGuard, BudgetExceeded
from src.steps import StepContext, StepResult
from src.steps.director import load_director_shots

logger = logging.getLogger(__name__)

# Seconds between requests — Vertex AI has strict 2 RPM; fal.ai is more lenient
_RATE_LIMIT_VERTEX = 35
_RATE_LIMIT_FAL = 5


class SceneGenerationError(Exception):
    """Raised when a scene fails, carrying enough context for a retry/edit flow."""
    def __init__(self, scene_id: int, veo_prompt: str, original_error: str):
        self.scene_id = scene_id
        self.veo_prompt = veo_prompt
        self.original_error = original_error
        super().__init__(
            f"Scene {scene_id} failed: {original_error}"
        )


def _get_scene_start_image(ctx: StepContext, character_id: str, location_id: str) -> Optional[Path]:
    """Look up the cached scene starting image for a character+location combo."""
    scene_starts_dir = ctx.project_dir / "scene_starts"
    cache_path = scene_starts_dir / f"{character_id}_{location_id}.png"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path
    return None


def run(ctx: StepContext) -> StepResult:
    """Render each director shot as a video clip, sequentially."""
    shots = load_director_shots(ctx.episode_dir)
    clips_dir = ctx.episode_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Initialize video client and budget guard with the configured model
    model_id = Config.ACTIVE_VIDEO_MODEL
    model_config = get_model(model_id)
    client = UnifiedVideoClient(model_id)
    guard = BudgetGuard(
        max_budget=Config.VIDEO_MAX_BUDGET,
        auto_downgrade=Config.VIDEO_AUTO_DOWNGRADE,
    )

    rate_limit_wait = _RATE_LIMIT_VERTEX if model_config.provider == "vertex_ai" else _RATE_LIMIT_FAL

    artifact_paths: List[str] = []
    last_call_at: Optional[float] = None

    logger.info(
        f"[scene_generator] Episode {ctx.episode_number}: "
        f"rendering {len(shots.shots)} shot(s) via {model_config.display_name} ({model_id}), "
        f"budget: ${Config.VIDEO_MAX_BUDGET:.2f}"
    )

    for shot in shots.shots:
        clip_path = clips_dir / f"scene_{shot.scene_id}.mp4"
        skip_marker = clips_dir / f"scene_{shot.scene_id}.skip"
        override_file = clips_dir / f"scene_{shot.scene_id}_override.txt"

        # ── Skip marker ─────────────────────────────────────────────────────
        if skip_marker.exists():
            logger.info(f"[scene_generator] Scene {shot.scene_id} marked as skipped — omitting")
            continue

        # ── Already rendered ─────────────────────────────────────────────────
        if clip_path.exists() and clip_path.stat().st_size > 0:
            logger.info(
                f"[scene_generator] Scene {shot.scene_id} clip already exists "
                f"({clip_path.stat().st_size // 1024} KB) — skipping"
            )
            artifact_paths.append(str(clip_path))
            continue

        # ── Resolve prompt (check for user override) ────────────────────────
        if override_file.exists():
            veo_prompt = override_file.read_text(encoding="utf-8").strip()
            logger.info(
                f"[scene_generator] Scene {shot.scene_id}: using user-edited prompt override "
                f"({len(veo_prompt.split())} words)"
            )
        else:
            veo_prompt = shot.veo_prompt

        # ── Locate scene starting image (prefer set_designer output) ───────
        scene_start = _get_scene_start_image(ctx, shot.primary_character_id, shot.location_id)
        if scene_start:
            ref_image = scene_start
            logger.info(
                f"[scene_generator] Using scene start image for "
                f"'{shot.primary_character_id}' @ '{shot.location_id}'"
            )
        else:
            # Fall back to character reference if no scene start was generated
            ref_image = ctx.characters_dir / f"{shot.primary_character_id}_reference.png"
            logger.warning(
                f"[scene_generator] No scene start image for "
                f"'{shot.primary_character_id}' @ '{shot.location_id}' "
                f"— falling back to character reference"
            )

        if not ref_image.exists():
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=(
                    f"No starting image found for character '{shot.primary_character_id}' "
                    f"at location '{shot.location_id}'. "
                    f"Re-run the Set Designer or Casting step, or skip this scene."
                ),
            )

        # ── Collect reference images for models that support them ───────────
        # Pass scene start images as references to avoid white character sheets
        # bleeding into the video output
        reference_images = None
        if model_config.has_reference_images and scene_start:
            reference_images = [str(scene_start)]
            logger.info(
                f"[scene_generator] Passing scene start as reference image "
                f"for '{shot.primary_character_id}' @ '{shot.location_id}'"
            )

        # ── Rate-limit enforcement ──────────────────────────────────────────
        if last_call_at is not None:
            elapsed = time.monotonic() - last_call_at
            wait_needed = rate_limit_wait - elapsed
            if wait_needed > 0:
                logger.info(
                    f"[scene_generator] Rate-limit wait: {wait_needed:.1f}s remaining "
                    f"(enforcing {rate_limit_wait}s minimum between requests)..."
                )
                time.sleep(wait_needed)

        # ── Budget check ────────────────────────────────────────────────────
        try:
            approved_model = guard.check_budget(
                client.model_id,
                duration=model_config.max_duration_sec,
                include_audio=False,
            )
            if approved_model != client.model_id:
                logger.info(
                    f"[scene_generator] Budget guard downgraded model: "
                    f"{client.model_id} -> {approved_model}"
                )
                client.switch_model(approved_model)
                model_config = get_model(approved_model)
                rate_limit_wait = _RATE_LIMIT_VERTEX if model_config.provider == "vertex_ai" else _RATE_LIMIT_FAL
        except BudgetExceeded as e:
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=(
                    f"Budget exceeded: ${e.remaining:.2f} remaining, "
                    f"${e.estimated:.2f} needed. Increase budget or switch to a cheaper model."
                ),
            )

        logger.info(
            f"[scene_generator] Sending scene {shot.scene_id} to {model_config.display_name} "
            f"— character: '{shot.primary_character_id}', location: '{shot.location_id}', "
            f"shot: {shot.shot_type} {shot.camera_angle}"
        )
        logger.debug(f"[scene_generator] Prompt preview: {veo_prompt[:150]}...")

        def _on_poll(elapsed: int) -> None:
            if ctx.progress_callback:
                ctx.progress_callback({
                    "type": "veo_polling",
                    "scene_id": shot.scene_id,
                    "elapsed": elapsed,
                    "model": model_id,
                })

        try:
            last_call_at = time.monotonic()

            # Use fallback for fal.ai models, direct for Vertex
            if model_config.provider == "fal.ai":
                result_path = client.generate_with_fallback(
                    prompt=veo_prompt,
                    output_dir=clips_dir,
                    filename=f"scene_{shot.scene_id}.mp4",
                    duration=model_config.max_duration_sec,
                    resolution=model_config.max_resolution,
                    include_audio=False,  # Use our own TTS pipeline
                    image_path=str(ref_image),
                    reference_images=reference_images,
                    dialogue=shot.dialogue,
                    voice_profile=shot.voice_profile,
                    on_poll=_on_poll,
                )
            else:
                result_path = client.generate_video(
                    prompt=veo_prompt,
                    output_dir=clips_dir,
                    filename=f"scene_{shot.scene_id}.mp4",
                    image_path=str(ref_image),
                    dialogue=shot.dialogue,
                    voice_profile=shot.voice_profile,
                    on_poll=_on_poll,
                )

            if not result_path:
                # Build detailed error from fallback chain or single model failure
                fallback_errs = client.get_fallback_errors()
                if fallback_errs:
                    detail = "All models failed:\n" + "\n".join(f"  - {e}" for e in fallback_errs)
                elif client._last_error:
                    detail = f"Generation failed ({client.model_id}): {client._last_error}"
                else:
                    detail = "Video generation returned no output"
                raise RuntimeError(detail)

            size_kb = clip_path.stat().st_size // 1024
            # Record cost with budget guard
            from src.video_models import estimate_cost as _est_cost
            scene_cost = _est_cost(client.model_id, model_config.max_duration_sec, False)
            guard.record_spend(scene_cost)

            # Emit live cost update to UI
            if ctx.progress_callback:
                ctx.progress_callback({
                    "type": "cost_update",
                    "scene_id": shot.scene_id,
                    "scene_cost": round(scene_cost, 4),
                    "budget": guard.summary(),
                    "model_name": model_config.display_name,
                })

            logger.info(
                f"[scene_generator] Scene {shot.scene_id} rendered successfully "
                f"— {size_kb} KB saved to {clip_path.name}"
            )
            artifact_paths.append(str(clip_path))

            # Clean up override file after successful render
            if override_file.exists():
                override_file.unlink()
                logger.info(f"[scene_generator] Override file removed after successful render")

        except Exception as e:
            # Unwrap tenacity RetryError to expose the actual underlying exception
            cause = getattr(e, 'last_attempt', None)
            if cause is not None:
                try:
                    underlying = cause.exception()
                except Exception:
                    underlying = None
                if underlying is not None:
                    e = underlying
            logger.error(
                f"[scene_generator] Scene {shot.scene_id} FAILED: {e}\n"
                f"  Prompt sent ({len(veo_prompt.split())} words): {veo_prompt[:200]}..."
            )
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=str(e),
            )

    if not artifact_paths:
        raise RuntimeError(
            f"[scene_generator] No clips were rendered for episode {ctx.episode_number}"
        )

    total_cost = client.get_total_cost()
    budget = guard.summary()
    logger.info(
        f"[scene_generator] Episode {ctx.episode_number} complete — "
        f"{len(artifact_paths)} clip(s) rendered, estimated cost: ${total_cost:.2f} "
        f"(budget: ${budget['remaining']:.2f} remaining)"
    )
    return StepResult(
        artifact_paths=artifact_paths,
        data={
            "model_id": client.model_id,
            "model_name": client.model.display_name,
            "generation_count": client.get_generation_count(),
            "estimated_cost": total_cost,
            "budget": budget,
        },
    )
