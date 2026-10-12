"""
Step 5.5 (per episode): Set Designer — Generate scene starting images.

Input:  director_shots.json + characters/{id}_reference.png + worlds/{location}_reference.png
Output: project_dir/scene_starts/{character_id}_{location_id}.png (cached)
Persists: project_dir/scene_starts/

Composites character reference images into world environments using Gemini Imagen,
producing scene-appropriate starting frames for video generation. This prevents
raw character sheet images (white background) from appearing in generated video.

Caching: Images are keyed by {character_id}_{location_id} and reused across episodes.
"""

import logging
from pathlib import Path
from typing import List, Optional

from google.genai import types

from src.config import Config
from src.steps import StepContext, StepResult, slug_part
from src.steps.director import load_director_shots
from src.pricing import charge_genai

logger = logging.getLogger(__name__)


def _find_reference_image(directory: Path, stem: str) -> Optional[Path]:
    """Find a reference image by stem, trying common extensions."""
    for ext in ("png", "jpg", "jpeg", "webp"):
        path = directory / f"{stem}_reference.{ext}"
        if path.exists():
            return path
    return None


def _generate_scene_start(
    char_image_path: Path,
    world_image_path: Path,
    character_id: str,
    location_id: str,
    scene_context: str,
    gemini_client,
) -> Optional[bytes]:
    """
    Generate a scene starting image by compositing a character into a world.

    Feeds both the character reference image and world reference image to Gemini
    to produce a scene-appropriate starting frame.
    """
    char_bytes = char_image_path.read_bytes()
    world_bytes = world_image_path.read_bytes()

    # Detect mime type from extension
    char_mime = f"image/{char_image_path.suffix.lstrip('.').replace('jpg', 'jpeg')}"
    world_mime = f"image/{world_image_path.suffix.lstrip('.').replace('jpg', 'jpeg')}"

    prompt = (
        f"Generate a scene starting frame for a 3D Pixar-style animated video. "
        f"Place the character from the first image naturally into the environment "
        f"from the second image. The character should be positioned in the scene "
        f"as if the camera just started rolling — natural pose, grounded in the "
        f"environment, matching the world's lighting and atmosphere. "
        f"Do NOT include any white background, reference sheet borders, or "
        f"character turnaround views — this must look like a still from the film. "
        f"Scene context: {scene_context}. "
        f"9:16 vertical ratio, cinematic composition, 3D Pixar-style animation."
    )

    # Multimodal content: character image + world image + text prompt
    contents = [
        types.Part(inline_data=types.Blob(mime_type=char_mime, data=char_bytes)),
        types.Part(inline_data=types.Blob(mime_type=world_mime, data=world_bytes)),
        prompt,
    ]

    try:
        response = gemini_client.models.generate_content(
            model=Config.GEMINI_IMAGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        charge_genai(response, "image", Config.GEMINI_IMAGE_MODEL, "scene start image", prompt)

        for part in response.candidates[0].content.parts:
            if (
                part.inline_data
                and part.inline_data.mime_type
                and part.inline_data.mime_type.startswith("image/")
            ):
                return part.inline_data.data

        logger.warning(
            f"[set_designer] No image in Gemini response for "
            f"{character_id}@{location_id}"
        )
        return None

    except Exception as e:
        logger.error(
            f"[set_designer] Image generation failed for "
            f"{character_id}@{location_id}: {e}"
        )
        return None


def run(ctx: StepContext) -> StepResult:
    """Generate scene starting images for all shots in the current episode."""
    shots = load_director_shots(ctx.episode_dir)
    scene_starts_dir = ctx.project_dir / "scene_starts"
    scene_starts_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths: List[str] = []
    seen_combos: set = set()

    logger.info(
        f"[set_designer] Episode {ctx.episode_number}: "
        f"preparing scene starting images for {len(shots.shots)} shot(s)"
    )

    for shot in shots.shots:
        cache_key = f"{slug_part(shot.primary_character_id)}_{slug_part(shot.location_id)}"
        cache_path = scene_starts_dir / f"{cache_key}.png"

        # Skip duplicate character+location combos within this episode
        if cache_key in seen_combos:
            continue
        seen_combos.add(cache_key)

        # Check cache — reuse existing scene start images across episodes
        if cache_path.exists() and cache_path.stat().st_size > 0:
            logger.info(
                f"[set_designer] Cached scene start for {cache_key} "
                f"({cache_path.stat().st_size // 1024} KB) — reusing"
            )
            artifact_paths.append(str(cache_path))
            continue

        # Find source images
        char_img = _find_reference_image(ctx.characters_dir, shot.primary_character_id)
        world_img = _find_reference_image(ctx.worlds_dir, shot.location_id)

        if not char_img:
            logger.warning(
                f"[set_designer] No character reference for "
                f"'{shot.primary_character_id}' — skipping {cache_key}"
            )
            continue

        if not world_img:
            logger.warning(
                f"[set_designer] No world reference for "
                f"'{shot.location_id}' — skipping {cache_key}"
            )
            continue

        logger.info(
            f"[set_designer] Generating scene start: "
            f"'{shot.primary_character_id}' in '{shot.location_id}'..."
        )

        image_data = _generate_scene_start(
            char_image_path=char_img,
            world_image_path=world_img,
            character_id=shot.primary_character_id,
            location_id=shot.location_id,
            scene_context=shot.veo_prompt[:200],
            gemini_client=ctx.gemini_client,
        )

        if image_data:
            cache_path.write_bytes(image_data)
            artifact_paths.append(str(cache_path))
            logger.info(
                f"[set_designer] Scene start saved: {cache_path.name} "
                f"({len(image_data) // 1024} KB)"
            )
        else:
            logger.warning(
                f"[set_designer] Failed to generate scene start for {cache_key} "
                f"— scene_generator will fall back to character reference"
            )

    logger.info(
        f"[set_designer] Episode {ctx.episode_number} set design complete "
        f"— {len(artifact_paths)} scene start image(s)"
    )

    return StepResult(artifact_paths=artifact_paths)
