# Project Structure & Architecture

StudioZero is a modular AI video generation system designed for high scalability and rapid iteration. This document provides an architectural map of the codebase and detailed information on the project's technical stack.

---

## 1. Directory Structure

```text
StudioZero/
├── src/
│   ├── app.py              # CLI Entry Point & Argument Parsing
│   ├── pipeline.py         # Pipeline Orchestrator (Generator Pattern)
│   ├── animation_manager.py # Multi-episode State Persistence
│   ├── narrative.py        # LLM Scripting (Movie, Animated, Series)
│   ├── veo_client.py       # Vertex AI Veo 3.1 Integration
│   ├── renderer.py         # FFmpeg Video & Audio Composition
│   ├── gemini_tts.py       # Google Gemini TTS Engine
│   ├── moviedbapi.py       # Wikipedia & TMDB Data Fetching
│   ├── stock_media.py      # Pexels API Stock Video Downloader
│   ├── subtitles.py        # ASS (Hormozi-style) Subtitle Generator
│   ├── marketing.py        # Social Media Caption Generator
│   ├── config.py           # Environment & Path Configuration
│   ├── config_mappings.py  # Voice, Music, and Genre Meta-data
│   ├── batch_runner.py     # Batch Processing Orchestrator
│   ├── cloud_services.py   # Google Drive & Sheets Integration
│   └── logging_utils.py    # Centralized Logging Configuration
├── assets/
│   ├── basevideos/         # Fallback portrait video clips
│   ├── music/              # Background tracks organized by genre
│   └── creds/              # Service account credentials
├── docs/                   # Detailed documentation (Pipelines, Models, Guides)
├── output/
│   ├── final/              # Rendered MP4 videos
│   ├── temp/               # Per-project temporary asset storage
│   └── pipeline_logs/      # Script generation JSON logs
├── .env.template           # Template for environment variables
└── README.md               # Project overview and quick start
```

---

## 2. Technical Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.10+ |
| **Data Validation** | Pydantic v2 |
| **LLM (Primary)** | Google Gemini 2.0/2.5 Pro/Flash |
| **LLM (Fallback)** | Groq LLaMA 3.3 70B |
| **Video Generation** | Vertex AI Veo 3.1 |
| **Image Generation** | Gemini Image Generation |
| **Text-to-Speech** | Google Gemini TTS |
| **Transcription** | OpenAI Whisper (Local `base` model) |
| **Rendering Engine** | FFmpeg (H.264, libass, sidechain compression) |
| **Stock Video** | Pexels API |
| **Metadata Sources** | Wikipedia API, TMDB v3 API |
| **Automation** | Google Sheets API, Google Drive API |
| **Retry Logic** | Tenacity (Exponential Backoff) |

---

## 3. Key Design Patterns

### Generator-Based Progress
Both the Movie and Animated pipelines are implemented as Python generators in `src/pipeline.py`. They yield `PipelineStatus` objects, allowing the calling application (CLI or Batch Runner) to track real-time progress without blocking.

### Multi-Level Fallback Chains
Resilience is a core architectural mandate:
1. **Data:** Wikipedia → TMDB API → TMDB Search.
2. **LLM:** Gemini → Groq LLaMA.
3. **TTS:** Voice Narration → Sanitized Text → Silent Audio.
4. **Visuals:** Query 1 → Query 2 → Query 3 → Local Fallback Video.
5. **Rendering:** Stream-copy Concat → Full Re-encode.

### Persistent Project State
For multi-episode animation series, the `AnimationManager` tracks the lifecycle of episodes in `project_log.json`, enabling atomic rendering of individual episodes from a shared series project.
