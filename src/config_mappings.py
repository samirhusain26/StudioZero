"""Centralized asset mappings for StudioZero.

Voice IDs are mapped to Gemini TTS voices in gemini_tts.py.
"""

import os
import random
from pathlib import Path


# Music files mapped to genres (same file can appear in multiple genres)
MUSIC_GENRES = {
    'action': [
        'epic-cinematic-background-music-456462.mp3',
        'epic-cinematic-music-398309.mp3',
        'epic-cinematic-music-466452.mp3',
        'serious-dramatic-intense-music-338204.mp3',
        'risk-136788.mp3',
    ],
    'thriller': [
        'cinematic-dark-mysterious-music-412770.mp3',
        'mysterious-cinematic-music-412769.mp3',
        'serious-dramatic-intense-music-338204.mp3',
        'risk-136788.mp3',
    ],
    'horror': [
        'horror-scary-music-376357.mp3',
        'spooky-horror-461470.mp3',
        'cinematic-dark-mysterious-music-412770.mp3',
        'mysterious-cinematic-music-412769.mp3',
    ],
    'comedy': [
        'funny-comedy-cartoon-background-music-340853.mp3',
    ],
    'romance': [
        'love-romantic-music-412707.mp3',
        'romantic-454545.mp3',
        'romantic-piano-431010.mp3',
        'romantic-saxophone-244539.mp3',
    ],
    'drama': [
        'dramatic-sad-documentary-music-2-min-391488.mp3',
        'sad-dramatic-music-414118.mp3',
        'serious-dramatic-intense-music-338204.mp3',
        'victorian-period-drama-375850.mp3',
    ],
    'documentary': [
        'dramatic-sad-documentary-music-2-min-391488.mp3',
        'history-historical-music-261143.mp3',
        'history-historical-music-442837.mp3',
    ],
    'sci-fi': [
        'mysterious-cinematic-music-412769.mp3',
        'experimental-cinematic-hip-hop-315904.mp3',
        'cinematic-dark-mysterious-music-412770.mp3',
    ],
    'mystery': [
        'mysterious-cinematic-music-412769.mp3',
        'cinematic-dark-mysterious-music-412770.mp3',
    ],
    'adventure': [
        'epic-cinematic-background-music-456462.mp3',
        'epic-cinematic-music-398309.mp3',
        'epic-cinematic-music-466452.mp3',
    ],
    'animation': [
        'funny-comedy-cartoon-background-music-340853.mp3',
    ],
    'war': [
        'epic-cinematic-music-398309.mp3',
        'epic-cinematic-music-466452.mp3',
        'serious-dramatic-intense-music-338204.mp3',
    ],
    'history': [
        'history-historical-music-261143.mp3',
        'history-historical-music-442837.mp3',
        'dramatic-sad-documentary-music-2-min-391488.mp3',
        'victorian-period-drama-375850.mp3',
    ],
    'fantasy': [
        'epic-cinematic-background-music-456462.mp3',
        'epic-cinematic-music-466452.mp3',
        'mysterious-cinematic-music-412769.mp3',
    ],
    'crime': [
        'cinematic-dark-mysterious-music-412770.mp3',
        'mysterious-cinematic-music-412769.mp3',
        'serious-dramatic-intense-music-338204.mp3',
        'risk-136788.mp3',
    ],
    'family': [
        'funny-comedy-cartoon-background-music-340853.mp3',
        'romantic-piano-431010.mp3',
    ],
    'western': [
        'epic-cinematic-music-398309.mp3',
        'serious-dramatic-intense-music-338204.mp3',
    ],
    'musical': [
        'romantic-saxophone-244539.mp3',
        'romantic-piano-431010.mp3',
        'romantic-454545.mp3',
    ],
    'sport': [
        'epic-cinematic-background-music-456462.mp3',
        'epic-cinematic-music-398309.mp3',
        'serious-dramatic-intense-music-338204.mp3',
    ],
    'biographical': [
        'history-historical-music-261143.mp3',
        'history-historical-music-442837.mp3',
        'dramatic-sad-documentary-music-2-min-391488.mp3',
        'victorian-period-drama-375850.mp3',
    ],
    'period': [
        'victorian-period-drama-375850.mp3',
        'history-historical-music-261143.mp3',
        'history-historical-music-442837.mp3',
    ],
}


# Language codes for TTS (kept for compatibility, Gemini uses English voices)
LANG_CODES = {
    'a': 'American English',
    'b': 'British English',
}


# Voice metadata - these IDs map to Gemini TTS voices in gemini_tts.py
# Mapping: af_bella->Kore, af_sarah->Puck, af_nicole->Charon, af_heart->Aoede,
#          af_sky->Leda, am_adam->Orus, am_michael->Zephyr, bf_emma->Kore,
#          bf_isabella->Aoede, bm_george->Charon, bm_lewis->Zephyr
# All speed_range values increased by 25% for faster social media pacing
TTS_VOICES = {
    # American Female voices (lang_code='a')
    'af_bella': {
        'description': "Soft, Emotional, Intimate",
        'lang_code': 'a',
        'speed_range': (1.05, 1.25),  # Slower for emotional delivery
        'best_for': ['romance', 'drama', 'family'],
        'tone': 'warm',
    },
    'af_sarah': {
        'description': "Energetic, Happy, Upbeat",
        'lang_code': 'a',
        'speed_range': (1.25, 1.45),  # Faster for energy
        'best_for': ['comedy', 'animation', 'family', 'musical'],
        'tone': 'bright',
    },
    'af_nicole': {
        'description': "Whispered, Mysterious, Breathy",
        'lang_code': 'a',
        'speed_range': (1.0, 1.2),  # Slow for suspense
        'best_for': ['horror', 'mystery', 'thriller', 'sci-fi'],
        'tone': 'dark',
    },
    'af_heart': {
        'description': "Warm, Conversational, Friendly",
        'lang_code': 'a',
        'speed_range': (1.2, 1.4),
        'best_for': ['documentary', 'biographical', 'family'],
        'tone': 'neutral',
    },
    'af_sky': {
        'description': "Youthful, Dreamy, Ethereal",
        'lang_code': 'a',
        'speed_range': (1.15, 1.3),
        'best_for': ['fantasy', 'romance', 'animation'],
        'tone': 'light',
    },
    # American Male voices (lang_code='a')
    'am_adam': {
        'description': "Deep, Authoritative, Commanding",
        'lang_code': 'a',
        'speed_range': (1.15, 1.4),
        'best_for': ['action', 'thriller', 'war', 'western', 'crime', 'sport'],
        'tone': 'intense',
    },
    'am_michael': {
        'description': "Casual, Conversational, Relatable",
        'lang_code': 'a',
        'speed_range': (1.2, 1.4),
        'best_for': ['comedy', 'documentary', 'biographical'],
        'tone': 'neutral',
    },
    # British Female voices (lang_code='b')
    'bf_emma': {
        'description': "Elegant, Formal, Refined",
        'lang_code': 'b',
        'speed_range': (1.05, 1.25),
        'best_for': ['drama', 'period', 'fantasy', 'history'],
        'tone': 'refined',
    },
    'bf_isabella': {
        'description': "Sophisticated, Articulate, Warm",
        'lang_code': 'b',
        'speed_range': (1.15, 1.3),
        'best_for': ['romance', 'drama', 'documentary'],
        'tone': 'warm',
    },
    # British Male voices (lang_code='b')
    'bm_george': {
        'description': "Academic, Authoritative, Scholarly",
        'lang_code': 'b',
        'speed_range': (1.05, 1.25),
        'best_for': ['documentary', 'history', 'biographical', 'sci-fi'],
        'tone': 'intellectual',
    },
    'bm_lewis': {
        'description': "Warm, Narrative, Storytelling",
        'lang_code': 'b',
        'speed_range': (1.15, 1.3),
        'best_for': ['fantasy', 'adventure', 'history', 'period'],
        'tone': 'narrative',
    },
}


# Speed presets for different emotional contexts (kept for API compatibility)
# All speeds increased by 25% for faster social media pacing
SPEED_PRESETS = {
    'dramatic_slow': 1.0,      # Emotional reveals, deaths, twists
    'contemplative': 1.05,     # Introspective moments, setup
    'normal': 1.25,            # Standard narration
    'energetic': 1.4,          # Action sequences, excitement
    'urgent': 1.45,            # Chase scenes, tension peaks
    'frantic': 1.5,            # Climax moments, panic
}


# Scene mood to speed mapping (helps Groq select appropriate speed)
# All speeds increased by 25% for faster social media pacing
SCENE_MOOD_SPEEDS = {
    'tense': 1.4,
    'suspenseful': 1.15,
    'dramatic': 1.05,
    'sad': 1.0,
    'happy': 1.3,
    'exciting': 1.45,
    'calm': 1.2,
    'mysterious': 1.05,
    'romantic': 1.15,
    'action': 1.4,
    'horror': 1.05,
    'comedic': 1.4,
    'epic': 1.2,
    'neutral': 1.25,
}


def get_available_music() -> list[str]:
    """Scan assets/music/ directory for .mp3 files.

    Returns:
        List of mp3 filenames, or a default placeholder if folder is empty.
    """
    music_dir = Path(__file__).parent.parent / "assets" / "music"

    if not music_dir.exists():
        return ["default_music.mp3"]

    mp3_files = [f.name for f in music_dir.iterdir() if f.suffix.lower() == ".mp3"]

    if not mp3_files:
        return ["default_music.mp3"]

    return sorted(mp3_files)


def get_voice_for_genre(genre: str) -> str:
    """Get the best matching voice ID for a given genre.

    Args:
        genre: A genre string (e.g., "Action", "Comedy", "Horror").

    Returns:
        The best matching voice ID, or 'am_adam' as default.
    """
    genre_lower = genre.lower()

    # Direct mapping for all MUSIC_GENRES keys
    genre_to_voice = {
        # Action/Adventure voices - Deep, authoritative male
        'action': 'am_adam',
        'thriller': 'am_adam',
        'adventure': 'am_adam',
        'war': 'am_adam',
        'western': 'am_adam',
        'sport': 'am_adam',
        'crime': 'am_adam',
        # Horror/Mystery voices - Whispered, mysterious female
        'horror': 'af_nicole',
        'mystery': 'af_nicole',
        'sci-fi': 'af_nicole',
        # Comedy/Family voices - Energetic, happy female
        'comedy': 'af_sarah',
        'animation': 'af_sarah',
        'family': 'af_sarah',
        'musical': 'af_sarah',
        # Romance voices - Soft, emotional female
        'romance': 'af_bella',
        # Drama voices - Elegant, formal British female
        'drama': 'bf_emma',
        'period': 'bf_emma',
        'fantasy': 'bf_emma',
        # Documentary/History voices - Academic British male
        'documentary': 'bm_george',
        'history': 'bm_george',
        'biographical': 'bm_george',
    }

    # Direct match
    if genre_lower in genre_to_voice:
        return genre_to_voice[genre_lower]

    # Keyword search for partial matches
    for keyword, voice_id in genre_to_voice.items():
        if keyword in genre_lower or genre_lower in keyword:
            return voice_id

    return 'am_adam'


def get_voice_metadata(voice_id: str) -> dict:
    """Get full metadata for a TTS voice.

    Args:
        voice_id: The voice ID (e.g., 'af_bella', 'am_adam').

    Returns:
        Dict with description, lang_code, speed_range, best_for, tone.
        Returns default metadata if voice not found.
    """
    return TTS_VOICES.get(voice_id, {
        'description': 'Unknown voice',
        'lang_code': 'a',
        'speed_range': (0.9, 1.1),
        'best_for': [],
        'tone': 'neutral',
    })


def get_lang_code_for_voice(voice_id: str) -> str:
    """Get the language code for a voice ID.

    The language code should match the voice prefix for optimal pronunciation.

    Args:
        voice_id: The voice ID (e.g., 'af_bella' -> 'a', 'bf_emma' -> 'b').

    Returns:
        Single character language code.
    """
    metadata = get_voice_metadata(voice_id)
    return metadata.get('lang_code', 'a')


def get_speed_for_mood(mood: str) -> float:
    """Get recommended TTS speed for a scene mood.

    Args:
        mood: The mood/emotion of the scene (e.g., 'tense', 'dramatic', 'happy').

    Returns:
        Speed multiplier (0.8 - 1.2 typical range).
    """
    return SCENE_MOOD_SPEEDS.get(mood.lower(), 1.0)


def get_voice_speed_range(voice_id: str) -> tuple[float, float]:
    """Get the recommended speed range for a voice.

    Args:
        voice_id: The voice ID.

    Returns:
        Tuple of (min_speed, max_speed).
    """
    metadata = get_voice_metadata(voice_id)
    return metadata.get('speed_range', (0.9, 1.1))


def clamp_speed_for_voice(voice_id: str, desired_speed: float) -> float:
    """Clamp a speed value to the recommended range for a voice.

    Args:
        voice_id: The voice ID.
        desired_speed: The desired speed multiplier.

    Returns:
        Speed clamped to the voice's recommended range.
    """
    min_speed, max_speed = get_voice_speed_range(voice_id)
    return max(min_speed, min(max_speed, desired_speed))


def get_available_voices_for_groq() -> str:
    """Get a formatted string of available voices for the Groq prompt.

    Returns:
        Formatted multi-line string describing available voices.
    """
    lines = []
    for voice_id, meta in TTS_VOICES.items():
        lang = LANG_CODES.get(meta['lang_code'], 'Unknown')
        lines.append(
            f"  - '{voice_id}': {meta['description']} ({lang}) - Best for: {', '.join(meta['best_for'])}"
        )
    return '\n'.join(lines)


def get_music_for_genre(genre: str) -> str:
    """Get a random music file matching the given genre.

    Args:
        genre: A genre string (e.g., "Action", "Comedy", "Horror").

    Returns:
        A music filename from the matching genre, or a random track as fallback.
    """
    genre_lower = genre.lower()

    # Direct match
    if genre_lower in MUSIC_GENRES:
        return random.choice(MUSIC_GENRES[genre_lower])

    # Partial match (e.g., "science fiction" matches "sci-fi")
    genre_aliases = {
        'science fiction': 'sci-fi',
        'scifi': 'sci-fi',
        'romantic': 'romance',
        'historical': 'history',
        'biography': 'biographical',
        'biopic': 'biographical',
        'animated': 'animation',
        'cartoon': 'animation',
        'scary': 'horror',
        'suspense': 'thriller',
        'sports': 'sport',
        'period piece': 'period',
        'period drama': 'period',
    }

    if genre_lower in genre_aliases:
        return random.choice(MUSIC_GENRES[genre_aliases[genre_lower]])

    # Keyword search in genre keys
    for key in MUSIC_GENRES:
        if key in genre_lower or genre_lower in key:
            return random.choice(MUSIC_GENRES[key])

    # Fallback: return a random cinematic track
    fallback = get_available_music()
    return random.choice(fallback)
