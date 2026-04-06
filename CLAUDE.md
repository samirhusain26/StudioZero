# CLAUDE.md - Project Context for Claude Code

## What is StudioZero?

StudioZero is an AI-powered automated video generation system that creates short, vertical (9:16) social media videos. It supports two video types through an interactive wizard:

1. **Movie Recap**: Input a movie name → narrative recap video with voiceover, stock footage, Hormozi-style subtitles, and background music.
2. **Animation**: Input a theme/storyline → AI-generated animated movie via Veo 3.1 (one-shot or multi-episode series).

A separate **batch automation** channel processes jobs from Google Sheets.

## Quick Reference

```bash
# Interactive Wizard (default)
python -m src.cli

# Headless Mode (backwards-compatible)
python -m src.cli --headless "The Matrix"
python -m src.cli --headless "Interstellar" --offline
python -m src.cli --headless "Kitchen Wars" --mode animation-series \
    --storyline "A spatula rebels" --char-desc "Sir Spatula: dented metal" --episodes 3

# Batch Process (Google Sheet automation — separate channel)
python -m src.batch_runner
```

## Architecture Overview

### Entry Points
- **`src/cli.py`** — Main entry point. Dispatches to interactive wizard or headless mode.
- **`src/wizard.py`** — Rich-based interactive wizard with review gates at key decision points.
- **`src/headless.py`** — Non-interactive runner (original CLI behavior, used by batch_runner too).
- **`src/batch_runner.py`** — Standalone Google Sheets batch automation.

### Pipelines
All pipelines use a **Generator Pattern** yielding `PipelineStatus` (with `review_gate` field for wizard pausing).

- **Movie Pipeline** (`pipeline.py`): TMDB data → Script → Parallel TTS + Pexels → Whisper → ASS Subtitles → FFmpeg Render.
- **Animated One-Shot** (`pipeline.py`): Parody Script → Character Blueprints → Veo 3.1 Rendering → FFmpeg Assembly.
- **Animation Series** (`animation_pipeline.py`): 9-step pipeline with crash recovery — World Builder → Character Designer → per-episode (Writer → Storyboard → Voice → Veo → Sound → Editor → Publisher).

## Key Data Models (in narrative.py)

- **VideoScript:** Movie recap metadata and list of 6 scenes.
- **Scene:** Narration, visual queries, mood, and TTS speed per scene.
- **AnthropomorphicScript:** 6-10 scenes of 6-8s each with character IDs and voice profiles.
- **AnimationProject:** Multi-episode "Series Bible" with episode scripts.
- **AnimationEpisode:** A single script in the series.

## Project Structure

```bash
src/
├── cli.py              # Main entry point — wizard or headless dispatch
├── wizard.py           # Interactive stepwise wizard (rich-based)
├── headless.py         # Non-interactive pipeline runner
├── pipeline.py         # Orchestration engine (movie, animated pipelines)
├── animation_pipeline.py # 9-step series pipeline with crash recovery
├── animation_manager.py # State and persistence for multi-episode projects
├── narrative.py        # LLM script and character blueprint generation
├── veo_client.py       # Vertex AI Veo 3.1 client
├── renderer.py         # FFmpeg composition - concat, ducking, subtitles, Ken Burns
├── gemini_tts.py       # Google Gemini TTS - 30 voices, mood-based style
├── config.py           # Environment, path management, Vertex AI config
├── batch_runner.py     # Batch processing from Google Sheets queue (separate channel)
├── cloud_services.py   # Google Drive/Sheets integration
└── marketing.py        # Social media caption generation
```

## Configuration

All config in `.env` (API keys for Gemini, Groq, Pexels, TMDB, Vertex AI). Key paths managed in `src/config.py`.

## Coding Conventions

- **Python 3.10+** with strict type hinting.
- **Pydantic v2** for all data validation models.
- **Rich** for interactive terminal UI (wizard).
- **Tenacity** for API retry logic with exponential backoff.
- **Threading** via `ThreadPoolExecutor` for parallel movie asset generation.
- **Generator pattern** for pipeline progress reporting (`yield PipelineStatus(...)`).
- **Review gates** — `PipelineStatus.review_gate=True` pauses the wizard for user confirmation; headless mode ignores them.
- **FFmpeg Filters:** `sidechaincompress` for ducking, `zoompan` for Ken Burns, `ass` for subtitles.
- Videos: 1080x1920 (9:16 portrait), 30fps, H.264 + AAC.

## Common Tasks

**Adding a voice:** Update `VOICE_MAP` in `src/config_mappings.py` and the system prompt in `src/narrative.py`.

**Changing subtitle style:** Edit `HORMOZI_STYLE` dict in `src/subtitles.py`.

**Modifying the narrative hook:** Edit `_SYSTEM_PROMPT` (movie) or `_ANTHROPOMORPHIC_SYSTEM_PROMPT` (animated/series) in `src/narrative.py`.

**Updating the Veo model:** Change `VEO_MODEL` in `src/veo_client.py`.
