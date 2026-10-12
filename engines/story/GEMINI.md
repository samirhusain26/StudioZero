# StudioZero: AI Video Generation Pipeline

> Part of the StudioZero studio: this is the **story engine** (`engines/story`). Run every command from this folder. Retired in October 2026: the Google Sheets batch runner, Drive/iCloud upload, Groq captions, the app launcher, Cloud Run, StudioZero.app and the legacy Vertex client. Studio rules (public repository, no paid generation without the owner's OK): `../../AGENTS.md`.

StudioZero is an automated system for creating vertical (9:16) social media videos. It features two core production routes:
- **Stock Footage Route**: Narrative recaps using LLM scripts, Gemini TTS, Pexels stock footage, and FFmpeg rendering with audio ducking. Includes "Sheet Automated" and "User Entry" modes.
- **Animation Series Route**: A production-grade 8-step modular pipeline for multi-episode series with consistent characters, persistent state tracking, and multi-model video generation (10 verified models across 3 tiers via the Gemini API and fal.ai).

## Foundational Mandates

- **Safety First**: Never log or commit API keys (`GEMINI_API_KEY`, etc.). All secrets must remain in `.env`.
- **Vertical-First**: All assets, prompts, and rendering logic must target a 1080x1920 (9:16) aspect ratio.
- **Resilience**: Maintain the "fallback chain" pattern (e.g., Wikipedia -> TMDB, Gemini -> Groq, Pexels -> local assets).
- **Validation**: Use Pydantic v2 models for all structured data exchange between LLMs and the pipeline.
- **Input Integrity**: Use the `validate_input` logic to detect garbage text and trigger random story generation if needed.
- **Consistency**: Maintain character visual consistency in animation via shared reference blueprints and world bibles.

## Core Workflows

### Execution
- **Main Entry**: `python -m src.cli` (from engines/story).
- **Story worker agent**: `python -m src.agent` serves the Pi UI's Studio › Story jobs (see `docs/HEADLESS.md`).

### Development & Extension
- **Adding Voices**: Update `VOICE_MAP` in `src/config_mappings.py`.
- **Modifying Prompts**: Centralized in `src/narrative.py` and modular steps in `src/steps/`.
- **FFmpeg Changes**: Primary logic resides in `src/renderer.py` and `src/steps/editor.py`.

## Architectural Map

- `src/cli.py`: The interactive CLI wizard implementing the two-route flow.
- `src/agent.py`: Story worker agent (FastAPI) behind the Pi's studio proxy.
- `src/pipeline.py`: Orchestration engine for the Stock Footage route.
- `src/animation_pipeline.py`: Orchestrator for the 8-step Animation series.
- `src/steps/`: Modular steps for the Animation series (writer, screenwriter, casting, world_builder, director, set_designer, scene_generator, editor).
- `src/video_models.py`: Central registry of all 11 supported video generation models (Gemini API + fal.ai).
- `src/video_client.py`: Unified client routing to the Gemini API (Veo) or fal.ai; only models with a `verified` record in registry.json are called. Handles retries, uncertain submits, cost tracking, price-ordered fallback.
- `src/budget_guard.py`: Per-project budget enforcement with auto-downgrade to cheaper models.
- `src/pricing.py`: list prices (with sources) for Gemini/Groq text, image and TTS calls; charges every call into the active `spend_ledger.json`.
- `src/music.py`: recap background music: a CC0 track from the motion engine's music catalog (licence recorded), or none.
- `src/status.py`: `PipelineStatus`, shared by both routes.
- `fonts/`: the OFL caption font (Fraunces Black) and its licence.
- `src/tools/model_compare.py`: CLI utility to compare video outputs across models.
- `src/narrative.py`: Script generation, input validation, and random story logic.
- `src/renderer.py`: FFmpeg-based composition and audio ducking.
- `src/gemini_tts.py`: Gemini-powered Text-to-Speech.
- `src/subtitles.py`: Hormozi-style (karaoke) ASS subtitles.
- `src/config.py`: Centralized environment and path management.

## Technical Standards

- **Python Version**: 3.10+ with strict type hinting.
- **Error Handling**: Use `tenacity` for exponential backoff on all API calls.
- **Concurrency**: Use `ThreadPoolExecutor` for parallel asset generation in the stock route.
- **Logging**: Use `src/logging_utils.py`; initialize with `logging.getLogger(__name__)`.
- **Data Validation**: Pydantic v2 is mandatory for script models.
- **FFmpeg**: Must support `libx264` and `libass`.
