# StudioZero

AI-powered video generation pipeline that creates short, vertical (9:16) social media videos. It autonomously handles everything from script generation and voiceovers to visual asset selection and final rendering.

## Core Operational Routes

StudioZero is organized into two primary production routes:

1.  **Stock Footage Route**: 
    *   **User Entry**: Input a movie name or story idea. If the input is unrecognizable, the system automatically generates a creative random story.
    *   **Sheet Automated**: Fetches multiple jobs from a Google Sheet for high-volume automated production.
    *   **Output**: Narrative recaps with AI voiceover, stock footage (Pexels), and Hormozi-style captions.

2.  **Animation Series Route**:
    *   **Modular 7-Step Pipeline**: A robust, crash-resilient process for multi-episode series (Writer, Screenwriter, Casting, World Builder, Director, Scene Gen, Editor).
    *   **Features**: Consistent characters via visual blueprints, world-building (Series Bible), and Vertex AI Veo 3.1 video generation.
    *   **Retry Gate**: Interactive failure handling that allows users to retry, edit prompts, or skip failed video generation scenes.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys
```bash
cp .env.template .env
```
Requires: Google Gemini (LLM/TTS/Vision), Groq (Fallback), Pexels (Stock Media), and Vertex AI (Veo 3.1).

### 3. Run the Application
```bash
python -m src.app
```
You will be prompted to choose between:
*   **CLI Wizard**: The recommended interactive terminal interface for both production routes.
*   **Web Dashboard**: A modern FastAPI/WebSocket interface for project management and real-time monitoring.

## Documentation

Detailed guides and technical references:

- [**FLOW_AND_FEATURES.md**](docs/FLOW_AND_FEATURES.md) — Visual flow maps and development roadmap.
- [**PIPELINE_OVERVIEW.md**](docs/PIPELINE_OVERVIEW.md) — Deep dive into Stock Footage vs. Animation routes.
- [**TECHNICAL_REFERENCE.md**](docs/TECHNICAL_REFERENCE.md) — Technical breakdown of the rendering engine and 7-step logic.
- [**PROJECT_STRUCTURE.md**](docs/PROJECT_STRUCTURE.md) — Codebase map and technical stack.
- [**BATCH_PROCESSING.md**](docs/BATCH_PROCESSING.md) — Guide for Google Sheets automation.
- [**MODELS_REFERENCE.md**](docs/MODELS_REFERENCE.md) — Pydantic schema and data model documentation.

## Key Features

- **Modular 7-Step Pipeline**: Production-grade animation series workflow with isolated pre-production and production phases.
- **Smart Input Validation**: Detects "garbage" text and falls back to AI-generated random stories to ensure successful runs.
- **Hierarchical Resilience**: Wikipedia → TMDB, Gemini → Groq, Pexels → Local assets.
- **Hormozi-Style Captions**: High-energy, frame-accurate karaoke subtitles (ASS format).
- **Sidechain Audio Ducking**: Professional-grade audio mixing with automatic music ducking.
- **Crash Recovery**: The animation series pipeline persists state in `pipeline_state.json` and can resume from any failure point.

## Technical Specs

- **Resolution**: 1080x1920 (9:16 portrait)
- **Frame Rate**: 30 FPS
- **Video Codec**: H.264 (libx264)
- **Audio**: AAC 192kbps with sidechain ducking
- **Models**: Gemini 2.5 Flash (Scripts/TTS/Vision), Veo 3.1 (Video)
