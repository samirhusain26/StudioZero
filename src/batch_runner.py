"""
Batch Runner for StudioZero Pipeline.

Processes multiple movies from a Google Sheet, running the full pipeline
for each pending job, updating the sheet with results, and exporting
videos to iCloud.

Usage:
    python -m src.batch_runner                    # Uses BATCH_SHEET_URL from .env
    python -m src.batch_runner --sheet-url URL    # Override sheet URL
    python -m src.batch_runner --verbose          # Enable debug logging
"""

import argparse
import logging
import shutil
import time
import traceback
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.logging_utils import setup_logging
from src.pipeline import run_pipeline
from src.cloud_services import get_pending_jobs, update_row
from src.marketing import generate_social_caption
from src.config import Config

logger = logging.getLogger(__name__)


def copy_to_icloud(mp4_path: str) -> Optional[str]:
    """
    Copy final MP4 to iCloud (macOS only). Returns None if on Linux/Cloud.
    """
    # 1. Check if we are on a Mac. If not, skip this entirely.
    if platform.system() != "Darwin":
        logger.info("Skipping iCloud export (Not running on macOS)")
        return None

    icloud_dir = Path(Config.ICLOUD_EXPORT_PATH)
    try:
        icloud_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fallback if the Config path is totally invalid on this OS
        logger.warning(f"Could not create iCloud directory: {icloud_dir}")
        return None

    source = Path(mp4_path)
    destination = icloud_dir / source.name

    # Handle filename collision
    if destination.exists():
        stem = source.stem
        suffix = source.suffix
        counter = 1
        while destination.exists():
            destination = icloud_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.copy2(source, destination)
    logger.info(f"Copied to iCloud: {destination}")

    return str(destination.resolve())


def save_caption_file(video_path: str, caption_text: str) -> Optional[str]:
    """
    Save a social media caption to a .txt file next to the video file.

    Args:
        video_path: Path to the MP4 video file.
        caption_text: The generated social media caption text.

    Returns:
        Path to the saved caption file, or None on failure.
    """
    try:
        caption_path = Path(video_path).with_suffix(".txt")
        caption_path.write_text(caption_text, encoding="utf-8")
        logger.info(f"Caption saved to: {caption_path}")
        return str(caption_path)
    except Exception as e:
        logger.warning(f"Failed to save caption file: {e}")
        return None


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a human-readable string."""
    minutes, secs = divmod(int(seconds), 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def process_movie(
    movie_name: str,
    sheet_url: str,
    row_index: int,
    verbose: bool = False,
) -> None:
    """
    Process a single movie through the full pipeline.

    Args:
        movie_name: Name of the movie to process.
        sheet_url: Google Sheet URL for status updates.
        row_index: Row index (1-based) in the sheet.
        verbose: Enable verbose logging.
    """
    # Record start time as human-readable timestamp
    start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_time = time.time()

    # Step 1: Mark as Processing with start_time
    logger.info(f"Starting: '{movie_name}' (row {row_index})")
    update_row(sheet_url, row_index, {
        "Status": "Processing",
        "start_time": start_timestamp,
        "end_time": "",
        "notes": "",
    })

    try:
        # Step 2: Run Pipeline
        logger.info(f"Running pipeline for '{movie_name}'...")

        def progress_callback(step: int, message: str, data: Optional[dict], is_error: bool):
            if is_error:
                logger.error(f"[Step {step}] {message}")
            elif verbose:
                logger.debug(f"[Step {step}] {message}")
            else:
                logger.info(f"[Step {step}] {message}")

        scene_assets, script, mp4_path = run_pipeline(
            movie_name=movie_name,
            progress_callback=progress_callback,
            offline=False,
        )

        if not mp4_path or not script:
            raise RuntimeError(f"Pipeline failed to produce output for '{movie_name}'")

        logger.info(f"Pipeline complete: {mp4_path}")

        # Step 3: Generate Social Caption
        logger.info(f"Generating social caption for '{movie_name}'...")
        social_caption = generate_social_caption(script)
        logger.info("Caption generated successfully")

        # Step 3b: Save caption as .txt file next to the video
        save_caption_file(mp4_path, social_caption)

        # Step 4: Copy to iCloud (Will return None if on Colab)
        logger.info(f"Copying to iCloud...")
        icloud_path = copy_to_icloud(mp4_path)

        # Record end time
        end_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = time.time() - start_time
        duration_str = format_duration(elapsed)

        # Step 5: Final Update - Mark as Completed
        update_row(sheet_url, row_index, {
            "Status": "Completed",
            "start_time": start_timestamp,
            "end_time": end_timestamp,
            # Use a safe default if icloud_path is None
            "icloud_link": icloud_path if icloud_path else "Saved to Drive (Cloud)", 
            "notes": "",
            "api_cost": "",
            "caption": social_caption,
            "ytshorts_status": "Ready for Upload",
            "ig_status": "Ready for Upload",
            "tiktok_status": "Ready for Upload",
        })

        logger.info(f"✓ Completed '{movie_name}' in {duration_str}")

    except Exception as e:
        # Error handling: log error and mark as Failed
        end_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = time.time() - start_time
        duration_str = format_duration(elapsed)
        error_msg = f"{type(e).__name__}: {str(e)}"
        full_traceback = traceback.format_exc()

        logger.error(f"Failed '{movie_name}': {error_msg}")
        logger.debug(full_traceback)

        update_row(sheet_url, row_index, {
            "Status": "Failed",
            "start_time": start_timestamp,
            "end_time": end_timestamp,
            "notes": f"{error_msg}\n{full_traceback[:500]}",
        })


def run_batch(sheet_url: str, verbose: bool = False, limit: Optional[int] = None) -> None:
    """
    Main batch processing loop.

    Fetches all pending jobs from the sheet and processes each one sequentially.

    Args:
        sheet_url: Google Sheet URL with movie queue.
        verbose: Enable verbose logging.
        limit: Maximum number of movies to process (None = all).
    """
    logger.info("Fetching pending jobs from Google Sheet...")
    pending_jobs = get_pending_jobs(sheet_url)

    if not pending_jobs:
        logger.info("No pending jobs found. Exiting.")
        return

    # Apply limit if specified
    if limit is not None and limit > 0:
        pending_jobs = pending_jobs[:limit]
        logger.info(f"Limited to {limit} job(s)")

    logger.info(f"Found {len(pending_jobs)} pending job(s)")

    for i, job in enumerate(pending_jobs, 1):
        # Support multiple column name variants for movie title
        movie_name = (
            job.get("movie_title") or
            job.get("Movie") or
            job.get("movie") or
            job.get("Title") or
            job.get("title")
        )
        row_index = job.get("_row_index")

        if not movie_name:
            logger.warning(f"Row {row_index}: No movie name found, skipping")
            update_row(sheet_url, row_index, {
                "Status": "Failed",
                "notes": "No movie name provided in row",
            })
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"Processing job {i}/{len(pending_jobs)}: '{movie_name}'")
        logger.info(f"{'='*60}")

        process_movie(
            movie_name=movie_name,
            sheet_url=sheet_url,
            row_index=row_index,
            verbose=verbose,
        )

    logger.info(f"\nBatch processing complete. Processed {len(pending_jobs)} job(s).")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="StudioZero Batch Runner - Process movies from Google Sheet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.batch_runner
    python -m src.batch_runner --sheet-url "https://docs.google.com/spreadsheets/d/abc123"
    python -m src.batch_runner --verbose

Environment Variables (set in .env file):
    BATCH_SHEET_URL: Default Google Sheet URL (can be overridden with --sheet-url)
    ICLOUD_EXPORT_PATH: Local path for iCloud export (optional, has default)

Sheet Requirements:
    The Google Sheet must have these columns:
    - movie_title: The movie name to process
    - Status: Set to "Pending" for jobs to be processed
    - start_time: Will be populated when processing starts
    - end_time: Will be populated when processing completes
    - icloud_link: Will be populated with local iCloud path
    - notes: Will be populated with error details (blank on success)
    - api_cost: Placeholder for future API cost tracking
    - caption: Will be populated with generated social media caption
        """,
    )

    parser.add_argument(
        "-s", "--sheet-url",
        default=None,
        help="Full URL to the Google Sheet (defaults to BATCH_SHEET_URL env var)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Maximum number of movies to process (default: all pending)",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    # Determine sheet URL from args or environment
    sheet_url = args.sheet_url or Config.BATCH_SHEET_URL
    if not sheet_url:
        parser.error(
            "No sheet URL provided. Either:\n"
            "  1. Pass --sheet-url on the command line, or\n"
            "  2. Set BATCH_SHEET_URL in your .env file"
        )

    try:
        run_batch(
            sheet_url=sheet_url,
            verbose=args.verbose,
            limit=args.limit,
        )
    except KeyboardInterrupt:
        logger.info("\nBatch processing interrupted by user.")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
