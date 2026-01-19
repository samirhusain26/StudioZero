# StudioZero

StudioZero is an AI-powered video generation pipeline that creates short, stylized vertical videos (9:16 aspect ratio) from movie titles. Input a movie name, and the system automatically fetches movie data, generates a compelling narrative via LLM, synthesizes voiceovers, downloads matching stock footage, and renders a final video with Hormozi-style animated captions.

**Target Output**: Viral-ready social media videos suitable for TikTok, Instagram Reels, and YouTube Shorts.

## How It Works

```
Movie Name → Wikipedia/TMDB → Groq LLM → Gemini TTS + Pexels + Whisper → FFmpeg → Video
```

### The 5-Step Pipeline

The pipeline is implemented as a **generator-based orchestration engine** that yields real-time progress updates:

#### Step 1: Movie Data Retrieval & Script Generation
- Searches Wikipedia for movie data (with TMDB fallback)
- Extracts plot, year, tagline, and poster path
- Passes data to Groq LLM with a comprehensive system prompt
- LLM generates a `VideoScript` with:
  - Genre classification and voice selection (from 30 available voices)
  - 6-scene narrative arc with detailed annotations
  - Visual search queries per scene (literal, abstract, atmospheric)
  - Mood-based pacing recommendations

#### Step 2: Parallel Asset Generation
- **TTS (Parallel)**: Gemini generates narration audio per scene with mood-based style prompts
- **Stock Video (Parallel)**: Pexels API downloads portrait footage using 3 visual queries per scene
- **Ending Scene**: Special handling for movie poster reveal with Ken Burns zoom effect
- Fallback to local base videos if Pexels search fails

#### Step 3: Whisper Transcription
- Whisper "base" model extracts word-level timestamps from each audio file
- Cumulative timestamp adjustment across all scenes for frame-accurate sync

#### Step 4: Karaoke Subtitle Generation
- Generates ASS (Advanced SubStation Alpha) subtitles
- Hormozi-style formatting: Arial Black 80pt, white with black outline
- Word-by-word appearance based on Whisper timestamps

#### Step 5: Video Rendering
- **Video Normalization**: All clips normalized to 1080x1920, 30fps, H.264
- **Audio Mixing**: Voiceover concatenation with looped background music
- **Audio Ducking**: Sidechain compression reduces music when voice is present
- **Subtitle Burning**: ASS subtitles overlaid via FFmpeg `ass` filter
- **Final Encode**: H.264 MP4 with AAC audio (192kbps)

## Technology Stack

| Component | Technology | Details |
|-----------|------------|---------|
| **Language** | Python 3.10+ | Modern async/threading support |
| **LLM** | Groq API | Llama 3.3-70b-versatile model |
| **Text-to-Speech** | Google Gemini 2.5 Flash TTS | 30 voices, mood-based style prompts |
| **Transcription** | OpenAI Whisper | Base model with word-level timestamps |
| **Stock Video** | Pexels API | Portrait filtering, 3-query fallback |
| **Video Rendering** | FFmpeg | filter_complex pipelines, Ken Burns |
| **Subtitles** | pysubs2 | ASS format, Hormozi-style captions |
| **Movie Data** | Wikipedia API + TMDB | Dual-source with fallback |
| **Data Validation** | Pydantic 2.0+ | Structured script models |
| **Retry Logic** | tenacity | Exponential backoff for rate limits |
| **Config** | python-dotenv | Environment variable management |
| **Cloud Storage** | Google Drive API | Video/log uploads via service account |
| **Job Queue** | Google Sheets API | Batch processing with status tracking |
| **Sheets Client** | gspread | Pythonic Google Sheets interface |

## Project Structure

```
StudioZero/
├── src/                          # Main application code
│   ├── app.py                    # CLI entry point with argument parsing
│   ├── pipeline.py               # 5-step orchestration engine (generator-based)
│   ├── narrative.py              # Groq LLM script generation with Pydantic models
│   ├── moviedbapi.py             # Wikipedia/TMDB client for movie data
│   ├── gemini_tts.py             # Google Gemini TTS voice synthesis
│   ├── stock_media.py            # Pexels API video download with fallback
│   ├── subtitles.py              # ASS subtitle generation (word-by-word captions)
│   ├── renderer.py               # FFmpeg video composition with Ken Burns
│   ├── config.py                 # Environment variables & path management
│   ├── config_mappings.py        # Voice/music genre mappings
│   ├── batch_runner.py           # Batch processing from Google Sheets queue
│   ├── cloud_services.py         # Google Drive/Sheets integration
│   └── marketing.py              # Social media caption generation
├── assets/
│   ├── basevideos/               # Fallback stock footage (.mp4 clips)
│   ├── music/                    # Background music tracks by genre
│   └── creds/                    # Google service account credentials
├── output/
│   ├── temp/                     # Intermediate files (audio, video, metadata)
│   ├── final/                    # Final rendered videos
│   └── pipeline_logs/            # Script generation logs (JSON)
├── requirements.txt              # Python dependencies
├── .env.template                 # Environment variable template
└── .env                          # API keys and configuration (create from template)
```

## Module Overview

### Core Modules

| Module | Responsibility |
|--------|---------------|
| **app.py** | CLI interface, argument parsing, logging setup, pipeline orchestration |
| **pipeline.py** | Generator-based 5-step orchestration, caching, parallel scene processing |
| **narrative.py** | Groq LLM integration, system prompts, Pydantic models for scripts |
| **moviedbapi.py** | Wikipedia/TMDB API client, plot extraction, poster download |
| **gemini_tts.py** | Gemini TTS API, 30 voices, mood-based style prompts, WAV generation |
| **stock_media.py** | Pexels API, portrait filtering, 3-query fallback, local video fallback |
| **subtitles.py** | ASS subtitle generation, Hormozi-style formatting, word timing |
| **renderer.py** | FFmpeg composition, Ken Burns, audio ducking, subtitle burning |
| **config.py** | Environment loading, path management, API key validation |
| **config_mappings.py** | Voice metadata, music-genre mapping, mood-speed mapping |
| **batch_runner.py** | Batch processing loop, Google Sheet job queue, iCloud export |
| **cloud_services.py** | Google Drive uploads, Google Sheets read/write, service account auth |
| **marketing.py** | LLM-powered social caption generation, genre-based hashtags |

### Key Data Models (Pydantic)

```python
VideoScript:
  - title: str              # Movie title
  - genre: str              # Primary genre classification
  - overall_mood: str       # TTS voice tone consistency
  - selected_voice_id: str  # Chosen voice for narration
  - selected_music_file: str # Background music filename
  - scenes: List[Scene]     # 6 scene objects

Scene:
  - scene_index: int        # 0-5 index
  - narration: str          # 25-40 word conversational text
  - visual_queries: List[str] # 3 search queries (literal, abstract, atmospheric)
  - mood: str               # Scene emotional tone
  - tts_speed: float        # 1.0-1.6 speed multiplier

SceneAssets:
  - audio_path: Path        # Generated WAV file
  - audio_duration: float   # Duration in seconds
  - video_path: Path        # Downloaded/fallback video
  - word_timestamps: List   # Whisper-extracted timing
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Movie Name Input                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Movie Data Retrieval & Script Generation               │
│  ├─ Wikipedia/TMDB Search                                       │
│  ├─ Extract Plot, Year, Tagline                                 │
│  └─ Groq LLM → VideoScript (6 scenes, voice, music, moods)      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Parallel Asset Generation (ThreadPoolExecutor)         │
│  ├─ Scene 1-5:                                                  │
│  │   ├─ Gemini TTS → Audio (WAV)                                │
│  │   └─ Pexels API → Video (MP4) [or local fallback]            │
│  └─ Scene 6 (Ending):                                           │
│      ├─ Poster Download → Ken Burns Video                       │
│      └─ Closing Narration Audio                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Whisper Transcription                                  │
│  └─ Word-level timestamps with cumulative offset adjustment     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Subtitle Generation                                    │
│  └─ ASS format (Hormozi-style: 80pt Arial Black, word-by-word)  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: FFmpeg Rendering                                       │
│  ├─ Normalize Videos (1080x1920, 30fps, H.264)                  │
│  ├─ Concatenate Videos + Audio                                  │
│  ├─ Loop Background Music                                       │
│  ├─ Sidechain Compression (audio ducking)                       │
│  ├─ Burn ASS Subtitles                                          │
│  └─ Final H.264 + AAC Encode                                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Output: output/final/<movie>.mp4                │
└─────────────────────────────────────────────────────────────────┘
```

## Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows (via chocolatey)
choco install ffmpeg
```

FFmpeg must be compiled with `libx264` and `libass` support.

### 3. Configure API Keys

Copy the template and fill in your values:

```bash
cp .env.template .env
```

**Required API Keys (for video generation):**

```bash
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
PEXELS_API_KEY=your_pexels_key
TMDB_API_KEY=your_tmdb_key  # Optional but recommended
```

**Get API Keys:**
- **Groq**: [console.groq.com/keys](https://console.groq.com/keys)
- **Gemini**: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Pexels**: [pexels.com/api](https://www.pexels.com/api/)
- **TMDB**: [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)

### 4. Configure Batch Processing (Optional)

For automated batch processing from Google Sheets:

**a) Create a Google Service Account:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Create a new service account
3. Enable Google Drive API and Google Sheets API
4. Download the JSON credentials file
5. Place it in `assets/creds/drive_credentials.json`

**b) Add batch configuration to `.env`:**

```bash
# Path to service account credentials
DRIVE_APPLICATION_CREDENTIALS=assets/creds/drive_credentials.json

# Google Sheet URL with movie queue
BATCH_SHEET_URL=https://docs.google.com/spreadsheets/d/your_sheet_id

# Google Drive folder IDs for uploads
DRIVE_VIDEO_FOLDER_ID=your_video_folder_id
DRIVE_LOGS_FOLDER_ID=your_logs_folder_id
```

**c) Share your Google Sheet and Drive folders** with the service account email (found in the JSON file).

### 5. Add Fallback Footage (Optional)

Place `.mp4` video clips in `assets/basevideos/` for when Pexels search fails. These should be portrait (9:16) clips.

### 6. Add Background Music (Optional)

Place music tracks in `assets/music/<genre>/` folders. Supported genres: action, comedy, drama, horror, romance, sci-fi, thriller, etc.

## Usage

### Basic Usage

```bash
python -m src.app "Inception"
```

### CLI Options

```bash
# Full pipeline with verbose logging
python -m src.app "The Matrix" --verbose

# Generate assets only (skip final render)
python -m src.app "Pulp Fiction" --assets-only

# Use cached data (offline mode)
python -m src.app "Interstellar" --offline

# Custom output path
python -m src.app "Dune" -o custom_output.mp4
```

### Output

- **Final Video**: `output/final/<movie_name>.mp4`
- **Intermediate Files**: `output/temp/<movie_name>/`
- **Pipeline Logs**: `output/pipeline_logs/`
- **Cache**: `pipeline_cache.json`

## Batch Processing

Process multiple movies automatically from a Google Sheet queue.

### Google Sheet Setup

Create a sheet with these columns:
| Column | Description |
|--------|-------------|
| `movie_title` | Movie name to process |
| `Status` | Set to `Pending` for jobs to run |
| `start_time` | Auto-populated when processing starts |
| `end_time` | Auto-populated when processing completes |
| `video_link` | Auto-populated with Google Drive link |
| `log_link` | Auto-populated with pipeline JSON log link |
| `icloud_link` | Auto-populated with local iCloud path |
| `caption` | Auto-populated with generated social caption |
| `notes` | Auto-populated with error details (blank on success) |

### Running Batch Processing

```bash
# Use default sheet from .env
python -m src.batch_runner

# Override sheet URL
python -m src.batch_runner --sheet-url "https://docs.google.com/spreadsheets/d/..."

# Verbose logging
python -m src.batch_runner --verbose
```

### Batch Processing Pipeline

For each pending job, the batch runner:
1. Marks row as `Processing` with start timestamp
2. Runs the full video generation pipeline
3. Generates a viral social media caption (via Groq LLM)
4. Copies video to iCloud (macOS)
5. Uploads video to Google Drive
6. Uploads pipeline log to Google Drive
7. Updates row with `Completed` status and all links

Failed jobs are marked with error details in the `notes` column.

## Advanced Features

### Generator-Based Progress Reporting
The pipeline yields `PipelineStatus` objects for real-time UI feedback, enabling progress bars and status updates.

### Caching System
`pipeline_cache.json` stores generated scripts for offline processing and faster re-runs.

### Multi-Level Fallback
```
Pexels Query 1 → Pexels Query 2 → Pexels Query 3 → Local Fallback Video
```

### Audio Ducking
Professional sidechain compression automatically lowers music volume when voice is present:
- Threshold: 0.1
- Ratio: 10:1
- Attack: 50ms
- Release: 200ms

### Ken Burns Effect
Subtle zoom applied to static poster images for dynamic ending sequences.

### Voice Selection
30 available voices (14 female, 16 male) with genre-optimized recommendations:
- Dramatic: Orus, Fenrir
- Conversational: Kore, Puck
- Warm: Aoede, Leda
- Energetic: Zephyr, Charon

### Mood-Based TTS Pacing
14 emotional contexts with optimized speech speeds (1.0-1.6x):
- Tense/Suspenseful: 0.95x
- Exciting/Action: 1.15x
- Calm/Reflective: 0.9x
- Dramatic: 1.0x

### Social Media Caption Generation
Automated viral caption generation for TikTok/Instagram Reels:
- Hook-first format optimized for engagement
- Genre-specific hashtag selection (15 genres supported)
- Conversational tone via Groq LLM
- Includes soft CTA for follower growth

## Requirements

- Python 3.10+
- FFmpeg 4.0+ (with libx264, libass)
- FFprobe (included with FFmpeg)
- ~2GB RAM for Whisper transcription
- Internet connection for API calls

## License

MIT License
