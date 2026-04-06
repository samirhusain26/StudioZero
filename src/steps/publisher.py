"""
Step 9: Publisher — Generate marketing materials and optionally upload.

Input: Final video + SeriesBible
Output: Social caption, marketing metadata
Persists: project_dir/episodes/episode_N/marketing.json
"""

import json
import logging
from pathlib import Path

from src.steps import StepContext, StepResult
from src.steps.world_builder import load_bible
from src.steps.episode_writer import load_script

logger = logging.getLogger(__name__)


def run(ctx: StepContext) -> StepResult:
    """Generate social media captions and marketing metadata."""
    marketing_path = ctx.episode_dir / "marketing.json"

    if marketing_path.exists():
        logger.info(f"Marketing data exists for episode {ctx.episode_number}, skipping")
        return StepResult(artifact_paths=[str(marketing_path)])

    bible = load_bible(ctx.project_dir)
    script = load_script(ctx.episode_dir)

    # Generate social caption — the marketing module expects a VideoScript,
    # so we build a simple caption directly for animation episodes.
    caption = (
        f"{script.cold_open_hook}\n\n"
        f"{bible.project_title} | Episode {ctx.episode_number}: {script.episode_title}\n\n"
        f"Follow for more episodes!"
    )

    marketing_data = {
        "episode_number": ctx.episode_number,
        "episode_title": script.episode_title,
        "series_title": bible.project_title,
        "caption": caption,
        "hashtags": [
            "#animation", "#animated", "#aislop", "#viral",
            f"#{bible.project_title.replace(' ', '').lower()}",
        ],
        "hook": script.cold_open_hook,
    }

    marketing_path.write_text(json.dumps(marketing_data, indent=2), encoding="utf-8")
    logger.info(f"Marketing data saved for episode {ctx.episode_number}")

    return StepResult(artifact_paths=[str(marketing_path)], data=marketing_data)
