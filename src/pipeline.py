"""
Video Generation Pipeline - Modular Architecture

This module orchestrates the complete video generation workflow:
    1. Generate script from movie name (narrative module)
    2. Parallel: Download stock videos + Generate TTS audio
    3. Transcribe audio with Whisper for word timestamps
    4. Generate karaoke-style ASS subtitles
    5. Render final video with background music and subtitles
"""

import json
import logging
import random
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Dict, Any

import whisper

from src.config import Config
from src.moviedbapi import MovieDBClient
from src.narrative import StoryGenerator, VideoScript, Scene
from src.gemini_tts import generate_audio
from src.stock_media import download_video
from src.subtitles import generate_karaoke_subtitles
from src.renderer import VideoRenderer

logger = logging.getLogger(__name__)

CACHE_FILENAME = "pipeline_cache.json"


@dataclass
class SceneAssets:
    """Holds all assets for a single scene."""
    index: int
    narration: str
    visual_queries: List[str]
    audio_path: str
    audio_duration: float
    video_path: str
    video_metadata: dict
    word_timestamps: Optional[List[dict]] = None
    poster_path: Optional[str] = None  # If set, use this image instead of video
    is_ending_scene: bool = False  # True for the final "This was the story of..." scene


@dataclass
class PipelineStatus:
    """Represents a status update from the pipeline."""
    step: int
    message: str
    data: Optional[Dict[str, Any]] = None
    is_error: bool = False


def _create_silent_audio(output_path: str, duration_seconds: float = 3.0,
                         sample_rate: int = 24000, channels: int = 1,
                         sample_width: int = 2) -> str:
    """
    Create a silent WAV audio file.

    Args:
        output_path: Path to save the silent audio file.
        duration_seconds: Duration of silence in seconds (default 3.0).
        sample_rate: Audio sample rate in Hz (default 24000 to match Gemini TTS).
        channels: Number of audio channels (default 1 for mono).
        sample_width: Bytes per sample (default 2 for 16-bit).

    Returns:
        The output path where the file was saved.
    """
    import wave

    num_frames = int(sample_rate * duration_seconds)
    # Create silent PCM data (all zeros)
    silent_data = bytes(num_frames * channels * sample_width)

    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(silent_data)

    logger.info(f"Created silent audio: {output_path} ({duration_seconds:.2f}s)")
    return output_path


def run_animation_script_writer(
    storyline: str,
    character_descriptions: str,
    num_episodes: int = 3,
) -> Generator[PipelineStatus, None, Optional[Path]]:
    """
    Phase 1 of Animation Pipeline: Generate a multi-episode project script.
    """
    from google import genai as genai_lib
    from src.narrative import generate_animation_project
    from src.animation_manager import AnimationManager

    yield PipelineStatus(step=1, message=f"Starting animation script writer job for {num_episodes} episodes...")

    gemini_client = genai_lib.Client(api_key=Config.GEMINI_API_KEY)

    try:
        project = generate_animation_project(
            storyline=storyline,
            character_descriptions=character_descriptions,
            gemini_client=gemini_client,
            num_episodes=num_episodes
        )
        
        manager = AnimationManager(project.project_title)
        manager.save_project(project)

        yield PipelineStatus(
            step=1,
            message=f"Animation project '{project.project_title}' generated and saved with {len(project.episodes)} episodes.",
            data={"project_title": project.project_title, "num_episodes": len(project.episodes)}
        )
        return manager.project_file

    except Exception as e:
        yield PipelineStatus(step=1, message=f"Animation script writer failed: {e}", is_error=True)
        return None


def run_animation_episode_pipeline(
    project_name: str,
    episode_number: Optional[int] = None,
) -> Generator[PipelineStatus, None, Optional[str]]:
    """
    Phase 2 of Animation Pipeline: Render a single episode from a project.
    """
    from google import genai as genai_lib
    from src.animation_manager import AnimationManager
    from src.narrative import generate_character_blueprint
    from src.veo_client import generate_veo_scene
    from src.renderer import assemble_veo_clips

    manager = AnimationManager(project_name)
    project = manager.load_project()
    if not project:
        yield PipelineStatus(step=0, message=f"Project '{project_name}' not found.", is_error=True)
        return None

    if episode_number is None:
        episode_number = manager.get_next_pending_episode()
        if episode_number is None:
            yield PipelineStatus(step=0, message=f"All episodes in project '{project_name}' are already completed.")
            return None

    episode = next((ep for ep in project.episodes if ep.episode_number == episode_number), None)
    if not episode:
        yield PipelineStatus(step=0, message=f"Episode {episode_number} not found in project '{project_name}'.", is_error=True)
        return None

    yield PipelineStatus(step=1, message=f"Starting video generation for Episode {episode_number}: '{episode.episode_title}'")
    manager.update_episode_status(episode_number, "rendering")

    output_dir = manager.project_dir / f"episode_{episode_number}"
    output_dir.mkdir(parents=True, exist_ok=True)

    gemini_client = genai_lib.Client(api_key=Config.GEMINI_API_KEY)

    # =================================================================
    # Step 1: Character Blueprint Generation
    # =================================================================
    yield PipelineStatus(step=2, message="Generating character reference images...")
    character_images: dict[str, str] = {}
    
    # Identify unique characters in this episode
    unique_characters = {scene.character_id: scene for scene in episode.script.scenes}

    for char_id, scene in unique_characters.items():
        # Check if blueprint already exists in project root (shared across episodes)
        safe_char_id = Config.safe_title(char_id)
        shared_img_path = manager.project_dir / f"character_{safe_char_id}.png"
        
        if shared_img_path.exists():
            character_images[char_id] = str(shared_img_path)
            yield PipelineStatus(step=2, message=f"Using existing blueprint for '{char_id}'")
            continue

        yield PipelineStatus(step=2, message=f"Generating new blueprint for '{char_id}'...")
        try:
            image_data = generate_character_blueprint(scene.visual_context, gemini_client)
            if image_data:
                shared_img_path.write_bytes(image_data)
                character_images[char_id] = str(shared_img_path)
                yield PipelineStatus(step=2, message=f"Blueprint saved for '{char_id}'")
            else:
                yield PipelineStatus(step=2, message=f"Failed to generate blueprint for '{char_id}'", is_error=True)
        except Exception as e:
            yield PipelineStatus(step=2, message=f"Blueprint error for '{char_id}': {e}", is_error=True)

    # =================================================================
    # Step 2: Veo Scene Rendering
    # =================================================================
    yield PipelineStatus(step=3, message="Rendering scenes with Veo 3.1...")
    clip_paths: list[str] = []

    for scene in episode.script.scenes:
        yield PipelineStatus(step=3, message=f"Rendering scene {scene.scene_id}: '{scene.character_id}'...")
        ref_image = character_images.get(scene.character_id)
        if not ref_image:
            yield PipelineStatus(step=3, message=f"No blueprint for '{scene.character_id}', skipping scene {scene.scene_id}", is_error=True)
            continue

        clip_output = str(output_dir / f"veo_scene_{scene.scene_id}.mp4")
        try:
            generate_veo_scene(
                image_path=ref_image,
                visual_description=scene.visual_context,
                dialogue=scene.dialogue,
                voice_profile=scene.voice_profile,
                output_path=clip_output,
            )
            clip_paths.append(clip_output)
            yield PipelineStatus(step=3, message=f"Scene {scene.scene_id} rendered")
        except Exception as e:
            yield PipelineStatus(step=3, message=f"Veo rendering failed for scene {scene.scene_id}: {e}", is_error=True)

    if not clip_paths:
        manager.update_episode_status(episode_number, "failed", error="No scenes rendered")
        return None

    # =================================================================
    # Step 3: Assembly
    # =================================================================
    yield PipelineStatus(step=4, message="Assembling final video...")
    final_output = str(Config.FINAL_DIR / f"{manager.project_name}_ep{episode_number}.mp4")
    try:
        assemble_veo_clips(clip_paths, final_output)
        manager.update_episode_status(episode_number, "completed", output_path=final_output)
        yield PipelineStatus(step=4, message=f"Episode {episode_number} completed: {final_output}")
        return final_output
    except Exception as e:
        manager.update_episode_status(episode_number, "failed", error=f"Assembly failed: {e}")
        yield PipelineStatus(step=4, message=f"Assembly failed: {e}", is_error=True)
        return None

# Creative ending templates for the movie reveal
# {title} = movie title, {year} = release year
# Templates designed to be impactful and clearly state the movie name and year
ENDING_TEMPLATES = [
    "And that... was {title}. Released in {year}.",
    "This was the story of {title}, from {year}.",
    "{title}. A {year} film that left its mark.",
    "That's {title} for you. Out since {year}.",
    "The movie? {title}. The year? {year}.",
]

# Lazy-loaded Whisper model
_whisper_model = None


_whisper_load_lock = threading.Lock()


def _get_whisper_model():
    """Lazily load the Whisper model (thread-safe)."""
    global _whisper_model
    if _whisper_model is None:
        with _whisper_load_lock:
            if _whisper_model is None:
                logger.info("Loading Whisper model (base)...")
                _whisper_model = whisper.load_model("base")
    return _whisper_model


def _preload_whisper_model():
    """Start loading Whisper model in background thread."""
    threading.Thread(target=_get_whisper_model, daemon=True).start()


def whisper_transcribe(audio_path: str) -> List[dict]:
    """
    Transcribes audio using Whisper and returns word-level timestamps.

    Args:
        audio_path: Path to the audio file (WAV format).

    Returns:
        List of Whisper segment dictionaries with word timestamps.
        Each segment contains 'text', 'start', 'end', and 'words' list.
    """
    model = _get_whisper_model()
    result = model.transcribe(audio_path, word_timestamps=True)
    return result.get("segments", [])


def generate_ending_text(movie_title: str, release_year: str) -> str:
    """
    Generate a creative ending line for the movie reveal.

    Args:
        movie_title: The title of the movie
        release_year: The release year of the movie

    Returns:
        A creative ending sentence
    """
    template = random.choice(ENDING_TEMPLATES)
    return template.format(title=movie_title, year=release_year or "an unforgettable year")


def run_animated_pipeline(
    prompt_idea: str,
) -> Generator[PipelineStatus, None, Tuple[List[SceneAssets], None, Optional[str]]]:
    """
    Full pipeline for animated episodic parodies using Gemini Pro + Veo 3.1.

    Yields PipelineStatus updates at each stage so CLI and batch runner
    logging works identically to the movie pipeline.

    Args:
        prompt_idea: The creative prompt or movie name to build the parody from.

    Returns:
        Tuple of ([], None, final_video_path) — SceneAssets list is empty since
        this pipeline produces Veo clips directly.
    """
    from google import genai as genai_lib
    from src.narrative import (
        generate_episodic_script,
        generate_character_blueprint,
        EpisodicScript,
    )
    from src.veo_client import generate_veo_scene
    from src.renderer import assemble_veo_clips

    Config.ensure_directories()
    project_name = Config.safe_title(prompt_idea)
    output_dir = Config.TEMP_DIR / project_name
    output_dir.mkdir(parents=True, exist_ok=True)

    gemini_client = genai_lib.Client(api_key=Config.GEMINI_API_KEY)

    # =================================================================
    # Step 1: Script Adaptation
    # =================================================================
    yield PipelineStatus(step=1, message=f"[Animated] Generating episodic parody script for '{prompt_idea}'...")

    try:
        script = generate_episodic_script(prompt_idea, gemini_client)
    except Exception as e:
        yield PipelineStatus(step=1, message=f"[Animated] Script generation failed: {e}", is_error=True)
        return [], None, None

    # Save script JSON
    import json as _json
    script_path = output_dir / "episodic_script.json"
    with open(script_path, "w", encoding="utf-8") as f:
        _json.dump(script.model_dump(), f, indent=2, ensure_ascii=False)

    yield PipelineStatus(
        step=1,
        message=f"[Animated] Script complete: '{script.title}' — {len(script.scenes)} scenes",
        data={"title": script.title, "theme": script.theme},
    )

    # =================================================================
    # Step 2: Character Blueprint Generation
    # =================================================================
    yield PipelineStatus(step=2, message="[Animated] Generating character reference images...")

    # Deduplicate characters across scenes
    character_images: dict[str, str] = {}  # character_name -> image_path
    seen = set()

    for scene in script.scenes:
        name = scene.character_name
        if name in seen:
            continue
        seen.add(name)

        yield PipelineStatus(step=2, message=f"[Animated] Generating blueprint for '{name}'...")

        try:
            image_data = generate_character_blueprint(scene.visual_description, gemini_client)
        except Exception as e:
            yield PipelineStatus(step=2, message=f"[Animated] Blueprint failed for '{name}': {e}", is_error=True)
            continue

        if image_data:
            safe_name = Config.safe_title(name)
            img_path = output_dir / f"character_{safe_name}.png"
            img_path.write_bytes(image_data)
            character_images[name] = str(img_path)
            yield PipelineStatus(step=2, message=f"[Animated] Blueprint saved for '{name}': {img_path.name}")
        else:
            yield PipelineStatus(step=2, message=f"[Animated] No image returned for '{name}'", is_error=True)

    if not character_images:
        yield PipelineStatus(step=2, message="[Animated] No character blueprints generated. Cannot proceed.", is_error=True)
        return [], None, None

    yield PipelineStatus(
        step=2,
        message=f"[Animated] Character generation complete: {len(character_images)} unique character(s)",
    )

    # =================================================================
    # Step 3: Veo Scene Rendering
    # =================================================================
    yield PipelineStatus(step=3, message="[Animated] Rendering scenes with Veo 3.1...")

    clip_paths: list[str] = []

    for scene in script.scenes:
        scene_num = scene.scene_number
        yield PipelineStatus(step=3, message=f"[Animated] Rendering scene {scene_num}/6: '{scene.character_name}'...")

        # Find the character's reference image
        ref_image = character_images.get(scene.character_name)
        if not ref_image:
            yield PipelineStatus(
                step=3,
                message=f"[Animated] No blueprint for '{scene.character_name}', skipping scene {scene_num}",
                is_error=True,
            )
            continue

        clip_output = str(output_dir / f"veo_scene_{scene_num}.mp4")

        try:
            generate_veo_scene(
                image_path=ref_image,
                visual_description=scene.visual_description,
                dialogue=scene.dialogue,
                voice_profile=scene.voice_profile,
                output_path=clip_output,
            )
            clip_paths.append(clip_output)
            yield PipelineStatus(step=3, message=f"[Animated] Scene {scene_num} rendered: {Path(clip_output).name}")
        except Exception as e:
            yield PipelineStatus(
                step=3,
                message=f"[Animated] Veo rendering failed for scene {scene_num}: {e}",
                is_error=True,
            )

    if not clip_paths:
        yield PipelineStatus(step=3, message="[Animated] No scenes were rendered. Cannot assemble.", is_error=True)
        return [], None, None

    yield PipelineStatus(step=3, message=f"[Animated] Veo rendering complete: {len(clip_paths)} clip(s)")

    # =================================================================
    # Step 4: Assembly
    # =================================================================
    yield PipelineStatus(step=4, message="[Animated] Assembling final video...")

    Config.FINAL_DIR.mkdir(parents=True, exist_ok=True)
    final_output = str(Config.FINAL_DIR / f"{project_name}_animated.mp4")

    try:
        assemble_veo_clips(clip_paths, final_output)
    except Exception as e:
        yield PipelineStatus(step=4, message=f"[Animated] Assembly failed: {e}", is_error=True)
        return [], None, None

    yield PipelineStatus(
        step=4,
        message=f"[Animated] Video assembled: {final_output}",
        data={"output_path": final_output},
    )

    # =================================================================
    # Step 5 (Optional): Subtitles from Veo audio
    # =================================================================
    yield PipelineStatus(step=5, message="[Animated] Extracting audio for subtitle generation...")

    try:
        import subprocess as _sp
        extracted_audio = str(output_dir / "assembled_audio.wav")
        extract_cmd = [
            "ffmpeg", "-y",
            "-i", final_output,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            extracted_audio,
        ]
        result = _sp.run(extract_cmd, capture_output=True, text=True)

        if result.returncode == 0 and Path(extracted_audio).exists():
            segments = whisper_transcribe(extracted_audio)

            if segments:
                subtitle_path = str(output_dir / "subtitles.ass")
                generate_karaoke_subtitles(
                    whisper_segments=segments,
                    output_ass_path=subtitle_path,
                    words_per_line=4,
                )
                yield PipelineStatus(step=5, message=f"[Animated] Subtitles generated: {subtitle_path}")

                # Re-render with subtitles burned in
                subtitled_output = str(Config.FINAL_DIR / f"{project_name}_animated_subs.mp4")
                burn_cmd = [
                    "ffmpeg", "-y",
                    "-i", final_output,
                    "-vf", f"ass='{subtitle_path}'",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy",
                    subtitled_output,
                ]
                burn_result = _sp.run(burn_cmd, capture_output=True, text=True)

                if burn_result.returncode == 0:
                    final_output = subtitled_output
                    yield PipelineStatus(step=5, message=f"[Animated] Subtitles burned in: {final_output}")
                else:
                    yield PipelineStatus(step=5, message="[Animated] Subtitle burn-in failed, using video without subs")
            else:
                yield PipelineStatus(step=5, message="[Animated] No speech segments found, skipping subtitles")
        else:
            yield PipelineStatus(step=5, message="[Animated] Audio extraction failed, skipping subtitles")

    except Exception as e:
        yield PipelineStatus(step=5, message=f"[Animated] Subtitle step failed (non-fatal): {e}")

    logger.info(f"Animated pipeline complete for '{prompt_idea}': {final_output}")
    return [], None, final_output


class VideoGenerationPipeline:
    """
    Orchestrates the video generation pipeline with modular components.

    The pipeline follows these steps:
        1. Fetch movie data and generate script
        2. Parallel download videos + generate TTS audio for each scene
        3. Transcribe audio with Whisper for word timestamps
        4. Generate karaoke subtitles
        5. Render final video
    """

    def __init__(self, offline: bool = False, clean: bool = False):
        """
        Initialize the pipeline.

        Args:
            offline: If True, use cached data instead of making API calls.
            clean: If True, delete temp files after successful render.
        """
        self.offline = offline
        self.clean = clean
        Config.ensure_directories()
        self.movie_client = None if offline else MovieDBClient(tmdb_api_key=Config.TMDB_API_KEY)
        self.story_gen = None if offline else StoryGenerator()

    def _cleanup_temp_dir(self, movie_name: str) -> None:
        """Remove the temp directory for a movie after successful render."""
        temp_dir = Config.TEMP_DIR / Config.safe_title(movie_name)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp directory: {temp_dir}")

    def _get_output_dir(self, movie_name: str) -> Path:
        """Get the temp output directory for a movie."""
        output_dir = Config.TEMP_DIR / Config.safe_title(movie_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _get_cache_path(self, movie_name: str) -> Path:
        """Get the path to the cache file for a movie."""
        return self._get_output_dir(movie_name) / CACHE_FILENAME

    def _load_cache(self, movie_name: str) -> Optional[Dict]:
        """Load cached data for a movie if it exists."""
        cache_path = self._get_cache_path(movie_name)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load cache: {e}")
        return None

    def _save_cache(self, movie_name: str, cache_data: Dict) -> None:
        """Save cache data for a movie."""
        cache_path = self._get_cache_path(movie_name)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Cache saved to {cache_path}")

    def _process_scene_parallel(
        self,
        scene: Scene,
        output_dir: Path,
        voice_id: str,
        overall_mood: str = "neutral",
    ) -> Tuple[str, str, float, dict, List[str]]:
        """
        Process a single scene: download video and generate TTS in parallel.

        Args:
            scene: The Scene object from the script.
            output_dir: Directory to save assets.
            voice_id: Voice ID for TTS.
            overall_mood: The script-level mood for consistent TTS tone across all scenes.

        Returns:
            Tuple of (audio_path, video_path, audio_duration, video_metadata, status_messages)
        """
        scene_num = scene.scene_index
        status_messages = []

        audio_filename = f"scene_{scene_num}_audio.wav"
        audio_output_path = str(output_dir / audio_filename)
        video_filename = f"scene_{scene_num}_video.mp4"
        video_output_path = str(output_dir / video_filename)

        audio_path = None
        audio_duration = 0.0
        video_path = None
        video_metadata = {}

        # Get TTS customization - use script-level overall_mood for consistency
        tts_speed = scene.tts_speed

        def generate_tts():
            nonlocal audio_path, audio_duration
            status_messages.append(f"Generating TTS for scene {scene_num} (mood={overall_mood}, speed={tts_speed})...")
            audio_path, audio_duration = generate_audio(
                text=scene.narration,
                output_path=audio_output_path,
                voice=voice_id,
                speed=tts_speed,
                mood=overall_mood,
            )
            status_messages.append(f"TTS complete for scene {scene_num}: {audio_duration:.2f}s")

        def download_stock_video():
            nonlocal video_path, video_metadata
            queries = scene.visual_queries
            status_messages.append(f"Searching Pexels for scene {scene_num}: {queries[0]}...")

            video_path, video_metadata = download_video(
                queries=queries,
                output_path=video_output_path
            )

            if video_metadata.get('fallback'):
                status_messages.append(f"Scene {scene_num}: Fallback to base video (Pexels search failed)")
            else:
                status_messages.append(f"Scene {scene_num}: Downloaded video for '{video_metadata.get('query', queries[0])}'")

        # Execute TTS and video download in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(generate_tts),
                executor.submit(download_stock_video)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    status_messages.append(f"Error in scene {scene_num}: {e}")
                    raise

        return audio_path, video_path, audio_duration, video_metadata, status_messages

    def run(
        self,
        movie_name: str,
        mode: str = "movie",
        **kwargs
    ) -> Generator[PipelineStatus, None, Tuple[List[SceneAssets], Optional[VideoScript], Optional[str]]]:
        """
        Runs the video generation pipeline as a generator yielding status updates.

        Yields:
            PipelineStatus objects with progress information.

        Returns:
            Tuple of (List[SceneAssets], VideoScript, final_video_path).
        """
        # Validate config for the requested mode (skip for offline)
        if not self.offline:
            Config.validate(mode=mode)

        # Route to special animation modes if requested
        if mode == "animation-script":
            storyline = kwargs.get('storyline')
            char_desc = kwargs.get('character_descriptions')
            num_episodes = kwargs.get('num_episodes', 3)

            if not storyline or not char_desc:
                yield PipelineStatus(
                    step=0,
                    message="storyline and character_descriptions are required for animation-script mode.",
                    is_error=True,
                )
                return ([], None, None)

            result = yield from run_animation_script_writer(
                storyline=storyline,
                character_descriptions=char_desc,
                num_episodes=num_episodes
            )
            # Return result path as final_video_path for compatibility
            return ([], None, str(result) if result else None)

        if mode == "animation-render":
            from src.animation_manager import AnimationManager
            project_name = kwargs.get('project_name') or movie_name
            # Try to resolve the project name (handles theme -> generated title mapping)
            resolved = AnimationManager.find_project_by_theme(project_name)
            if resolved:
                project_name = resolved
            episode_number = kwargs.get('episode_number')
            result = yield from run_animation_episode_pipeline(
                project_name=project_name,
                episode_number=episode_number
            )
            return ([], None, result)

        # Route to legacy animated pipeline if requested
        if mode == "animated":
            result = yield from run_animated_pipeline(movie_name)
            return result if result else ([], None, None)

        scene_assets_list: List[SceneAssets] = []
        script: Optional[VideoScript] = None
        cache_data: Dict = {}
        output_dir = self._get_output_dir(movie_name)

        try:
            # =================================================================
            # Step 1: Fetch Movie Data & Generate Script
            # =================================================================
            yield PipelineStatus(step=1, message="Fetching movie data...")

            # Start loading Whisper model in background (needed in Step 3)
            _preload_whisper_model()

            if self.offline:
                cache_data = self._load_cache(movie_name)
                if not cache_data:
                    yield PipelineStatus(
                        step=1,
                        message=f"No cached data found for '{movie_name}'. Run without --offline first.",
                        is_error=True
                    )
                    return scene_assets_list, script, None

                movie_details = cache_data.get('movie_details')
                if not movie_details:
                    yield PipelineStatus(step=1, message="No movie details in cache.", is_error=True)
                    return scene_assets_list, script, None

                yield PipelineStatus(step=1, message="Using cached movie details")
            else:
                yield PipelineStatus(step=1, message=f"Searching for movie: '{movie_name}'...")

                search_result = self.movie_client.search_movie(movie_name)
                if not search_result:
                    yield PipelineStatus(
                        step=1,
                        message=f"Could not find any movie matching '{movie_name}'.",
                        is_error=True
                    )
                    return scene_assets_list, script, None

                movie_details = self.movie_client.get_movie_details(search_result)
                if not movie_details:
                    yield PipelineStatus(step=1, message="Failed to retrieve movie details.", is_error=True)
                    return scene_assets_list, script, None

                cache_data['movie_details'] = movie_details

            movie_title = movie_details.get('title', movie_name)
            plot = movie_details.get('plot', '')
            movie_year = movie_details.get('year', '')
            poster_path_tmdb = movie_details.get('poster_path', '')
            movie_tagline = movie_details.get('tagline', '')

            if not plot:
                yield PipelineStatus(step=1, message="No plot found for this movie.", is_error=True)
                return scene_assets_list, script, None

            # If we're missing poster/year (e.g., from Wikipedia), fetch from TMDB
            if not self.offline and (not poster_path_tmdb or not movie_year):
                yield PipelineStatus(step=1, message="Fetching additional metadata from TMDB...")
                tmdb_metadata = self.movie_client.get_tmdb_metadata(movie_title)
                if tmdb_metadata:
                    if not poster_path_tmdb:
                        poster_path_tmdb = tmdb_metadata.get('poster_path', '')
                    if not movie_year:
                        movie_year = tmdb_metadata.get('year', '')
                    if not movie_tagline:
                        movie_tagline = tmdb_metadata.get('tagline', '')
                    # Update movie_details with TMDB metadata for caching
                    movie_details['poster_path'] = poster_path_tmdb
                    movie_details['year'] = movie_year
                    movie_details['tagline'] = movie_tagline
                    movie_details['tmdb_id'] = tmdb_metadata.get('tmdb_id')
                    cache_data['movie_details'] = movie_details
                    yield PipelineStatus(step=1, message=f"TMDB metadata: year={movie_year}, poster={'yes' if poster_path_tmdb else 'no'}")
                else:
                    yield PipelineStatus(step=1, message="Could not fetch TMDB metadata")

            yield PipelineStatus(
                step=1,
                message=f"Found: {movie_title} ({movie_year or 'Unknown'})",
                data={'movie_details': movie_details}
            )

            # Download movie poster from TMDB
            poster_local_path = None
            if poster_path_tmdb and not self.offline:
                yield PipelineStatus(step=1, message="Downloading movie poster...")
                poster_output = str(output_dir / "poster.jpg")
                poster_local_path = self.movie_client.download_poster(poster_path_tmdb, poster_output)
                if poster_local_path:
                    yield PipelineStatus(step=1, message=f"Poster downloaded: {poster_local_path}")
                    cache_data['poster_path'] = poster_local_path
                else:
                    yield PipelineStatus(step=1, message="Could not download poster (will skip ending poster scene)")
            elif self.offline:
                poster_local_path = cache_data.get('poster_path')
                if poster_local_path and Path(poster_local_path).exists():
                    yield PipelineStatus(step=1, message="Using cached poster")

            # Generate script
            yield PipelineStatus(step=1, message="Generating video script with AI...")

            if self.offline:
                script_data = cache_data.get('video_script')
                if not script_data:
                    yield PipelineStatus(step=1, message="No script data in cache.", is_error=True)
                    return scene_assets_list, script, None
                script = VideoScript.model_validate(script_data)
                yield PipelineStatus(step=1, message="Using cached script")
            else:
                script = self.story_gen.generate_script(
                    movie_title=movie_title,
                    plot=plot
                )
                cache_data['video_script'] = script.model_dump()

            yield PipelineStatus(
                step=1,
                message=f"Script generated: {len(script.scenes)} scenes, genre={script.genre}, voice={script.selected_voice_id}, mood={script.overall_mood}, lang={script.lang_code}",
                data={'script': script.model_dump()}
            )

            # =================================================================
            # Step 2: Parallel Scene Processing (TTS + Video Download)
            # =================================================================
            yield PipelineStatus(step=2, message="Processing scenes (parallel TTS + video download)...")

            if 'scene_assets' not in cache_data:
                cache_data['scene_assets'] = {}

            for scene in script.scenes:
                scene_num = scene.scene_index
                scene_cache_key = f"scene_{scene_num}"

                yield PipelineStatus(
                    step=2,
                    message=f"Processing scene {scene_num + 1}/{len(script.scenes)}..."
                )

                if self.offline:
                    cached_scene = cache_data.get('scene_assets', {}).get(scene_cache_key)
                    if not cached_scene:
                        yield PipelineStatus(
                            step=2,
                            message=f"No cached data for scene {scene_num}",
                            is_error=True
                        )
                        continue

                    audio_path = cached_scene['audio_path']
                    video_path = cached_scene['video_path']
                    audio_duration = cached_scene['audio_duration']
                    video_metadata = cached_scene['video_metadata']

                    if not Path(audio_path).exists() or not Path(video_path).exists():
                        yield PipelineStatus(
                            step=2,
                            message=f"Cached files not found for scene {scene_num}",
                            is_error=True
                        )
                        continue

                    yield PipelineStatus(step=2, message=f"Scene {scene_num}: Using cached assets")
                else:
                    try:
                        audio_path, video_path, audio_duration, video_metadata, status_msgs = \
                            self._process_scene_parallel(
                                scene=scene,
                                output_dir=output_dir,
                                voice_id=script.selected_voice_id,
                                overall_mood=script.overall_mood,
                            )

                        for msg in status_msgs:
                            yield PipelineStatus(step=2, message=msg)

                        cache_data['scene_assets'][scene_cache_key] = {
                            'audio_path': audio_path,
                            'audio_duration': audio_duration,
                            'video_path': video_path,
                            'video_metadata': video_metadata
                        }
                    except Exception as e:
                        yield PipelineStatus(
                            step=2,
                            message=f"Failed to process scene {scene_num}: {e}",
                            is_error=True
                        )
                        continue

                scene_asset = SceneAssets(
                    index=scene_num,
                    narration=scene.narration,
                    visual_queries=scene.visual_queries,
                    audio_path=audio_path,
                    audio_duration=audio_duration,
                    video_path=video_path,
                    video_metadata=video_metadata
                )
                scene_assets_list.append(scene_asset)

            if not scene_assets_list:
                yield PipelineStatus(step=2, message="No scenes were processed successfully.", is_error=True)
                return scene_assets_list, script, None

            yield PipelineStatus(
                step=2,
                message=f"Scene processing complete: {len(scene_assets_list)} scenes"
            )

            # =================================================================
            # Step 2.5: Process Ending Scene with Movie Poster
            # =================================================================
            if self.offline:
                # Load ending scene from cache if available
                cached_ending = cache_data.get('scene_assets', {}).get('ending_scene')
                if cached_ending:
                    ending_audio_path = cached_ending.get('audio_path')
                    ending_poster_path = cached_ending.get('poster_path')
                    if (ending_audio_path and Path(ending_audio_path).exists() and
                        ending_poster_path and Path(ending_poster_path).exists()):
                        yield PipelineStatus(step=2, message="Loading cached ending scene...")
                        ending_scene_asset = SceneAssets(
                            index=len(scene_assets_list),
                            narration=cached_ending.get('narration', ''),
                            visual_queries=["movie poster"],
                            audio_path=ending_audio_path,
                            audio_duration=cached_ending.get('audio_duration', 0),
                            video_path="",
                            video_metadata={"type": "poster", "source": "tmdb"},
                            poster_path=ending_poster_path,
                            is_ending_scene=True,
                        )
                        scene_assets_list.append(ending_scene_asset)
                        yield PipelineStatus(step=2, message=f"Ending scene loaded: \"{cached_ending.get('narration', '')}\"")
                    else:
                        yield PipelineStatus(step=2, message="Cached ending scene files not found")
                else:
                    yield PipelineStatus(step=2, message="No ending scene in cache")
            elif poster_local_path and Path(poster_local_path).exists():
                yield PipelineStatus(step=2, message="Creating ending scene with movie poster...")

                # Generate the creative ending text
                ending_text = generate_ending_text(movie_title, movie_year)
                yield PipelineStatus(step=2, message=f"Ending narration: \"{ending_text}\"")

                # Generate TTS for the ending
                ending_audio_path = str(output_dir / "ending_audio.wav")
                ending_audio_duration = 3.0  # Default fallback duration
                tts_failed = False

                try:
                    tts_result = generate_audio(
                        text=ending_text,
                        output_path=ending_audio_path,
                        voice=script.selected_voice_id,
                        speed=1.2,  # Slightly slower for the reveal (but still 25% faster overall)
                        mood=script.overall_mood,
                    )

                    if tts_result is not None:
                        ending_audio_path, ending_audio_duration = tts_result
                        yield PipelineStatus(step=2, message=f"Ending TTS generated: {ending_audio_duration:.2f}s")
                    else:
                        tts_failed = True
                        logger.warning("Ending TTS returned None, using silent audio fallback")
                        yield PipelineStatus(step=2, message="TTS blocked/failed, using silent audio fallback (3s)")

                except Exception as e:
                    tts_failed = True
                    logger.warning(f"Ending TTS failed with exception: {e}, using silent audio fallback")
                    yield PipelineStatus(step=2, message=f"TTS failed ({e}), using silent audio fallback (3s)")

                # Create silent audio fallback if TTS failed
                if tts_failed:
                    ending_audio_path = str(output_dir / "ending_audio_silent.wav")
                    ending_audio_duration = 3.0
                    _create_silent_audio(ending_audio_path, duration_seconds=ending_audio_duration)
                    yield PipelineStatus(step=2, message="Silent audio track created for ending scene")

                # Create the ending scene asset (always, even with silent audio)
                ending_scene_index = len(scene_assets_list)
                ending_scene_asset = SceneAssets(
                    index=ending_scene_index,
                    narration=ending_text if not tts_failed else "",
                    visual_queries=["movie poster"],
                    audio_path=ending_audio_path,
                    audio_duration=ending_audio_duration,
                    video_path="",  # No video, we use poster
                    video_metadata={"type": "poster", "source": "tmdb", "silent_fallback": tts_failed},
                    poster_path=poster_local_path,
                    is_ending_scene=True,
                )
                scene_assets_list.append(ending_scene_asset)

                # Cache the ending scene
                cache_data['scene_assets']['ending_scene'] = {
                    'audio_path': ending_audio_path,
                    'audio_duration': ending_audio_duration,
                    'poster_path': poster_local_path,
                    'narration': ending_text if not tts_failed else "",
                    'silent_fallback': tts_failed,
                }

                yield PipelineStatus(step=2, message="Ending scene created with movie poster")
            else:
                yield PipelineStatus(step=2, message="Skipping ending scene (no poster available)")

            # =================================================================
            # Step 3: Whisper Transcription
            # =================================================================
            yield PipelineStatus(step=3, message="Transcribing audio with Whisper for word timestamps...")

            all_whisper_segments = []
            cumulative_offset = 0.0

            for asset in scene_assets_list:
                yield PipelineStatus(step=3, message=f"Transcribing scene {asset.index}...")

                try:
                    segments = whisper_transcribe(asset.audio_path)

                    # Adjust timestamps with cumulative offset and store on asset
                    adjusted_words = []
                    for segment in segments:
                        for word in segment.get('words', []):
                            adjusted_words.append({
                                'word': word.get('word', ''),
                                'start': word.get('start', 0) + cumulative_offset,
                                'end': word.get('end', 0) + cumulative_offset
                            })

                        # Also add to global segments with offset
                        adjusted_segment = segment.copy()
                        adjusted_segment['start'] = segment.get('start', 0) + cumulative_offset
                        adjusted_segment['end'] = segment.get('end', 0) + cumulative_offset
                        if 'words' in adjusted_segment:
                            adjusted_segment['words'] = [
                                {
                                    'word': w.get('word', ''),
                                    'start': w.get('start', 0) + cumulative_offset,
                                    'end': w.get('end', 0) + cumulative_offset
                                }
                                for w in segment.get('words', [])
                            ]
                        all_whisper_segments.append(adjusted_segment)

                    asset.word_timestamps = adjusted_words
                    cumulative_offset += asset.audio_duration

                except Exception as e:
                    yield PipelineStatus(
                        step=3,
                        message=f"Whisper transcription failed for scene {asset.index}: {e}",
                        is_error=True
                    )

            yield PipelineStatus(
                step=3,
                message=f"Transcription complete: {len(all_whisper_segments)} segments"
            )

            # =================================================================
            # Step 4: Generate Karaoke Subtitles
            # =================================================================
            yield PipelineStatus(step=4, message="Generating karaoke subtitles...")

            subtitle_path = str(output_dir / "subtitles.ass")

            try:
                generate_karaoke_subtitles(
                    whisper_segments=all_whisper_segments,
                    output_ass_path=subtitle_path,
                    words_per_line=4
                )
                yield PipelineStatus(step=4, message=f"Subtitles generated: {subtitle_path}")
            except Exception as e:
                yield PipelineStatus(
                    step=4,
                    message=f"Failed to generate subtitles: {e}",
                    is_error=True
                )
                subtitle_path = None

            # =================================================================
            # Step 5: Render Final Video
            # =================================================================
            yield PipelineStatus(step=5, message="Rendering final video...")

            # Determine background music path
            music_path = None
            if script.selected_music_file:
                music_file = Config.ASSETS_DIR / "music" / script.selected_music_file
                if music_file.exists():
                    music_path = str(music_file)
                    yield PipelineStatus(step=5, message=f"Using background music: {script.selected_music_file}")
                else:
                    yield PipelineStatus(step=5, message=f"Music file not found: {script.selected_music_file}")

            # Output path
            Config.FINAL_DIR.mkdir(parents=True, exist_ok=True)
            final_output_path = str(Config.FINAL_DIR / f"{Config.safe_title(movie_name)}.mp4")

            try:
                renderer = VideoRenderer()

                if not renderer.check_ffmpeg():
                    yield PipelineStatus(step=5, message="FFmpeg not installed.", is_error=True)
                    return scene_assets_list, script, None

                yield PipelineStatus(step=5, message="Concatenating scenes and mixing audio...")

                renderer.render_from_scenes(
                    scene_assets=scene_assets_list,
                    output_path=final_output_path,
                    subtitle_path=subtitle_path,
                    background_music_path=music_path
                )

                yield PipelineStatus(
                    step=5,
                    message=f"Video rendered successfully: {final_output_path}",
                    data={'output_path': final_output_path}
                )

            except Exception as e:
                yield PipelineStatus(
                    step=5,
                    message=f"Rendering failed: {e}",
                    is_error=True
                )
                return scene_assets_list, script, None

            # Save cache
            if not self.offline:
                self._save_cache(movie_name, cache_data)

            # Clean up temp files if requested
            if self.clean:
                self._cleanup_temp_dir(movie_name)
                yield PipelineStatus(step=5, message="Temp files cleaned up")

            return scene_assets_list, script, final_output_path

        except Exception as e:
            logger.exception("Pipeline error")
            yield PipelineStatus(step=0, message=f"Unexpected error: {str(e)}", is_error=True)
            return scene_assets_list, script, None


def run_pipeline(
    movie_name: str,
    progress_callback=None,
    offline: bool = False,
    clean: bool = False,
    mode: str = "movie",
    **kwargs
) -> Tuple[List[SceneAssets], Optional[VideoScript], Optional[str]]:
    """
    Convenience function to run the pipeline with a callback-based interface.

    Args:
        movie_name: Name of the movie to generate video for.
        progress_callback: Optional callback function(step, message, data, is_error).
        offline: If True, use cached data.
        clean: If True, delete temp files after successful render.
        mode: Pipeline mode - "movie", "animated", "animation-script", or "animation-render".
        **kwargs: Additional parameters for specific modes.

    Returns:
        Tuple of (scene_assets_list, script, final_video_path).
    """
    pipeline = VideoGenerationPipeline(offline=offline, clean=clean)
    gen = pipeline.run(movie_name, mode=mode, **kwargs)

    try:
        while True:
            status = next(gen)
            if progress_callback:
                progress_callback(status.step, status.message, status.data, status.is_error)
    except StopIteration as e:
        # Generator return value is in e.value
        return e.value if e.value else ([], None, None)
