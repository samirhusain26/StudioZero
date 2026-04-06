# CLAUDE.md - Project Context for Claude Code

## What is StudioZero?

StudioZero is an AI-powered automated video generation system that creates short, vertical (9:16) social media videos. It supports three modes:

1. **Movie mode** (default): Input a movie name → narrative recap video with voiceover, stock footage, animated captions, and background music.
2. **Animated mode (One-shot)**: Input a theme → episodic parody featuring household items/food as characters, generated with Gemini Pro + Vertex AI Veo 3.1.
3. **Animation Series mode**: Multi-episode series scripting and rendering with persistent tracking.

## Quick Reference

```bash
# Movie Mode (Default)
python -m src.app "The Matrix"
python -m src.app "Interstellar" --offline  # Use cached data

# Animated Mode (One-Shot)
python -m src.app "Star Wars" --mode animated

# Animation Series (Phase 1: Scripting)
python -m src.app "ProjectName" --mode animation-script --storyline "Story" --episodes 3

# Animation Series (Phase 2: Rendering)
python -m src.app "ProjectName" --mode animation-render --episode-num 1

# Animation Series (9-Step Pipeline — Recommended)
python -m src.app "Kitchen Wars" --mode animation-series --storyline "A spatula rebels against the chef" --char-desc "Sir Spatula: a dented metal spatula; Chef Knife: a gleaming 8-inch blade" --episodes 3
python -m src.app "Kitchen Wars" --mode animation-series --episodes 3  # Resume from last step

# Batch Process (from Google Sheet)
python -m src.batch_runner
```

## Architecture Overview

All pipelines are orchestrated in `src/pipeline.py` using a **Generator Pattern** yielding `PipelineStatus`.

### Key Pipelines
- **Movie Pipeline:** Wikipedia/TMDB data → Script → Parallel TTS + Pexels → Whisper → ASS Subtitles → FFmpeg Render.
- **Animated Mode (One-Shot):** Parody Script → Character Blueprints → Veo 3.1 Scene Rendering → FFmpeg Assembly.
- **Animation Series Pipeline:** `AnimationManager` project management → Phase 1: Scripting → Phase 2: Render individual episodes.

## Key Data Models (in narrative.py)

- **VideoScript:** Movie recap metadata and list of 6 scenes.
- **Scene:** Narration, visual queries, mood, and TTS speed per scene.
- **AnthropomorphicScript:** 6-10 scenes of 6-8s each with character IDs and voice profiles.
- **AnimationProject:** Multi-episode "Series Bible" with episode scripts.
- **AnimationEpisode:** A single script in the series.

## Project Structure

```bash
src/
├── app.py              # CLI entry point (movie|animated|animation-script|animation-render)
├── pipeline.py         # Orchestration engine (movie, animated, series pipelines)
├── animation_manager.py # State and persistence for multi-episode projects
├── narrative.py        # LLM script and character blueprint generation
├── veo_client.py       # Vertex AI Veo 3.1 client
├── renderer.py         # FFmpeg composition - concat, ducking, subtitles, Ken Burns
├── gemini_tts.py       # Google Gemini TTS - 30 voices, mood-based style
├── config.py           # Environment, path management, Vertex AI config
├── batch_runner.py     # Batch processing from Google Sheets queue
├── cloud_services.py   # Google Drive/Sheets integration
└── marketing.py        # Social media caption generation
```

## Configuration

All config in `.env` (API keys for Gemini, Groq, Pexels, TMDB, Vertex AI). Key paths managed in `src/config.py`.

## Coding Conventions

- **Python 3.10+** with strict type hinting.
- **Pydantic v2** for all data validation models.
- **Tenacity** for API retry logic with exponential backoff.
- **Threading** via `ThreadPoolExecutor` for parallel movie asset generation.
- **Generator pattern** for pipeline progress reporting (`yield PipelineStatus(...)`).
- **FFmpeg Filters:** `sidechaincompress` for ducking, `zoompan` for Ken Burns, `ass` for subtitles.
- Videos: 1080x1920 (9:16 portrait), 30fps, H.264 + AAC.

## Common Tasks

**Adding a voice:** Update `VOICE_MAP` in `src/config_mappings.py` and the system prompt in `src/narrative.py`.

**Changing subtitle style:** Edit `HORMOZI_STYLE` dict in `src/subtitles.py`.

**Modifying the narrative hook:** Edit `_SYSTEM_PROMPT` (movie) or `_ANTHROPOMORPHIC_SYSTEM_PROMPT` (animated/series) in `src/narrative.py`.

**Updating the Veo model:** Change `VEO_MODEL` in `src/veo_client.py`.
