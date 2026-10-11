# CLAUDE.md — StudioZero Development Guide

> Part of the StudioZero studio: this is the **story engine** (`engines/story`). Run every command from this folder. Retired in October 2026: the Google Sheets batch runner, Drive/iCloud upload, Groq captions, the app launcher, Cloud Run, StudioZero.app and the legacy Vertex client. Studio rules (public repository, no paid generation without the owner's OK): `../../AGENTS.md`.

## Build & Run Commands
- **Direct CLI Wizard**: `python -m src.cli`
- **FastAPI Dashboard**: `uvicorn src.server:app --port 8910 --reload`
- **Model Comparison**: `python -m src.tools.model_compare --prompt "..." --models kling-2.5-turbo-pro,seedance-2.0-fast`
- **Dependencies**: `pip install -r requirements.txt`
- **Type Checking**: `mypy .` (if configured)
- **Linting**: `ruff check .` (if configured)

## Operational Routes
1. **Stock Footage**: Narrative recap using LLM script + Gemini TTS + Pexels video + sidechain ducking.
   - Starts from a typed movie name or story idea.
   - Features: `validate_input` logic for garbage detection and random story fallback.
2. **Animation**: 8-step modular series pipeline with multi-model video generation.
   - Pre-Production (once): Writer → Screenwriter → Casting → World Builder.
   - Production (per episode): Director → Set Designer → Scene Generator → Editor.
   - Persistence: State stored in `pipeline_state.json` per project.
   - **Video Models**: Supports 11 models across 3 tiers (Budget/Recommended/Premium) via Gemini API (Veo 3.1 Lite/Fast/Standard) and fal.ai (Kling, Seedance, Wan, Sora). Model selection in Settings panel. Budget guard auto-downgrades when cost limits are reached.

## Code Style & Standards
- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes.
- **Typing**: Use strict type hints for all function signatures.
- **Validation**: Pydantic v2 is mandatory for all JSON data exchange.
- **Persistence**: Use the `PipelineStatus` generator pattern for all long-running processes.
- **Error Handling**: Use `tenacity` for API retries and `logging.getLogger(__name__)` for logs.
- **FFmpeg**: Use `subprocess` or `ffmpeg-python` wrapper; prioritize sidechain compression for audio.

## Architectural Notes
- `src/cli.py`: Interactive wizard logic with retry gate for Veo failures.
- `src/server.py`: FastAPI backend with WebSocket streaming.
- `src/narrative.py`: Primary LLM logic including random story generation.
- `src/pipeline.py`: Stock footage orchestration.
- `src/animation_pipeline.py`: 8-step animation orchestrator.
- `src/pipeline_state.py`: Crash-resilient state persistence.
- `src/steps/`: Modular steps for the animation series (writer, screenwriter, casting, world_builder, director, set_designer, scene_generator, editor).
- `src/project_manager.py`: Project CRUD for the web dashboard.
- `src/video_models.py`: Central registry of all 11 supported video generation models (Gemini API + fal.ai).
- `src/video_client.py`: Unified client routing to Gemini API, fal.ai, or Vertex AI. Handles retries, cost tracking, model fallback.
- `src/budget_guard.py`: Per-project budget enforcement with auto-downgrade to cheaper models.
- `src/tools/model_compare.py`: CLI utility to compare video outputs across models. Generates HTML report.
- `src/config_mappings.py`: Music/voice/mood lookup tables.
