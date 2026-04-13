# CLAUDE.md — StudioZero Development Guide

## Build & Run Commands
- **Main Entry**: `python -m src.app` (Choose CLI Wizard or Web Dashboard)
- **Direct CLI Wizard**: `python -m src.cli`
- **FastAPI Dashboard**: `uvicorn src.server:app --port 8910 --reload`
- **Batch Processor**: `python -m src.batch_runner`
- **Dependencies**: `pip install -r requirements.txt`
- **Type Checking**: `mypy .` (if configured)
- **Linting**: `ruff check .` (if configured)

## Operational Routes
1. **Stock Footage**: Narrative recap using LLM script + Gemini TTS + Pexels video + sidechain ducking.
   - Sub-routes: **User Entry** (manual) or **Sheet Automated** (Google Sheets).
   - Features: `validate_input` logic for garbage detection and random story fallback.
2. **Animation**: 7-step modular series pipeline using Vertex AI Veo 3.1.
   - Pre-Production (once): Writer → Screenwriter → Casting → World Builder.
   - Production (per episode): Director → Scene Generator → Editor.
   - Persistence: State stored in `pipeline_state.json` per project.

## Code Style & Standards
- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes.
- **Typing**: Use strict type hints for all function signatures.
- **Validation**: Pydantic v2 is mandatory for all JSON data exchange.
- **Persistence**: Use the `PipelineStatus` generator pattern for all long-running processes.
- **Error Handling**: Use `tenacity` for API retries and `logging.getLogger(__name__)` for logs.
- **FFmpeg**: Use `subprocess` or `ffmpeg-python` wrapper; prioritize sidechain compression for audio.

## Architectural Notes
- `src/app.py`: Interface switcher (CLI vs Web).
- `src/cli.py`: Interactive wizard logic with retry gate for Veo failures.
- `src/server.py`: FastAPI backend with WebSocket streaming.
- `src/narrative.py`: Primary LLM logic including random story generation.
- `src/pipeline.py`: Stock footage orchestration.
- `src/animation_pipeline.py`: 7-step animation orchestrator.
- `src/pipeline_state.py`: Crash-resilient state persistence.
- `src/steps/`: Modular steps for the animation series (writer, screenwriter, casting, world_builder, director, scene_generator, editor).
- `src/project_manager.py`: Project CRUD for the web dashboard.
- `src/veo_client.py`: Vertex AI Veo 3.1 integration (2 RPM rate limit).
- `src/config_mappings.py`: Music/voice/mood lookup tables.
