"""
Step 3: Episode Writer — Generate a detailed script for a single episode.

Input: SeriesBible + episode number
Output: EpisodeScript JSON
Persists: project_dir/episodes/episode_N/script.json
"""

import json
import logging
from pathlib import Path
from typing import List

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.world_builder import load_bible

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class SceneBeat(BaseModel):
    """A single scene in an episode script."""
    scene_id: int = Field(..., ge=1, le=10)
    character_id: str = Field(..., description="Character performing in this scene (must match roster)")
    dialogue: str = Field(..., description="First-person spoken dialogue, max 15-20 words")
    voice_profile: str = Field(..., description="Voice style for this scene's TTS/Veo generation")
    visual_context: str = Field(
        ...,
        description="Detailed 9:16 scene description: character appearance, environment, lighting, camera, action. Min 40 words."
    )
    mood: str = Field(..., description="Emotional tone (e.g., 'tense', 'comedic', 'dramatic')")
    beat_note: str = Field(..., description="Story purpose of this scene (e.g., 'inciting incident', 'climax')")


class EpisodeScript(BaseModel):
    """Complete script for a single episode."""
    episode_number: int = Field(..., ge=1)
    episode_title: str
    cold_open_hook: str = Field(..., description="1-sentence scroll-stopping hook for scene 1")
    scenes: List[SceneBeat] = Field(..., min_length=6, max_length=10)
    cliffhanger: str = Field(..., description="How this episode ends to drive viewers to the next one")


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a senior episode writer for a viral animated short-form series.

## YOUR TASK:
Write a single episode script based on the Series Bible provided.

## RULES:
- Every character ID must match the Series Bible roster exactly.
- Scene 1 MUST be a scroll-stopping hook (cognitive dissonance + high stakes).
- Dialogue: Max 15-20 words per scene, first-person.
- Visual Context: Highly detailed, 3D Pixar-style, 9:16 vertical, minimum 40 words.
- 6-8 scenes per episode, each targeting 6-8 seconds of video.
- End with a cliffhanger that makes viewers want the next episode.
- Include beat_note for each scene explaining its story purpose.

Output ONLY valid JSON matching the EpisodeScript schema."""


# ---------------------------------------------------------------------------
# Step Implementation
# ---------------------------------------------------------------------------

def run(ctx: StepContext) -> StepResult:
    """Generate a detailed script for the current episode."""
    script_path = ctx.episode_dir / "script.json"

    # Resume: if script already exists, skip
    if script_path.exists():
        logger.info(f"Episode {ctx.episode_number} script exists, skipping")
        return StepResult(artifact_paths=[str(script_path)])

    bible = load_bible(ctx.project_dir)
    schema = EpisodeScript.model_json_schema()

    # Build character roster summary for the prompt
    roster_text = "\n".join(
        f"- {c.character_id}: {c.display_name} ({c.base_object}) — {c.role_in_story}. "
        f"Voice: {c.voice_profile}. Traits: {', '.join(c.personality_traits)}"
        for c in bible.character_roster
    )

    user_prompt = (
        f"Write episode {ctx.episode_number} of '{bible.project_title}'.\n\n"
        f"Series setting: {bible.setting}\n"
        f"Series tone: {bible.tone}\n"
        f"Series arc: {bible.series_arc_outline}\n\n"
        f"Episode summary: {bible.episode_summaries[ctx.episode_number - 1]}\n\n"
        f"Character Roster:\n{roster_text}\n\n"
        f"World Rules:\n" + "\n".join(f"- {r}" for r in bible.rules) + "\n\n"
        f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    )

    combined_prompt = f"{_SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"

    logger.info(f"Generating script for episode {ctx.episode_number}...")
    response = ctx.gemini_client.models.generate_content(
        model=Config.GEMINI_MODEL_NAME,
        contents=combined_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    raw = json.loads(response.text)
    script = EpisodeScript.model_validate(raw)

    script_path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Episode {ctx.episode_number} script saved: '{script.episode_title}' — {len(script.scenes)} scenes")

    return StepResult(artifact_paths=[str(script_path)])


def load_script(episode_dir: Path) -> EpisodeScript:
    """Load a previously saved EpisodeScript from disk."""
    path = episode_dir / "script.json"
    return EpisodeScript.model_validate_json(path.read_text(encoding="utf-8"))
