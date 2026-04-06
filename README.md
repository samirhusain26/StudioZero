# StudioZero

AI-powered video generation pipeline that creates short, vertical (9:16) social media videos. It autonomously handles everything from script generation and voiceovers to stock video selection and final rendering.

## Pipeline Modes

- **Movie Mode (Default)**: Input a movie name → generates a narrative recap with AI voiceover, stock footage, and Hormozi-style captions.
- **Animated Mode (One-Shot)**: Input a theme → generates a funny parody with anthropomorphic household items/food as 3D Pixar-style characters using Vertex AI Veo 3.1.
- **Animation Series Mode**: Generate a multi-episode project with consistent characters and persistent tracking.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.template .env
```

Key required services: Google Gemini (LLM/TTS), Groq (Fallback/Captions), Pexels (Stock Video), and Vertex AI (Veo 3.1).

### 3. Generate a Video

#### Movie Mode
```bash
python -m src.app "Inception"
```

#### Animated Parody
```bash
python -m src.app "Game of Thrones" --mode animated
```

#### Animation Series (Multi-Phase)
```bash
# Phase 1: Write the multi-episode series bible
python -m src.app "Kitchen Chronicles" --mode animation-script --storyline "A drama about a toaster seeking revenge" --episodes 3

# Phase 2: Render a specific episode
python -m src.app "Kitchen Chronicles" --mode animation-render --episode-num 1
```

## Advanced Usage

| Flag | Description |
|------|-------------|
| `--mode` | `movie`, `animated`, `animation-script`, `animation-render` |
| `--offline` | Use cached data from `output/temp/` (no API calls) |
| `--assets-only` | Stop after gathering assets, skip rendering |
| `--clean` | Delete temporary files after successful render |
| `--verbose` / `-v` | Enable detailed debug logging |
| `--output` / `-o` | Specify custom output path for the final MP4 |

## Documentation

Detailed guides and technical references are available in the `docs/` directory:

- [**PIPELINE_OVERVIEW.md**](docs/PIPELINE_OVERVIEW.md) — Master documentation of all operational modes.
- [**TECHNICAL_REFERENCE.md**](docs/TECHNICAL_REFERENCE.md) — Low-level breakdown of the rendering engine.
- [**MODELS_REFERENCE.md**](docs/MODELS_REFERENCE.md) — Pydantic schema and data model documentation.
- [**BATCH_PROCESSING.md**](docs/BATCH_PROCESSING.md) — Google Sheets automation and macOS scheduling.
- [**PROJECT_STRUCTURE.md**](docs/PROJECT_STRUCTURE.md) — Architectural map and technical stack.

## Key Features

- **30+ TTS Voices**: Automatic selection based on genre/mood (14 female, 16 male).
- **Mood-Based Pacing**: TTS speed and tone automatically adjust to 14 emotional contexts.
- **Audio Ducking**: Background music automatically ducks during narration via sidechain compression.
- **Character Consistency**: In animated modes, character blueprints are shared across scenes/episodes for visual anchoring.
- **Smart Fallbacks**: Wikipedia → TMDB, Gemini → Groq, Pexels → Local assets.
- **Batch Processing**: Automate production via a Google Sheets queue using `src/batch_runner.py`.

## Technical Specs

- **Resolution**: 1080x1920 (9:16 portrait)
- **Frame Rate**: 30 FPS
- **Video Codec**: H.264 (libx264)
- **Subtitles**: Hormozi-style ASS (Advanced SubStation Alpha)
- **Audio**: AAC 192kbps with sidechain ducking
