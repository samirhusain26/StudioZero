# StudioZero: Technical Pipeline Reference

This document provides a low-level technical reference for the StudioZero video generation engine. It detail every stage of the process across the Movie, Animated, and Animation Series pipelines.

---

## 1. Movie Recap Pipeline (Default)

The movie pipeline generates high-energy recaps from a movie title.

### Step 1: Data Retrieval & Scripting
- **Sources:** Wikipedia API (primary plot) and TMDB API (poster, year, tagline).
- **LLM:** Google Gemini 2.0/2.5 Pro (Primary) or Groq LLaMA 3.3 70B (Fallback).
- **Schema:** `VideoScript` pydantic model (exactly 6 scenes).
- **Logic:** Identifies genre, selects voice ID, determines overall mood, and generates 3 Pexels search queries per scene.

### Step 2: Parallel Asset Generation
- **TTS:** Gemini TTS generates 24kHz mono WAVs. Pacing is adjusted per scene via `mood` and `tts_speed`. All clips are boosted 25% for social media.
- **Visuals:** Pexels API search with a 3-query fallback chain:
  `Literal -> Metaphorical -> Atmospheric -> assets/basevideos/`.
- **Poster Scene:** Downloads TMDB poster, generates "Ken Burns" video, and creates special "reveal" narration.

### Step 3: Transcription & Subtitles
- **Whisper:** Local `base` model transcribes all scenes with `word_timestamps=True`.
- **Subtitles:** `pysubs2` generates an ASS file with Hormozi-style (karaoke) formatting.

### Step 4: Final Rendering
- **Normalization:** FFmpeg ensures all clips are 1080x1920, 30fps, H.264. Short videos are looped via `-stream_loop -1`.
- **Audio Mixing:** Sidechain compression (ducking) lowers music volume when the voice track is active.
- **Filter:** `sidechaincompress=threshold=0.1:ratio=10:attack=50:release=200`.

---

## 2. Animated Parody Pipeline (One-Shot)

The animated pipeline uses Vertex AI Veo 3.1 to generate episodic parodies.

### Step 1: Parody Scripting
- **LLM:** Gemini Pro generates an `EpisodicScript` (6 scenes) based on a theme.
- **Characters:** All characters are household items/food with punny names parodying the theme.

### Step 2: Character Blueprints
- **Model:** Gemini Image Gen (`gemini-3.1-flash-image-preview`).
- **Output:** PNG reference sheets (front-facing 3/4 view, white background).
- **Purpose:** Passed to Veo 3.1 as a "visual ingredient" to anchor character appearance.

### Step 3: Veo 3.1 Rendering
- **Model:** `veo-3.1-fast-generate-001`.
- **Input:** Visual description + reference image + character dialogue + voice profile.
- **Output:** MP4 clips with native video, audio, and lip-sync.

### Step 4: Assembly & Subtitles
- **Concatenation:** Uses FFmpeg stream-copy (`-c copy`) for speed. Falls back to re-encode on failure.
- **Subtitles:** Optional transcription of the final audio track to burn in captions.

---

## 3. Animation Series Pipeline (Multi-Episode)

The series pipeline allows for persistent series management.

### Phase 1: Series Bible & Scripting
- **CLI:** `--mode animation-script`.
- **Orchestration:** `generate_animation_project` creates a multi-episode `AnimationProject`.
- **Persistence:** Saved to `output/temp/<title>/project.json` via `AnimationManager`.

### Phase 2: Episode Rendering
- **CLI:** `--mode animation-render --episode-num <N>`.
- **Tracking:** Progress stored in `project_log.json` (pending, rendering, completed, failed).
- **Consistency:** Re-uses character blueprints stored at the project root across all episodes.

---

## Technical Specifications Summary

| Feature | Movie Mode | Animated/Series Mode |
|---------|------------|----------------------|
| **Aspect Ratio** | 1080x1920 (9:16) | 1080x1920 (9:16) |
| **Video Model** | Pexels (Stock) | Vertex AI Veo 3.1 |
| **Voice Model** | Gemini TTS | Veo Native (Voice Profile) |
| **Subtitles** | Hormozi ASS (Mandatory) | Hormozi ASS (Optional) |
| **Audio Mix** | Voice + Music Ducking | Veo Scene Audio |
| **Persistence** | `pipeline_cache.json` | `project.json` + `project_log.json` |
