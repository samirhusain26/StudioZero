# StudioZero: Technical Pipeline Reference

This document provides a low-level technical reference for the StudioZero video generation engine. It details the two production routes and the shared infrastructure.

---

## 1. Route A: Stock Footage Pipeline

This pipeline focuses on speed and narrative clarity using stock media.

### Input Handling & Integrity
*   **Validation**: Uses `src.narrative.validate_input` (Gemini 2.5 Flash) to analyze user text.
*   **Random Story Logic**: If input is invalid, `generate_random_story_idea` creates a `Title - Summary` pair to ensure the pipeline always has valid content to process.

### Asset Generation
*   **Scripting**: LLM generates a 6-scene script with Pexels-optimized search queries.
*   **TTS**: Gemini TTS generates high-quality audio.Pacing is automatically adjusted by 25% for social media speed.
*   **Video**: Pexels API fetching with a multi-query fallback system (Literal → Metaphorical → Atmospheric).

### Rendering (FFmpeg)
*   **Sidechain Ducking**: Background music volume is dynamically lowered when voice is detected.
*   **Normalization**: All clips are standardized to 1080x1920 @ 30fps.
*   **Reveal Ending**: TMDB poster fetch + Ken Burns effect animation.

---

## 2. Route B: Animation Pipeline (Modular 7-Step)

A robust, step-based workflow for multi-episode series with character and world consistency.

### Orchestration & State
*   **Orchestrator**: `src/animation_pipeline.py`.
*   **Persistence**: `src/pipeline_state.py` manages `pipeline_state.json`, storing completion flags and artifact paths for every step.

### Detailed Steps:
1.  **Writer**: Takes the brief and expands it into a full story, character seeds, and episode outlines.
2.  **Screenwriter**: Converts the story into detailed scene breakdowns for all episodes.
3.  **Casting**: Generates character blueprints and visual reference images using Gemini Image Gen.
4.  **World Builder**: Establishes the series bible, setting, and location layout references.
5.  **Director**: Combines episode scenes with character/world references to engineer final Veo prompts.
6.  **Scene Generator**: Renders high-fidelity video clips via **Vertex AI Veo 3.1**.
7.  **Editor**: Final FFmpeg assembly with audio mixing and Hormozi-style karaoke subtitles.

---

## Technical Specifications Summary

| Feature | Stock Footage Route | Animation Route |
| :--- | :--- | :--- |
| **Video Engine** | Pexels API (Stock) | Vertex AI Veo 3.1 |
| **Voice Engine** | Gemini TTS | Gemini TTS |
| **Subtitle Format** | Hormozi-style ASS | Hormozi-style ASS |
| **Audio Mix** | Sidechain Ducking | Sidechain Ducking |
| **Resilience** | Input Validation + Random Story | 7-Step State Persistence + Retry Gate |
| **UI Support** | CLI / Batch / Web | CLI / Web |

---

## Web Server Architecture

The dashboard uses **FastAPI** with **WebSockets** for real-time log streaming.
*   **Project Manager**: `src/project_manager.py` handles CRUD for projects.
*   **WebSocket streaming**: Progress is yielded via the `PipelineStatus` generator and pushed to the client in real-time.
