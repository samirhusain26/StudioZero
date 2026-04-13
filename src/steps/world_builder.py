"""
Step 4: World Builder — Define visual layout and atmosphere for every unique location.

Input:  all_episodes.json (extract unique location_slugs from scene breakdowns)
Output: worlds/{location_id}_layout.json + worlds/{location_id}_reference.png
Persists: project_dir/worlds/

Runs after Screenwriter so it knows exactly which locations are needed.
Reference images give the Director agent a visual anchor for each environment,
ensuring consistency across all scenes set in the same place.
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
from src.steps.writer import load_story
from src.steps.screenwriter import load_all_episodes

logger = logging.getLogger(__name__)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class WorldLayout(BaseModel):
    """Visual and atmospheric definition for one location."""
    location_id: str = Field(..., description="Matches the location_slug from scene breakdowns")
    display_name: str = Field(..., description="Human-readable location name")
    visual_description: str = Field(
        ...,
        description=(
            "Full environment description for Veo prompts. Min 50 words. "
            "Include: layout, surfaces, colours, props, lighting source, atmosphere. "
            "3D Pixar-style rendering aesthetic."
        )
    )
    atmosphere: str = Field(
        ...,
        description="Emotional atmosphere of this location, e.g. 'chaotic and warm, smells of burnt toast'"
    )
    lighting_notes: str = Field(
        ...,
        description="Specific lighting setup: source, colour temperature, shadow direction"
    )
    color_palette: List[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3-5 dominant hex or named colours that define this location's look"
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_world_layout(
    location_slug: str,
    scene_contexts: List[str],
    gemini_client,
    story_tone: str,
    story_setting: str,
) -> WorldLayout:
    """Ask Gemini to produce a full WorldLayout for a location slug."""
    schema = WorldLayout.model_json_schema()

    scene_samples = "\n".join(f"  - {ctx[:120]}" for ctx in scene_contexts[:3])

    prompt = (
        f"You are a production designer for a 3D animated series.\n"
        f"Series setting: {story_setting}\n"
        f"Series tone: {story_tone}\n\n"
        f"Design the visual layout for this location: '{location_slug}'\n\n"
        f"Sample scenes set here:\n{scene_samples}\n\n"
        f"Produce a detailed WorldLayout with at least 50 words in visual_description. "
        f"This description will be injected verbatim into every Veo prompt for this location "
        f"to maintain visual consistency across all scenes set here.\n\n"
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
    return WorldLayout.model_validate(raw)


def _generate_world_image(layout: WorldLayout, gemini_client) -> bytes | None:
    """Generate a reference image for a world layout using Gemini Imagen."""
    image_prompt = (
        f"Generate an establishing shot reference image for an animated location. "
        f"3D Pixar-style rendering. Plain white background border for reference use.\n\n"
        f"Location: {layout.display_name}\n"
        f"Description: {layout.visual_description}\n"
        f"Lighting: {layout.lighting_notes}\n"
        f"Color palette: {', '.join(layout.color_palette)}"
    )

    # Reuse the same image generation utility used by the Casting step
    return generate_character_blueprint(
        visual_description=image_prompt,
        gemini_client=gemini_client,
    )


# ── Step Implementation ──────────────────────────────────────────────────────

def run(ctx: StepContext) -> StepResult:
    """Generate world layout files and reference images for all unique locations."""
    story = load_story(ctx.project_dir)
    all_eps = load_all_episodes(ctx.project_dir)

    # Extract all unique location slugs and the scene contexts where they appear
    location_scenes: dict[str, List[str]] = {}
    for ep in all_eps.episodes:
        for scene in ep.scenes:
            slug = scene.location_slug
            if slug not in location_scenes:
                location_scenes[slug] = []
            location_scenes[slug].append(scene.visual_context)

    logger.info(f"[world_builder] Unique locations across all episodes: {sorted(location_scenes.keys())}")

    artifact_paths: List[str] = []

    for location_slug, scene_contexts in location_scenes.items():
        layout_path = ctx.worlds_dir / f"{location_slug}_layout.json"
        img_path = ctx.worlds_dir / f"{location_slug}_reference.png"

        # ── Layout JSON ─────────────────────────────────────────────────────
        if layout_path.exists():
            logger.info(f"[world_builder] Layout exists for '{location_slug}' — skipping LLM call")
            layout = WorldLayout.model_validate_json(layout_path.read_text(encoding="utf-8"))
        else:
            logger.info(
                f"[world_builder] Designing layout for '{location_slug}' "
                f"({len(scene_contexts)} scene(s) set here)..."
            )
            layout = _generate_world_layout(
                location_slug=location_slug,
                scene_contexts=scene_contexts,
                gemini_client=ctx.gemini_client,
                story_tone=story.tone,
                story_setting=story.setting,
            )
            layout_path.write_text(layout.model_dump_json(indent=2), encoding="utf-8")
            logger.info(
                f"[world_builder] Layout saved: '{layout.display_name}' "
                f"— palette: {', '.join(layout.color_palette)}"
            )

        artifact_paths.append(str(layout_path))

        # ── Reference image ─────────────────────────────────────────────────
        if img_path.exists():
            logger.info(f"[world_builder] Reference image exists for '{location_slug}' — skipping")
            artifact_paths.append(str(img_path))
            continue

        logger.info(f"[world_builder] Generating reference image for '{layout.display_name}'...")
        image_data = _generate_world_image(layout, ctx.gemini_client)

        if image_data:
            img_path.write_bytes(image_data)
            artifact_paths.append(str(img_path))
            logger.info(f"[world_builder] Reference image saved: {img_path.name}")
        else:
            logger.warning(f"[world_builder] No image returned for '{location_slug}' — continuing")

    if not artifact_paths:
        raise RuntimeError("[world_builder] No world layout assets were generated")

    logger.info(f"[world_builder] World building complete — {len(location_scenes)} location(s) defined")
    return StepResult(artifact_paths=artifact_paths)


def load_world_layout(worlds_dir: Path, location_id: str) -> WorldLayout:
    """Load a persisted world layout from disk."""
    path = worlds_dir / f"{location_id}_layout.json"
    return WorldLayout.model_validate_json(path.read_text(encoding="utf-8"))


def load_all_world_layouts(worlds_dir: Path) -> List[WorldLayout]:
    """Load all world layout files from the worlds directory."""
    layouts = []
    for layout_path in sorted(worlds_dir.glob("*_layout.json")):
        layouts.append(WorldLayout.model_validate_json(layout_path.read_text(encoding="utf-8")))
    return layouts
