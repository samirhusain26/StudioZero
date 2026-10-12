# Project Structure & Architecture

StudioZero is a modular AI video generation system designed for high scalability and rapid iteration. This document provides an architectural map of the codebase and technical stack.

---

## 1. Directory Structure

```text
StudioZero/
├── src/
│   ├── cli.py              # Interactive CLI Wizard
│   ├── headless.py         # Headless (non-interactive) runner
│   ├── agent.py            # Story worker agent (FastAPI) for the Pi UI's Story jobs
│   ├── pipeline.py         # Stock Footage Route Orchestrator
│   ├── animation_pipeline.py # Animation Series Route Orchestrator (8-step)
│   ├── pipeline_state.py   # Persistence & State for Animation series
│   ├── project_manager.py  # Project CRUD for the worker agent
│   ├── video_models.py     # Central registry of all 11 video generation models
│   ├── video_client.py     # Unified video client (fal.ai + Gemini API routing)
│   ├── budget_guard.py     # Per-project budget enforcement + auto-downgrade, spend ledger
│   ├── render_json.py      # render.json + cover.jpg per final video (docs/HEADLESS.md)
│   ├── steps/              # Modular Pipeline Steps (Animation Series)
│   │   ├── writer.py        # Brief → Story + Character Seeds
│   │   ├── screenwriter.py  # Story → Episode Scene Breakdowns
│   │   ├── casting.py       # Scene Breakdowns → Character Blueprints
│   │   ├── world_builder.py # Scene Breakdowns → Location Layouts
│   │   ├── director.py      # Episode scenes + refs → Video Gen Prompts
│   │   ├── set_designer.py  # Character + World refs → Scene Starting Images
│   │   ├── scene_generator.py # Prompts → MP4 Clips (multi-model)
│   │   └── editor.py        # Clips → Assembled Episode MP4
│   ├── tools/              # CLI Utilities
│   │   └── model_compare.py # Compare video outputs across models (HTML report)
│   ├── narrative.py        # LLM Scripting, Validation, and Random Story logic
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
├── assets/
│   ├── basevideos/         # old local clips (ignored, licence unknown, never used)
│   ├── music/              # Background tracks by genre
│   └── creds/              # Service account credentials
├── output/
│   ├── final/              # Rendered MP4s; recaps in <safe_title>/ with cover.jpg + render.json
│   ├── temp/               # Per-project temporary assets and state
│   ├── projects/           # Project state JSON files (story worker agent)
│   └── pipeline_logs/      # Script generation JSON logs
├── docs/                   # Detailed documentation
├── tests/                  # $0 unittest suite (smoke tests for both routes)
├── registry.json           # Routes, default models, video model registry (single source)
└── README.md               # Project overview
```

---

## 2. Technical Stack

| Component | Technology |
| :--- | :--- |
| **Language** | Python 3.10+ |
| **LLM (Primary)** | Google Gemini 2.5 Flash |
| **LLM (Fallback)** | Groq LLaMA 3.3 70B |
| **Video Generation** | 10 verified models via Gemini API (Veo 3.1 Lite/Fast/Standard) + fal.ai (Kling, Seedance, Wan) |
| **Image Generation** | Gemini 2.0 Flash (Blueprints) |
| **Text-to-Speech** | Google Gemini TTS |
| **Rendering** | FFmpeg (H.264, libass, sidechain) |
| **Transcription** | OpenAI Whisper (Local) |
| **Worker agent** | FastAPI, polling JSON (UI: the Pi's Studio › Story jobs) |

---

## 3. Key Design Patterns

### Generator-Based Progress
Both production routes use Python generators that yield `PipelineStatus` objects. This allows any UI (CLI or Web) to consume real-time updates and update progress bars/logs without blocking the main thread.

### Modular Step Pattern (Animation Series)
The Animation route decomposes video generation into 8 discrete steps in `src/steps/`. Each step is isolated, making it easy to test, modify, or replace individual components (e.g., swapping the Screenwriter LLM or video generation model) without affecting the rest of the pipeline.

### Multi-Model Video Generation
The `UnifiedVideoClient` (`src/video_client.py`) routes video generation to the correct provider (fal.ai or the Gemini API) based on the model registry (`src/video_models.py`). The `BudgetGuard` (`src/budget_guard.py`) enforces per-project budget caps and auto-downgrades to cheaper models when limits are reached.

### Crash-Resilient State
The `PipelineState` model tracks every step's completion and artifact paths. This allows the Animation pipeline to resume from the exact point of failure, critical for long-running video generation tasks.
