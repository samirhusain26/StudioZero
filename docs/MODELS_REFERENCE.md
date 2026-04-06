# Data Models & Schema Reference

StudioZero uses Pydantic v2 for structured data validation and LLM response parsing. This document details all primary data models used across the Movie, Animated, and Series pipelines.

---

## 1. Movie Recap Models (`src/narrative.py`)

These models define the structure for the default movie recap mode.

### `VideoScript`
The root model for a movie recap project.

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | The movie title. |
| `genre` | `str` | Primary genre (e.g., "action", "horror"). |
| `overall_mood` | `str` | Global TTS tone for consistency (e.g., "tense", "dramatic"). |
| `selected_voice_id` | `str` | Gemini TTS voice ID (e.g., "am_adam"). |
| `selected_music_file` | `str` | Filename of background track. |
| `lang_code` | `str` | Accent code ('a' for American, 'b' for British). |
| `bpm` | `int` | Estimated video tempo (60-200). |
| `scenes` | `List[Scene]` | Exactly 6 scenes covering the narrative arc. |

### `Scene`
A single narrative beat in a movie recap.

| Field | Type | Description |
|-------|------|-------------|
| `scene_index` | `int` | 0-based index. |
| `narration` | `str` | 25-40 words of conversational past-tense storytelling. |
| `visual_queries` | `List[str]` | 3 Pexels search queries (Literal, Abstract, Atmospheric). |
| `visual_style_modifiers` | `List[str]` | Style hints (e.g., ["4k", "cinematic"]). |
| `mood` | `str` | Emotional mood for per-scene TTS pacing. |
| `tts_speed` | `float` | Speech multiplier (1.0-1.6). |

---

## 2. Animated Parody Models (`src/narrative.py`)

Used for one-shot animated parodies featuring household items.

### `EpisodicScript`
| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Parody title (e.g., "Game of Scones"). |
| `theme` | `str` | Source material being parodied. |
| `scenes` | `List[EpisodicScene]` | Exactly 6 scenes. |

### `EpisodicScene`
| Field | Type | Description |
|-------|------|-------------|
| `scene_number` | `int` | 1-6. |
| `character_name` | `str` | Name of the household item character. |
| `dialogue` | `str` | 15-30 words of punny dialogue. |
| `voice_profile` | `str` | Descriptive voice for Veo (e.g., "deep baritone"). |
| `visual_description` | `str` | 40+ word Pixar-style scene description for Veo. |

---

## 3. Animation Series Models (`src/narrative.py`)

Used for multi-episode series orchestration.

### `AnimationProject`
The series bible and episode list.

| Field | Type | Description |
|-------|------|-------------|
| `project_title` | `str` | Overall series title. |
| `storyline` | `str` | General plot for the entire series. |
| `character_descriptions` | `str` | Details on the anthropomorphic cast. |
| `episodes` | `List[AnimationEpisode]` | List of episode scripts. |

### `AnimationEpisode`
| Field | Type | Description |
|-------|------|-------------|
| `episode_number` | `int` | 1-based index. |
| `episode_title` | `str` | Specific episode title. |
| `script` | `AnthropomorphicScript` | The actual scene-level script. |

### `AnthropomorphicScript`
A parody script optimized for 6-8 second clips.

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Episode title. |
| `theme` | `str` | Source material. |
| `scenes` | `List[AnthropomorphicScene]` | 6-10 high-stakes scenes. |

---

## 4. Operational Models (`src/pipeline.py`, `src/animation_manager.py`)

### `PipelineStatus`
Yielded by the pipeline generator for UI/CLI updates.

| Field | Type | Description |
|-------|------|-------------|
| `step` | `int` | Current pipeline step (1-5). |
| `message` | `str` | User-friendly status message. |
| `data` | `Optional[Dict]` | Payload containing IDs, paths, or scripts. |
| `is_error` | `bool` | True if the step encountered a failure. |

### `EpisodeStatus`
Used for tracking series progress in `project_log.json`.

| Field | Type | Description |
|-------|------|-------------|
| `episode_number` | `int` | 1-based index. |
| `status` | `str` | `pending`, `rendering`, `completed`, or `failed`. |
| `output_path` | `Optional[str]` | Path to final MP4 on success. |
| `error` | `Optional[str]` | Error message on failure. |
