# StudioZero

AI-powered video generation pipeline that creates short, vertical (9:16) social media videos from movie titles. Input a movie name and the system automatically fetches movie data, generates a narrative script, synthesizes voiceovers, downloads matching stock footage, and renders a final video with animated captions.

**Output**: Viral-ready videos for TikTok, Instagram Reels, and YouTube Shorts.

## Pipeline at a Glance

```
Movie Name → Wikipedia/TMDB → Gemini LLM → Gemini TTS + Pexels + Whisper → FFmpeg → Video
```

| Step | What Happens | Services Used |
|------|-------------|---------------|
| 1. Script Generation | Fetch movie data, generate 6-scene narrative | Wikipedia, TMDB, Gemini (Groq fallback) |
| 2. Asset Generation | Parallel TTS audio + stock video per scene | Gemini TTS, Pexels API |
| 3. Transcription | Word-level timestamp extraction | OpenAI Whisper (local) |
| 4. Subtitles | Hormozi-style word-by-word captions | pysubs2 (ASS format) |
| 5. Rendering | Compose video with audio ducking + subtitles | FFmpeg |

For the full technical breakdown, see [VIDEO_PIPELINE.md](docs/VIDEO_PIPELINE.md).

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
choco install ffmpeg
```

FFmpeg must include `libx264` and `libass` support.

### 3. Configure API Keys

```bash
cp .env.template .env
```

Fill in your keys:

| Key | Source | Required |
|-----|--------|----------|
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Yes (LLM + TTS) |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Yes (fallback + captions) |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) | Yes (stock video) |
| `TMDB_API_KEY` | [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) | Recommended (movie data) |

### 4. Generate a Video

```bash
python -m src.app "Inception"
```

Output lands in `output/final/Inception.mp4`.

## Usage

### Single Video

```bash
# Basic
python -m src.app "The Matrix"

# Verbose logging
python -m src.app "The Matrix" --verbose

# Generate assets only (skip render)
python -m src.app "Pulp Fiction" --assets-only

# Use cached data (no API calls)
python -m src.app "Interstellar" --offline

# Custom output path
python -m src.app "Dune" -o custom_output.mp4
```

### Batch Processing

Process multiple movies from a Google Sheet queue:

```bash
# Process all pending
python -m src.batch_runner

# Override sheet URL
python -m src.batch_runner --sheet-url "https://docs.google.com/spreadsheets/d/..."

# Limit to N movies
python -m src.batch_runner --limit 5

# Verbose
python -m src.batch_runner --verbose
```

#### Google Sheet Setup

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
| `ytshorts_status` | Auto-populated posting status |
| `ig_status` | Auto-populated posting status |
| `tiktok_status` | Auto-populated posting status |

Share the sheet with your Google service account email.

#### Batch Setup

1. Create a [Google service account](https://console.cloud.google.com/iam-admin/serviceaccounts) with Drive + Sheets API enabled
2. Download credentials JSON to `assets/creds/drive_credentials.json`
3. Add to `.env`:
   ```bash
   DRIVE_APPLICATION_CREDENTIALS=assets/creds/drive_credentials.json
   BATCH_SHEET_URL=https://docs.google.com/spreadsheets/d/your_sheet_id
   DRIVE_VIDEO_FOLDER_ID=your_video_folder_id
   DRIVE_LOGS_FOLDER_ID=your_logs_folder_id
   ```
4. Share your Sheet and Drive folders with the service account email

#### macOS Automation

Trigger batch processing via macOS Shortcuts or cron:

```bash
#!/bin/bash
PROJECT_DIR="/path/to/StudioZero"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/output/shortcut_log.txt"

{
    echo "=== Run started: $(date) ==="
    cd "$PROJECT_DIR" || exit 1
    "$PYTHON_BIN" -m src.batch_runner --limit 1
    echo "=== Run finished: $(date) ==="
} >> "$LOG_FILE" 2>&1
```

## Project Structure

```
StudioZero/
├── src/
│   ├── app.py              # CLI entry point
│   ├── pipeline.py         # 5-step orchestration engine (generator-based)
│   ├── narrative.py        # LLM script generation (Gemini + Groq fallback)
│   ├── moviedbapi.py       # Wikipedia/TMDB movie data client
│   ├── gemini_tts.py       # Gemini TTS (30 voices, mood-based)
│   ├── stock_media.py      # Pexels stock video download
│   ├── subtitles.py        # ASS subtitle generation
│   ├── renderer.py         # FFmpeg video composition
│   ├── config.py           # Environment variables & paths
│   ├── config_mappings.py  # Voice/music/mood mappings
│   ├── batch_runner.py     # Batch processing from Google Sheets
│   ├── cloud_services.py   # Google Drive/Sheets integration
│   ├── marketing.py        # Social media caption generation
│   └── logging_utils.py    # Logging configuration
├── assets/
│   ├── basevideos/         # 24 fallback video clips
│   ├── music/              # Background tracks by genre (17 genres)
│   └── creds/              # Google service account credentials
├── output/
│   ├── temp/               # Intermediate files per movie
│   ├── final/              # Rendered videos
│   └── pipeline_logs/      # Script generation logs
├── docs/
│   └── VIDEO_PIPELINE.md   # Detailed pipeline documentation
├── requirements.txt
├── .env.template
└── CLAUDE.md               # AI assistant project context
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| LLM (primary) | Google Gemini 2.0 Flash |
| LLM (fallback) | Groq LLaMA 3.3 70B |
| Text-to-Speech | Google Gemini 2.5 Flash TTS (30 voices) |
| Transcription | OpenAI Whisper (base, local) |
| Stock Video | Pexels API |
| Movie Data | Wikipedia API + TMDB v3 |
| Video Rendering | FFmpeg (H.264, ASS subtitles, sidechain compression) |
| Subtitles | pysubs2 (ASS format) |
| Data Validation | Pydantic 2.0+ |
| Retry Logic | tenacity (exponential backoff) |
| Cloud Storage | Google Drive API |
| Job Queue | Google Sheets API + gspread |
| Config | python-dotenv |

## Key Features

- **30 TTS voices** with genre-optimized selection (14 female, 16 male)
- **Mood-based pacing** across 14 emotional contexts (0.9x-1.6x speed)
- **Audio ducking** via sidechain compression (music auto-lowers during narration)
- **Ken Burns effect** on movie poster for dynamic ending scenes
- **Multi-level fallback** at every stage (Wikipedia→TMDB, Gemini→Groq, Pexels→Local)
- **Pipeline caching** for offline re-rendering without API calls
- **Social media captions** auto-generated with hook-first format and genre hashtags
- **Batch automation** from Google Sheets with Drive upload and status tracking
- **Generator-based progress** reporting via `PipelineStatus` objects

## Output Specs

| Property | Value |
|----------|-------|
| Resolution | 1080x1920 (9:16 portrait) |
| Frame Rate | 30 fps |
| Video Codec | H.264 (libx264, CRF 23) |
| Audio Codec | AAC 192kbps |
| Duration | ~45-60 seconds |
| Scenes | 6 (hook → context → escalation → turn → climax → resolution) |

## Requirements

- Python 3.10+
- FFmpeg 4.0+ (with libx264, libass)
- ~2GB RAM for Whisper transcription
- Internet connection for API calls (or use `--offline` with cached data)

## License

MIT License
