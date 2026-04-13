"""
Step 1: Writer — Generate a full structured story from a user brief.

Input:  brief (1-2 sentence user idea), num_episodes
Output: StoryOutput JSON — full story, character seeds, per-episode outlines
Persists: project_dir/story.json
"""

import json
import logging
from pathlib import Path
from typing import List

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.steps import StepContext, StepResult

logger = logging.getLogger(__name__)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class CharacterSeed(BaseModel):
    """Minimal character definition produced by the Writer."""
    character_id: str = Field(..., description="Unique slug, e.g. 'brave_teapot'")
    display_name: str = Field(..., description="Human-readable name, e.g. 'Lady Teapot'")
    base_object: str = Field(..., description="Real-world object this character is, e.g. 'teapot'")
    role_in_story: str = Field(..., description="e.g. 'protagonist', 'antagonist', 'comic relief'")
    personality_traits: List[str] = Field(..., description="3-5 personality adjectives")
    visual_description: str = Field(
        ...,
        description="3D Pixar-style appearance description, minimum 30 words"
    )
    voice_profile: str = Field(
        ...,
        description="Pitch, texture, accent, emotional quality for Veo audio"
    )


class EpisodeOutline(BaseModel):
    """High-level outline for one episode."""
    episode_number: int = Field(..., ge=1)
    title: str
    summary: str = Field(..., description="2-3 sentence story summary for this episode")
    opening_hook: str = Field(..., description="Scroll-stopping first moment — 1 sentence")
    ending_moment: str = Field(
        ...,
        description="How the episode ends — cliffhanger or resolution. 1-2 sentences."
    )


class StoryOutput(BaseModel):
    """Full story output from the Writer agent."""
    project_title: str
    logline: str = Field(..., description="One-sentence story pitch")
    setting: str = Field(..., description="Where the story takes place — vivid and specific")
    tone: str = Field(..., description="Overall emotional register, e.g. 'dark comedy with heart'")
    world_rules: List[str] = Field(
        ...,
        min_length=3,
        max_length=6,
        description="Rules that govern this world — create drama and comedy"
    )
    series_arc: str = Field(..., description="2-3 sentence arc spanning all episodes")
    episode_count: int = Field(..., ge=1, le=10)
    episode_outlines: List[EpisodeOutline] = Field(
        ...,
        description="One outline per episode — must match episode_count"
    )
    character_seeds: List[CharacterSeed] = Field(
        ...,
        min_length=2,
        description="All characters who appear in this story"
    )


# ── System Prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a senior story developer for a viral animated short-form series.
All characters MUST be anthropomorphic household objects or food items.

## YOUR TASK:
Transform the user's brief into a complete, structured story document.

## REQUIREMENTS:
1. **Project Title**: Catchy and evocative.
2. **Logline**: One sentence that makes someone want to watch.
3. **Setting**: Specific, atmospheric, interesting. Not generic.
4. **Tone**: Clear emotional register. Lean into what makes the story unique.
5. **World Rules**: 3-6 rules that create dramatic irony, tension, or comedy.
6. **Series Arc**: A satisfying arc with escalation and payoff across all episodes.
7. **Episode Outlines**: Each episode must escalate from the previous. Include a strong
   opening hook and a memorable ending moment. Sequential narrative — episode 2 picks
   up where episode 1 ends.
8. **Characters**: Fully defined seeds. Visual descriptions must be vivid enough to
   generate a consistent reference image. Voice profiles must be specific enough for
   Veo audio generation.

Output ONLY valid JSON matching the StoryOutput schema."""


# ── Step Implementation ──────────────────────────────────────────────────────

def run(ctx: StepContext) -> StepResult:
    """Generate the full story from the user's brief."""
    story_path = ctx.project_dir / "story.json"

    if story_path.exists():
        cached = StoryOutput.model_validate_json(story_path.read_text(encoding="utf-8"))
        if cached.episode_count >= ctx.num_episodes:
            logger.info(
                f"[writer] story.json already exists ({cached.episode_count} episode(s)) — skipping"
            )
            return StepResult(artifact_paths=[str(story_path)])
        else:
            logger.warning(
                f"[writer] Cached story has {cached.episode_count} episode(s) but "
                f"{ctx.num_episodes} requested — regenerating story and clearing downstream files"
            )
            # Remove stale downstream files so they are regenerated with correct episode count
            for stale in ["all_episodes.json"]:
                stale_path = ctx.project_dir / stale
                if stale_path.exists():
                    stale_path.unlink()
                    logger.info(f"[writer] Removed stale {stale}")
            story_path.unlink()

    logger.info("[writer] Starting story generation from brief...")
    logger.info(f"[writer] Brief: {ctx.brief[:120]}{'...' if len(ctx.brief) > 120 else ''}")
    logger.info(f"[writer] Target episode count: {ctx.num_episodes}")

    schema = StoryOutput.model_json_schema()

    user_prompt = (
        f"Transform this brief into a full story for a {ctx.num_episodes}-episode animated series.\n\n"
        f"Brief: {ctx.brief}\n\n"
        f"Generate exactly {ctx.num_episodes} episode outline(s).\n\n"
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
    story = StoryOutput.model_validate(raw)

    story_path.write_text(story.model_dump_json(indent=2), encoding="utf-8")

    logger.info(
        f"[writer] Story complete: '{story.project_title}' — "
        f"{len(story.character_seeds)} character(s), {len(story.episode_outlines)} episode(s)"
    )
    logger.info(f"[writer] Logline: {story.logline}")
    for ep in story.episode_outlines:
        logger.info(f"[writer]   Episode {ep.episode_number}: {ep.title} — {ep.summary[:80]}...")

    return StepResult(
        artifact_paths=[str(story_path)],
        data={"project_title": story.project_title, "logline": story.logline},
    )


def load_story(project_dir: Path) -> StoryOutput:
    """Load the persisted story from disk."""
    path = project_dir / "story.json"
    return StoryOutput.model_validate_json(path.read_text(encoding="utf-8"))
