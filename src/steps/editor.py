"""
Step 8: Editor — Assemble final video from clips, audio, and music.

Input: Video clips + background music
Output: Final assembled MP4
Persists: project_dir/episodes/episode_N/final.mp4
"""

import logging
from pathlib import Path

from src.renderer import assemble_veo_clips
from src.steps import StepContext, StepResult

logger = logging.getLogger(__name__)


def run(ctx: StepContext) -> StepResult:
    """Assemble all scene clips into a final episode video."""
    final_path = ctx.episode_dir / "final.mp4"

    if final_path.exists() and final_path.stat().st_size > 0:
        logger.info(f"Final video exists for episode {ctx.episode_number}, skipping")
        return StepResult(artifact_paths=[str(final_path)])

    clips_dir = ctx.episode_dir / "clips"
    clip_paths = sorted(clips_dir.glob("scene_*.mp4"), key=lambda p: p.name)

    if not clip_paths:
        raise RuntimeError(f"No clips found in {clips_dir}")

    clip_strs = [str(p) for p in clip_paths]

    logger.info(f"Assembling {len(clip_strs)} clips into final video...")

    output_path = assemble_veo_clips(
        clip_paths=clip_strs,
        output_path=str(final_path),
    )

    if not output_path or not Path(output_path).exists():
        raise RuntimeError("Video assembly failed")

    # Copy to final output directory
    from src.config import Config
    Config.ensure_directories()
    from src.steps.world_builder import load_bible
    bible = load_bible(ctx.project_dir)
    safe_title = Config.safe_title(bible.project_title)
    final_output = Config.FINAL_DIR / f"{safe_title}_ep{ctx.episode_number}.mp4"

    import shutil
    shutil.copy2(final_path, final_output)
    logger.info(f"Final video: {final_output}")

    return StepResult(artifact_paths=[str(final_path), str(final_output)])
