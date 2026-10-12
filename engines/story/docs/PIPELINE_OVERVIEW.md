# StudioZero: Pipeline Overview Documentation

This document provides a comprehensive breakdown of the StudioZero video generation architecture. It covers the two primary production routes: **Stock Footage** and **Animation Series (8-Step modular)**.

---

## 1. System Architecture Overview

StudioZero uses a generator-based orchestrator model. Pipelines yield `PipelineStatus` objects, enabling real-time progress tracking across the CLI wizard, headless runs and the worker agent.

### High-Level Flow
```
User Selection 
    -> Route A: Stock Footage (src/pipeline.py)
    -> Route B: Animation (src/animation_pipeline.py)
    -> Final Output (output/final/*.mp4)
```

---

## 2. Stock Footage Route (Recaps & Stories)

This route is designed for rapid generation of high-energy narrative videos using stock media.

### Sub-Routes:
1.  **User Entry**:
    *   **Logic**: The user enters a movie title or story idea.
    *   **Validation**: The system uses Gemini (`validate_input`) to check if the text is recognizable.
    *   **Fallback**: If the input is "garbage" or nonsensical, the system triggers `generate_random_story_idea` to create a fresh, creative plot automatically.
2.  **Sheet Automated**:
    *   **Logic**: Fetches a queue of jobs from a pre-configured Google Sheet.
    *   **Automation**: Orchestrated by `src/batch_runner.py`, allowing for hands-free production of dozens of videos.

### Technical Workflow:
1.  **Research**: Meta-data lookup via Wikipedia/TMDB.
2.  **Scripting**: 6-scene structured script generation (Gemini/Groq).
3.  **Asset Prep**: Parallel generation of Gemini TTS and Pexels stock video fetching.
4.  **Transcription**: Word-level alignment using local OpenAI Whisper.
5.  **Composition**: FFmpeg assembly with music mixing and sidechain ducking.

---

## 3. Animation Series Route

A production-grade, 8-step modular framework for multi-episode series with character and world consistency.

#### Phase 1: Pre-Production (Runs once per project)
1.  **Writer**: Takes the user's brief and expands it into a full story, character seeds, and episode outlines.
2.  **Screenwriter**: Converts the story into detailed scene breakdowns for ALL episodes to ensure narrative continuity.
3.  **Casting**: Generates character blueprints and visual reference images (Gemini Image Gen) based on the scene breakdowns.
4.  **World Builder**: Establishes the series bible, setting, and location layout references.

#### Phase 2: Production (Runs per episode)
5.  **Director**: Combines episode scenes with character/world references to engineer final, optimized prompts for the active video model. Adapts prompt style per model family (Veo, Kling, Seedance, Wan, Sora).
6.  **Set Designer**: Composites character references into world environments using Gemini Imagen, producing scene-appropriate starting frames. Images are cached by character+location and reused across episodes.
7.  **Scene Generator**: Renders video clips via the active model (11 models supported across fal.ai and Vertex AI). Includes budget guard enforcement, model fallback, and a "retry gate" for failed scenes.
8.  **Editor**: Assembles clips, syncs dialogue/music, and burns in Hormozi-style karaoke subtitles.

### Multi-Model Video Generation
The Scene Generator supports 11 models across 3 tiers:
*   **Budget**: Veo 3.1 Lite (Gemini API), Wan 2.5, Kling 2.5 Turbo Pro, Wan 2.2
*   **Recommended**: Veo 3.1 Fast (Gemini API), Seedance 2.0 Fast, Seedance 1.5 Pro Fast
*   **Premium**: Veo 3.1 (Gemini API), Kling 3.0 Pro, Seedance 2.0, Sora 2 Pro

Model selection is configurable in the Settings panel. The `BudgetGuard` enforces per-project spending limits and auto-downgrades to cheaper models when the budget is exceeded.

### Persistence & Crash Recovery
The Animation Series route uses `src/pipeline_state.py` to track the completion of every step in `pipeline_state.json`. This allows the pipeline to resume from the exact point of failure, which is critical for long-running video generation tasks.

---

## 4. UI Interfaces

*   **CLI Wizard**: A lightweight, interactive terminal interface for launching jobs.
*   **Worker agent**: `src/agent.py` (FastAPI, polling JSON) behind the Pi's studio proxy; the Pi UI's Studio › Story jobs manage projects, review scripts and show logs.
