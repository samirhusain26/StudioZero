"""
Step 7 (per episode): Editor — Assemble all scene clips into a final episode video.

Input:  episodes/episode_N/clips/scene_*.mp4 (from Scene Generator)
Output: episodes/episode_N/final.mp4 + output/final/{title}_ep{N}.mp4

Trims the first 0.2s from each clip (removes the reference-image flash that
Veo produces when image-to-video mode anchors on the input PNG), then
concatenates all clips with stream copy.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from src.renderer import assemble_veo_clips
from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.writer import load_story

logger = logging.getLogger(__name__)

# Seconds to trim from the start of every Veo clip to remove the reference-image flash
_TRIM_START = 0.2


def _trim_clip(src: Path, dst: Path) -> bool:
    """
    Trim the first _TRIM_START seconds from src and write to dst using stream copy.
    Returns True on success. On failure dst is left unwritten and False is returned.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(_TRIM_START),
        "-i", str(src),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[editor] Trim failed for {src.name}: {result.stderr[-200:]}")
        return False
    return True


def run(ctx: StepContext) -> StepResult:
    """Trim clip starts and assemble into a final episode video."""
    final_path = ctx.episode_dir / "final.mp4"

    if final_path.exists() and final_path.stat().st_size > 0:
        logger.info(
            f"[editor] Final video already exists for episode {ctx.episode_number} "
            f"({final_path.stat().st_size // 1024} KB) — skipping"
        )
        return StepResult(artifact_paths=[str(final_path)])

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

    with tempfile.TemporaryDirectory(dir=clips_dir) as tmp:
        trimmed: List[str] = []
        for clip in clip_paths:
            dst = Path(tmp) / clip.name
            if _trim_clip(clip, dst):
                logger.info(f"[editor] Trimmed {_TRIM_START}s from {clip.name}")
                trimmed.append(str(dst))
            else:
                trimmed.append(str(clip))  # fall back to original

        output_path = assemble_veo_clips(
            clip_paths=trimmed,
            output_filepath=str(final_path),
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

    return StepResult(
        artifact_paths=[str(final_path), str(final_output)],
        data={"final_video": str(final_output)},
    )
