"""
Step 5 (per episode): Director — Synthesise all pre-production assets into final Veo prompts.

Input:  Episode script (from all_episodes.json)
        + character sheets (characters/*_sheet.json)
        + character reference images (characters/*_reference.png)
        + world layouts (worlds/*_layout.json)
Output: DirectorShots JSON — one fully engineered Veo prompt per scene
Persists: project_dir/episodes/episode_N/director_shots.json

The Director is the final creative gate before Veo. Each veo_prompt must be
complete enough to generate a consistent, production-quality clip with no
further context — character appearance, world, lighting, action, and audio
are all baked into the prompt.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from google.genai import types
from pydantic import BaseModel, Field

from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.screenwriter import load_episode
from src.steps.casting import load_all_character_sheets
from src.steps.world_builder import load_all_world_layouts

logger = logging.getLogger(__name__)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class DirectorShot(BaseModel):
    """Final production-ready prompt for a single scene."""
    scene_id: int = Field(..., ge=1)
    primary_character_id: str
    location_id: str
    camera_angle: str = Field(
        ...,
        description="e.g. 'low angle looking up', 'close-up', 'wide establishing shot'"
    )
    shot_type: str = Field(
        ...,
        description="e.g. 'close-up', 'medium', 'wide', 'over-the-shoulder'"
    )
    camera_movement: str = Field(
        ...,
        description="e.g. 'slow push in', 'static', 'pan left', 'dolly zoom'"
    )
    veo_prompt: str = Field(
        ...,
        description=(
            "Focused video generation prompt. 60–100 words. "
            "Character key appearance (1–2 sentences), environment (1 sentence), "
            "lighting, camera, action, mood. End with '9:16 vertical, cinematic, 3D Pixar-style animation.'"
        )
    )
    dialogue: str = Field(..., description="Character's spoken dialogue for lip-sync")
    voice_profile: str = Field(..., description="Voice profile for audio generation")
    model_hint: str = Field(
        default="veo",
        description="Which prompt style was used: veo, kling, seedance, wan, sora"
    )


class DirectorShots(BaseModel):
    """All director shots for one episode."""
    episode_number: int
    shots: List[DirectorShot]


# ── System Prompt ────────────────────────────────────────────────────────────

def _get_model_hint() -> str:
    """Determine which model family is active for prompt style adaptation."""
    model_id = Config.ACTIVE_VIDEO_MODEL
    if "kling" in model_id:
        return "kling"
    elif "seedance" in model_id:
        return "seedance"
    elif "wan" in model_id:
        return "wan"
    elif "sora" in model_id:
        return "sora"
    return "veo"


def _build_system_prompt(model_hint: str) -> str:
    """Build the director system prompt, adapted for the active video model."""

    # Model-specific prompt guidance
    model_guidance = {
        "veo": (
            "You are directing for Veo 3.1 (Google). "
            "Use detailed scene descriptions with specific camera directions. "
            "Veo excels at lip-sync and audio — describe dialogue delivery clearly. "
            "End each veo_prompt with: '9:16 vertical, cinematic, 3D Pixar-style animation.'"
        ),
        "kling": (
            "You are directing for Kling (Kuaishou). "
            "Emphasize motion descriptors and physical action — Kling excels at motion fluidity. "
            "Describe specific body movements, gestures, and physical interactions in detail. "
            "End each veo_prompt with: '9:16 vertical, cinematic, 3D Pixar-style animation.'"
        ),
        "seedance": (
            "You are directing for Seedance (ByteDance). "
            "Use cinematic shot types and camera movements — Seedance has director-level camera control. "
            "You can use multi-shot language (e.g. 'the camera starts wide then pushes in to close-up'). "
            "End each veo_prompt with: '9:16 vertical, cinematic, 3D Pixar-style animation.'"
        ),
        "wan": (
            "You are directing for Wan (Alibaba). "
            "Use cinema-grade aesthetic keywords for lighting and color grading. "
            "Reference film stock looks (e.g. 'Kodak Vision3 warmth') and lighting setups. "
            "End each veo_prompt with: '9:16 vertical, cinematic, 3D Pixar-style animation.'"
        ),
        "sora": (
            "You are directing for Sora (OpenAI). "
            "Use natural language descriptions — Sora has strong physics understanding. "
            "Describe the scene as you would narrate it to someone. Include spatial relationships. "
            "End each veo_prompt with: '9:16 vertical, cinematic, 3D Pixar-style animation.'"
        ),
    }

    guidance = model_guidance.get(model_hint, model_guidance["veo"])

    return f"""You are a film director preparing the final production brief for AI video generation.

## YOUR TASK:
For each scene in the episode, craft a focused, production-ready generation prompt.

## MODEL CONTEXT:
{guidance}

Set model_hint to "{model_hint}" for all shots.

## PROMPT RULES:
Each veo_prompt MUST be concise (60–100 words max). Include:
1. Character appearance: 1–2 sentences covering shape, colour, and ONE signature detail (e.g. trench coat, barcode sticker)
2. Environment: 1 sentence — dominant colours, key prop, and mood
3. Lighting: one phrase (e.g. "harsh neon-green overhead LED")
4. Camera: angle, shot type, and movement in one line
5. Action + emotion: what the character physically does and feels right now
6. End with the animation style tag as specified above.

DO NOT paste full character bios or world descriptions verbatim — distil them to the key visual facts.
Short, vivid, specific prompts outperform long ones.

## CAMERA VARIETY:
- Scene 1: dramatic hook (low angle, dutch tilt, or wide)
- Emotional beats: close-up, slow push in
- Action beats: dolly zoom, fast pan
- Establishing: wide shot, static
- Never repeat the same camera_movement for consecutive scenes

Output ONLY valid JSON matching the DirectorShots schema."""


# ── Step Implementation ──────────────────────────────────────────────────────

def run(ctx: StepContext) -> StepResult:
    """Generate final Veo prompts for all scenes in the current episode."""
    shots_path = ctx.episode_dir / "director_shots.json"

    if shots_path.exists():
        logger.info(f"[director] Director shots exist for episode {ctx.episode_number} — skipping")
        return StepResult(artifact_paths=[str(shots_path)])

    episode = load_episode(ctx.project_dir, ctx.episode_number)

    # Collect only the characters and locations that appear in this episode's scenes
    episode_char_ids = {
        cid for scene in episode.scenes for cid in scene.characters_present
    }
    episode_location_ids = {scene.location_slug for scene in episode.scenes}

    all_sheets = load_all_character_sheets(ctx.characters_dir)
    all_layouts = load_all_world_layouts(ctx.worlds_dir)

    character_sheets = [s for s in all_sheets if s.character_id in episode_char_ids]
    world_layouts = [w for w in all_layouts if w.location_id in episode_location_ids]

    logger.info(
        f"[director] Building Veo prompts for episode {ctx.episode_number} "
        f"'{episode.episode_title}' — {len(episode.scenes)} scene(s)"
    )
    logger.info(
        f"[director] Episode characters ({len(character_sheets)}): "
        f"{[s.character_id for s in character_sheets]}"
    )
    logger.info(
        f"[director] Episode locations ({len(world_layouts)}): "
        f"{[w.location_id for w in world_layouts]}"
    )

    model_hint = _get_model_hint()
    logger.info(f"[director] Active video model: {Config.ACTIVE_VIDEO_MODEL} — prompt style: {model_hint}")

    schema = DirectorShots.model_json_schema()

    # Build character reference block
    char_block = "\n\n".join(
        f"CHARACTER: {s.character_id} ({s.display_name})\n"
        f"  Visual: {s.visual_description}\n"
        f"  Voice: {s.voice_profile}\n"
        f"  Gesture: {s.signature_gesture}\n"
        f"  Emotion range: {s.emotional_range}"
        for s in character_sheets
    )

    # Build world reference block
    world_block = "\n\n".join(
        f"LOCATION: {w.location_id} ({w.display_name})\n"
        f"  Visual: {w.visual_description}\n"
        f"  Atmosphere: {w.atmosphere}\n"
        f"  Lighting: {w.lighting_notes}\n"
        f"  Palette: {', '.join(w.color_palette)}"
        for w in world_layouts
    )

    # Build scene list
    scenes_block = "\n".join(
        f"Scene {s.scene_id}: [{s.primary_character_id}] @ {s.location_slug}\n"
        f"  Context: {s.visual_context}\n"
        f"  Dialogue: \"{s.dialogue}\"\n"
        f"  Voice: {s.voice_profile}\n"
        f"  Mood: {s.mood} | Beat: {s.beat_note}\n"
        f"  Others present: {', '.join(s.characters_present)}"
        for s in episode.scenes
    )

    user_prompt = (
        f"Direct episode {ctx.episode_number}: '{episode.episode_title}'\n\n"
        f"Episode cold open: {episode.cold_open_hook}\n\n"
        f"== CHARACTER REFERENCE ==\n{char_block}\n\n"
        f"== WORLD REFERENCE ==\n{world_block}\n\n"
        f"== SCENES TO DIRECT ==\n{scenes_block}\n\n"
        f"Output ONLY valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    )

    system_prompt = _build_system_prompt(model_hint)
    combined_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

    response = ctx.gemini_client.models.generate_content(
        model=Config.GEMINI_MODEL_NAME,
        contents=combined_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    raw = json.loads(response.text)
    shots = DirectorShots.model_validate(raw)

    shots_path.write_text(shots.model_dump_json(indent=2), encoding="utf-8")

    for shot in shots.shots:
        logger.info(
            f"[director]   Shot {shot.scene_id}: {shot.shot_type} {shot.camera_angle}, "
            f"{shot.camera_movement} — {len(shot.veo_prompt.split())} words in prompt"
        )

    logger.info(
        f"[director] Episode {ctx.episode_number} direction complete "
        f"— {len(shots.shots)} shot(s) ready for Veo"
    )

    return StepResult(
        artifact_paths=[str(shots_path)],
        data={"shot_count": len(shots.shots)},
    )


def load_director_shots(episode_dir: Path) -> DirectorShots:
    """Load persisted director shots from disk."""
    path = episode_dir / "director_shots.json"
    return DirectorShots.model_validate_json(path.read_text(encoding="utf-8"))
