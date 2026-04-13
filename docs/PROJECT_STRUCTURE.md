# Project Structure & Architecture

StudioZero is a modular AI video generation system designed for high scalability and rapid iteration. This document provides an architectural map of the codebase and technical stack.

---

## 1. Directory Structure

```text
StudioZero/
├── src/
│   ├── app.py              # Main entry point (Interface Switcher)
│   ├── cli.py              # Interactive CLI Wizard
│   ├── headless.py         # Headless (non-interactive) runner
│   ├── server.py           # FastAPI Web Dashboard backend
│   ├── pipeline.py         # Stock Footage Route Orchestrator
│   ├── animation_pipeline.py # Animation Series Route Orchestrator (7-step)
│   ├── pipeline_state.py   # Persistence & State for Animation series
│   ├── project_manager.py  # Project CRUD for Web Dashboard
│   ├── server_launcher.py  # Server startup helper
│   ├── steps/              # Modular Pipeline Steps (Animation Series)
│   │   ├── writer.py        # Brief → Story + Character Seeds
│   │   ├── screenwriter.py  # Story → Episode Scene Breakdowns
│   │   ├── casting.py       # Scene Breakdowns → Character Blueprints
│   │   ├── world_builder.py # Scene Breakdowns → Location Layouts
│   │   ├── director.py      # Episode scenes + refs → Veo Prompts
│   │   ├── scene_generator.py # Veo Prompts → MP4 Clips
│   │   └── editor.py        # Clips → Assembled Episode MP4
│   ├── narrative.py        # LLM Scripting, Validation, and Random Story logic
│   ├── veo_client.py       # Vertex AI Veo 3.1 Integration
│   ├── renderer.py         # FFmpeg Video & Audio Composition
│   ├── subtitles.py        # Hormozi-style karaoke captions (ASS)
│   ├── gemini_tts.py       # Google Gemini TTS Engine
│   ├── moviedbapi.py       # Wikipedia & TMDB Data Fetching
│   ├── stock_media.py      # Pexels API Integration
│   ├── batch_runner.py     # Google Sheets Batch processor
│   ├── cloud_services.py   # Google Drive & Sheets integrations
│   ├── project_manager.py  # Project listing and management utility
│   ├── config.py           # Environment & Path Configuration
│   ├── config_mappings.py  # Music/Voice/Mood lookup tables
│   ├── marketing.py        # Social media caption generation (Groq)
│   └── logging_utils.py    # Centralized Logging
├── static/                 # Web Dashboard Frontend (HTML/JS/CSS)
├── assets/
│   ├── basevideos/         # Fallback portrait clips
│   ├── music/              # Background tracks by genre
│   └── creds/              # Service account credentials
├── output/
│   ├── final/              # Rendered MP4 videos
│   ├── temp/               # Per-project temporary assets and state
│   ├── projects/           # Project state JSON files (Web Dashboard)
│   └── pipeline_logs/      # Script generation JSON logs
├── docs/                   # Detailed documentation
└── README.md               # Project overview
```

---

## 2. Technical Stack

| Component | Technology |
| :--- | :--- |
| **Language** | Python 3.10+ |
| **LLM (Primary)** | Google Gemini 2.5 Flash |
| **LLM (Fallback)** | Groq LLaMA 3.3 70B |
| **Video Generation** | Vertex AI Veo 3.1 |
| **Image Generation** | Gemini 2.0 Flash (Blueprints) |
| **Text-to-Speech** | Google Gemini TTS |
| **Rendering** | FFmpeg (H.264, libass, sidechain) |
| **Transcription** | OpenAI Whisper (Local) |
| **Dashboard** | FastAPI, WebSockets, Vanilla CSS |

---

## 3. Key Design Patterns

### Generator-Based Progress
Both production routes use Python generators that yield `PipelineStatus` objects. This allows any UI (CLI or Web) to consume real-time updates and update progress bars/logs without blocking the main thread.

### Modular Step Pattern (Animation Series)
The Animation route decomposes video generation into 7 discrete steps in `src/steps/`. Each step is isolated, making it easy to test, modify, or replace individual components (e.g., swapping the Screenwriter LLM) without affecting the rest of the pipeline.

### Crash-Resilient State
The `PipelineState` model tracks every step's completion and artifact paths. This allows the Animation pipeline to resume from the exact point of failure, critical for long-running video generation tasks.
