import json
import logging
import sys
import asyncio
from src.config import Config
from src.moviedbapi import MovieDBClient
from src.narrative import StoryGenerator
from src.assets import AssetGenerator
from src.renderer import VideoRenderer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """
    Main entry point for the ZeroCostVideoGen application.
    Interactively prompts for movie details and generation style, then orchestrates
    data fetching from TMDB and script generation via Groq.
    """
    try:
        # Validate configuration first
        Config.validate()
        Config.ensure_directories()
        
        # Interactive Inputs
        print("--- ZeroCostVideoGen Story Scripter ---")
        movie_name = input("Enter the movie name: ").strip()
        if not movie_name:
            print("Movie name cannot be empty.")
            return

        style = input("Enter the narrative style (e.g., Noir, Comedy, Wes Anderson): ").strip()
        if not style:
            print("Style cannot be empty.")
            return

        # 1. Fetch Movie Data
        print(f"\nSearching for movie: '{movie_name}'...")
        tmdb_client = MovieDBClient(api_key=Config.TMDB_API_KEY)
        
        # Initialize Video Renderer and check for ffmpeg
        renderer = VideoRenderer()
        if not renderer.check_ffmpeg():
            print("\nERROR: FFmpeg or FFprobe is missing.")
            print("These tools are required for video generation.")
            print("Please install them to continue:")
            print("  - macOS: brew install ffmpeg")
            print("  - Windows: choco install ffmpeg")
            print("  - Linux: sudo apt install ffmpeg")
            return

        search_result = tmdb_client.search_movie(movie_name)
        if not search_result:
            print(f"Could not find any movie matching '{movie_name}'.")
            return

        movie_id = search_result.get('id')
        print(f"Found: {search_result.get('title')} ({search_result.get('release_date', '')[:4]})")
        
        print("Fetching full movie details...")
        movie_details = tmdb_client.get_movie_details(movie_id)
        if not movie_details:
             print("Failed to retrieve movie details.")
             return

        # Transform data for StoryGenerator
        # MovieDBClient returns actors as a comma-separated string, StoryGenerator expects a list
        actors_list = [a.strip() for a in movie_details.get('actors', '').split(',') if a.strip()]
        
        # Prepare data packet
        narrative_input = {
            'title': movie_details.get('title'),
            'plot': movie_details.get('plot'),
            'actors': actors_list
        }

        # 2. Generate Script
        print(f"\nGenerating '{style}' style script using Groq...")
        story_gen = StoryGenerator()
        script = story_gen.generate_script(narrative_input, style)

        # 3. Generate Assets
        print(f"\nGenerating assets for '{movie_name}'...")
        # Create a safe directory name
        safe_title = "".join(x for x in movie_name if x.isalnum() or x in " -_").strip().replace(" ", "_")
        output_dir = Config.ASSETS_DIR / safe_title
        
        asset_gen = AssetGenerator(str(output_dir))
        assets_report = await asset_gen.generate_all_assets(script)

        # 4. Generate Video Clips and Final Video
        print(f"\nGenerating video clips and final render...")
        scene_clips = []
        for asset in assets_report:
            if asset.get('image_path') and asset.get('audio_path'):
                # Output clip path - same directory as assets
                clip_filename = f"scene_{asset['index']}.mp4"
                clip_path = output_dir / clip_filename
                
                print(f"Rendering clip for Scene {asset['index']}...")
                try:
                    renderer.create_scene_clip(
                        asset['image_path'],
                        asset['audio_path'],
                        str(clip_path)
                    )
                    scene_clips.append(str(clip_path))
                except Exception as e:
                    print(f"Failed to create clip for Scene {asset['index']}: {e}")
        
        final_video_path = None
        if scene_clips:
            print(f"\nStitching {len(scene_clips)} clips into final video...")
            try:
                final_filename = f"{safe_title}_final.mp4"
                final_output_path = str(Config.OUTPUT_DIR / final_filename)
                final_video_path = renderer.render_final_video(scene_clips, final_output_path)
            except Exception as e:
                print(f"Failed to render final video: {e}")
        else:
            print("No clips generated, skipping final video render.")

        # 5. Output
        print("\n" + "="*50)
        print("FINAL OUTPUT")
        print("="*50)
        
        print("\n--- TMDB DATA ---")
        print(json.dumps(movie_details, indent=2))
        
        print("\n--- GROQ GENERATED SCRIPT ---")
        print(json.dumps(script, indent=2))
        
        print("\n--- GENERATED ASSETS ---")
        print(json.dumps(assets_report, indent=2))
        
        if final_video_path:
            print("\n--- FINAL VIDEO ---")
            print(f"Location: {final_video_path}")
        print("="*50)

    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        logger.exception("An unexpected error occurred:")
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
