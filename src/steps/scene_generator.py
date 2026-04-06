"""
Step 6: Scene Generator — Render video clips with Veo 3.1.

Input: Storyboard shots + character reference images
Output: Per-scene MP4 clips
Persists: project_dir/episodes/episode_N/clips/scene_N.mp4
"""

import logging
import time
from pathlib import Path

from src.veo_client import generate_veo_scene
from src.steps import StepContext, StepResult
from src.steps.storyboard import load_storyboard

logger = logging.getLogger(__name__)


def run(ctx: StepContext) -> StepResult:
    """Render each storyboard shot as a video clip using Veo 3.1."""
    storyboard = load_storyboard(ctx.episode_dir)
    clips_dir = ctx.episode_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = []

    for shot in storyboard.shots:
        clip_path = clips_dir / f"scene_{shot.scene_id}.mp4"

        # Resume: skip if already rendered
        if clip_path.exists() and clip_path.stat().st_size > 0:
            logger.info(f"Clip exists for scene {shot.scene_id}, skipping")
            artifact_paths.append(str(clip_path))
            continue

        # Find character reference image
        ref_image = ctx.characters_dir / f"{shot.character_id}_reference.png"
        if not ref_image.exists():
            logger.warning(f"No reference image for '{shot.character_id}', skipping scene {shot.scene_id}")
            continue

        # Rate-limit: wait between Veo requests to avoid 429s
        if artifact_paths:
            logger.info("Waiting 35s between Veo requests to avoid rate limits (2 RPM)...")
            time.sleep(35)

        logger.info(f"Rendering scene {shot.scene_id} via Veo 3.1...")

        try:
            generate_veo_scene(
                image_path=str(ref_image),
                visual_description=shot.veo_prompt,
                dialogue=shot.dialogue,
                voice_profile=shot.voice_profile,
                output_path=str(clip_path),
            )
            artifact_paths.append(str(clip_path))
            logger.info(f"Scene {shot.scene_id} rendered: {clip_path.name}")
        except Exception as e:
            logger.error(f"Veo rendering failed for scene {shot.scene_id}: {e}")

    if not artifact_paths:
        raise RuntimeError("No video clips were rendered")

    return StepResult(artifact_paths=artifact_paths)
