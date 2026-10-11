# StudioZero

> Part of the StudioZero studio: this is the **story engine** (`engines/story`). Run every command from this folder. Retired in October 2026: the Google Sheets batch runner, Drive/iCloud upload, Groq captions, the app launcher, Cloud Run, StudioZero.app and the legacy Vertex client. Studio rules (public repository, no paid generation without the owner's OK): `../../AGENTS.md`.

AI-powered video generation pipeline that creates short, vertical (9:16) social media videos. It autonomously handles everything from script generation and voiceovers to visual asset selection and final rendering.

## Core Operational Routes

StudioZero is organized into two primary production routes:

1.  **Stock Footage Route**: 
    *   **User Entry**: Input a movie name or story idea. If the input is unrecognizable, the system automatically generates a creative random story.
    *   **Output**: Narrative recaps with AI voiceover, stock footage (Pexels), and Hormozi-style captions.

2.  **Animation Series Route**:
    *   **Modular 8-Step Pipeline**: A robust, crash-resilient process for multi-episode series (Writer, Screenwriter, Casting, World Builder, Director, Set Designer, Scene Gen, Editor).
    *   **Features**: Consistent characters via visual blueprints, world-building (Series Bible), and multi-model video generation (11 models across 3 tiers via Gemini API and fal.ai).
    *   **Retry Gate**: Interactive failure handling that allows users to retry, edit prompts, or skip failed video generation scenes.
    *   **Budget Guard**: Per-project budget enforcement with auto-downgrade to cheaper models when cost limits are reached.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys
```bash
cp .env.template .env
```
Requires: Google Gemini (LLM/TTS/Vision + Veo video generation), Groq (Fallback), Pexels (Stock Media). Optional: fal.ai (Kling, Seedance, Wan, Sora models).

### 3. Run the Application
```bash
python -m src.cli
```
You will be prompted to choose between:
*   **CLI Wizard**: The recommended interactive terminal interface for both production routes.
*   **Web Dashboard**: A modern FastAPI/WebSocket interface for project management and real-time monitoring.

## Documentation

Detailed guides and technical references:

- [**FLOW_AND_FEATURES.md**](docs/FLOW_AND_FEATURES.md) — Visual flow maps and development roadmap.
- [**PIPELINE_OVERVIEW.md**](docs/PIPELINE_OVERVIEW.md) — Deep dive into Stock Footage vs. Animation routes.
- [**TECHNICAL_REFERENCE.md**](docs/TECHNICAL_REFERENCE.md) — Technical breakdown of the rendering engine and 8-step logic.
- [**PROJECT_STRUCTURE.md**](docs/PROJECT_STRUCTURE.md) — Codebase map and technical stack.
- [**MODELS_REFERENCE.md**](docs/MODELS_REFERENCE.md) — Pydantic schema and data model documentation.

## Key Features

- **Modular 8-Step Pipeline**: Production-grade animation series workflow with isolated pre-production and production phases.
- **Smart Input Validation**: Detects "garbage" text and falls back to AI-generated random stories to ensure successful runs.
- **Hierarchical Resilience**: Wikipedia → TMDB, Gemini → Groq, Pexels → Local assets.
- **Hormozi-Style Captions**: High-energy, frame-accurate karaoke subtitles (ASS format).
- **Sidechain Audio Ducking**: Professional-grade audio mixing with automatic music ducking.
- **Crash Recovery**: The animation series pipeline persists state in `pipeline_state.json` and can resume from any failure point.
- **Multi-Model Video Generation**: 11 models across 3 tiers (Budget/Recommended/Premium) via Gemini API (Veo 3.1) and fal.ai, with per-project budget enforcement and auto-downgrade.

## Technical Specs

- **Resolution**: 1080x1920 (9:16 portrait)
- **Frame Rate**: 30 FPS
- **Video Codec**: H.264 (libx264)
- **Audio**: AAC 192kbps with sidechain ducking
- **Video Models**: 11 supported models — Veo 3.1 (Lite/Fast/Standard via Gemini API), Kling (2.5/3.0), Seedance (1.5/2.0), Wan (2.2/2.5), Sora 2 Pro — via fal.ai
- **LLM**: Gemini 2.5 Flash (Scripts/TTS/Vision)
