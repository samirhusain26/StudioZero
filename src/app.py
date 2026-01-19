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

from src.pipeline import VideoGenerationPipeline, PipelineStatus


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure detailed logging with timestamps."""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter with detailed output
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # Also configure specific module loggers for detailed output
    for module in ['src.pipeline', 'src.narrative', 'src.moviedbapi',
                   'src.gemini_tts', 'src.stock_media', 'src.renderer', 'src.config']:
        module_logger = logging.getLogger(module)
        module_logger.setLevel(log_level)

    return logging.getLogger('src.app')


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
    assets_only: bool = False
):
    """
    Run the video generation pipeline with logging output.

    Args:
        movie_name: Name of the movie to generate video for.
        logger: Logger instance for output.
        offline: If True, use cached data.
        assets_only: If True, stop after gathering assets (skip rendering).

    Returns:
        Tuple of (scene_assets, script, final_video_path).
    """
    pipeline = VideoGenerationPipeline(offline=offline)
    gen = pipeline.run(movie_name)

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
        help='Name of the movie to generate a video about'
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

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(verbose=args.verbose)

    print_banner()

    logger.info(f"Movie: {args.movie}")
    if args.offline:
        logger.info("Mode: OFFLINE (using cached data)")
    if args.assets_only:
        logger.info("Mode: ASSETS-ONLY (skip rendering)")
    print()

    start_time = datetime.now()

    try:
        # Run the pipeline
        scene_assets, script, final_video_path = run_pipeline_with_logging(
            movie_name=args.movie,
            logger=logger,
            offline=args.offline,
            assets_only=args.assets_only
        )

        elapsed = datetime.now() - start_time

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
