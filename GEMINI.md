# StudioZero: AI Video Generation Pipeline

StudioZero is an automated system for creating vertical (9:16) social media videos (TikTok/Reels/Shorts). It features three distinct pipelines:
- **Movie Mode**: Generates narrative recaps using LLM scripts, Gemini TTS, Pexels stock footage, and FFmpeg rendering with audio ducking and a poster reveal ending.
- **Animated Mode**: Creates episodic parodies using household items as characters, powered by Vertex AI Veo 3.1 for video/audio/lip-sync generation.
- **Animation Series Mode**: Multi-episode series with consistent characters and project persistence.

## Foundational Mandates

- **Safety First**: Never log or commit API keys (`GEMINI_API_KEY`, `GROQ_API_KEY`, etc.). All secrets must remain in `.env`.
- **Vertical-First**: All assets, prompts, and rendering logic must target a 1080x1920 (9:16) aspect ratio.
- **Resilience**: Maintain the "fallback chain" pattern (e.g., Wikipedia -> TMDB, Gemini -> Groq, Pexels -> local assets, TTS -> silent WAV).
- **Non-Breaking Changes**: Ensure modifications to one pipeline do not break the shared infrastructure used by the others.
- **Validation**: Use Pydantic v2 models for all structured data exchange between LLMs and the pipeline.
- **Consistency**: Maintain character visual consistency in animation series via shared reference blueprints.

## Core Workflows

### Execution
- **Single Movie**: `python -m src.app "Movie Name"`
- **Animated Parody**: `python -m src.app "Theme" --mode animated`
- **Animation Series (Script)**: `python -m src.app "Title" --mode animation-script --storyline "..."`
- **Animation Series (Render)**: `python -m src.app "Title" --mode animation-render --episode-num 1`
- **Batch Processing**: `python -m src.batch_runner` (requires Google Sheets setup)
- **Offline Mode**: `python -m src.app "Movie" --offline` (uses `pipeline_cache.json`)

### Development & Extension
- **Adding Voices**: Update `VOICE_MAP` in `src/config_mappings.py`.
- **Adding Music**: Add folders to `assets/music/<genre>/` and update `MUSIC_GENRE_MAP` in `src/config_mappings.py`.
- **Modifying Prompts**: Centralized in `src/narrative.py` (`_SYSTEM_PROMPT` for Movie, `_ANTHROPOMORPHIC_SYSTEM_PROMPT` for Animated/Series).
- **FFmpeg Changes**: Primary logic resides in `src/renderer.py`.

## Architectural Map

- `src/app.py`: CLI Entry point and argument parsing.
- `src/pipeline.py`: Orchestration engine using the **Generator Pattern** to yield `PipelineStatus`.
- `src/animation_manager.py`: Project persistence and episode tracking.
- `src/narrative.py`: Structured LLM script generation and character blueprinting.
- `src/veo_client.py`: Integration with Vertex AI Veo 3.1 for animated video generation.
- `src/renderer.py`: FFmpeg-based composition, audio ducking, clip assembly, and Ken Burns effects.
- `src/gemini_tts.py`: Gemini-powered Text-to-Speech with mood-based pacing.
- `src/subtitles.py`: Generation of Hormozi-style (karaoke) ASS subtitles.
- `src/config.py`: Centralized environment and path management.

## Technical Standards

- **Python Version**: 3.10+ with strict type hinting.
- **Error Handling**: Use `tenacity` for exponential backoff on all API calls.
- **Concurrency**: Use `ThreadPoolExecutor` for parallel asset generation (TTS + Stock Video).
- **Logging**: Use `src/logging_utils.py`; initialize with `logging.getLogger(__name__)`.
- **Data Validation**: Pydantic v2 is mandatory for script models.
- **FFmpeg**: Must support `libx264` and `libass`.

## External Dependencies

- **LLM/TTS**: Google Gemini 2.0/2.5 Flash, Groq LLaMA 3.3 (fallback).
- **Video Gen**: Vertex AI Veo 3.1.
- **Data**: Wikipedia API, TMDB v3 API.
- **Media**: Pexels API (Stock Video).
- **Transcription**: Local OpenAI Whisper (`base` model).
- **Cloud**: Google Drive & Sheets APIs for batch automation.
