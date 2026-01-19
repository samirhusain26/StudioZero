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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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


def _get_whisper_model():
    """Lazily load the Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        logger.info("Loading Whisper model (base)...")
        _whisper_model = whisper.load_model("base")
    return _whisper_model


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

    def __init__(self, offline: bool = False):
        """
        Initialize the pipeline.

        Args:
            offline: If True, use cached data instead of making API calls.
        """
        self.offline = offline
        if not offline:
            Config.validate()
        Config.ensure_directories()
        self.movie_client = None if offline else MovieDBClient(tmdb_api_key=Config.TMDB_API_KEY)
        self.story_gen = None if offline else StoryGenerator()

    def _get_output_dir(self, movie_name: str) -> Path:
        """Get the temp output directory for a movie."""
        safe_title = "".join(x for x in movie_name if x.isalnum() or x in " -_").strip().replace(" ", "_")
        output_dir = Config.TEMP_DIR / safe_title
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
        tts_speed = getattr(scene, 'tts_speed', 1.0)

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
    ) -> Generator[PipelineStatus, None, Tuple[List[SceneAssets], VideoScript, str]]:
        """
        Runs the video generation pipeline as a generator yielding status updates.

        Yields:
            PipelineStatus objects with progress information.

        Returns:
            Tuple of (List[SceneAssets], VideoScript, final_video_path).
        """
        scene_assets_list: List[SceneAssets] = []
        script: Optional[VideoScript] = None
        cache_data: Dict = {}
        output_dir = self._get_output_dir(movie_name)

        try:
            # =================================================================
            # Step 1: Fetch Movie Data & Generate Script
            # =================================================================
            yield PipelineStatus(step=1, message="Fetching movie data...")

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
                message=f"Script generated: {len(script.scenes)} scenes, genre={script.genre}, voice={script.selected_voice_id}, mood={getattr(script, 'overall_mood', 'neutral')}, lang={getattr(script, 'lang_code', 'a')}",
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
                                overall_mood=getattr(script, 'overall_mood', 'neutral'),
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
                try:
                    ending_audio_path, ending_audio_duration = generate_audio(
                        text=ending_text,
                        output_path=ending_audio_path,
                        voice=script.selected_voice_id,
                        speed=1.2,  # Slightly slower for the reveal (but still 25% faster overall)
                        mood=getattr(script, 'overall_mood', 'neutral'),
                    )
                    yield PipelineStatus(step=2, message=f"Ending TTS generated: {ending_audio_duration:.2f}s")

                    # Create the ending scene asset
                    ending_scene_index = len(scene_assets_list)
                    ending_scene_asset = SceneAssets(
                        index=ending_scene_index,
                        narration=ending_text,
                        visual_queries=["movie poster"],
                        audio_path=ending_audio_path,
                        audio_duration=ending_audio_duration,
                        video_path="",  # No video, we use poster
                        video_metadata={"type": "poster", "source": "tmdb"},
                        poster_path=poster_local_path,
                        is_ending_scene=True,
                    )
                    scene_assets_list.append(ending_scene_asset)

                    # Cache the ending scene
                    cache_data['scene_assets']['ending_scene'] = {
                        'audio_path': ending_audio_path,
                        'audio_duration': ending_audio_duration,
                        'poster_path': poster_local_path,
                        'narration': ending_text,
                    }

                    yield PipelineStatus(step=2, message="Ending scene created with movie poster")
                except Exception as e:
                    yield PipelineStatus(
                        step=2,
                        message=f"Failed to create ending scene: {e}",
                        is_error=True
                    )
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
            safe_name = "".join(c for c in movie_name if c.isalnum() or c in " -_").strip().replace(" ", "_")
            Config.FINAL_DIR.mkdir(parents=True, exist_ok=True)
            final_output_path = str(Config.FINAL_DIR / f"{safe_name}.mp4")

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

            return scene_assets_list, script, final_output_path

        except Exception as e:
            logger.exception("Pipeline error")
            yield PipelineStatus(step=0, message=f"Unexpected error: {str(e)}", is_error=True)
            return scene_assets_list, script, None


def run_pipeline(
    movie_name: str,
    progress_callback=None,
    offline: bool = False
) -> Tuple[List[SceneAssets], Optional[VideoScript], Optional[str]]:
    """
    Convenience function to run the pipeline with a callback-based interface.

    Args:
        movie_name: Name of the movie to generate video for.
        progress_callback: Optional callback function(step, message, data, is_error).
        offline: If True, use cached data.

    Returns:
        Tuple of (scene_assets_list, script, final_video_path).
    """
    pipeline = VideoGenerationPipeline(offline=offline)
    gen = pipeline.run(movie_name)

    try:
        while True:
            status = next(gen)
            if progress_callback:
                progress_callback(status.step, status.message, status.data, status.is_error)
    except StopIteration as e:
        # Generator return value is in e.value
        return e.value if e.value else ([], None, None)
