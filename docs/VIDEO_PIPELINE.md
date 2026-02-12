# Video Generation Pipeline

Technical documentation for the StudioZero video generation pipeline. This covers every stage of the system, from movie name input to final MP4 output.

## Pipeline Overview

```
Movie Name
    |
    v
[Step 1] Movie Data Retrieval & Script Generation
    |        Wikipedia/TMDB -> Gemini LLM (Groq fallback)
    |        Output: VideoScript with 6 scenes
    v
[Step 2] Parallel Asset Generation
    |        TTS Audio (Gemini) + Stock Video (Pexels) per scene
    |        Ending scene: movie poster + title reveal
    v
[Step 3] Whisper Transcription
    |        Word-level timestamps from audio
    v
[Step 4] Subtitle Generation
    |        ASS format, Hormozi-style word-by-word captions
    v
[Step 5] FFmpeg Rendering
    |        Normalize -> Concat -> Audio ducking -> Subtitle burn -> Encode
    v
output/final/<movie>.mp4  (1080x1920, 30fps, H.264, AAC)
```

The pipeline is implemented as a Python generator in `src/pipeline.py` that yields `PipelineStatus` objects at each step, enabling real-time progress tracking.

---

## Step 1: Movie Data Retrieval & Script Generation

**Module**: `src/narrative.py`, `src/moviedbapi.py`

### 1A. Movie Data Fetching

Two data sources with automatic fallback:

**Wikipedia (primary)**:
- Searches for the movie name directly, then falls back to `"{name} (film)"` format
- Extracts the plot section from the article
- Library: `Wikipedia-API`

**TMDB (secondary)**:
- Search endpoint: `/search/movie`
- Detail endpoint: `/movie/{id}`
- Fetches: release year, poster URL, tagline, genre list
- Auth: API key or Bearer token
- Poster downloaded to `output/temp/{movie}/poster.jpg`

### 1B. Script Generation

The movie data is passed to an LLM with a comprehensive system prompt that instructs it to generate a 6-scene narrative.

**Primary model**: Google Gemini (`gemini-flash-latest` or `gemini-2.5-flash-preview`)
- Uses structured JSON output with Pydantic schema enforcement
- Single API call returns the full `VideoScript`

**Fallback model**: Groq LLaMA 3.3 70B
- Activated when Gemini fails
- Uses `tenacity` retry with exponential backoff (max 5 attempts)
- Same system prompt, parses JSON response into Pydantic model

### Script Structure

```
VideoScript
├── title: str                    "The Matrix"
├── genre: str                    "sci-fi"
├── overall_mood: str             "tense"
├── selected_voice_id: str        "am_adam"
├── selected_music_file: str      "epic-cinematic-background-music.mp3"
├── lang_code: str                "a" (American)
├── bpm: int                      120
└── scenes: List[Scene]           (exactly 6)
    └── Scene
        ├── scene_index: int      0-5
        ├── narration: str        25-40 words, conversational
        ├── visual_queries: [str] 3 queries (literal, abstract, atmospheric)
        ├── visual_style_modifiers: [str]
        ├── mood: str             tense, dramatic, happy, etc.
        └── tts_speed: float      1.0-1.6
```

### Narrative Arc

The 6 scenes follow a structured arc:
| Scene | Role | Purpose |
|-------|------|---------|
| 0 | Hook | Grab attention in first 3 seconds |
| 1 | Context | Introduce protagonist and setting |
| 2 | Escalation | Raise stakes, introduce conflict |
| 3 | Turn | Unexpected twist or revelation |
| 4 | Climax | Peak dramatic moment |
| 5 | Resolution | Ending with movie title reveal (poster) |

### Voice Selection

The LLM selects from 30 Gemini TTS voices based on genre fit:

| Voice Category | Voices | Best For |
|----------------|--------|----------|
| Authoritative male | Orus, Fenrir | Action, thriller, crime, war |
| Mysterious female | Leda, Kore | Horror, mystery, sci-fi |
| Upbeat female | Puck, Zephyr | Comedy, animation, family |
| Warm female | Aoede, Achernar | Romance, drama |
| Academic British | Schedar | Documentary, history |
| Elegant British | Gacrux | Period drama, fantasy |

### Music Selection

Background music auto-selected based on genre from `assets/music/<genre>/`:

Supported genres (17): action, thriller, horror, comedy, romance, drama, documentary, sci-fi, mystery, adventure, animation, war, history, fantasy, crime, family, western, musical.

Each genre has 1-5 tracks. The LLM picks from the available tracks for the detected genre.

### Caching

The full `VideoScript` plus movie data is cached to `output/temp/{movie}/pipeline_cache.json`. This enables:
- `--offline` mode (re-render without API calls)
- Faster re-runs on the same movie
- Manual script editing before re-rendering

---

## Step 2: Parallel Asset Generation

**Modules**: `src/gemini_tts.py`, `src/stock_media.py`, `src/pipeline.py`

For each of the 6 scenes, audio and video generation happen in parallel using `ThreadPoolExecutor` (2 workers per scene).

### 2A. Text-to-Speech Audio

**Service**: Google Gemini 2.5 Flash TTS
- Model: `gemini-2.5-flash-preview-tts`
- Output: WAV (24 kHz, 16-bit mono)

**Process per scene**:
1. Select voice from `VideoScript.selected_voice_id`
2. Map voice ID to Gemini voice name (e.g., `am_adam` -> `Orus`)
3. Build style prompt from mood (e.g., `tense` -> `"Speak with tension and urgency"`)
4. Generate audio with specified speed multiplier
5. Save to `output/temp/{movie}/scene_{N}_audio.wav`
6. Calculate duration from audio data length

**Mood-to-style prompt mapping**:

| Mood | Style Prompt | Speed Range |
|------|-------------|-------------|
| tense | "Speak with tension and urgency" | 0.95x |
| suspenseful | "Narrate with building suspense, slightly slower" | 1.15x |
| dramatic | "Deliver dramatically with emotional weight" | 1.0x |
| sad | "Speak with somber, melancholic tone" | 1.0x |
| happy | "Narrate with warmth and happiness" | 1.25x |
| exciting | "Speak with excitement and enthusiasm" | 1.45x |
| calm | "Narrate in calm, measured, peaceful tone" | 1.2x |
| mysterious | "Speak with air of mystery and intrigue" | 1.05x |
| action | "Narrate with intensity and dynamic energy" | 1.4x |
| horror | "Speak with dread and unease" | 1.05x |
| comedic | "Deliver with light-hearted amusement" | 1.25x |
| epic | "Narrate with grandeur and majesty" | 1.15x |
| neutral | "Narrate clearly, naturally, professionally" | 1.15x |

All speeds are boosted 25% from base for social media pacing.

**Fallback chain**:
1. Generate with original narration text
2. If blocked by safety filter: sanitize text (remove quotes, years, proper nouns) and retry
3. If all attempts fail: create 3-second silent WAV as placeholder

### 2B. Stock Video Download

**Service**: Pexels API (`/videos/search`)

**Process per scene**:
1. Take the 3 `visual_queries` from the scene
2. For each query, append `"cinematic 4k"` and search Pexels
3. Filter for portrait (9:16) orientation videos, minimum 5 seconds
4. Select video file closest to 1080x1920 resolution
5. Download and save to `output/temp/{movie}/scene_{N}_video.mp4`

**Fallback chain**:
```
Query 1 (literal) -> Query 2 (abstract) -> Query 3 (atmospheric) -> Random local fallback
```

Local fallback videos are stored in `assets/basevideos/` (24 clips, video1.mp4 through video24.mp4).

**Video metadata tracked**:
- Dimensions, duration, Pexels URL, photographer credit
- Whether fallback was used and which queries failed

### 2C. Ending Scene (Scene 5)

The final scene gets special treatment:

1. **Narration**: Generated from randomized templates:
   - `"And that... was {title}. Released in {year}."`
   - `"This was the story of {title}, from {year}."`
   - `"That's {title} for you. Out since {year}."`

2. **Audio**: TTS at slightly slower speed (1.2x) for dramatic reveal effect

3. **Video**: Static movie poster image (downloaded from TMDB in Step 1). FFmpeg converts the static image to a video matching the audio duration.

4. If TTS is blocked for the ending, a 3-second silent audio fallback is used.

---

## Step 3: Whisper Transcription

**Module**: `src/pipeline.py` (uses `whisper` package)

**Model**: OpenAI Whisper "base" (lazy-loaded on first use)

### Process

1. For each scene audio file, run Whisper with `word_timestamps=True`
2. Extract segments with word-level timing:
   ```json
   {
     "text": "In a world where nothing is real",
     "start": 0.0,
     "end": 2.5,
     "words": [
       {"word": "In", "start": 0.0, "end": 0.2},
       {"word": "a", "start": 0.2, "end": 0.3},
       {"word": "world", "start": 0.3, "end": 0.7},
       ...
     ]
   }
   ```

3. Apply cumulative timestamp offset across scenes:
   - Scene 0: offset = 0
   - Scene 1: offset = duration(scene_0)
   - Scene 2: offset = duration(scene_0) + duration(scene_1)
   - etc.

4. Merge all segments into a single `all_whisper_segments` list with global timestamps

This produces frame-accurate word timing for the entire video duration.

---

## Step 4: Subtitle Generation

**Module**: `src/subtitles.py`

**Format**: ASS (Advanced SubStation Alpha) via `pysubs2`

### Hormozi Style

The subtitles use a style inspired by Alex Hormozi's social media videos:

| Property | Value |
|----------|-------|
| Font | Arial Black (fallback: Roboto-Bold) |
| Font Size | 80pt |
| Primary Color | White (#00FFFFFF) |
| Outline | Black, 4pt border |
| Shadow | Semi-transparent black |
| Alignment | Center (position 5) |
| Border Style | 1 (outline + shadow) |
| Margins | 20px left/right |

### Process

1. Extract all words from Whisper segments with start/end timestamps
2. Group words (default: 1 word per line for single-word display)
3. For each word, create an `SSAEvent`:
   - Start time: word start (milliseconds)
   - End time: word end (minimum 100ms display time)
   - Position: fixed center (960, 540 in 1920x1080 coordinate space)
   - Text: lowercased, punctuation stripped for clean display

4. Output: `output/temp/{movie}/subtitles.ass`

---

## Step 5: FFmpeg Video Rendering

**Module**: `src/renderer.py`

This is the most complex step, composing all generated assets into a final video.

### 5A. Video Normalization

Each scene video is normalized to consistent specs:
- Resolution: 1080x1920 (scale + crop to fill)
- Frame rate: 30 fps
- Pixel format: yuv420p
- Codec: H.264

If a video is shorter than its corresponding audio, it loops (`-stream_loop -1`) and is trimmed to audio duration.

For the ending scene, the poster image is converted to a video of the correct duration.

### 5B. Video Concatenation

All normalized scene videos are concatenated using FFmpeg's concat demuxer:
```
ffmpeg -f concat -safe 0 -i videos.txt -c:v copy -an concat_video.mp4
```

A 1-second silent poster segment is appended at the end if an ending scene exists.

### 5C. Audio Mixing & Ducking

**Voice track**: All scene audio WAVs concatenated and normalized to 44.1kHz stereo.

**Background music**: Selected genre track, looped infinitely (`aloop` filter), base volume 0.3.

**Sidechain compression** (audio ducking):
```
sidechaincompress=threshold=0.1:ratio=10:attack=50:release=200
```

| Parameter | Value | Effect |
|-----------|-------|--------|
| Threshold | 0.1 | Duck when voice exceeds 10% level |
| Ratio | 10:1 | Aggressive compression (near-mute music) |
| Attack | 50ms | Quick duck when voice starts |
| Release | 200ms | Gradual music return after voice stops |

The ducked music and voice are mixed:
```
amix=inputs=2:duration=first:dropout_transition=2
```

### 5D. Subtitle Burning

ASS subtitles are burned directly into the video frames using FFmpeg's `ass` filter:
```
ass='/path/to/subtitles.ass'
```

Requires FFmpeg compiled with `libass` support. If not available, subtitles are skipped and a warning is logged.

### 5E. Final Encoding

```
ffmpeg \
  -i concat_video.mp4 \
  -i concat_voice.wav \
  -i background_music.mp3 \
  -filter_complex "[video_filters];[audio_filters]" \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  -t {total_duration} \
  output/final/{movie_name}.mp4
```

### Output Specs

| Property | Value |
|----------|-------|
| Resolution | 1080x1920 |
| Aspect Ratio | 9:16 (portrait) |
| Frame Rate | 30 fps |
| Video Codec | H.264 (libx264) |
| CRF | 23 |
| Audio Codec | AAC |
| Audio Bitrate | 192 kbps |
| Pixel Format | yuv420p |
| Duration | ~45-60 seconds |

---

## Post-Pipeline: Batch Processing & Distribution

**Modules**: `src/batch_runner.py`, `src/cloud_services.py`, `src/marketing.py`

When run via the batch runner, additional steps occur after video generation:

### Social Media Caption Generation

**Service**: Groq LLaMA via `src/marketing.py`

Generates viral captions with:
- Hook-first format (attention-grabbing opening line, max 150 chars)
- 1-2 descriptive sentences
- Soft call-to-action for follower growth
- Genre-specific hashtags (15+ genres mapped to relevant tags)

### Cloud Upload

**Google Drive** (via service account):
- Video uploaded to `DRIVE_VIDEO_FOLDER_ID`
- Pipeline log (JSON) uploaded to `DRIVE_LOGS_FOLDER_ID`
- Shareable links generated and stored in the Sheet

### Status Tracking

The Google Sheet row is updated with:
- `Status`: Processing -> Completed (or Failed)
- `start_time` / `end_time`: timestamps
- `video_link`: Google Drive shareable link
- `log_link`: Pipeline log link
- `icloud_link`: Local path (macOS) or "Saved to Drive (Cloud)"
- `caption`: Generated social media caption
- `ytshorts_status` / `ig_status` / `tiktok_status`: "Ready for Upload"
- `notes`: Error details on failure (blank on success)

### iCloud Export (macOS)

On macOS, the final video is copied to the iCloud Drive folder for easy access on mobile devices. Default path: `~/Library/Mobile Documents/com~apple~CloudDocs/StudioZero/Videos`.

---

## Error Handling & Fallback Summary

| Component | Error | Fallback |
|-----------|-------|----------|
| Movie data | Wikipedia fails | TMDB API |
| Movie plot | No plot found | TMDB overview field |
| Script generation | Gemini fails | Groq LLaMA (5 retries, exponential backoff) |
| TTS audio | Safety filter blocks | Sanitize text and retry |
| TTS audio | All retries fail | 3-second silent WAV |
| Stock video | Pexels query 1 fails | Try query 2, then query 3 |
| Stock video | All queries fail | Random clip from `assets/basevideos/` |
| Subtitle burning | FFmpeg lacks libass | Skip subtitles, continue render |
| Batch job | Pipeline crashes | Mark as "Failed" with error in Sheet |

---

## Intermediate Files

For each movie, the following files are created in `output/temp/{movie_name}/`:

```
output/temp/{movie_name}/
├── pipeline_cache.json     # Full state cache (script, assets, metadata)
├── scene_0_audio.wav       # TTS audio for scene 0
├── scene_0_video.mp4       # Stock video for scene 0
├── scene_1_audio.wav
├── scene_1_video.mp4
├── scene_2_audio.wav
├── scene_2_video.mp4
├── scene_3_audio.wav
├── scene_3_video.mp4
├── scene_4_audio.wav
├── scene_4_video.mp4
├── ending_audio.wav        # TTS audio for ending scene
├── poster.jpg              # Movie poster from TMDB
└── subtitles.ass           # Generated ASS subtitles
```

These files persist after rendering, enabling re-runs with `--offline` flag.

---

## Performance

Typical generation time per video: **4-8 minutes**

| Step | Duration | Bottleneck |
|------|----------|-----------|
| Step 1: Script | ~30s | LLM API latency |
| Step 2: Assets | ~60-90s | Pexels downloads (parallel helps) |
| Step 3: Whisper | ~45s | Model loading + inference |
| Step 4: Subtitles | ~5s | Minimal (file generation) |
| Step 5: Render | ~120-180s | FFmpeg encoding |

Parallelization in Step 2 significantly reduces total time - TTS and video download run simultaneously per scene.
