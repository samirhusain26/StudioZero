# StudioZero: Pipeline Overview Documentation

This document provides a comprehensive breakdown of the StudioZero video generation architecture. It covers the two primary production routes: **Stock Footage** and **Animation Series (7-Step modular)**.

---

## 1. System Architecture Overview

StudioZero uses a generator-based orchestrator model. Pipelines yield `PipelineStatus` objects, enabling real-time progress tracking across the CLI Wizard, Web Dashboard, and Batch Runner.

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

A production-grade, 7-step modular framework for multi-episode series with character and world consistency.

#### Phase 1: Pre-Production (Runs once per project)
1.  **Writer**: Takes the user's brief and expands it into a full story, character seeds, and episode outlines.
2.  **Screenwriter**: Converts the story into detailed scene breakdowns for ALL episodes to ensure narrative continuity.
3.  **Casting**: Generates character blueprints and visual reference images (Gemini Image Gen) based on the scene breakdowns.
4.  **World Builder**: Establishes the series bible, setting, and location layout references.

#### Phase 2: Production (Runs per episode)
5.  **Director**: Combines episode scenes with character/world references to engineer final, optimized prompts for the video model.
6.  **Scene Generator**: Renders high-fidelity video clips using **Vertex AI Veo 3.1**. Includes a "retry gate" for failed scenes.
7.  **Editor**: Assembles clips, syncs dialogue/music, and burns in Hormozi-style karaoke subtitles.

### Persistence & Crash Recovery
The Animation Series route uses `src/pipeline_state.py` to track the completion of every step in `pipeline_state.json`. This allows the pipeline to resume from the exact point of failure, which is critical for long-running video generation tasks.

---

## 4. UI Interfaces

*   **CLI Wizard**: A lightweight, interactive terminal interface for launching jobs.
*   **Web Dashboard**: A modern FastAPI/WebSocket interface for managing projects, editing scripts, and viewing real-time rendering logs.
