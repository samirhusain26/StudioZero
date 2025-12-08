import logging
import subprocess
import os
import ffmpeg

logger = logging.getLogger(__name__)

class VideoRenderer:
    def check_ffmpeg(self):
        """
        Checks if both FFmpeg and FFprobe are installed and accessible.
        Returns True if both are found, False otherwise.
        """
        ffmpeg_ok = False
        ffprobe_ok = False

        # Check ffmpeg
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

        # Check ffprobe
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
        else:
            return False

    def create_scene_clip(self, image_path, audio_path, output_path):
        """
        Creates a video clip from an image and audio file with a Ken Burns effect.
        Applies scale and zoompan filters, and trims to audio duration.
        """
        try:
            # Probe audio duration using ffmpeg.probe
            probe = ffmpeg.probe(audio_path)
            duration = float(probe['format']['duration'])
            
            # Define input streams
            input_image = ffmpeg.input(image_path)
            input_audio = ffmpeg.input(audio_path)
            
            # Apply Ken Burns effect filter chain
            # Apply Ken Burns effect filter chain
            # 1. Scale image to 1920 width (HD) to provide detail for zoom, but not excessive (was 8000)
            # 2. zoompan: 
            #    - z='min(zoom+0.0015,1.5)': Zoom in slowly from 1.0 to 1.5
            #    - d={duration*25}: Duration in frames (assuming 25fps)
            #    - x/y: Center the zoom
            #    - s=1280x720: Output resolution
            #    - fps=25: Explicit output framerate
            video_stream = (
                input_image
                .filter('scale', 1920, -1)
                .filter(
                    'zoompan',
                    z='min(zoom+0.0015,1.5)',
                    d=int(duration * 25),
                    x='iw/2-(iw/zoom/2)',
                    y='ih/2-(ih/zoom/2)',
                    s='1280x720',
                    fps=25
                )
            )
            
            # Combine video and audio, trim to duration, and output as mp4
            # Using t=duration to ensure the clip matches the audio length exactly
            # Added explicit fps usage
            stream = ffmpeg.output(
                video_stream,
                input_audio,
                output_path,
                t=duration,
                vcodec='libx264',
                pix_fmt='yuv420p',
                acodec='aac',
                r=25  # Force output frame rate
            )
            
            # Run the ffmpeg command
            stream.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
            logger.info(f"Successfully created scene clip at {output_path}")

        except ffmpeg.Error as e:
            error_message = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg error creating clip: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in create_scene_clip: {e}")
            raise

    def render_final_video(self, scene_clips, output_path):
        """
        Concatenates a list of scene clips into a single final video.
        Saves the result to the specified output_path.
        """
        try:
            if not scene_clips:
                raise ValueError("No scene clips provided for rendering.")

            # Create input streams for each clip
            input_streams = []
            for clip in scene_clips:
                inp = ffmpeg.input(clip)
                input_streams.append(inp.video)
                input_streams.append(inp.audio)
            
            # Stitch clips together using concat filter
            # v=1, a=1 indicates both video and audio streams are present
            joined = ffmpeg.concat(*input_streams, v=1, a=1).output(
                output_path, 
                vcodec='libx264', 
                pix_fmt='yuv420p', 
                acodec='aac'
            )

            # Run ffmpeg with -y (overwrite_output=True)
            joined.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
            
            logger.info(f"Successfully rendered final video at {output_path}")
            return output_path

        except ffmpeg.Error as e:
            error_message = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg error rendering final video: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in render_final_video: {e}")
            raise
