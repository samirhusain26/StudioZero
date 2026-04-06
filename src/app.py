#!/usr/bin/env python3
"""
StudioZero CLI - Generate viral movie videos from the command line.

Usage:
    python -m src.app "The Matrix"                      # Full pipeline + render video
    python -m src.app "Inception" -o my_video.mp4       # Custom output path
    python -m src.app "Toy Story" -v                    # Verbose logging
    python -m src.app "The Matrix" --assets-only        # Assets only, skip rendering
    python -m src.app "The Matrix" --offline            # Use cached data (no API calls)
"""

import argparse
import logging
import sys
from datetime import datetime

from src.logging_utils import setup_logging
from src.pipeline import VideoGenerationPipeline, PipelineStatus


def print_banner():
    """Print a simple startup banner."""
    print("\n" + "=" * 60)
    print("  StudioZero - AI Movie Video Generator")
    print("  Modular Pipeline with Parallel Processing")
    print("=" * 60 + "\n")


def print_scene_assets(scene_assets: list, script=None):
    """Print a summary of generated scene assets."""
    if not scene_assets:
        return

    print("\n" + "-" * 60)
    print("  GENERATED ASSETS SUMMARY")
    print("-" * 60)

    if script:
        print(f"\n  Genre: {script.genre}")
        print(f"  Voice: {script.selected_voice_id}")
        print(f"  Music: {script.selected_music_file}")
        print(f"  BPM: {script.bpm}")

    for asset in scene_assets:
        print(f"\n  Scene {asset.index}:")
        narration_preview = asset.narration[:60] + "..." if len(asset.narration) > 60 else asset.narration
        print(f"    Narration: {narration_preview}")
        print(f"    Visuals:   {', '.join(asset.visual_queries[:2])}...")
        print(f"    Audio:     {asset.audio_path} ({asset.audio_duration:.2f}s)")
        print(f"    Video:     {asset.video_path}")

    print("\n" + "-" * 60 + "\n")


def run_pipeline_with_logging(
    movie_name: str,
    logger: logging.Logger,
    offline: bool = False,
    assets_only: bool = False,
    clean: bool = False,
    mode: str = "movie",
    **kwargs
):
    """
    Run the video generation pipeline with logging output.

    Args:
        movie_name: Name of the movie to generate video for.
        logger: Logger instance for output.
        offline: If True, use cached data.
        assets_only: If True, stop after gathering assets (skip rendering).
        clean: If True, delete temp files after successful render.
        mode: Pipeline mode - "movie", "animated", "animation-script", or "animation-render".
        **kwargs: Additional parameters for specific modes.

    Returns:
        Tuple of (scene_assets, script, final_video_path).
    """
    pipeline = VideoGenerationPipeline(offline=offline, clean=clean)
    gen = pipeline.run(movie_name, mode=mode, **kwargs)

    scene_assets = []
    script = None
    final_video_path = None

    try:
        while True:
            status = next(gen)

            # Log the status update
            prefix = f"[Step {status.step}]" if status.step > 0 else "[ERROR]"
            if status.is_error:
                logger.error(f"{prefix} {status.message}")
            else:
                logger.info(f"{prefix} {status.message}")

            # Log additional data if verbose
            if status.data:
                logger.debug(f"Data: {status.data}")

            # Check if we should stop early (assets only mode)
            if assets_only and status.step == 2 and "complete" in status.message.lower():
                logger.info("Assets-only mode: stopping before transcription/rendering")
                break

    except StopIteration as e:
        # Generator finished, get return value
        if e.value:
            scene_assets, script, final_video_path = e.value

    return scene_assets, script, final_video_path


def main():
    parser = argparse.ArgumentParser(
        description='Generate viral movie videos using AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.app "The Matrix"                      # Full pipeline + render
    python -m src.app "Inception" -o my_video.mp4       # Custom output path
    python -m src.app "Toy Story" -v                    # Verbose logging
    python -m src.app "The Matrix" --assets-only        # Assets only, skip render
    python -m src.app "The Matrix" --offline            # Use cached data (no API calls)
        """
    )

    parser.add_argument(
        'movie',
        type=str,
        help='Name of the movie, project title, or prompt idea to generate a video about'
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['movie', 'animated', 'animation-script', 'animation-render', 'animation-series'],
        default='movie',
        help='Pipeline mode: "movie" (recap), "animated" (one-shot parody), "animation-script" (Phase 1 series writer), "animation-render" (Phase 2 series renderer), "animation-series" (9-step series pipeline)'
    )

    parser.add_argument(
        '--storyline',
        type=str,
        default=None,
        help='General storyline for animation-script mode'
    )

    parser.add_argument(
        '--char-desc',
        type=str,
        default=None,
        help='Character descriptions for animation-script mode'
    )

    parser.add_argument(
        '--episodes',
        type=int,
        default=3,
        help='Number of episodes to generate in animation-script mode (default: 3)'
    )

    parser.add_argument(
        '--episode-num',
        type=int,
        default=None,
        help='Specific episode number to render in animation-render mode'
    )

    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Start fresh instead of resuming from last state (animation-series mode)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose/debug logging'
    )

    parser.add_argument(
        '--assets-only',
        action='store_true',
        help='Stop after gathering assets (skip transcription and rendering)'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output path for the final video (default: output/final/<movie_name>.mp4)'
    )

    parser.add_argument(
        '--offline',
        action='store_true',
        help='Use cached data from output/temp folder instead of calling APIs'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Delete temp files after successful render'
    )

    args = parser.parse_args()

    # Validate required inputs for animation modes
    if args.mode in ("animation-script", "animation-series"):
        if not args.storyline or not args.char_desc:
            parser.error(
                f"--storyline and --char-desc are required for {args.mode} mode.\n"
                f'Example: python -m src.app "My Series" --mode {args.mode} '
                '--storyline "A tomato seeks revenge" --char-desc "Sir Tomato: a bruised roma tomato"'
            )

    # Setup logging
    logger = setup_logging(verbose=args.verbose, logger_name='src.app')

    print_banner()

    logger.info(f"Input: {args.movie}")
    mode_labels = {
        "movie": "MOVIE RECAP",
        "animated": "ANIMATED (episodic parody via Veo 3.1)",
        "animation-script": f"ANIMATION SCRIPT WRITER ({args.episodes} episodes)",
        "animation-render": f"ANIMATION RENDERER (episode {args.episode_num or 'next pending'})",
        "animation-series": f"ANIMATION SERIES (9-step pipeline, {args.episodes} episodes)",
    }
    logger.info(f"Mode: {mode_labels.get(args.mode, args.mode)}")
    if args.offline:
        logger.info("Mode: OFFLINE (using cached data)")
    if args.assets_only:
        logger.info("Mode: ASSETS-ONLY (skip rendering)")
    if args.clean:
        logger.info("Mode: CLEAN (temp files will be deleted after render)")
    print()

    start_time = datetime.now()

    try:
        # Animation Series mode uses a separate pipeline
        if args.mode == "animation-series":
            from src.animation_pipeline import run_animation_series

            gen = run_animation_series(
                project_title=args.movie,
                storyline=args.storyline,
                character_descriptions=args.char_desc,
                num_episodes=args.episodes,
                resume=not args.no_resume,
            )

            project_dir = None
            try:
                while True:
                    status = next(gen)
                    prefix = f"[Step {status.step}]" if status.step > 0 else "[INFO]"
                    if status.is_error:
                        logger.error(f"{prefix} {status.message}")
                    else:
                        logger.info(f"{prefix} {status.message}")
            except StopIteration as e:
                project_dir = e.value

            elapsed = datetime.now() - start_time
            logger.info(f"Total time: {elapsed.total_seconds():.1f} seconds")
            if project_dir:
                print(f"\nDone! Project directory: {project_dir}\n")
            else:
                logger.error("Pipeline failed — check logs and re-run to resume from last step")
                return 1
            return 0

        # Run the standard pipeline
        scene_assets, script, final_video_path = run_pipeline_with_logging(
            movie_name=args.movie,
            logger=logger,
            offline=args.offline,
            assets_only=args.assets_only,
            clean=args.clean,
            mode=args.mode,
            storyline=args.storyline,
            character_descriptions=args.char_desc,
            num_episodes=args.episodes,
            episode_number=args.episode_num,
        )

        elapsed = datetime.now() - start_time

        # animation-script and animation-render modes don't produce scene_assets
        if args.mode == "animation-script":
            logger.info(f"Total time: {elapsed.total_seconds():.1f} seconds")
            if final_video_path:
                print(f"\nDone! Project saved: {final_video_path}")
                print(f"Next step: render episodes with:")
                print(f"  python -m src.app \"{args.movie}\" --mode animation-render\n")
            else:
                logger.error("Pipeline completed but produced no output")
                return 1
            return 0

        if args.mode == "animation-render":
            logger.info(f"Total time: {elapsed.total_seconds():.1f} seconds")
            if final_video_path:
                print(f"\nDone! Video: {final_video_path}\n")
            else:
                logger.error("Pipeline completed but produced no output")
                return 1
            return 0

        if scene_assets:
            print_scene_assets(scene_assets, script)
            logger.info(f"Successfully processed {len(scene_assets)} scenes")
            logger.info(f"Total time: {elapsed.total_seconds():.1f} seconds")

            if final_video_path:
                print(f"\nDone! Final video: {final_video_path}\n")
            else:
                print("\nDone! Assets gathered.\n")

            return 0
        else:
            logger.error("No scene assets were generated")
            return 1

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
