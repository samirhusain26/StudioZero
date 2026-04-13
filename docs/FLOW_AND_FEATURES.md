# StudioZero: Pipeline Flow & Feature Roadmap

This document provides a map of the current StudioZero video generation logic and outlines the roadmap for future development.

---

## 1. System-Wide Features

*   **Hormozi-Style Captions**: High-energy, frame-accurate karaoke subtitles (ASS format).
*   **Sidechain Audio Ducking**: Professional music volume management during voiceover.
*   **Smart Input Validation**: Gemini-powered detection of "garbage" text entries.
*   **Random Story Fallback**: Automatic generation of creative plots when user input is invalid.
*   **Modular Architecture**: Crash-resilient, step-based execution for complex series.
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

### B. Route B: Animation Flow (Modular 7-Step)
1.  **[Pre-Production] Writer**: Expand brief into full story, characters, and episode outlines.
2.  **[Pre-Production] Screenwriter**: Detailed scene breakdowns for all episodes.
3.  **[Pre-Production] Casting**: Generate character blueprints and reference images.
4.  **[Pre-Production] World Builder**: Define world rules, setting, and location layouts.
5.  **[Production] Director**: Engineer final Veo 3.1 prompts from scenes and references.
6.  **[Production] Scene Gen**: Video generation using **Vertex AI Veo 3.1** (with Retry Gate).
7.  **[Production] Editor**: Final clip assembly, audio mixing, and caption burning.

---

## 3. Brainstormed Improvements & Roadmap

### Phase 1: Enhancement (Short-Term)
- [x] **Retry Gate**: Added interactive failure handling for Veo scenes in the CLI wizard.
- [x] **Modular Step Pattern**: Successfully transitioned to 7 discrete pre-production and production steps.
- [ ] **Multi-Angle Blueprints**: Generate 3-5 angles per character for better Veo consistency.
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
