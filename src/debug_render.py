import asyncio
import logging
import os
from pathlib import Path
from src.renderer import VideoRenderer
from src.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    Config.ensure_directories()
    renderer = VideoRenderer()
    
    if not renderer.check_ffmpeg():
        print("FFmpeg missing. Aborting.")
        return

    # Target directory
    movie_name = "Inception"
    assets_dir = Config.ASSETS_DIR / movie_name
    output_final_path = Config.OUTPUT_DIR / f"{movie_name}_debug.mp4"

    if not assets_dir.exists():
        print(f"Assets directory not found: {assets_dir}")
        return

    print(f"Scanning {assets_dir} for assets...")
    
    # Gather valid scenes
    scenes = []
    # Arbitrary limit of 20 scenes
    for i in range(1, 20):
        img_path = assets_dir / f"scene_{i}.jpg"
        audio_path = assets_dir / f"scene_{i}.mp3"
        clip_path = assets_dir / f"scene_{i}_debug.mp4"

        if img_path.exists() and audio_path.exists():
            print(f"Found Scene {i}...")
            # Re-render clip
            try:
                renderer.create_scene_clip(str(img_path), str(audio_path), str(clip_path))
                scenes.append(str(clip_path))
            except Exception as e:
                print(f"Error rendering Scene {i}: {e}")
        elif audio_path.exists():
             print(f"Scene {i} has audio but no image. Skipping.")
    
    if scenes:
         print(f"Stitching {len(scenes)} clips...")
         try:
             renderer.render_final_video(scenes, str(output_final_path))
             print(f"Done! Saved to: {output_final_path}")
         except Exception as e:
             print(f"Error stitching: {e}")
    else:
        print("No valid scenes found to render.")

if __name__ == "__main__":
    main()
