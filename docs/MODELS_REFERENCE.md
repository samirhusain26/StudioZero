# Data Models & Schema Reference

StudioZero uses Pydantic v2 for structured data validation and LLM response parsing. This document details all primary data models used across the Stock Footage and Animation pipelines.

---

## 1. Stock Footage Models (`src/narrative.py`)

Used by the **Stock Footage Route** to generate structured scripts for recaps.

### `VideoScript`
The root model for a movie recap or story project.

| Field | Type | Description |
| :--- | :--- | :--- |
| `title` | `str` | The movie title or story name. |
| `genre` | `str` | Primary genre (e.g., "action", "horror"). |
| `overall_mood` | `str` | Global TTS tone for consistency (e.g., "tense", "dramatic"). |
| `selected_voice_id` | `str` | Gemini TTS voice ID. |
| `selected_music_file` | `str` | Background music track filename. |
| `lang_code` | `str` | Language/accent code ('a' for American, etc.). |
| `bpm` | `int` | Estimated tempo for video pacing. |
| `scenes` | `List[Scene]` | Exactly 6 scenes covering the narrative arc. |

### `Scene`
A single narrative beat in a movie recap.

| Field | Type | Description |
| :--- | :--- | :--- |
| `scene_index` | `int` | 0-based index. |
| `narration` | `str` | 25-40 words of conversational past-tense storytelling. |
| `visual_queries` | `List[str]` | 3 Pexels search queries (Literal, Metaphorical, Vibe). |
| `visual_style_modifiers` | `List[str]` | Style hints for visual selection. |
| `mood` | `str` | Emotional mood for per-scene TTS pacing. |
| `tts_speed` | `float` | Speech multiplier (1.0-1.6). |

---

## 2. Animation Series Models (`src/steps/`)

Used by the **7-Step Animation Pipeline** to generate multi-episode series content.

### Writer Output (`src/steps/writer.py`)

#### `StoryOutput`
The root model produced by the Writer step.

| Field | Type | Description |
| :--- | :--- | :--- |
| `project_title` | `str` | Title of the series. |
| `logline` | `str` | One-sentence series pitch. |
| `setting` | `str` | Primary world/setting description. |
| `tone` | `str` | Tonal direction (e.g., "dark comedy"). |
| `world_rules` | `List[str]` | Rules governing the story world. |
| `series_arc` | `str` | Overarching narrative arc. |
| `episode_outlines` | `List[EpisodeOutline]` | Per-episode summaries. |
| `character_seeds` | `List[CharacterSeed]` | Initial character definitions. |

#### `CharacterSeed`

| Field | Type | Description |
| :--- | :--- | :--- |
| `character_id` | `str` | Unique slug identifier. |
| `display_name` | `str` | Character's display name. |
| `base_object` | `str` | What the character is (e.g., "cat", "robot"). |
| `role` | `str` | Narrative role (protagonist, mentor, etc.). |
| `personality_traits` | `List[str]` | Key traits. |
| `visual_description` | `str` | Appearance description. |
| `voice_profile` | `str` | Voice style hints for TTS/dialogue. |

#### `EpisodeOutline`

| Field | Type | Description |
| :--- | :--- | :--- |
| `episode_number` | `int` | Episode index. |
| `title` | `str` | Episode title. |
| `summary` | `str` | Brief plot summary. |
| `opening_hook` | `str` | Opening scene hook. |
| `ending_moment` | `str` | Closing beat. |

### Screenwriter Output (`src/steps/screenwriter.py`)

#### `AllEpisodesScript`
Generated in a single LLM call for narrative continuity.

| Field | Type | Description |
| :--- | :--- | :--- |
| `episodes` | `List[EpisodeScript]` | All episode scripts. |

#### `EpisodeScript`

| Field | Type | Description |
| :--- | :--- | :--- |
| `episode_number` | `int` | Episode index. |
| `title` | `str` | Episode title. |
| `cold_open_hook` | `str` | Opening hook line. |
| `scenes` | `List[SceneBeat]` | 4-8 scene beats. |
| `episode_ending` | `str` | Closing moment. |

#### `SceneBeat`

| Field | Type | Description |
| :--- | :--- | :--- |
| `scene_id` | `str` | Unique scene identifier. |
| `primary_character_id` | `str` | Main character in the scene. |
| `characters_present` | `List[str]` | All characters in the scene. |
| `location_slug` | `str` | Location identifier. |
| `dialogue` | `str` | Scene dialogue. |
| `voice_profile` | `str` | TTS voice direction. |
| `visual_context` | `str` | What the viewer should see. |
| `mood` | `str` | Scene mood/tone. |
| `beat_note` | `str` | Narrative purpose of the scene. |

### Casting Output (`src/steps/casting.py`)

#### `CharacterSheet`
Expanded from `CharacterSeed` with additional production details.

| Field | Type | Description |
| :--- | :--- | :--- |
| *(inherits all CharacterSeed fields)* | | |
| `emotional_range` | `str` | Range of emotions the character displays. |
| `signature_gesture` | `str` | Distinctive physical mannerism. |

### World Builder Output (`src/steps/world_builder.py`)

#### `WorldLayout`

| Field | Type | Description |
| :--- | :--- | :--- |
| `location_id` | `str` | Unique slug identifier. |
| `display_name` | `str` | Human-readable location name. |
| `visual_description` | `str` | Detailed description (50+ words). |
| `atmosphere` | `str` | Overall atmosphere/feel. |
| `lighting_notes` | `str` | Lighting direction. |
| `color_palette` | `List[str]` | Dominant colors. |

### Director Output (`src/steps/director.py`)

#### `DirectorShots`

| Field | Type | Description |
| :--- | :--- | :--- |
| `episode_number` | `int` | Episode index. |
| `shots` | `List[DirectorShot]` | Sequence of shots. |

#### `DirectorShot`

| Field | Type | Description |
| :--- | :--- | :--- |
| `scene_id` | `str` | Reference to SceneBeat. |
| `primary_character_id` | `str` | Main character in shot. |
| `location_id` | `str` | Location reference. |
| `camera_angle` | `str` | Camera angle direction. |
| `shot_type` | `str` | Shot type (close-up, wide, etc.). |
| `camera_movement` | `str` | Camera movement direction. |
| `veo_prompt` | `str` | Final Veo 3.1 prompt (60-100 words). |
| `dialogue` | `str` | Dialogue for the shot. |
| `voice_profile` | `str` | Voice direction. |

---

## 3. Pipeline State Models (`src/pipeline_state.py`)

These models manage the persistent state of the **7-Step Animation Pipeline**.

### `PipelineState`

| Field | Type | Description |
| :--- | :--- | :--- |
| `project_title` | `str` | Name of the series. |
| `created_at` | `str` | ISO timestamp of project creation. |
| `series_steps` | `Dict[str, StepStatus]` | Status of pre-production steps (writer, screenwriter, casting, world_builder). |
| `episodes` | `Dict[int, EpisodeState]` | Map of episode numbers to their states. |

### `StepStatus`

| Field | Type | Description |
| :--- | :--- | :--- |
| `step_name` | `str` | Name of the step. |
| `completed` | `bool` | Whether the step finished successfully. |
| `started_at` | `str` | ISO timestamp when started. |
| `completed_at` | `str` | ISO timestamp when completed. |
| `error` | `str` | Error message if failed. |
| `artifact_paths` | `List[str]` | Paths to output files. |

### `EpisodeState`

| Field | Type | Description |
| :--- | :--- | :--- |
| `episode_number` | `int` | Episode index. |
| `steps` | `Dict[str, StepStatus]` | Status of production steps (director, scene_generator, editor). |

---

## 4. Operational Models (`src/pipeline.py`)

### `PipelineStatus`
Yielded by all pipeline generators for UI progress tracking.

| Field | Type | Description |
| :--- | :--- | :--- |
| `step` | `int` | Current step index. |
| `message` | `str` | User-friendly status message. |
| `data` | `Dict` | Optional payload (IDs, paths, script previews). |
| `is_error` | `bool` | True if an error occurred. |
| `retry_gate` | `bool` | True if the pipeline should pause for user review. |

### `SceneAssets` (`src/pipeline.py`)
Per-scene asset bundle for the Stock Footage route.

| Field | Type | Description |
| :--- | :--- | :--- |
| `narration` | `str` | Scene narration text. |
| `visual_queries` | `List[str]` | Pexels search queries. |
| `audio_path` | `str` | Path to TTS audio file. |
| `video_path` | `str` | Path to stock video clip. |
| `timestamps` | `List` | Word-level Whisper timestamps. |
| `poster_path` | `str` | Optional poster image path. |

---

## 5. Web Dashboard Models (`src/server.py`, `src/project_manager.py`)

### `Project`

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `str` | Unique project identifier. |
| `name` | `str` | Project display name. |
| `mode` | `str` | Production route (stock/animation). |
| `params` | `Dict` | Route-specific parameters. |
| `current_step` | `str` | Active pipeline step. |
| `status` | `str` | Project status (pending, running, completed, error). |
| `created_at` | `str` | Creation timestamp. |
| `updated_at` | `str` | Last update timestamp. |
| `step_data` | `Dict` | Per-step output data. |
| `error` | `str` | Error message if failed. |
