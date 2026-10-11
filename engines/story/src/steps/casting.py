"""
Step 3: Casting — Flesh out character sheets and generate reference images.

Input:  story.json (character seeds) + all_episodes.json (which characters actually appear)
Output: characters/{character_id}_sheet.json + characters/{character_id}_reference.png
Persists: project_dir/characters/

Only generates assets for characters who appear in at least one scene across all episodes,
avoiding wasted Imagen API calls for unused characters.
"""

import json
import logging
from pathlib import Path
from typing import List

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.narrative import generate_character_blueprint
from src.steps import StepContext, StepResult
from src.steps.writer import load_story, CharacterSeed
from src.steps.screenwriter import load_all_episodes

logger = logging.getLogger(__name__)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class CharacterSheet(BaseModel):
    """Fully fleshed-out character profile used by the Director and Veo."""
    character_id: str
    display_name: str
    base_object: str
    role_in_story: str
    personality_traits: List[str]
    visual_description: str = Field(
        ...,
        description="Final visual description used verbatim in Veo prompts. Min 50 words. "
                    "3D Pixar-style, include colour, texture, size, distinguishing features."
    )
    voice_profile: str = Field(
        ...,
        description="Final voice profile used verbatim in Veo audio generation"
    )
    emotional_range: str = Field(
        ...,
        description="How this character physically expresses emotions — for Veo direction"
    )
    signature_gesture: str = Field(
        ...,
        description="One recurring physical mannerism that makes this character recognisable"
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _flesh_out_character(
    seed: CharacterSeed,
    gemini_client,
    story_tone: str,
    story_setting: str,
) -> CharacterSheet:
    """Ask Gemini to expand a character seed into a full character sheet."""
    schema = CharacterSheet.model_json_schema()

    prompt = (
        f"You are a character designer for a 3D animated series. "
        f"Expand this character seed into a full character sheet.\n\n"
        f"Series tone: {story_tone}\n"
        f"Series setting: {story_setting}\n\n"
        f"Character seed:\n"
        f"  ID: {seed.character_id}\n"
        f"  Name: {seed.display_name}\n"
        f"  Object: {seed.base_object}\n"
        f"  Role: {seed.role_in_story}\n"
        f"  Traits: {', '.join(seed.personality_traits)}\n"
        f"  Visual: {seed.visual_description}\n"
        f"  Voice: {seed.voice_profile}\n\n"
        f"Produce a richer visual_description (50+ words, 3D Pixar-style, specific colours, "
        f"textures, facial features, size relative to other objects). "
        f"Keep character_id, display_name, base_object, role_in_story, personality_traits "
        f"and voice_profile consistent with the seed.\n\n"
        f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    )

    response = gemini_client.models.generate_content(
        model=Config.GEMINI_MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    raw = json.loads(response.text)
    return CharacterSheet.model_validate(raw)


# ── Step Implementation ──────────────────────────────────────────────────────

def run(ctx: StepContext) -> StepResult:
    """Generate character sheets and reference images for all active characters."""
    story = load_story(ctx.project_dir)
    all_eps = load_all_episodes(ctx.project_dir)

    # Collect only character_ids that actually appear in scenes
    active_ids = {
        cid
        for ep in all_eps.episodes
        for scene in ep.scenes
        for cid in scene.characters_present
    }
    logger.info(f"[casting] Active characters across all episodes: {sorted(active_ids)}")

    # Filter character seeds to active characters
    active_seeds = [c for c in story.character_seeds if c.character_id in active_ids]
    unused = [c.character_id for c in story.character_seeds if c.character_id not in active_ids]
    if unused:
        logger.info(f"[casting] Skipping unused characters: {unused}")

    artifact_paths: List[str] = []

    for seed in active_seeds:
        sheet_path = ctx.characters_dir / f"{seed.character_id}_sheet.json"
        img_path = ctx.characters_dir / f"{seed.character_id}_reference.png"

        # ── Character sheet ─────────────────────────────────────────────────
        if sheet_path.exists():
            logger.info(f"[casting] Sheet exists for '{seed.display_name}' — skipping LLM call")
            sheet = CharacterSheet.model_validate_json(sheet_path.read_text(encoding="utf-8"))
        else:
            logger.info(f"[casting] Fleshing out character sheet for '{seed.display_name}'...")
            sheet = _flesh_out_character(
                seed=seed,
                gemini_client=ctx.gemini_client,
                story_tone=story.tone,
                story_setting=story.setting,
            )
            sheet_path.write_text(sheet.model_dump_json(indent=2), encoding="utf-8")
            logger.info(
                f"[casting] Sheet saved for '{sheet.display_name}' "
                f"— signature gesture: {sheet.signature_gesture}"
            )

        artifact_paths.append(str(sheet_path))

        # ── Reference image ─────────────────────────────────────────────────
        if img_path.exists():
            logger.info(f"[casting] Reference image exists for '{seed.display_name}' — skipping")
            artifact_paths.append(str(img_path))
            continue

        logger.info(f"[casting] Generating reference image for '{sheet.display_name}'...")
        image_data = generate_character_blueprint(
            visual_description=sheet.visual_description,
            gemini_client=ctx.gemini_client,
        )

        if image_data:
            img_path.write_bytes(image_data)
            artifact_paths.append(str(img_path))
            logger.info(f"[casting] Reference image saved: {img_path.name}")
        else:
            logger.warning(f"[casting] No image returned for '{sheet.display_name}' — continuing")

    if not artifact_paths:
        raise RuntimeError("[casting] No character assets were generated")

    logger.info(f"[casting] Casting complete — {len(active_seeds)} character(s) ready")
    return StepResult(artifact_paths=artifact_paths)


def load_character_sheet(characters_dir: Path, character_id: str) -> CharacterSheet:
    """Load a persisted character sheet from disk."""
    path = characters_dir / f"{character_id}_sheet.json"
    return CharacterSheet.model_validate_json(path.read_text(encoding="utf-8"))


def load_all_character_sheets(characters_dir: Path) -> List[CharacterSheet]:
    """Load all character sheets from the characters directory."""
    sheets = []
    for sheet_path in sorted(characters_dir.glob("*_sheet.json")):
        sheets.append(CharacterSheet.model_validate_json(sheet_path.read_text(encoding="utf-8")))
    return sheets
