# StudioZero: AI Video Generation Pipeline

StudioZero is an automated system for creating vertical (9:16) social media videos. It features two core production routes:
- **Stock Footage Route**: Narrative recaps using LLM scripts, Gemini TTS, Pexels stock footage, and FFmpeg rendering with audio ducking. Includes "Sheet Automated" and "User Entry" modes.
- **Animation Series Route**: A production-grade 7-step modular pipeline for multi-episode series with consistent characters and persistent state tracking.

## Foundational Mandates

- **Safety First**: Never log or commit API keys (`GEMINI_API_KEY`, etc.). All secrets must remain in `.env`.
- **Vertical-First**: All assets, prompts, and rendering logic must target a 1080x1920 (9:16) aspect ratio.
- **Resilience**: Maintain the "fallback chain" pattern (e.g., Wikipedia -> TMDB, Gemini -> Groq, Pexels -> local assets).
- **Validation**: Use Pydantic v2 models for all structured data exchange between LLMs and the pipeline.
- **Input Integrity**: Use the `validate_input` logic to detect garbage text and trigger random story generation if needed.
- **Consistency**: Maintain character visual consistency in animation via shared reference blueprints and world bibles.

## Core Workflows

### Execution
- **Main Entry**: `python -m src.app` (Select CLI Wizard or Web Dashboard).
- **Batch Processing**: Managed via "Stock Footage -> Sheet Automated" in the CLI wizard or `src/batch_runner.py` directly.
- **Web Dashboard**: Access the FastAPI dashboard by choosing Option 2 in the main entry point.

### Development & Extension
- **Adding Voices**: Update `VOICE_MAP` in `src/config_mappings.py`.
- **Modifying Prompts**: Centralized in `src/narrative.py` and modular steps in `src/steps/`.
- **FFmpeg Changes**: Primary logic resides in `src/renderer.py` and `src/steps/editor.py`.

## Architectural Map

- `src/app.py`: Main entry point with interface selection.
- `src/cli.py`: The interactive CLI wizard implementing the two-route flow.
- `src/server.py`: FastAPI backend for the web dashboard.
- `src/pipeline.py`: Orchestration engine for the Stock Footage route.
- `src/animation_pipeline.py`: Orchestrator for the 7-step Animation series.
- `src/steps/`: Modular steps for the Animation series.
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
