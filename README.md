# ZeroCostVideoGen (StudioZero)

ZeroCostVideoGen is an automated video generation pipeline that creates short, stylized video narratives based on existing movies. By inputting a movie name and a desired narrative style (e.g., "Noir", "Wes Anderson"), the system generates a script, synthesis voiceovers, creates AI-generated imagery, and renders a final video file with Ken Burns effects, all using free or open-source tiers of various APIs.

## Technology Stack

The project relies on a robust set of Python libraries and external APIs:

### External APIs
*   **The Movie Database (TMDB) API v3**: Used to fetch accurate metadata (plot, cast, release year) for the requested movie.
*   **Groq API (Llama 3-70b-versatile)**: Serves as the creative "screenwriter". It generates a generic JSON-structured script (scenes, narration, visual prompts) based on the movie data and user-defined style.
*   **Pollinations.ai (Flux Model)**: Generates high-quality images for each scene based on the visual prompts from the script.
*   **Microsoft Edge TTS**: Provides high-quality text-to-speech synthesis for the scene narration without requiring an API key.

### Core Python Libraries
*   **`ffmpeg-python`**: A wrapper for FFmpeg, used for all video processing, including image sealing, zoom/pan effects, and clip concatenation.
*   **`groq`**: The official client for interacting with the Groq API.
*   **`edge-tts`**: An asynchronous library for the Microsoft Edge Text-to-Speech service.
*   **`requests`**: Handles synchronous HTTP requests to TMDB.
*   **`aiohttp`**: Handles asynchronous HTTP requests for downloading images concurrently.
*   **`tenacity`**: Implements retry logic for API consistency (specifically for Groq).
*   **`python-dotenv`**: Manages environment variables and configuration.

## System Architecture & Logic Flow

The application is orchestrated by `src/main.py` which manages the data flow through several specialized modules.

### 1. Initialization & Configuration (`src/config.py`)
The system starts by loading environment variables (API keys for TMDB and Groq) and ensuring all necessary output directories (`assets/`, `output/`, `logs/`) exist.

### 2. User Input & Data Retrieval (`src/main.py`, `src/moviedbapi.py`)
*   The user is prompted for a **Movie Name** and a **Narrative Style**.
*   The `MovieDBClient` searches TMDB for the movie.
*   If found, it retrieves the Movie ID and fetches full details, specifically the **Plot Summary** and **Top Cast**.

### 3. Script Generation (`src/narrative.py`)
*   The `StoryGenerator` constructs a prompt containing the movie's plot, cast, and the requested style.
*   It sends this prompt to the Groq API (using the Llama 3 model).
*   The LLM returns a strictly formatted JSON object containing a title and a list of **5 Scenes**.
*   Each scene includes:
    *   `narration`: The text to be spoken.
    *   `visual_prompt`: A detailed description for the image generator.

### 4. Asset Generation (`src/assets.py`)
The `AssetGenerator` handles the parallel creation of media files:
*   **Images**: It uses `aiohttp` to request images from Pollinations.ai based on the `visual_prompt`. Downloads are rate-limited with a semaphore to be polite.
*   **Audio**: It uses `edge-tts` to generate an MP3 file for the `narration` text.
*   Assets are saved in a sanitized directory named after the movie (e.g., `assets/The_Matrix`).

### 5. Video Rendering (`src/renderer.py`)
The `VideoRenderer` assembles the final product using FFmpeg:
*   **Scene Components**: For each scene, it takes the generated image and audio.
*   **Clip Creation**:
    *   It calculates the duration of the audio.
    *   It applies a **Ken Burns effect** (zoom/pan) to the static image.
    *   It scales the video to 720p (1280x720) @ 25fps.
    *   It outputs a standalone MP4 clip for the scene (e.g., `scene_1.mp4`).
*   **Final Stitching**:
    *   Once all scene clips are ready, it concatenates them into a single continuous video file.
    *   The final video is saved to the `output/` directory.

## Directory Structure (Source)

*   **`src/main.py`**: Entry point. Orchestrates the entire pipeline from input to final render.
*   **`src/config.py`**: Centralized configuration and validation logic.
*   **`src/moviedbapi.py`**: Wrapper class for the TMDB API.
*   **`src/narrative.py`**: Wrapper class for the Groq API, handling prompt engineering and JSON parsing.
*   **`src/assets.py`**: Utilities for downloading images and generating TTS audio.
*   **`src/renderer.py`**: FFmpeg logic for creating video effects and processing streams.

## Requirements

*   Python 3.10+
*   FFmpeg and FFprobe installed on the system (accessible via PATH).
