"""
Step 2: Screenwriter — Break the full story into per-scene breakdowns for all episodes.

Input:  story.json (from Writer step)
Output: AllEpisodesScript JSON — every episode's scenes in a single one-shot LLM call
        to ensure sequential narrative continuity across episodes.
Persists: project_dir/all_episodes.json
"""

import json
import logging
from pathlib import Path
from typing import List

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.writer import load_story

logger = logging.getLogger(__name__)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class SceneBeat(BaseModel):
    """A single scene within an episode."""
    scene_id: int = Field(..., ge=1)
    primary_character_id: str = Field(
        ...,
        description="The character_id of the character who is the focus of this scene"
    )
    characters_present: List[str] = Field(
        ...,
        description="All character_ids visible or audible in this scene"
    )
    location_slug: str = Field(
        ...,
        description="Unique slug for this location, e.g. 'kitchen_counter', 'fridge_interior'. "
                    "Reuse the same slug for the same place across scenes."
    )
    dialogue: str = Field(
        ...,
        description="The primary character's spoken line. First-person, max 20 words."
    )
    voice_profile: str = Field(
        ...,
        description="Voice style for Veo audio: pitch, pace, emotion, accent"
    )
    visual_context: str = Field(
        ...,
        description=(
            "Detailed scene description for the Director agent: character appearance, "
            "action, environment, lighting, atmosphere. Min 40 words. 9:16 vertical framing."
        )
    )
    mood: str = Field(..., description="Emotional tone, e.g. 'tense', 'comedic', 'dramatic'")
    beat_note: str = Field(
        ...,
        description="Story function of this scene, e.g. 'inciting incident', 'climax', 'comic relief'"
    )


class EpisodeScript(BaseModel):
    """Full scene breakdown for one episode."""
    episode_number: int = Field(..., ge=1)
    episode_title: str
    cold_open_hook: str = Field(
        ...,
        description="1-sentence scroll-stopping hook that opens this episode"
    )
    scenes: List[SceneBeat] = Field(
        ...,
        min_length=4,
        max_length=8,
        description="4-8 scenes. Each scene = one Veo clip (20-40 seconds)."
    )
    episode_ending: str = Field(
        ...,
        description="How this episode ends. If not the last episode, must be a cliffhanger."
    )


class AllEpisodesScript(BaseModel):
    """Complete scene breakdown for all episodes — generated in one shot."""
    episodes: List[EpisodeScript]


# ── System Prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a senior screenwriter adapting a story into a shot-ready scene breakdown.

## YOUR TASK:
Convert the full story into scene-by-scene breakdowns for ALL episodes in one pass.
This ensures narrative continuity — episode 2 picks up where episode 1 ends.

## SCENE RULES:
- 4-8 scenes per episode. Each scene will become one Veo video clip (20-40 seconds).
- Scene 1 of episode 1 MUST be a cognitive-dissonance hook that grabs attention immediately.
- Dialogue: max 20 words, first-person, natural speech.
- Visual context: highly detailed, 3D Pixar-style, 9:16 vertical. Min 40 words.
- Every scene must have a clear story function (beat_note).
- location_slug: reuse the SAME slug every time a scene is in the same place.
  This is used downstream for world-building consistency.
- characters_present: list all character_ids visible in the scene, not just the speaker.
- All character_ids MUST match those defined in the story's character_seeds exactly.

## EPISODE CONTINUITY:
- Each episode must continue where the previous left off.
- The episode_ending must set up what happens next (cliffhanger), except for the final episode.

Output ONLY valid JSON matching the AllEpisodesScript schema."""


# ── Step Implementation ──────────────────────────────────────────────────────

def run(ctx: StepContext) -> StepResult:
    """Generate scene breakdowns for all episodes in one shot."""
    output_path = ctx.project_dir / "all_episodes.json"

    if output_path.exists():
        logger.info("[screenwriter] all_episodes.json already exists — skipping generation")
        return StepResult(artifact_paths=[str(output_path)])

    story = load_story(ctx.project_dir)

    logger.info(
        f"[screenwriter] Starting scene breakdown for '{story.project_title}' "
        f"— {story.episode_count} episode(s), one-shot generation for continuity"
    )

    schema = AllEpisodesScript.model_json_schema()

    # Build character roster for the prompt
    roster_text = "\n".join(
        f"  - {c.character_id}: {c.display_name} ({c.base_object}), {c.role_in_story}. "
        f"Traits: {', '.join(c.personality_traits)}. Voice: {c.voice_profile}"
        for c in story.character_seeds
    )

    # Build episode outlines for the prompt
    outlines_text = "\n".join(
        f"  Episode {ep.episode_number} — '{ep.title}':\n"
        f"    Summary: {ep.summary}\n"
        f"    Opening hook: {ep.opening_hook}\n"
        f"    Ending: {ep.ending_moment}"
        for ep in story.episode_outlines
    )

    user_prompt = (
        f"Write scene breakdowns for ALL {story.episode_count} episode(s) of '{story.project_title}'.\n\n"
        f"Setting: {story.setting}\n"
        f"Tone: {story.tone}\n"
        f"Series arc: {story.series_arc}\n\n"
        f"World rules:\n" + "\n".join(f"  - {r}" for r in story.world_rules) + "\n\n"
        f"Character roster:\n{roster_text}\n\n"
        f"Episode outlines:\n{outlines_text}\n\n"
        f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    )

    combined_prompt = f"{_SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"

    response = ctx.gemini_client.models.generate_content(
        model=Config.GEMINI_MODEL_NAME,
        contents=combined_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    raw = json.loads(response.text)
    all_eps = AllEpisodesScript.model_validate(raw)

    # Validate that the LLM didn't hallucinate character IDs
    valid_ids = {c.character_id for c in story.character_seeds}
    bad_ids: set[str] = set()
    for ep in all_eps.episodes:
        for scene in ep.scenes:
            for cid in scene.characters_present:
                if cid not in valid_ids:
                    bad_ids.add(cid)
            if scene.primary_character_id not in valid_ids:
                bad_ids.add(scene.primary_character_id)
    if bad_ids:
        raise ValueError(
            f"[screenwriter] LLM produced unknown character IDs not in story character_seeds: "
            f"{sorted(bad_ids)}. Valid IDs: {sorted(valid_ids)}. "
            f"This step will be retried on next run."
        )

    output_path.write_text(all_eps.model_dump_json(indent=2), encoding="utf-8")

    # Log a summary of what was written
    for ep in all_eps.episodes:
        scene_ids = [s.scene_id for s in ep.scenes]
        locations = list(dict.fromkeys(s.location_slug for s in ep.scenes))
        logger.info(
            f"[screenwriter] Episode {ep.episode_number} '{ep.episode_title}': "
            f"{len(ep.scenes)} scenes, locations: {locations}"
        )

    all_chars = {cid for ep in all_eps.episodes for s in ep.scenes for cid in s.characters_present}
    logger.info(f"[screenwriter] Characters appearing across all episodes: {sorted(all_chars)}")

    return StepResult(
        artifact_paths=[str(output_path)],
        data={"episode_count": len(all_eps.episodes)},
    )


def load_all_episodes(project_dir: Path) -> AllEpisodesScript:
    """Load the persisted episode breakdowns from disk."""
    path = project_dir / "all_episodes.json"
    return AllEpisodesScript.model_validate_json(path.read_text(encoding="utf-8"))


def load_episode(project_dir: Path, episode_number: int) -> EpisodeScript:
    """Load a specific episode's script from the all_episodes file."""
    all_eps = load_all_episodes(project_dir)
    for ep in all_eps.episodes:
        if ep.episode_number == episode_number:
            return ep
    raise ValueError(f"Episode {episode_number} not found in all_episodes.json")
