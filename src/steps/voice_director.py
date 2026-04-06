"""
Step 5: Voice Director — Generate TTS audio for each scene.

Input: EpisodeScript with dialogue and voice profiles
Output: Per-scene WAV audio files
Persists: project_dir/episodes/episode_N/audio/scene_N.wav
"""

import logging
import time
from pathlib import Path

from src.gemini_tts import generate_audio
from src.steps import StepContext, StepResult
from src.steps.episode_writer import load_script

logger = logging.getLogger(__name__)


def run(ctx: StepContext) -> StepResult:
    """Generate TTS audio for every scene in the episode."""
    script = load_script(ctx.episode_dir)
    audio_dir = ctx.episode_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = []

    for scene in script.scenes:
        audio_path = audio_dir / f"scene_{scene.scene_id}.wav"

        # Resume: skip if already generated
        if audio_path.exists() and audio_path.stat().st_size > 0:
            logger.info(f"Audio exists for scene {scene.scene_id}, skipping")
            artifact_paths.append(str(audio_path))
            continue

        # Rate-limit: wait between TTS requests to avoid 429s (10 req/min limit)
        if artifact_paths:
            logger.info("Waiting 12s between TTS requests to avoid rate limits (10 RPM)...")
            time.sleep(12)

        logger.info(f"Generating TTS for scene {scene.scene_id} ({scene.mood})...")

        result = generate_audio(
            text=scene.dialogue,
            output_path=str(audio_path),
            voice=None,  # Use default Gemini voice
            mood=scene.mood,
        )

        if result:
            artifact_paths.append(str(audio_path))
            logger.info(f"Audio saved: {audio_path.name}")
        else:
            logger.warning(f"TTS failed for scene {scene.scene_id}")

    if not artifact_paths:
        raise RuntimeError("No audio files were generated")

    return StepResult(artifact_paths=artifact_paths)
