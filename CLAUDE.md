# CLAUDE.md - Project Context for Claude Code

## What is StudioZero?

StudioZero is an AI-powered automated video generation system that creates short, vertical (9:16) social media videos from movie titles. Input a movie name and the system produces a complete narrative video with voiceover, stock footage, animated captions, and background music.

**Target platforms**: TikTok, Instagram Reels, YouTube Shorts.

## Quick Reference

```
# Run single video generation
python -m src.app "Movie Name"
python -m src.app "Movie Name" --verbose
python -m src.app "Movie Name" --assets-only
python -m src.app "Movie Name" --offline

# Run batch processing from Google Sheet
python -m src.batch_runner
python -m src.batch_runner --limit 5 --verbose
```

## Architecture Overview

The system follows a 5-step generator-based pipeline defined in `src/pipeline.py`:

```
Movie Name → [Step 1] Fetch Data & Generate Script
           → [Step 2] Parallel TTS Audio + Stock Video Download
           → [Step 3] Whisper Transcription (word-level timestamps)
           → [Step 4] ASS Subtitle Generation (Hormozi-style)
           → [Step 5] FFmpeg Video Rendering with Audio Ducking
           → output/final/<movie>.mp4
```

## Project Structure

```
src/
├── app.py              # CLI entry point - argument parsing, orchestrates pipeline
├── pipeline.py         # Core 5-step orchestration engine (generator yielding PipelineStatus)
├── narrative.py        # LLM script generation (Gemini primary, Groq fallback)
├── moviedbapi.py       # Wikipedia + TMDB movie data fetching
├── gemini_tts.py       # Google Gemini TTS - 30 voices, mood-based style prompts
├── stock_media.py      # Pexels API stock video download with 3-query fallback
├── subtitles.py        # ASS subtitle generation - word-by-word Hormozi-style captions
├── renderer.py         # FFmpeg video composition - concat, ducking, subtitle burn
├── config.py           # Environment variables, path management, directory setup
├── config_mappings.py  # Voice metadata, music-genre mapping, mood-speed mapping
├── batch_runner.py     # Batch processing from Google Sheets queue
├── cloud_services.py   # Google Drive/Sheets integration (service account auth)
├── marketing.py        # Social media caption generation via Groq LLM
└── logging_utils.py    # Centralized logging configuration

assets/
├── basevideos/         # 24 fallback .mp4 clips (used when Pexels fails)
├── music/              # Background tracks organized by genre (17 genres)
└── creds/              # Google service account JSON credentials

output/
├── temp/<movie>/       # Intermediate files (scene audio, video, cache, subtitles)
├── final/              # Completed .mp4 videos
└── pipeline_logs/      # Script generation logs (JSON)
```

## Key Data Models (in narrative.py)

```python
VideoScript(BaseModel):
    title: str
    genre: str
    overall_mood: str
    selected_voice_id: str      # One of 30 Gemini voices
    selected_music_file: str    # Genre-matched from assets/music/
    lang_code: str              # a=American, b=British
    bpm: int                    # 60-200, estimated video tempo
    scenes: List[Scene]         # Exactly 6 scenes

Scene(BaseModel):
    scene_index: int            # 0-5
    narration: str              # 25-40 words, conversational
    visual_queries: List[str]   # 3 Pexels search queries
    visual_style_modifiers: List[str]
    mood: str                   # tense, dramatic, happy, etc.
    tts_speed: float            # 1.0-1.6
```

## External Services & APIs

| Service | Used For | Module | Auth |
|---------|----------|--------|------|
| Google Gemini | Script generation (primary LLM) + TTS | narrative.py, gemini_tts.py | GEMINI_API_KEY |
| Groq LLaMA | Script fallback + caption generation | narrative.py, marketing.py | GROQ_API_KEY |
| Pexels | Stock video download | stock_media.py | PEXELS_API_KEY |
| TMDB | Movie metadata + poster | moviedbapi.py | TMDB_API_KEY |
| Wikipedia | Movie plot (primary source) | moviedbapi.py | None |
| OpenAI Whisper | Audio transcription (local model) | pipeline.py | None (local) |
| Google Drive | Video/log uploads | cloud_services.py | Service account |
| Google Sheets | Batch job queue | cloud_services.py | Service account |

## Configuration

All config lives in `.env` (see `.env.template`). Key variables:
- `GEMINI_API_KEY` - Primary LLM + TTS
- `GROQ_API_KEY` - Fallback LLM + captions
- `PEXELS_API_KEY` - Stock video
- `TMDB_API_KEY` - Movie data
- `DRIVE_APPLICATION_CREDENTIALS` - Google service account JSON path
- `BATCH_SHEET_URL` - Google Sheet queue URL
- `DRIVE_VIDEO_FOLDER_ID` / `DRIVE_LOGS_FOLDER_ID` - Drive upload targets

## Coding Conventions

- **Python 3.10+** with type hints
- **Pydantic v2** for data validation (VideoScript, Scene models)
- **tenacity** for retry logic with exponential backoff
- **Threading** via `ThreadPoolExecutor` for parallel scene processing
- **Generator pattern** for pipeline progress reporting (`yield PipelineStatus(...)`)
- **Fallback chains** everywhere: Wikipedia→TMDB, Gemini→Groq, Pexels→Local videos, TTS→Silent audio
- **Logging** via `logging_utils.py` - use `logging.getLogger(__name__)` in each module
- All paths managed through `config.py` constants (ASSETS_DIR, OUTPUT_DIR, TEMP_DIR, etc.)

## Important Implementation Details

- Videos are 1080x1920 (9:16 portrait), 30fps, H.264 + AAC 192kbps
- TTS outputs WAV at 24kHz mono
- Subtitles use ASS format with 80pt Arial Black, white text, black outline
- Audio ducking uses sidechain compression (threshold=0.1, ratio=10:1, attack=50ms, release=200ms)
- Scene 6 (index 5) is always the ending scene with movie poster + title reveal
- Pipeline cache stored at `output/temp/<movie>/pipeline_cache.json` for offline re-runs
- All TTS speeds are boosted 25% for social media pacing
- The batch runner marks rows in Google Sheets as Processing→Completed/Failed

## Common Tasks

**Adding a new voice**: Update `VOICE_MAP` and `VOICE_CHARACTERISTICS` in `config_mappings.py`, then add to the system prompt in `narrative.py`.

**Adding a new music genre**: Create folder in `assets/music/<genre>/`, add mapping in `config_mappings.py` `MUSIC_GENRE_MAP`.

**Changing subtitle style**: Modify `HORMOZI_STYLE` dict in `subtitles.py`.

**Modifying the narrative prompt**: Edit the system prompt string in `narrative.py` `generate_script()`.

**Adding a new pipeline step**: Add to the generator in `pipeline.py` `run_pipeline()`, yield `PipelineStatus` updates.

## Dependencies

Key packages: `google-genai`, `groq`, `ffmpeg-python`, `openai-whisper`, `pydantic`, `pysubs2`, `tenacity`, `python-dotenv`, `gspread`, `google-api-python-client`, `Wikipedia-API`, `requests`.

Full list in `requirements.txt`.
