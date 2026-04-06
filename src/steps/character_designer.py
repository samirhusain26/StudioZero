"""
Step 2: Character Designer — Generate reference images for all characters.

Input: SeriesBible character roster
Output: PNG reference images per character
Persists: project_dir/characters/{character_id}_reference.png
"""

import logging
from pathlib import Path

from src.config import Config
from src.narrative import generate_character_blueprint
from src.steps import StepContext, StepResult
from src.steps.world_builder import load_bible

logger = logging.getLogger(__name__)


def run(ctx: StepContext) -> StepResult:
    """Generate character reference images for all characters in the roster."""
    bible = load_bible(ctx.project_dir)
    characters_dir = ctx.characters_dir
    artifact_paths = []

    for character in bible.character_roster:
        img_path = characters_dir / f"{character.character_id}_reference.png"

        # Resume: skip if already generated
        if img_path.exists():
            logger.info(f"Character reference exists for '{character.display_name}', skipping")
            artifact_paths.append(str(img_path))
            continue

        logger.info(f"Generating reference image for '{character.display_name}'...")

        image_data = generate_character_blueprint(
            visual_description=character.visual_description,
            gemini_client=ctx.gemini_client,
        )

        if image_data:
            img_path.write_bytes(image_data)
            artifact_paths.append(str(img_path))
            logger.info(f"Saved reference: {img_path.name}")
        else:
            logger.warning(f"No image returned for '{character.display_name}'")

    if not artifact_paths:
        raise RuntimeError("No character reference images were generated")

    return StepResult(artifact_paths=artifact_paths)
