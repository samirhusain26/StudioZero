# StudioZero

StudioZero is an AI-powered video generation pipeline that creates short, stylized vertical videos (9:16) from movie titles. Input a movie name, and the system automatically fetches movie data, generates a narrative script via LLM, synthesizes voiceovers, downloads matching stock footage, and renders a final video with Hormozi-style animated captions.

## How It Works

```
Movie Name → Wikipedia/TMDB → Groq LLM → Gemini TTS + Pexels + Whisper → FFmpeg → Video
```

1. **Movie Data Retrieval**: Fetches plot and metadata from Wikipedia (with TMDB fallback)
2. **Script Generation**: Groq LLM generates a structured 5-6 scene narrative with visual search queries
3. **Parallel Asset Generation**: Gemini TTS creates voiceovers while Pexels API downloads matching stock footage
4. **Transcription**: Whisper extracts word-level timestamps for subtitle sync
5. **Video Rendering**: FFmpeg composites everything with Ken Burns effects and word-by-word captions

## Technology Stack

| Component | Technology |
|-----------|------------|
| LLM | Groq API (Llama 3-70b-versatile) |
| TTS | Gemini 2.5 Flash TTS (30 voices, style prompts) |
| Transcription | OpenAI Whisper (base model) |
| Stock Video | Pexels API |
| Subtitles | pysubs2 (ASS format) |
| Video Rendering | FFmpeg with filter_complex pipelines |
| Movie Data | Wikipedia API (primary) + TMDB (fallback) |

## Project Structure

```
StudioZero/
├── src/
│   ├── app.py              # CLI entry point
│   ├── pipeline.py         # 5-step orchestration engine
│   ├── narrative.py        # Groq LLM script generation
│   ├── moviedbapi.py       # Wikipedia/TMDB client
│   ├── gemini_tts.py       # Text-to-speech synthesis (Gemini API)
│   ├── stock_media.py      # Pexels video download
│   ├── subtitles.py        # ASS subtitle generation
│   ├── renderer.py         # FFmpeg video composition
│   ├── config.py           # Environment & paths
│   ├── config_mappings.py  # Voice & music mappings
│   └── static/             # Web UI assets
├── assets/
│   ├── basevideos/         # Fallback stock footage
│   ├── music/              # Background music tracks
│   └── temp/               # Generated assets per movie
├── models/                 # Model files (if any)
├── output/                 # Final rendered videos
├── requirements.txt
└── .env                    # API keys
```

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install FFmpeg:**
   ```bash
   brew install ffmpeg  # macOS
   ```

3. **Configure API keys:**
   ```bash
   cp .env.template .env
   # Add your API keys to .env:
   # GROQ_API_KEY=your_groq_key
   # GEMINI_API_KEY=your_gemini_key
   # PEXELS_API_KEY=your_pexels_key
   # TMDB_API_KEY=your_tmdb_key (optional)
   ```

4. **Get Gemini API key for TTS:**
   - Go to [Google AI Studio](https://aistudio.google.com/apikey)
   - Create a new API key
   - Add to `.env`: `GEMINI_API_KEY=your_key_here`

5. **Add fallback footage (optional):**
   Place `.mp4` video clips in `assets/basevideos/` for when Pexels search fails

## Usage

**Generate a video via CLI:**
```bash
python -m src.app "Inception"
```

**CLI options:**
```bash
python -m src.app "The Matrix" --verbose        # Detailed logging
python -m src.app "Pulp Fiction" --assets-only  # Generate assets without rendering
python -m src.app "Interstellar" --offline      # Use cached data only
python -m src.app "Dune" -o custom_output.mp4   # Custom output path
```

**Output:** Final video saved to `output/<movie_name>.mp4`

## Requirements

- Python 3.10+
- FFmpeg and FFprobe in PATH
- Groq API key ([console.groq.com](https://console.groq.com/keys))
- Gemini API key ([aistudio.google.com](https://aistudio.google.com/apikey))
- Pexels API key ([pexels.com/api](https://www.pexels.com/api/))
- TMDB API key (optional, for fallback)
