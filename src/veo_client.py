"""
Veo 3.1 Client — Generates animated video scenes via Google GenAI API.

Uses the "Ingredients to Video" capability: a character reference image is passed
as a visual ingredient alongside a rich text prompt to produce a short animated
clip with native lip-sync and audio.
"""

import logging
import mimetypes
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError as GenAIServerError
from google.api_core.exceptions import (
    ServiceUnavailable,
    ResourceExhausted,
    DeadlineExceeded,
    InternalServerError,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import Config

logger = logging.getLogger(__name__)

# Model is configured via Config.VEO_MODEL (settings.json or env var VEO_MODEL)
# Default: veo-3.1-lite-generate-preview (cheapest)
VEO_MODEL = Config.VEO_MODEL

# How often (seconds) to poll for long-running video generation
_POLL_INTERVAL = 10
_MAX_POLL_TIME = 300  # 5 minutes


def _build_veo_prompt(
    visual_description: str,
    dialogue: str,
    voice_profile: str,
) -> str:
    """
    Combine scene metadata into a single Veo generation prompt.

    The prompt instructs Veo to animate the character speaking with
    lip-sync, using the reference image for visual consistency.
    """
    return (
        f"{visual_description}\n\n"
        f"The character speaks the following dialogue with natural lip-sync and "
        f"expressive body language: \"{dialogue}\"\n\n"
        f"Voice style: {voice_profile}. "
        f"Generate audio with the character's voice matching this profile. "
        f"Cinematic camera movement, shallow depth of field, 9:16 vertical format."
    )


def _get_veo_client() -> genai.Client:
    """
    Create a GenAI client.

    If Config.VERTEX_PROJECT_ID is set, returns a Vertex AI-backed client.
    Otherwise, returns a standard GenAI client using Config.GEMINI_API_KEY.
    """
    if Config.VERTEX_PROJECT_ID:
        logger.info(f"Using Vertex AI client (Project: {Config.VERTEX_PROJECT_ID})")
        return genai.Client(
            vertexai=True,
            project=Config.VERTEX_PROJECT_ID,
            location=Config.VERTEX_LOCATION,
        )

    logger.info("Using standard GenAI client with API Key")
    return genai.Client(api_key=Config.GEMINI_API_KEY)


@retry(
    retry=retry_if_exception_type((
        ServiceUnavailable,
        ResourceExhausted,
        DeadlineExceeded,
        InternalServerError,
        ClientError,
        GenAIServerError,
        ConnectionError,
        TimeoutError,
    )),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=35, max=120),
    before_sleep=lambda retry_state: logger.warning(
        f"Veo request failed (attempt {retry_state.attempt_number}), retrying: "
        f"{retry_state.outcome.exception()}"
    ),
)
def generate_veo_scene(
    image_path: str,
    visual_description: str,
    dialogue: str,
    voice_profile: str,
    output_path: str,
    on_poll: Optional[Callable[[int], None]] = None,
) -> str:
    """
    Generate an animated video scene using Veo 3.1.

    Passes the character reference image as a visual ingredient and a rich
    text prompt combining visual_description, dialogue, and voice_profile
    to produce a short clip with native lip-sync and audio.

    Args:
        image_path: Path to the character reference PNG/JPG image.
        visual_description: Detailed scene visual description from the episodic script.
        dialogue: The character's spoken dialogue for this scene.
        voice_profile: Descriptive voice profile string for audio generation.
        output_path: Where to save the resulting MP4 file.

    Returns:
        The output_path where the MP4 was saved.

    Raises:
        FileNotFoundError: If image_path does not exist.
        RuntimeError: If video generation fails or times out.
    """
    image_file = Path(image_path)
    if not image_file.exists():
        raise FileNotFoundError(f"Character reference image not found: {image_path}")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    client = _get_veo_client()

    # Adjust model name if using Vertex AI
    model_name = VEO_MODEL
    if Config.VERTEX_PROJECT_ID:
        model_name = "veo-3.1-fast-generate-001"

    # Read the reference image for character consistency across episodes
    image_bytes = image_file.read_bytes()
    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

    # Build the combined prompt
    prompt_text = _build_veo_prompt(visual_description, dialogue, voice_profile)
    logger.info(f"Veo prompt ({len(prompt_text)} chars) using model {model_name}: {prompt_text[:120]}...")

    operation = client.models.generate_videos(
        model=model_name,
        prompt=prompt_text,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
        ),
        image=types.Image(image_bytes=image_bytes, mime_type=mime_type),
    )

    # Poll until the operation completes
    logger.info("Veo generation submitted, polling for completion...")
    deadline = time.time() + _MAX_POLL_TIME

    while not operation.done:
        if time.time() > deadline:
            raise RuntimeError(
                f"Veo generation timed out after {_MAX_POLL_TIME}s"
            )
        elapsed = int(time.time() - (deadline - _MAX_POLL_TIME))
        
        # Log metadata if available (often contains progress or state)
        meta = getattr(operation, 'metadata', None)
        status_msg = f"Polling Veo operation... ({elapsed}s elapsed)"
        if meta:
            # Handle both dict-like and attribute-like access
            if isinstance(meta, dict):
                progress = meta.get('progress_percentage')
                if progress is not None:
                    status_msg += f" - Progress: {progress}%"
            elif hasattr(meta, 'progress_percentage'):
                status_msg += f" - Progress: {meta.progress_percentage}%"

        logger.info(status_msg)
        if on_poll:
            on_poll(elapsed)
        time.sleep(_POLL_INTERVAL)
        operation = client.operations.get(operation)

    # Check for errors in the completed operation
    if operation.error:
        logger.error(f"Veo operation failed — full error: {operation.error}")
        logger.error(f"Full operation state: {operation}")
        raise RuntimeError(f"Veo generation error: {operation.error}")

    # Extract video from completed operation
    logger.info("Veo generation complete, extracting video data...")
    logger.debug(f"Full operation response: {getattr(operation, 'response', None)}")

    if operation.response and operation.response.generated_videos:
        video = operation.response.generated_videos[0]
        if hasattr(video, 'video_metadata'):
            logger.info(f"Veo Video Metadata: {video.video_metadata}")

        if hasattr(video, 'video') and video.video:
            raw = video.video
            if raw.video_bytes:
                out = Path(output_path)
                out.write_bytes(raw.video_bytes)
                logger.info(f"Veo scene saved: {out} ({len(raw.video_bytes)} bytes)")
                return str(out)
            elif raw.uri:
                # Video returned as a URI — download it
                logger.info(f"Veo returned URI, downloading: {raw.uri}")
                uri = raw.uri
                if "key=" not in uri:
                    uri = f"{uri}&key={Config.GEMINI_API_KEY}"
                out = Path(output_path)
                urllib.request.urlretrieve(uri, out)
                logger.info(f"Veo scene downloaded and saved: {out} ({out.stat().st_size} bytes)")
                return str(out)
            else:
                logger.error("video.video exists but both video_bytes and uri are empty")
        else:
            logger.error(f"No video attribute on generated_videos[0]. Object: {video}")
    else:
        logger.error(
            f"operation.response={getattr(operation, 'response', None)} | "
            f"generated_videos={getattr(getattr(operation, 'response', None), 'generated_videos', None)}"
        )

    raise RuntimeError("Veo returned no video data in response")
