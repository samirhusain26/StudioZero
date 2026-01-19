import logging
import subprocess
import os
import random
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING

import ffmpeg

from src.config import Config

if TYPE_CHECKING:
    from src.pipeline import SceneAssets

logger = logging.getLogger(__name__)

# Background music path
BACKGROUND_MUSIC_PATH = Config.ASSETS_DIR / "audio" / "background_track.mp3"

# Output resolution for vertical 9:16 video
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FPS = 30


# Base video clip duration range (seconds)
VIDEO_CLIP_DURATION_MIN = 3
VIDEO_CLIP_DURATION_MAX = 4

# Duration of silent poster at the end (seconds)
SILENT_POSTER_DURATION = 1.0


class VideoRenderer:
    """
    Renders vertical 9:16 videos with Ken Burns effects and Hormozi-style captions.
    """

    def __init__(self, base_videos_dir: Optional[str] = None):
        """
        Initialize the VideoRenderer.
        
        Args:
            base_videos_dir: Path to directory containing base video clips.
        """
        self.base_videos_dir = base_videos_dir
        self._base_videos: List[str] = []
        
        if base_videos_dir and os.path.exists(base_videos_dir):
            self._base_videos = [
                os.path.join(base_videos_dir, f)
                for f in os.listdir(base_videos_dir)
                if f.endswith(('.mp4', '.mov', '.avi', '.mkv'))
            ]
            logger.info(f"Loaded {len(self._base_videos)} base videos from {base_videos_dir}")

    def check_ffmpeg(self) -> bool:
        """
        Checks if both FFmpeg and FFprobe are installed and accessible.
        Returns True if both are found, False otherwise.
        """
        ffmpeg_ok = False
        ffprobe_ok = False

        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            ffmpeg_ok = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.error("FFmpeg binary not found.")
        except Exception as e:
            logger.error(f"Error checking FFmpeg: {e}")

        try:
            subprocess.run(
                ["ffprobe", "-version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            ffprobe_ok = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.error("FFprobe binary not found.")
        except Exception as e:
            logger.error(f"Error checking FFprobe: {e}")

        if ffmpeg_ok and ffprobe_ok:
            logger.info("FFmpeg and FFprobe are installed and accessible.")
            return True
        return False

    def _get_media_duration(self, path: str) -> float:
        """Get duration of a media file in seconds."""
        try:
            probe = ffmpeg.probe(path)
            return float(probe['format']['duration'])
        except Exception as e:
            logger.warning(f"Could not probe duration for {path}: {e}")
            return 0.0

    def _get_random_base_video(self) -> Optional[str]:
        """Get a random base video path."""
        if not self._base_videos:
            return None
        return random.choice(self._base_videos)

    def _create_video_from_image(
        self,
        image_path: str,
        output_path: str,
        duration: float,
        add_ken_burns: bool = True,
    ) -> str:
        """
        Create a video from a static image with optional Ken Burns effect.

        Args:
            image_path: Path to the source image
            output_path: Output path for the generated video
            duration: Duration of the video in seconds
            add_ken_burns: If True, adds subtle zoom effect

        Returns:
            Path to the created video
        """
        # Build the video filter
        # Scale to fit 9:16 while maintaining aspect ratio, then crop to exact size
        if add_ken_burns:
            # Ken Burns: smooth slow zoom from 100% to 105% over the duration
            # Using linear interpolation based on frame number for smooth motion
            total_frames = int(duration * FPS)
            video_filter = (
                f"loop=loop=-1:size=1:start=0,"
                f"scale={int(OUTPUT_WIDTH * 1.1)}:{int(OUTPUT_HEIGHT * 1.1)}:force_original_aspect_ratio=increase,"
                f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
                f"zoompan=z='1+0.05*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:fps={FPS},"
                f"setsar=1"
            )
        else:
            video_filter = (
                f"loop=loop=-1:size=1:start=0,"
                f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
                f"setsar=1,fps={FPS}"
            )

        cmd = [
            'ffmpeg', '-y',
            '-loop', '1',
            '-i', image_path,
            '-vf', video_filter,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-t', str(duration),
            '-an',  # No audio
            output_path
        ]

        logger.info(f"Creating video from image: {image_path} -> {output_path} ({duration:.2f}s)")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg image-to-video error: {result.stderr}")
            raise RuntimeError(f"Failed to create video from image: {result.stderr[-500:]}")

        return output_path

    def _escape_text_for_ffmpeg(self, text: str) -> str:
        """Escape special characters for FFmpeg drawtext filter."""
        # Escape characters that need escaping in FFmpeg drawtext
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "'\\''")
        text = text.replace(":", "\\:")
        text = text.replace("[", "\\[")
        text = text.replace("]", "\\]")
        text = text.replace(",", "\\,")
        text = text.replace(";", "\\;")
        return text

    def _build_subtitle_filter(
        self,
        word_timestamps: List[Dict[str, Any]],
        time_offset: float = 0.0
    ) -> str:
        """
        Build FFmpeg drawtext filter chain for Hormozi-style word-by-word captions.
        
        Classic Hormozi style: Yellow text, bold, black outline, centered.
        
        Args:
            word_timestamps: List of {'word': str, 'start': float, 'end': float}
            time_offset: Offset to add to all timestamps (for concatenated clips)
            
        Returns:
            FFmpeg filter string for subtitles
        """
        if not word_timestamps:
            return ""

        filters = []
        
        for i, wt in enumerate(word_timestamps):
            word = self._escape_text_for_ffmpeg(wt['word'])
            start = wt['start'] + time_offset
            end = wt['end'] + time_offset
            
            # Hormozi style: Yellow (#FFFF00), bold, black stroke
            # Using system font (sans-serif will use Arial/Helvetica on most systems)
            drawtext = (
                f"drawtext=text='{word}'"
                f":fontsize=72"
                f":fontcolor=#FFFF00"  # Yellow - classic Hormozi
                f":borderw=4"
                f":bordercolor=black"
                f":shadowx=2"
                f":shadowy=2"
                f":shadowcolor=black@0.6"
                f":x=(w-text_w)/2"
                f":y=h*0.75"
                f":enable='between(t,{start:.3f},{end:.3f})'"
            )
            filters.append(drawtext)
        
        return ",".join(filters)

    def create_audio_video_clip(
        self,
        audio_path: str,
        output_path: str,
        word_timestamps: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Creates a vertical 9:16 video clip using base videos stitched together
        to match audio duration, with Hormozi-style word-by-word subtitles.
        
        This method does NOT use images - it relies entirely on base videos.
        
        Args:
            audio_path: Path to the audio narration
            output_path: Output path for the video clip
            word_timestamps: List of {'word': str, 'start': float, 'end': float}
            
        Returns:
            Path to the created clip
        """
        try:
            # Get audio duration
            audio_duration = self._get_media_duration(audio_path)
            if audio_duration <= 0:
                raise ValueError(f"Invalid audio duration for {audio_path}")

            if not self._base_videos:
                raise ValueError("No base videos available for rendering")

            # Build list of video segments to fill the audio duration
            segments = []
            total_video_duration = 0.0
            
            while total_video_duration < audio_duration:
                video_path = self._get_random_base_video()
                video_duration = self._get_media_duration(video_path)
                
                # Use a random clip duration between 3-6 seconds
                clip_duration = min(
                    random.uniform(3.0, 6.0),
                    audio_duration - total_video_duration,
                    video_duration - 1.0  # Leave 1s buffer
                )
                
                if clip_duration <= 0:
                    break
                
                # Random start point within the video
                max_start = max(0, video_duration - clip_duration - 0.5)
                start_time = random.uniform(0, max_start) if max_start > 0 else 0
                
                segments.append({
                    'path': video_path,
                    'start': start_time,
                    'duration': clip_duration
                })
                total_video_duration += clip_duration

            if not segments:
                raise ValueError("Could not create any video segments")

            # Build FFmpeg filter complex
            inputs = []
            filter_parts = []
            
            for i, seg in enumerate(segments):
                inputs.extend(['-i', seg['path']])
                filter_parts.append(
                    f"[{i}:v]"
                    f"trim=start={seg['start']:.3f}:duration={seg['duration']:.3f},"
                    f"setpts=PTS-STARTPTS,"
                    f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
                    f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
                    f"setsar=1,fps={FPS}[v{i}]"
                )
            
            # Add audio input
            inputs.extend(['-i', audio_path])
            audio_idx = len(segments)
            
            # Concatenate all video segments
            concat_inputs = "".join([f"[v{i}]" for i in range(len(segments))])
            filter_parts.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[video]")
            
            # Add subtitle overlay
            subtitle_filter = self._build_subtitle_filter(word_timestamps or [])
            if subtitle_filter:
                filter_parts.append(f"[video]{subtitle_filter}[final]")
                video_output = "[final]"
            else:
                video_output = "[video]"
            
            # Build complete filter_complex
            filter_complex = ";\n".join(filter_parts)
            
            # Build FFmpeg command
            cmd = ['ffmpeg', '-y']
            cmd.extend(inputs)
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', video_output,
                '-map', f'{audio_idx}:a',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-t', str(audio_duration),
                '-r', str(FPS),
                '-shortest',
                output_path
            ])
            
            logger.info(f"Running FFmpeg for audio-video clip: {output_path}")
            logger.debug(f"Using {len(segments)} video segments for {audio_duration:.2f}s audio")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg stderr: {result.stderr}")
                raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
            
            logger.info(f"Successfully created audio-video clip: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error creating audio-video clip: {e}")
            raise

    def render_final_video(
        self,
        scene_clips: List[str],
        output_path: str
    ) -> str:
        """
        Concatenates scene clips into a final video.
        
        Args:
            scene_clips: List of paths to scene clip videos
            output_path: Output path for the final video
            
        Returns:
            Path to the final video
        """
        try:
            if not scene_clips:
                raise ValueError("No scene clips provided for rendering.")

            # Use ffmpeg concat demuxer for efficiency
            # Create a concat file
            concat_list_path = output_path + ".concat.txt"
            with open(concat_list_path, 'w') as f:
                for clip in scene_clips:
                    # Escape single quotes in path
                    escaped_path = clip.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_list_path,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '192k',
                output_path
            ]
            
            logger.info(f"Rendering final video from {len(scene_clips)} clips...")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up concat list
            if os.path.exists(concat_list_path):
                os.remove(concat_list_path)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg stderr: {result.stderr}")
                raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
            
            logger.info(f"Successfully rendered final video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error rendering final video: {e}")
            raise

    def render_from_scenes(
        self,
        scene_assets: List["SceneAssets"],
        output_path: str,
        subtitle_path: Optional[str] = None,
        background_music_path: Optional[str] = None,
        music_volume: float = 0.3,
    ) -> str:
        """
        Renders the final video from a list of SceneAssets.

        Concatenates all scene videos and audio, adds background music with
        sidechain compression (ducking), and overlays subtitles.

        Args:
            scene_assets: List of SceneAssets from the pipeline.
            output_path: Output path for the final video.
            subtitle_path: Path to .ass subtitle file (optional).
            background_music_path: Path to background music file.
                                   Defaults to assets/audio/background_track.mp3.
            music_volume: Base volume for background music (0.0-1.0).

        Returns:
            Path to the rendered video.
        """
        if not scene_assets:
            raise ValueError("No scene assets provided for rendering")

        # Use default background music if not specified
        if background_music_path is None:
            background_music_path = str(BACKGROUND_MUSIC_PATH)

        has_background_music = (
            background_music_path and Path(background_music_path).exists()
        )

        try:
            # Create temporary directory for intermediate files
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Step 1: Create concat list files for videos and audios
                video_concat_file = temp_path / "videos.txt"
                audio_concat_file = temp_path / "audios.txt"

                # Track if we have an ending scene for the silent poster segment
                ending_scene = None
                ending_poster_path = None

                # Collect audio durations for trimming videos to match
                audio_durations = []
                with open(video_concat_file, 'w') as vf, open(audio_concat_file, 'w') as af:
                    for i, scene in enumerate(scene_assets):
                        # Check if this scene uses a poster instead of video
                        if hasattr(scene, 'poster_path') and scene.poster_path and Path(scene.poster_path).exists():
                            # Create a video from the poster image
                            poster_video_path = str(temp_path / f"poster_video_{i}.mp4")
                            self._create_video_from_image(
                                image_path=scene.poster_path,
                                output_path=poster_video_path,
                                duration=scene.audio_duration,
                                add_ken_burns=True,
                            )
                            video_escaped = poster_video_path.replace("'", "'\\''")
                            logger.info(f"Scene {i}: Using poster as video ({scene.audio_duration:.2f}s)")

                            # Track this as the ending scene for the silent segment
                            if hasattr(scene, 'is_ending_scene') and scene.is_ending_scene:
                                ending_scene = scene
                                ending_poster_path = scene.poster_path
                        else:
                            # Use the regular video path
                            video_escaped = scene.video_path.replace("'", "'\\''")

                        audio_escaped = scene.audio_path.replace("'", "'\\''")
                        vf.write(f"file '{video_escaped}'\n")
                        af.write(f"file '{audio_escaped}'\n")
                        audio_durations.append(scene.audio_duration)

                # Add silent poster segment at the end if we have an ending scene
                silent_segment_path = None
                if ending_poster_path and Path(ending_poster_path).exists():
                    logger.info(f"Adding {SILENT_POSTER_DURATION}s silent poster segment at the end")
                    silent_segment_path = str(temp_path / "silent_poster_segment.mp4")
                    self._create_video_from_image(
                        image_path=ending_poster_path,
                        output_path=silent_segment_path,
                        duration=SILENT_POSTER_DURATION,
                        add_ken_burns=False,  # Static for the silent ending
                    )
                    # Append to the concat list
                    with open(video_concat_file, 'a') as vf:
                        silent_escaped = silent_segment_path.replace("'", "'\\''")
                        vf.write(f"file '{silent_escaped}'\n")
                    audio_durations.append(SILENT_POSTER_DURATION)

                # Step 2: Concatenate videos (with normalization and trimming to audio duration)
                concat_video_path = temp_path / "concat_video.mp4"
                self._concat_media(
                    concat_file=str(video_concat_file),
                    output_path=str(concat_video_path),
                    media_type="video",
                    normalize_videos=True,
                    temp_dir=temp_path,
                    target_durations=audio_durations,
                )

                # Step 3: Concatenate audio (voiceovers)
                concat_voice_path = temp_path / "concat_voice.wav"
                self._concat_media(
                    concat_file=str(audio_concat_file),
                    output_path=str(concat_voice_path),
                    media_type="audio"
                )

                # Get durations and validate sync
                voice_duration = self._get_media_duration(str(concat_voice_path))
                video_duration = self._get_media_duration(str(concat_video_path))

                logger.info(f"Voice duration: {voice_duration:.2f}s, Video duration: {video_duration:.2f}s")

                # Determine total duration
                # If we have a silent ending segment, use video_duration (voice ends earlier, music continues)
                if silent_segment_path:
                    total_duration = video_duration
                    logger.info(f"Using video duration ({video_duration:.2f}s) to include silent poster ending")
                else:
                    # Check for sync issues (allow 1 second tolerance)
                    duration_diff = abs(video_duration - voice_duration)
                    if duration_diff > 1.0:
                        logger.warning(
                            f"Audio/video duration mismatch: {duration_diff:.2f}s difference. "
                            f"Video: {video_duration:.2f}s, Voice: {voice_duration:.2f}s. "
                            "Final render will use voice duration as reference."
                        )
                    # Use voice duration as the authoritative duration
                    total_duration = voice_duration

                # Step 4: Build final render command with all filters
                self._render_final_with_ducking(
                    video_path=str(concat_video_path),
                    voice_path=str(concat_voice_path),
                    music_path=background_music_path if has_background_music else None,
                    subtitle_path=subtitle_path,
                    output_path=output_path,
                    duration=total_duration,
                    music_volume=music_volume,
                )

            logger.info(f"Successfully rendered final video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error rendering from scenes: {e}")
            raise

    def _normalize_video(
        self,
        input_path: str,
        output_path: str,
        target_duration: Optional[float] = None,
    ) -> None:
        """
        Normalizes a video to consistent format for concatenation.

        Ensures all videos have identical:
        - Resolution (1080x1920)
        - Frame rate (30 fps)
        - Pixel format (yuv420p)
        - Codec (H.264)

        Args:
            input_path: Path to input video.
            output_path: Path for normalized output.
            target_duration: If specified, trim/loop video to this duration in seconds.
        """
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-vf', f'scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},setsar=1,fps={FPS}',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-an',  # Strip audio - we handle audio separately
            '-r', str(FPS),
        ]

        # Trim video to target duration if specified
        if target_duration is not None:
            cmd.extend(['-t', str(target_duration)])

        cmd.append(output_path)

        logger.debug(f"Normalizing video: {input_path}" + (f" (trimming to {target_duration:.2f}s)" if target_duration else ""))
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg normalize stderr: {result.stderr}")
            raise RuntimeError(f"Failed to normalize video: {result.stderr[-500:]}")

    def _concat_media(
        self,
        concat_file: str,
        output_path: str,
        media_type: str = "video",
        normalize_videos: bool = True,
        temp_dir: Optional[Path] = None,
        target_durations: Optional[List[float]] = None,
    ) -> None:
        """
        Concatenates media files using FFmpeg concat demuxer.

        For videos, normalizes each input first to ensure consistent format.

        Args:
            concat_file: Path to the concat list file.
            output_path: Output path for concatenated media.
            media_type: 'video' or 'audio'.
            normalize_videos: If True, normalize videos before concat (video only).
            temp_dir: Temporary directory for normalized files.
            target_durations: List of target durations for each video (video only).
                              Each video will be trimmed to its corresponding duration.
        """
        if media_type == "video" and normalize_videos:
            # Read the concat file to get video paths
            video_paths = []
            with open(concat_file, 'r') as f:
                for line in f:
                    if line.startswith("file "):
                        # Extract path from "file 'path'" format
                        path = line.strip()[6:-1]  # Remove "file '" and trailing "'"
                        # Unescape single quotes
                        path = path.replace("'\\''", "'")
                        video_paths.append(path)

            if not video_paths:
                raise RuntimeError("No video files found in concat list")

            # Normalize each video
            normalized_paths = []
            for i, video_path in enumerate(video_paths):
                if temp_dir:
                    norm_path = str(temp_dir / f"norm_{i}.mp4")
                else:
                    norm_path = video_path.replace('.mp4', '_norm.mp4')

                # Get target duration for this video if provided
                duration = None
                if target_durations and i < len(target_durations):
                    duration = target_durations[i]

                logger.info(f"Normalizing video {i+1}/{len(video_paths)}: {Path(video_path).name}" + (f" -> {duration:.2f}s" if duration else ""))
                self._normalize_video(video_path, norm_path, target_duration=duration)
                normalized_paths.append(norm_path)

            # Create new concat file with normalized videos
            norm_concat_file = concat_file.replace('.txt', '_norm.txt')
            with open(norm_concat_file, 'w') as f:
                for norm_path in normalized_paths:
                    escaped_path = norm_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            # Concat normalized videos - can use stream copy since they're all identical format
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', norm_concat_file,
                '-c:v', 'copy',  # Stream copy - no re-encoding needed
                '-an',
                output_path
            ]

            logger.debug(f"Concatenating normalized videos")
            result = subprocess.run(cmd, capture_output=True, text=True)

            # Clean up normalized concat file
            if os.path.exists(norm_concat_file):
                os.remove(norm_concat_file)

            if result.returncode != 0:
                logger.error(f"FFmpeg concat stderr: {result.stderr}")
                raise RuntimeError(f"Failed to concatenate video: {result.stderr[-500:]}")

        elif media_type == "video":
            # Non-normalized path (legacy)
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-an',
                output_path
            ]
            logger.debug(f"Concatenating video: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg concat stderr: {result.stderr}")
                raise RuntimeError(f"Failed to concatenate video: {result.stderr[-500:]}")

        else:  # audio
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:a', 'pcm_s16le',  # Lossless for intermediate
                output_path
            ]

            logger.debug(f"Concatenating audio: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg concat stderr: {result.stderr}")
                raise RuntimeError(f"Failed to concatenate audio: {result.stderr[-500:]}")

    def _render_final_with_ducking(
        self,
        video_path: str,
        voice_path: str,
        music_path: Optional[str],
        subtitle_path: Optional[str],
        output_path: str,
        duration: float,
        music_volume: float = 0.3,
    ) -> None:
        """
        Renders the final video with sidechain compression (audio ducking) and ASS subtitles.

        Audio Mixing:
            - Loops background music infinitely using aloop filter
            - Applies sidechain compression so music ducks when voice is present
            - Filter chain: [bgm]aloop -> [looped] -> sidechaincompress -> [mixed_audio]

        Subtitle Burning:
            - Uses the 'ass' filter instead of drawtext
            - Applied AFTER scaling video to 1080x1920, BEFORE final encode

        Final Output:
            - Video: libx264, yuv420p, CRF 23
            - Audio: AAC, 192kbps
            - Output: output/final_video.mp4

        Args:
            video_path: Path to concatenated video.
            voice_path: Path to concatenated voiceover audio.
            music_path: Path to background music (optional).
            subtitle_path: Path to .ass subtitle file (optional).
            output_path: Final output path.
            duration: Total duration in seconds.
            music_volume: Base volume for background music (0.0-1.0).
        """
        # Build input list
        inputs = ['-i', video_path, '-i', voice_path]
        input_count = 2

        if music_path:
            inputs.extend(['-i', music_path])
            music_idx = input_count
            input_count += 1

        # Build filter complex
        filter_parts = []

        # Video filter: scale to output resolution first, then apply ASS subtitles
        # The ass filter must be applied AFTER scaling to ensure correct subtitle positioning
        video_filter = (
            f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},setsar=1,fps={FPS}"
        )

        # Note: ASS subtitle burning requires FFmpeg compiled with --enable-libass
        # If not available, subtitles will be skipped with a warning
        use_subtitles = False
        if subtitle_path and Path(subtitle_path).exists():
            # Check if FFmpeg has ass filter support
            try:
                check_result = subprocess.run(
                    ['ffmpeg', '-filters'],
                    capture_output=True,
                    text=True
                )
                if ' ass ' in check_result.stdout or 'ass\n' in check_result.stdout:
                    use_subtitles = True
                else:
                    logger.warning(
                        "FFmpeg not compiled with libass - subtitles will be skipped. "
                        "To enable subtitles, reinstall FFmpeg with: brew install ffmpeg"
                    )
            except Exception:
                pass

        if use_subtitles:
            # Escape path for FFmpeg ass filter
            # The ass filter requires specific escaping:
            # 1. Backslash must be escaped first (\ -> \\\\)
            # 2. Colon, brackets, comma, semicolon need filter escaping
            escaped_path = subtitle_path
            # First: escape backslashes (needs 4 backslashes in filter_complex)
            escaped_path = escaped_path.replace("\\", "\\\\\\\\")
            # Escape filter special characters
            escaped_path = escaped_path.replace(":", "\\:")
            escaped_path = escaped_path.replace("[", "\\[")
            escaped_path = escaped_path.replace("]", "\\]")
            escaped_path = escaped_path.replace(",", "\\,")
            escaped_path = escaped_path.replace(";", "\\;")
            # Use the ass filter (applied after scaling, before encoding)
            video_filter += f",ass='{escaped_path}'"
            logger.info(f"ASS subtitles enabled: {subtitle_path}")
            logger.debug(f"Escaped subtitle path: {escaped_path}")

        video_filter += "[vout]"
        filter_parts.append(video_filter)

        # Audio filter: sidechain compression for ducking
        if music_path:
            # Prepare voice audio (normalize) and split into two streams:
            # - [voice] for final mix
            # - [voice_sc] for sidechain compression key signal
            filter_parts.append(
                "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                "asplit=2[voice][voice_sc]"
            )

            # Loop the background music infinitely using aloop filter
            # aloop=loop=-1 means infinite loop, size=2e+09 is a large sample buffer
            # Then apply base volume and format normalization
            filter_parts.append(
                f"[{music_idx}:a]aloop=loop=-1:size=2e+09,"
                f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"volume={music_volume}[looped_music]"
            )

            # Apply sidechain compression: music ducks when voice is present
            # threshold=0.1 - duck when voice exceeds this level
            # ratio=10 - compression ratio for ducking
            # attack=50 - ducking attack time in ms
            # release=200 - gradual return time in ms
            # Note: voice_sc is consumed here as the sidechain key signal
            filter_parts.append(
                "[looped_music][voice_sc]sidechaincompress="
                "threshold=0.1:ratio=10:attack=50:release=200[ducked_music]"
            )

            # Mix ducked music with voice
            filter_parts.append(
                "[voice][ducked_music]amix=inputs=2:duration=first:dropout_transition=2[mixed_audio]"
            )
            audio_map = "[mixed_audio]"
        else:
            # No background music - just use voice
            filter_parts.append("[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]")
            audio_map = "[aout]"

        filter_complex = ";\n".join(filter_parts)

        # Build FFmpeg command
        cmd = ['ffmpeg', '-y']
        cmd.extend(inputs)
        cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[vout]',
            '-map', audio_map,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-t', str(duration),
            '-r', str(FPS),
            output_path
        ])

        logger.info(f"Rendering final video with audio ducking and ASS subtitles to: {output_path}")
        logger.debug(f"Filter complex:\n{filter_complex}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg render stderr: {result.stderr}")
            raise RuntimeError(f"Failed to render final video: {result.stderr[-500:]}")
