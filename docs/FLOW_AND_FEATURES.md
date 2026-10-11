# StudioZero: Pipeline Flow & Feature Roadmap

This document provides a map of the current StudioZero video generation logic and outlines the roadmap for future development.

---

## 1. System-Wide Features

*   **Hormozi-Style Captions**: High-energy, frame-accurate karaoke subtitles (ASS format).
*   **Sidechain Audio Ducking**: Professional music volume management during voiceover.
*   **Smart Input Validation**: Gemini-powered detection of "garbage" text entries.
*   **Random Story Fallback**: Automatic generation of creative plots when user input is invalid.
*   **Modular Architecture**: Crash-resilient, 8-step execution for complex series.
*   **Multi-Model Video Generation**: 11 models across 3 tiers (Budget/Recommended/Premium) via Gemini API (Veo 3.1) and fal.ai, with per-project budget enforcement.
*   **Hybrid UI**: Choice between a high-speed CLI Wizard and a feature-rich Web Dashboard.

---

## 2. Pipeline Flow Maps

### A. Route A: Stock Footage Flow
1.  **Selection**: User chooses manual entry or Google Sheets automation.
2.  **Integrity Check**: `validate_input` runs on the movie name/story idea.
    *   *If valid*: Proceed with input.
    *   *If garbage*: Run `generate_random_story_idea`.
3.  **Scripting**: Generate a 6-scene recap optimized for social media.
4.  **Asset Generation**: Parallel fetch of Pexels stock video and Gemini TTS.
5.  **Alignment**: Local Whisper transcription for word-level timestamps.
6.  **Composition**: FFmpeg render with music ducking and poster reveal ending.

### B. Route B: Animation Flow (Modular 8-Step)
1.  **[Pre-Production] Writer**: Expand brief into full story, characters, and episode outlines.
2.  **[Pre-Production] Screenwriter**: Detailed scene breakdowns for all episodes.
3.  **[Pre-Production] Casting**: Generate character blueprints and reference images.
4.  **[Pre-Production] World Builder**: Define world rules, setting, and location layouts.
5.  **[Production] Director**: Engineer final video generation prompts, adapted per model family (Veo/Kling/Seedance/Wan/Sora).
6.  **[Production] Set Designer**: Composite character references into world environments for scene starting frames (cached across episodes).
7.  **[Production] Scene Gen**: Multi-model video generation via **fal.ai** or **Vertex AI** (with Retry Gate and Budget Guard).
8.  **[Production] Editor**: Final clip assembly, audio mixing, and caption burning.

---

## 3. Brainstormed Improvements & Roadmap

### Phase 1: Enhancement (Short-Term)
- [x] **Retry Gate**: Added interactive failure handling for Veo scenes in the CLI wizard.
- [x] **Modular Step Pattern**: Successfully transitioned to 8 discrete pre-production and production steps.
- [x] **Multi-Model Video Generation**: 11 models across 3 tiers via Gemini API and fal.ai with budget guard.
- [x] **Set Designer Step**: Scene starting images that composite characters into environments (eliminates white-background artifacts).
- [x] **Model-Adaptive Director**: Director adapts prompt style per video model family.
- [ ] **Multi-Angle Blueprints**: Generate 3-5 angles per character for better model consistency.
- [ ] **Dynamic Scene Count**: Support variable scene counts (4-12) based on story complexity.

### Phase 2: Interactivity (Mid-Term)
- [ ] **Live Script Editor**: Inline markdown editor in the dashboard to tweak scripts before rendering.
- [ ] **Asset Review Gates**: Optional pauses after World Building or Casting for human approval.
- [ ] **Music Library Expansion**: Integration with royalty-free music APIs for more variety.

### Phase 3: Scaling (Long-Term)
- [ ] **Auto-Publishing**: One-click upload to TikTok, Instagram, and YouTube.
- [ ] **Personalized Voice Cloning**: Integration with ElevenLabs for user-provided voices.
- [ ] **Community Templates**: Share and reuse "World Bibles" and "Character Rosters" across projects.
- [ ] **Distributed Rendering**: Offload FFmpeg tasks to a cloud worker cluster.
