"""
Step 7: Sound Designer — Select and prepare background music.

Input: SeriesBible tone, episode clips for duration reference
Output: Background music track
Persists: project_dir/episodes/episode_N/audio/music.mp3
"""

import logging
import random
import shutil
from pathlib import Path

from src.config import Config
from src.steps import StepContext, StepResult
from src.steps.world_builder import load_bible

logger = logging.getLogger(__name__)

# Tone-to-genre mapping for music selection
_TONE_GENRE_MAP = {
    "dark comedy": "comedy",
    "wholesome": "family",
    "absurdist": "comedy",
    "dramatic": "drama",
    "thriller": "thriller",
    "action": "action",
    "horror": "horror",
    "romantic": "romance",
    "epic": "epic",
    "mystery": "mystery",
}


def run(ctx: StepContext) -> StepResult:
    """Select background music based on series tone."""
    music_path = ctx.episode_dir / "audio" / "music.mp3"
    music_path.parent.mkdir(parents=True, exist_ok=True)

    if music_path.exists() and music_path.stat().st_size > 0:
        logger.info("Background music already selected, skipping")
        return StepResult(artifact_paths=[str(music_path)])

    bible = load_bible(ctx.project_dir)

    # Try to match tone to a genre, then find music files
    from src.config_mappings import MUSIC_GENRES

    tone_lower = bible.tone.lower()
    genre = None
    for keyword, mapped_genre in _TONE_GENRE_MAP.items():
        if keyword in tone_lower:
            genre = mapped_genre
            break

    # Find music tracks for the genre
    music_files = []
    if genre and genre in MUSIC_GENRES:
        music_files = MUSIC_GENRES[genre]

    # Fallback: pick from any available genre
    if not music_files:
        all_tracks = [t for tracks in MUSIC_GENRES.values() for t in tracks]
        if all_tracks:
            music_files = all_tracks

    if not music_files:
        # Last resort: check assets/music directory directly
        music_dir = Config.ASSETS_DIR / "music"
        if music_dir.exists():
            music_files = [f.name for f in music_dir.glob("*.mp3")]

    if not music_files:
        logger.warning("No music files found, skipping background music")
        return StepResult()

    # Pick a random track and copy to episode directory
    selected = random.choice(music_files)
    source = Config.ASSETS_DIR / "music" / selected
    if source.exists():
        shutil.copy2(source, music_path)
        logger.info(f"Background music selected: {selected}")
        return StepResult(artifact_paths=[str(music_path)])

    logger.warning(f"Music file not found: {source}")
    return StepResult()
