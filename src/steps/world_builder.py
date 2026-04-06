"""
Step 1: World Builder — Generate the Series Bible.

Input: storyline, character descriptions, episode count
Output: SeriesBible JSON (setting, rules, tone, character roster, arc outline)
Persists: project_dir/series_bible.json
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.steps import StepContext, StepResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class CharacterProfile(BaseModel):
    """A single character in the series roster."""
    character_id: str = Field(..., description="Unique slug (e.g., 'bruised_apple')")
    display_name: str = Field(..., description="Display name (e.g., 'Sir Bruised Apple')")
    base_object: str = Field(..., description="Real-world object the character is (e.g., 'apple')")
    personality_traits: List[str] = Field(..., description="3-5 personality adjectives")
    visual_description: str = Field(
        ...,
        description="Detailed 3D Pixar-style appearance description, minimum 30 words"
    )
    voice_profile: str = Field(
        ...,
        description="Pitch, texture, accent, emotional quality for TTS/Veo"
    )
    role_in_story: str = Field(..., description="Protagonist, antagonist, comic relief, etc.")


class SeriesBible(BaseModel):
    """The foundational document for an animation series."""
    project_title: str = Field(..., description="Title of the animation series")
    setting: str = Field(..., description="Where the story takes place (e.g., 'A chaotic kitchen')")
    tone: str = Field(..., description="Overall tone (e.g., 'dark comedy with heart')")
    rules: List[str] = Field(
        ...,
        description="World rules (e.g., 'Objects can only move when humans aren't watching')"
    )
    character_roster: List[CharacterProfile] = Field(
        ..., min_length=2, description="All recurring characters"
    )
    series_arc_outline: str = Field(
        ...,
        description="2-3 sentence high-level arc spanning all episodes"
    )
    episode_count: int = Field(..., ge=1, le=10)
    episode_summaries: List[str] = Field(
        ...,
        description="One-line summary for each episode"
    )


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a senior showrunner creating a Series Bible for a viral animated short-form series.

## YOUR TASK:
Create a detailed Series Bible from the user's storyline and character descriptions.
All characters MUST be anthropomorphic household objects or food items.

## REQUIREMENTS:
1. **Setting**: Vivid, specific location with atmosphere.
2. **Tone**: Clear emotional register (dark comedy, wholesome, absurdist, etc.).
3. **Rules**: 3-5 world rules that create dramatic tension and comedy.
4. **Character Roster**: Full profiles for each character with:
   - Unique visual description (3D Pixar-style, minimum 30 words)
   - Specific voice profile (pitch, texture, accent, emotion)
   - Clear story role and personality traits
5. **Series Arc**: A satisfying arc that spans all episodes.
6. **Episode Summaries**: One-line hook per episode showing escalation.

Characters must be CONSISTENT — same IDs and traits will be used across all episodes.
Output ONLY valid JSON matching the SeriesBible schema."""


# ---------------------------------------------------------------------------
# Step Implementation
# ---------------------------------------------------------------------------

def run(ctx: StepContext) -> StepResult:
    """Generate the Series Bible for the animation project."""
    bible_path = ctx.project_dir / "series_bible.json"

    # Resume: if bible already exists, load and return
    if bible_path.exists():
        logger.info("Series bible already exists, loading from disk")
        return StepResult(artifact_paths=[str(bible_path)])

    schema = SeriesBible.model_json_schema()

    user_prompt = (
        f"Create a Series Bible for a {ctx.num_episodes}-episode animated series.\n\n"
        f"Storyline: {ctx.storyline}\n\n"
        f"Characters: {ctx.character_descriptions}\n\n"
        f"Generate {ctx.num_episodes} episode summaries.\n\n"
        f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    )

    combined_prompt = f"{_SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"

    logger.info("Generating series bible...")
    response = ctx.gemini_client.models.generate_content(
        model=Config.GEMINI_MODEL_NAME,
        contents=combined_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    raw = json.loads(response.text)
    bible = SeriesBible.model_validate(raw)

    # Persist
    bible_path.write_text(bible.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Series bible saved: '{bible.project_title}' — {len(bible.character_roster)} characters")

    return StepResult(artifact_paths=[str(bible_path)])


def load_bible(project_dir: Path) -> SeriesBible:
    """Load a previously saved SeriesBible from disk."""
    path = project_dir / "series_bible.json"
    return SeriesBible.model_validate_json(path.read_text(encoding="utf-8"))
