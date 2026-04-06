# StudioZero: Master Video Generation Pipeline Documentation

This document provides a comprehensive technical breakdown of how StudioZero generates short-form vertical (9:16) videos. It covers all three major operational modes: **Movie Mode**, **Animated Mode (One-Shot)**, and the **Animation Series Pipeline**.

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Operational Modes](#operational-modes)
    - [Movie Mode (Narrative Recaps)](#movie-mode-narrative-recaps)
    - [Animated Mode (One-Shot Parodies)](#animated-mode-one-shot-parodies)
    - [Animation Series Pipeline (Multi-Episode)](#animation-series-pipeline-multi-episode)
3. [Core Technical Components](#core-technical-components)
    - [Script Generation (LLMs)](#script-generation-llms)
    - [Asset Generation (TTS & Visuals)](#asset-generation-tts--visuals)
    - [Transcription & Subtitles](#transcription--subtitles)
    - [Advanced Video Rendering (FFmpeg)](#advanced-video-rendering-ffmpeg)
4. [Project Infrastructure](#project-infrastructure)
    - [Configuration & Fallbacks](#configuration--fallbacks)
    - [Persistence & Caching](#persistence--caching)
    - [Batch Automation](#batch-automation)

---

## System Architecture Overview

StudioZero is built on a modular, generator-based pipeline (`src/pipeline.py`) that yields `PipelineStatus` updates. This allows for real-time progress tracking across CLI, web, and batch interfaces.

### High-Level Flow
```
User Input (Title/Theme) 
    -> Orchestrator (src/pipeline.py)
    -> Script Engine (src/narrative.py)
    -> Asset Generation (Parallel TTS + Visuals)
    -> Rendering (src/renderer.py)
    -> Final Output (output/final/*.mp4)
```

---

## Operational Modes

### Movie Mode (Narrative Recaps)
**Goal:** Create a 45-60 second movie summary with high-energy voiceover, stock footage, and animated captions.

- **Trigger:** `python -m src.app "Movie Title" --mode movie` (default)
- **Special Feature: Ending Reveal:** Automatically downloads the movie poster from TMDB and creates a "Ken Burns" style ending scene revealing the title and release year.
- **Consistency:** Uses an `overall_mood` flag to ensure the TTS voice maintains the same emotional tone (e.g., "tense", "horror", "exciting") across all 6 scenes.

### Animated Mode (One-Shot Parodies)
**Goal:** Create a ~1-minute animated parody featuring household items/food as 3D Pixar-style characters.

- **Trigger:** `python -m src.app "Theme" --mode animated`
- **Video Model:** Powered by **Vertex AI Veo 3.1** (`veo-3.1-fast-generate-001`).
- **Audio:** Veo generates native audio and lip-sync for each character based on a provided voice profile.
- **Visual Consistency:** A "Character Blueprint" (reference image) is generated via Gemini Image Gen and passed to Veo as a visual ingredient to anchor the character's look across scenes.

### Animation Series Pipeline (Multi-Episode)
**Goal:** Orchestrate a coherent multi-episode series with consistent characters and evolving storylines.

#### Phase 1: Series Scripting
- **Command:** `python -m src.app "Series Title" --mode animation-script --storyline "..." --char-desc "..." --episodes 3`
- **Output:** A `project.json` file in `output/temp/<title>/` containing the "Series Bible" and full scripts for all episodes.
- **Model:** `AnimationProject` (pydantic) containing multiple `AnimationEpisode` objects.

#### Phase 2: Episode Rendering
- **Command:** `python -m src.app "Series Title" --mode animation-render --episode-num 1`
- **Process:**
    1. Loads the series project from cache.
    2. Identifies unique characters for the episode.
    3. Generates/re-uses **shared character blueprints** (stored at the project root).
    4. Renders each scene via Veo 3.1.
    5. Assembles scenes into the final episode MP4.
    6. Tracks progress in `project_log.json`.

---

## Core Technical Components

### Script Generation (LLMs)
StudioZero uses a hierarchical LLM strategy:
1. **Primary:** Google Gemini 2.0/2.5 Pro/Flash for structured JSON output with Pydantic validation.
2. **Fallback:** Groq LLaMA 3.3 70B (via `tenacity` retries) if Gemini fails.

**Social Media Pacing Rules:**
- **Scene 1 MUST be a Hook:** Starts mid-action or with a shocking revelation ("Pause Reflex").
- **Dialogue Limits:** 25-40 words (Movie) or 15-20 words (Animated) per scene.
- **Narrative Arc:** Exactly 6 scenes (Hook -> Context -> Escalation -> Turn -> Climax -> Resolution).

### Asset Generation (TTS & Visuals)

#### Movie Mode Assets (Parallel Processing)
- **TTS:** Gemini TTS generates 24kHz mono WAVs. All speeds are boosted by **25%** for social media pacing.
- **Stock Video:** Pexels API uses a 3-query fallback chain:
  `Literal Query -> Metaphorical Query -> Atmospheric Query -> Local Fallback Clip`.

#### Animated Mode Assets (Veo 3.1)
- **Visual Ingredients:** Character reference PNGs are passed to Veo to ensure "visual anchoring".
- **Modalities:** Requests `["VIDEO", "AUDIO"]` from Vertex AI to get synced character performance.

### Transcription & Subtitles
- **Whisper (Local):** The `base` model is lazy-loaded in a background thread to minimize latency. It provides word-level timestamps.
- **ASS Subtitles:** Generates "Hormozi-style" (karaoke) captions:
    - Font: 80pt Arial Black, white text, black outline.
    - Format: ASS (Advanced SubStation Alpha) for frame-accurate timing.
    - Rendering: Burned into video via FFmpeg `ass` filter.

### Advanced Video Rendering (FFmpeg)

#### Audio Ducking (Sidechain Compression)
The background music automatically lowers its volume when the narrator speaks.
- **Filter:** `sidechaincompress=threshold=0.1:ratio=10:attack=50:release=200`.
- **Mixing:** `amix` combines the ducked music with the voice track.

#### Video Normalization
Ensures every input clip (from Pexels or Veo) is standardized:
- **Resolution:** 1080x1920 (9:16 portrait).
- **Frame Rate:** 30 FPS.
- **Codec:** H.264 (libx264, yuv420p).
- **Looping:** If a video is shorter than its audio, it is looped via `-stream_loop -1` and trimmed to the exact audio duration.

#### Ken Burns Effect
Applied to the movie poster in the ending scene to create dynamic motion from a static image.
- **Filter:** `zoompan` with linear interpolation over the scene duration.

---

## Project Infrastructure

### Configuration & Fallbacks
- **Config Centralization:** All API keys and paths are managed in `src/config.py`.
- **Safety Fallbacks:**
    - TTS Blocked -> Silent WAV.
    - Pexels Fails -> `assets/basevideos/`.
    - Gemini Fails -> Groq LLaMA.
    - Stream-copy Concat Fails -> Full Re-encode.

### Persistence & Caching
- **Movie Cache:** `output/temp/<movie>/pipeline_cache.json` stores the script and asset paths for `--offline` re-renders.
- **Animation Series Tracking:** `AnimationManager` tracks episode status (pending, rendering, completed, failed) in `project_log.json`.

### Batch Automation
The `src/batch_runner.py` processes jobs from a Google Sheet queue.
- **Job_Type Column:** Routes jobs to either the Movie or Animated pipeline.
- **Automated Delivery:** Uploads final MP4s to Google Drive and populates the Sheet with shareable links, generated social captions (via `marketing.py`), and timestamps.
