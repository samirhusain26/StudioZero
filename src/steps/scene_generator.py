"""
Step 6 (per episode): Scene Generator — Render each director shot as a Veo video clip.

Input:  director_shots.json + characters/{character_id}_reference.png
Output: episodes/episode_N/clips/scene_N.mp4
Persists: project_dir/episodes/episode_N/clips/

Scenes are generated strictly sequentially to respect Veo's 2 RPM rate limit.
A 35-second wait is enforced between requests.

On failure, a SceneGenerationError is raised with the scene_id and the prompt
that was sent, allowing the pipeline orchestrator to offer the user a retry or
prompt-edit flow without losing completed clips.

Retry / override mechanism:
  - Before sending, the generator checks for clips/scene_X_override.txt.
    If present, its contents replace the default veo_prompt.
  - A skip marker at clips/scene_X.skip causes the scene to be skipped entirely.
    The orchestrator creates these files when the user chooses to skip a scene.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

from src.veo_client import generate_veo_scene
from src.steps import StepContext, StepResult
from src.steps.director import load_director_shots

logger = logging.getLogger(__name__)

# Seconds to wait between Veo requests (2 RPM limit = 30s minimum; use 35s for safety)
_VEO_RATE_LIMIT_WAIT = 35


class SceneGenerationError(Exception):
    """Raised when a Veo scene fails, carrying enough context for a retry/edit flow."""
    def __init__(self, scene_id: int, veo_prompt: str, original_error: str):
        self.scene_id = scene_id
        self.veo_prompt = veo_prompt
        self.original_error = original_error
        super().__init__(
            f"Scene {scene_id} failed: {original_error}"
        )


def run(ctx: StepContext) -> StepResult:
    """Render each director shot as a Veo video clip, sequentially."""
    shots = load_director_shots(ctx.episode_dir)
    clips_dir = ctx.episode_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths: List[str] = []
    last_veo_call_at: Optional[float] = None  # timestamp of last Veo request (success or attempt)

    logger.info(
        f"[scene_generator] Episode {ctx.episode_number}: "
        f"rendering {len(shots.shots)} shot(s) via Veo 3.1"
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

        # ── Resolve Veo prompt (check for user override) ────────────────────
        if override_file.exists():
            veo_prompt = override_file.read_text(encoding="utf-8").strip()
            logger.info(
                f"[scene_generator] Scene {shot.scene_id}: using user-edited prompt override "
                f"({len(veo_prompt.split())} words)"
            )
        else:
            veo_prompt = shot.veo_prompt

        # ── Locate character reference image ────────────────────────────────
        ref_image = ctx.characters_dir / f"{shot.primary_character_id}_reference.png"
        if not ref_image.exists():
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=(
                    f"Reference image missing for character '{shot.primary_character_id}'. "
                    f"Expected: {ref_image}. Re-run the Casting step or skip this scene."
                ),
            )

        # ── Timestamp-based rate-limit enforcement ──────────────────────────
        # Track wall-clock time since the last Veo request (regardless of success/failure)
        # so retries after a tenacity retry loop don't fire two requests back-to-back.
        if last_veo_call_at is not None:
            elapsed = time.monotonic() - last_veo_call_at
            wait_needed = _VEO_RATE_LIMIT_WAIT - elapsed
            if wait_needed > 0:
                logger.info(
                    f"[scene_generator] Rate-limit wait: {wait_needed:.1f}s remaining "
                    f"(enforcing {_VEO_RATE_LIMIT_WAIT}s minimum between Veo requests)..."
                )
                time.sleep(wait_needed)

        logger.info(
            f"[scene_generator] Sending scene {shot.scene_id} to Veo 3.1 "
            f"— character: '{shot.primary_character_id}', location: '{shot.location_id}', "
            f"shot: {shot.shot_type} {shot.camera_angle}"
        )
        logger.debug(f"[scene_generator] Veo prompt preview: {veo_prompt[:150]}...")

        def _on_poll(elapsed: int) -> None:
            if ctx.progress_callback:
                ctx.progress_callback({
                    "type": "veo_polling",
                    "scene_id": shot.scene_id,
                    "elapsed": elapsed,
                })

        try:
            last_veo_call_at = time.monotonic()  # record before the call (covers retries too)
            generate_veo_scene(
                image_path=str(ref_image),
                visual_description=veo_prompt,
                dialogue=shot.dialogue,
                voice_profile=shot.voice_profile,
                output_path=str(clip_path),
                on_poll=_on_poll,
            )

            size_kb = clip_path.stat().st_size // 1024
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

    logger.info(
        f"[scene_generator] Episode {ctx.episode_number} complete — "
        f"{len(artifact_paths)} clip(s) rendered"
    )
    return StepResult(artifact_paths=artifact_paths)
