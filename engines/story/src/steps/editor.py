"""
Step 7 (per episode): Editor — Assemble all scene clips into a final episode video.

Input:  episodes/episode_N/clips/scene_*.mp4 (from Scene Generator)
Output: episodes/episode_N/final.mp4 + cover.jpg + render.json, and a copy at
        output/final/{title}_ep{N}.mp4

Trims the first 0.2s from each clip (removes the reference-image flash that
Veo produces when image-to-video mode anchors on the input PNG), normalises every
clip to 1080x1920 / 30 fps / AAC 48 kHz stereo (silence where a clip has no audio:
the series audio policy, Config.SERIES_NATIVE_AUDIO) and joins them (review B3).
"""

import logging
import shutil
from pathlib import Path

from src.renderer import assemble_veo_clips
from src.render_json import RENDER_JSON, write_series_render_json
from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.writer import load_story

logger = logging.getLogger(__name__)

# Seconds to trim from the start of every Veo clip to remove the reference-image flash
_TRIM_START = 0.2


def run(ctx: StepContext) -> StepResult:
    """Trim clip starts and assemble into a final episode video."""
    final_path = ctx.episode_dir / "final.mp4"

    if final_path.exists() and final_path.stat().st_size > 0:
        logger.info(
            f"[editor] Final video already exists for episode {ctx.episode_number} "
            f"({final_path.stat().st_size // 1024} KB) — skipping"
        )
        render_json = ctx.episode_dir / RENDER_JSON
        if not render_json.exists():
            write_series_render_json(ctx.project_dir, ctx.episode_number, final_path)
        return StepResult(artifact_paths=[str(final_path), str(render_json)])

    clips_dir = ctx.episode_dir / "clips"
    clip_paths = sorted(
        [p for p in clips_dir.glob("scene_*.mp4") if p.stat().st_size > 0],
        key=lambda p: int(p.stem.split("_")[1]),
    )

    if not clip_paths:
        raise RuntimeError(
            f"[editor] No rendered clips found in {clips_dir} for episode {ctx.episode_number}"
        )

    logger.info(
        f"[editor] Assembling episode {ctx.episode_number}: "
        f"{len(clip_paths)} clip(s) — {[p.name for p in clip_paths]}"
    )

    output_path = assemble_veo_clips(
        clip_paths=[str(p) for p in clip_paths],
        output_filepath=str(final_path),
        trim_start=_TRIM_START,
    )

    if not output_path or not Path(output_path).exists():
        raise RuntimeError(
            f"[editor] FFmpeg assembly failed for episode {ctx.episode_number}"
        )

    size_mb = final_path.stat().st_size / (1024 * 1024)
    logger.info(f"[editor] Assembly complete — {final_path.name} ({size_mb:.1f} MB)")

    story = load_story(ctx.project_dir)
    safe_title = Config.safe_title(story.project_title)
    Config.ensure_directories()
    final_output = Config.FINAL_DIR / f"{safe_title}_ep{ctx.episode_number}.mp4"

    shutil.copy2(final_path, final_output)
    logger.info(f"[editor] Copied to output: {final_output}")

    # render.json + cover.jpg next to final.mp4 (engine → packager hand-off)
    render_json = write_series_render_json(ctx.project_dir, ctx.episode_number, final_path)

    return StepResult(
        artifact_paths=[str(final_path), str(final_output), str(render_json)],
        data={"final_video": str(final_output), "render_json": str(render_json)},
    )
