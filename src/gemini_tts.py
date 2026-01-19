"""
Gemini TTS module for generating speech audio using Google AI Gemini API.

This module provides text-to-speech functionality using Gemini 2.5 Flash TTS with:
- 30 available voices (male and female)
- Style prompts for tone/mood control via natural language
- Multi-language support

IMPORTANT: Requires GEMINI_API_KEY environment variable.
Get your API key at: https://aistudio.google.com/apikey

Model: gemini-2.5-flash-preview-tts
"""

import logging
import os
import wave
from pathlib import Path
from typing import Tuple, Optional, Dict

from google import genai
from google.genai import types

from src.config import Config

logger = logging.getLogger(__name__)

# All available Gemini TTS voices with gender
# Source: https://ai.google.dev/gemini-api/docs/speech-generation
GEMINI_VOICES = {
    # Female voices
    "Achernar": "Female",
    "Aoede": "Female",
    "Autonoe": "Female",
    "Callirrhoe": "Female",
    "Despina": "Female",
    "Erinome": "Female",
    "Gacrux": "Female",
    "Kore": "Female",
    "Laomedeia": "Female",
    "Leda": "Female",
    "Pulcherrima": "Female",
    "Sulafat": "Female",
    "Vindemiatrix": "Female",
    "Zephyr": "Female",
    # Male voices
    "Achird": "Male",
    "Algenib": "Male",
    "Algieba": "Male",
    "Alnilam": "Male",
    "Charon": "Male",
    "Enceladus": "Male",
    "Fenrir": "Male",
    "Iapetus": "Male",
    "Orus": "Male",
    "Puck": "Male",
    "Rasalgethi": "Male",
    "Sadachbia": "Male",
    "Sadaltager": "Male",
    "Schedar": "Male",
    "Umbriel": "Male",
    "Zubenelgenubi": "Male",
}

# Voice characteristics for better selection
VOICE_CHARACTERISTICS = {
    "Kore": {"tone": "firm", "style": "confident", "best_for": ["drama", "narration"]},
    "Aoede": {"tone": "breezy", "style": "conversational", "best_for": ["casual", "friendly"]},
    "Charon": {"tone": "informative", "style": "calm", "best_for": ["documentary", "educational"]},
    "Puck": {"tone": "upbeat", "style": "energetic", "best_for": ["comedy", "animation"]},
    "Zephyr": {"tone": "bright", "style": "clear", "best_for": ["narration", "storytelling"]},
    "Fenrir": {"tone": "excitable", "style": "dynamic", "best_for": ["action", "excitement"]},
    "Leda": {"tone": "youthful", "style": "fresh", "best_for": ["young", "modern"]},
    "Orus": {"tone": "firm", "style": "authoritative", "best_for": ["serious", "commanding"]},
    "Achernar": {"tone": "warm", "style": "gentle", "best_for": ["romance", "emotional"]},
    "Gacrux": {"tone": "clear", "style": "professional", "best_for": ["news", "formal"]},
}

# Voice mapping from old voice IDs to Gemini voices
VOICE_MAPPING = {
    # American Female voices
    'af_bella': 'Achernar',     # Soft, Emotional -> Warm, gentle female
    'af_sarah': 'Puck',         # Energetic, Happy -> Upbeat (note: Puck is male but energetic)
    'af_nicole': 'Leda',        # Whispered, Mysterious -> Youthful female
    'af_heart': 'Aoede',        # Warm, Conversational -> Breezy female
    'af_sky': 'Zephyr',         # Youthful, Dreamy -> Bright female
    # American Male voices
    'am_adam': 'Orus',          # Deep, Authoritative -> Firm male
    'am_michael': 'Charon',     # Casual, Conversational -> Informative male
    # British Female voices
    'bf_emma': 'Kore',          # Elegant, Formal -> Firm female
    'bf_isabella': 'Gacrux',    # Sophisticated, Warm -> Clear female
    # British Male voices
    'bm_george': 'Charon',      # Academic, Authoritative -> Informative male
    'bm_lewis': 'Fenrir',       # Warm, Narrative -> Excitable male (storytelling)
}

# Default voice for narration
DEFAULT_VOICE = 'Zephyr'

# Mood to style prompt mapping for expressive delivery
MOOD_STYLE_PROMPTS = {
    'tense': 'Speak with tension and urgency in your voice.',
    'suspenseful': 'Narrate with building suspense, slightly slower pace.',
    'dramatic': 'Deliver dramatically with emotional weight and gravitas.',
    'sad': 'Speak with a somber, melancholic, reflective tone.',
    'happy': 'Narrate with warmth, happiness, and a smile in your voice.',
    'exciting': 'Speak with excitement, energy, and enthusiasm.',
    'calm': 'Narrate in a calm, measured, peaceful, soothing tone.',
    'mysterious': 'Speak with an air of mystery and intrigue.',
    'romantic': 'Deliver with warmth, tenderness, and heartfelt emotion.',
    'action': 'Narrate with intensity, drive, and dynamic energy.',
    'horror': 'Speak with dread and unease, building tension and fear.',
    'comedic': 'Deliver with light-hearted amusement and playful wit.',
    'epic': 'Narrate with grandeur, majesty, and awe-inspiring tone.',
    'neutral': 'Narrate clearly, naturally, and professionally.',
}

# Lazy-loaded Gemini client
_gemini_client = None


def _get_client():
    """
    Returns a lazily-initialized Gemini API client.

    Requires GEMINI_API_KEY environment variable.
    """
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY") or Config.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not found. Please set it in your .env file.\n"
                "Get your API key at: https://aistudio.google.com/apikey"
            )
        _gemini_client = genai.Client(api_key=api_key)
        logger.info("Gemini TTS client initialized")
    return _gemini_client


def _map_voice(voice_id: str) -> str:
    """
    Map old voice ID to Gemini voice name.

    Args:
        voice_id: The old voice ID (e.g., 'af_bella') or Gemini voice name

    Returns:
        Gemini voice name (e.g., 'Kore')
    """
    # If it's already a valid Gemini voice, return it
    if voice_id in GEMINI_VOICES:
        return voice_id
    # Map from old voice ID
    return VOICE_MAPPING.get(voice_id, DEFAULT_VOICE)


def _build_style_prompt(mood: Optional[str] = None) -> str:
    """
    Build a style prompt based on mood for expressive delivery.

    Args:
        mood: The mood/emotion for delivery style

    Returns:
        Style instruction string
    """
    if mood and mood.lower() in MOOD_STYLE_PROMPTS:
        return MOOD_STYLE_PROMPTS[mood.lower()]
    return MOOD_STYLE_PROMPTS['neutral']


def _write_wave_file(filename: str, pcm_data: bytes, channels: int = 1,
                     rate: int = 24000, sample_width: int = 2) -> None:
    """
    Write PCM audio data to a WAV file.

    Args:
        filename: Output file path
        pcm_data: Raw PCM audio bytes
        channels: Number of audio channels (default 1 for mono)
        rate: Sample rate in Hz (default 24000)
        sample_width: Bytes per sample (default 2 for 16-bit)
    """
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)


def generate_audio(
    text: str,
    output_path: str,
    voice: str = "af_bella",
    speed: float = 1.0,
    lang_code: Optional[str] = None,
    mood: Optional[str] = None,
) -> Tuple[str, float]:
    """
    Generates speech audio from text using Gemini TTS API.

    Args:
        text: The text to convert to speech.
        output_path: The path where the audio file will be saved.
        voice: The voice to use. Can be old voice ID (mapped) or Gemini voice name.
        speed: Speech speed hint (incorporated into style prompt).
        lang_code: Language code hint (incorporated into style prompt).
        mood: Optional mood for style prompt (e.g., 'dramatic', 'exciting', 'calm').

    Returns:
        Tuple of (output_path, duration_seconds).

    Raises:
        ValueError: If the text is empty.
        RuntimeError: If audio generation fails.
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    # Ensure output path has proper extension
    output_path = str(output_path)
    if not output_path.lower().endswith('.wav'):
        output_path = output_path.rsplit('.', 1)[0] + '.wav' if '.' in output_path else output_path + '.wav'

    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Map voice ID to Gemini voice name
    gemini_voice = _map_voice(voice)

    # Build style prompt based on mood
    style_instruction = _build_style_prompt(mood)

    # Incorporate speed into the style prompt
    if speed < 0.9:
        style_instruction += " Speak slowly and deliberately."
    elif speed > 1.1:
        style_instruction += " Speak at a slightly faster pace."

    # Create the prompt with style instruction
    prompt = f"{style_instruction}\n\n{text}"

    logger.info(f"Generating TTS with Gemini voice '{gemini_voice}' (mood={mood})")
    logger.debug(f"Text: {text[:100]}...")
    logger.debug(f"Style: {style_instruction}")

    try:
        client = _get_client()

        # Generate audio using Gemini TTS
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=gemini_voice,
                        )
                    )
                ),
            )
        )

        # Extract audio data from response
        audio_data = response.candidates[0].content.parts[0].inline_data.data

        # Write to WAV file
        _write_wave_file(output_path, audio_data)

        # Calculate duration (24kHz, 16-bit mono)
        duration_seconds = len(audio_data) / (24000 * 2 * 1)

        logger.info(f"TTS complete: {output_path} ({duration_seconds:.2f}s)")
        return output_path, max(0.1, duration_seconds)

    except Exception as e:
        logger.error(f"Failed to generate audio: {e}")
        raise RuntimeError(f"Failed to generate audio: {e}") from e


def generate_audio_with_metadata(
    text: str,
    output_path: str,
    voice: str = "af_bella",
    speed: float = 1.0,
    mood: Optional[str] = None,
) -> Dict:
    """
    Generate audio with full metadata returned.

    Args:
        text: The text to convert to speech.
        output_path: The path where the audio file will be saved.
        voice: The voice to use.
        speed: Speech speed multiplier.
        mood: Optional mood string for style control.

    Returns:
        Dict with keys: output_path, duration, voice, gemini_voice, mood, speed, text_length.
    """
    gemini_voice = _map_voice(voice)

    final_path, duration = generate_audio(
        text=text,
        output_path=output_path,
        voice=voice,
        speed=speed,
        mood=mood,
    )

    return {
        'output_path': final_path,
        'duration': duration,
        'voice': voice,
        'gemini_voice': gemini_voice,
        'mood': mood,
        'speed': speed,
        'text_length': len(text),
    }


def list_available_voices() -> list:
    """
    Returns a list of available Gemini voice names.

    Returns:
        List of voice name strings.
    """
    return list(GEMINI_VOICES.keys())


def get_voice_info(voice_id: str) -> Dict:
    """
    Get information about a voice.

    Args:
        voice_id: The voice ID (old ID or Gemini voice name).

    Returns:
        Dict with voice information including gender and characteristics.
    """
    gemini_voice = _map_voice(voice_id)
    gender = GEMINI_VOICES.get(gemini_voice, "Unknown")
    characteristics = VOICE_CHARACTERISTICS.get(gemini_voice, {})

    return {
        'voice_id': voice_id,
        'gemini_voice': gemini_voice,
        'gender': gender,
        'tone': characteristics.get('tone', 'neutral'),
        'style': characteristics.get('style', 'standard'),
        'best_for': characteristics.get('best_for', []),
    }


def get_voices_by_gender(gender: str) -> list:
    """
    Get all voices of a specific gender.

    Args:
        gender: 'Male' or 'Female'

    Returns:
        List of voice names matching the gender.
    """
    return [name for name, g in GEMINI_VOICES.items() if g.lower() == gender.lower()]


def get_recommended_voice_for_genre(genre: str) -> str:
    """
    Get a recommended Gemini voice for a genre.

    Args:
        genre: The content genre (e.g., 'action', 'romance', 'documentary')

    Returns:
        Recommended Gemini voice name.
    """
    genre_lower = genre.lower()

    genre_voice_map = {
        # Action/Thriller - authoritative or excitable
        'action': 'Orus',
        'thriller': 'Fenrir',
        'war': 'Orus',
        'crime': 'Charon',
        # Horror/Mystery - atmospheric
        'horror': 'Leda',
        'mystery': 'Charon',
        'sci-fi': 'Charon',
        # Comedy/Animation - upbeat
        'comedy': 'Puck',
        'animation': 'Puck',
        'family': 'Aoede',
        # Romance - warm
        'romance': 'Achernar',
        # Drama - expressive
        'drama': 'Kore',
        'period': 'Gacrux',
        # Documentary - informative
        'documentary': 'Charon',
        'history': 'Charon',
        'biographical': 'Gacrux',
        # Fantasy/Adventure - storytelling
        'fantasy': 'Fenrir',
        'adventure': 'Zephyr',
    }

    return genre_voice_map.get(genre_lower, DEFAULT_VOICE)
