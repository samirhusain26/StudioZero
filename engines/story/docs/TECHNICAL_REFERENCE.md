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

## 2. Route B: Animation Pipeline (Modular 8-Step)

A robust, step-based workflow for multi-episode series with character and world consistency.

### Orchestration & State
*   **Orchestrator**: `src/animation_pipeline.py`.
*   **Persistence**: `src/pipeline_state.py` manages `pipeline_state.json`, storing completion flags and artifact paths for every step.
*   **Video Routing**: `src/video_client.py` (UnifiedVideoClient) routes to fal.ai or the Gemini API based on the active model from `src/video_models.py`.
*   **Budget**: `src/budget_guard.py` enforces per-project cost caps with auto-downgrade.

### Detailed Steps:
1.  **Writer**: Takes the brief and expands it into a full story, character seeds, and episode outlines.
2.  **Screenwriter**: Converts the story into detailed scene breakdowns for all episodes.
3.  **Casting**: Generates character blueprints and visual reference images using Gemini Image Gen.
4.  **World Builder**: Establishes the series bible, setting, and location layout references.
5.  **Director**: Combines episode scenes with character/world references to engineer final video generation prompts. Adapts prompt style per model family (veo, kling, seedance, wan, sora).
6.  **Set Designer**: Composites character reference images into world environments using Gemini Imagen, producing scene-appropriate starting frames. Cached by `{character_id}_{location_id}` and reused across episodes.
7.  **Scene Generator**: Renders video clips via the active model (10 verified models across fal.ai and the Gemini API). Uses `UnifiedVideoClient` with `BudgetGuard` enforcement and tier-based model fallback.
8.  **Editor**: Final FFmpeg assembly with audio mixing and Hormozi-style karaoke subtitles.

---

## Technical Specifications Summary

| Feature | Stock Footage Route | Animation Route |
| :--- | :--- | :--- |
| **Video Engine** | Pexels API (Stock) | 10 verified models via Gemini API + fal.ai |
| **Voice Engine** | Gemini TTS | Gemini TTS |
| **Subtitle Format** | Hormozi-style ASS | Hormozi-style ASS |
| **Audio Mix** | Sidechain Ducking | Sidechain Ducking |
| **Resilience** | Input Validation + Random Story | 8-Step State Persistence + Retry Gate + Budget Guard |
| **UI Support** | CLI / Batch / Web | CLI / Web |

---

## Web Server Architecture

The worker agent (`src/agent.py`) uses **FastAPI** with polling JSON (`…/events?since=N`); the old WebSocket dashboard was retired in Phase 3.
*   **Project Manager**: `src/project_manager.py` handles CRUD for projects.
*   **WebSocket streaming**: Progress is yielded via the `PipelineStatus` generator and pushed to the client in real-time.
*   **Video Model Settings**: `/api/settings/video-models` returns the full model registry; `/api/settings/active-model` manages the selected model and budget.
*   **Scene Retry**: `/api/projects/{id}/retry-scene` handles retry/edit/skip after scene failures.
*   **Pipeline Control**: `/api/projects/{id}/pause` pauses active runs; `/api/projects/{id}/state` returns raw pipeline state.
*   **Step Artifacts**: `/api/projects/{id}/step-artifacts` returns artifact URLs for completed steps.
*   **Finals Library**: `/api/finals` lists all rendered MP4s from `output/final/`.
