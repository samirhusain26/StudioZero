"""
Step 4: Storyboard — Generate shot-by-shot visual plan with Veo prompts.

Input: EpisodeScript + character reference paths
Output: Storyboard JSON with per-scene Veo generation prompts
Persists: project_dir/episodes/episode_N/storyboard.json
"""

import json
import logging
from pathlib import Path
from typing import List

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.episode_writer import load_script
from src.steps.world_builder import load_bible

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class StoryboardShot(BaseModel):
    """A single shot in the storyboard."""
    scene_id: int = Field(..., ge=1)
    character_id: str
    camera_angle: str = Field(..., description="e.g., 'low angle looking up', 'close-up', 'wide establishing'")
    shot_type: str = Field(..., description="e.g., 'close-up', 'medium', 'wide', 'over-the-shoulder'")
    camera_movement: str = Field(..., description="e.g., 'slow push in', 'static', 'pan left', 'dolly zoom'")
    veo_prompt: str = Field(
        ...,
        description=(
            "Complete Veo 3.1 generation prompt combining character visual, environment, "
            "lighting, camera work, and action. This is the final prompt sent to Veo. Min 60 words."
        )
    )
    dialogue: str = Field(..., description="Dialogue for Veo lip-sync audio generation")
    voice_profile: str = Field(..., description="Voice profile for Veo audio")


class Storyboard(BaseModel):
    """Shot-by-shot visual plan for an episode."""
    episode_number: int
    shots: List[StoryboardShot]


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a storyboard artist and scene director for a 3D animated short-form series.

## YOUR TASK:
Convert an episode script into a shot-by-shot storyboard with complete Veo 3.1 generation prompts.

## RULES FOR VEO PROMPTS:
- Each veo_prompt is the FINAL text sent to Veo 3.1 for video generation.
- Include: character's full 3D Pixar-style appearance, environment details, lighting (warm/cool/dramatic),
  camera angle and movement, and the character's physical action.
- Always specify "9:16 vertical format" and "cinematic shallow depth of field".
- Reference the character's visual description from the Series Bible for consistency.
- Minimum 60 words per veo_prompt.

## CAMERA LANGUAGE:
- Use varied shot types across scenes (don't repeat the same angle).
- Scene 1 (hook): dramatic angle to grab attention.
- Emotional scenes: close-ups.
- Action scenes: dynamic camera movement.
- Establishing scenes: wide shots.

Output ONLY valid JSON matching the Storyboard schema."""


def run(ctx: StepContext) -> StepResult:
    """Generate storyboard with Veo prompts for the current episode."""
    storyboard_path = ctx.episode_dir / "storyboard.json"

    if storyboard_path.exists():
        logger.info(f"Storyboard exists for episode {ctx.episode_number}, skipping")
        return StepResult(artifact_paths=[str(storyboard_path)])

    bible = load_bible(ctx.project_dir)
    script = load_script(ctx.episode_dir)
    schema = Storyboard.model_json_schema()

    # Build character visual reference for the prompt
    char_visuals = "\n".join(
        f"- {c.character_id}: {c.visual_description}"
        for c in bible.character_roster
    )

    scenes_text = "\n".join(
        f"Scene {s.scene_id}: [{s.character_id}] {s.visual_context}\n"
        f"  Dialogue: \"{s.dialogue}\"\n"
        f"  Voice: {s.voice_profile}\n"
        f"  Mood: {s.mood} | Beat: {s.beat_note}"
        for s in script.scenes
    )

    user_prompt = (
        f"Create a storyboard for episode {ctx.episode_number}: '{script.episode_title}'\n\n"
        f"Setting: {bible.setting}\n"
        f"Tone: {bible.tone}\n\n"
        f"Character Visual References:\n{char_visuals}\n\n"
        f"Episode Scenes:\n{scenes_text}\n\n"
        f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    )

    combined_prompt = f"{_SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"

    logger.info(f"Generating storyboard for episode {ctx.episode_number}...")
    response = ctx.gemini_client.models.generate_content(
        model=Config.GEMINI_MODEL_NAME,
        contents=combined_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    raw = json.loads(response.text)
    storyboard = Storyboard.model_validate(raw)

    storyboard_path.write_text(storyboard.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Storyboard saved: {len(storyboard.shots)} shots")

    return StepResult(artifact_paths=[str(storyboard_path)])


def load_storyboard(episode_dir: Path) -> Storyboard:
    """Load a previously saved Storyboard from disk."""
    path = episode_dir / "storyboard.json"
    return Storyboard.model_validate_json(path.read_text(encoding="utf-8"))
