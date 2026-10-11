"""
Stock Media module for downloading videos from Pexels API.

This module provides functionality to search and download portrait (9:16)
stock videos that match visual keywords from the narrative script.
Videos are optimized for cinematic quality with 4K enhancement.
"""

import logging
import os
import random
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from src.config import Config

logger = logging.getLogger(__name__)

# Pexels API endpoint
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

# Target resolution for 9:16 portrait videos
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# Minimum video duration in seconds
MIN_VIDEO_DURATION = 5

# Local fallback video directory
FALLBACK_VIDEO_DIR = Config.ASSETS_DIR / "basevideos"


class PexelsAPIError(Exception):
    """Raised when Pexels API returns an error."""
    pass


class VideoNotFoundError(Exception):
    """Raised when no suitable video is found."""
    pass


def _get_headers() -> dict:
    """
    Returns the headers required for Pexels API requests.

    Returns:
        Dictionary of HTTP headers.

    Raises:
        ValueError: If PEXELS_API_KEY is not configured.
    """
    if not Config.PEXELS_API_KEY:
        raise ValueError(
            "PEXELS_API_KEY is not configured. "
            "Please add it to your .env file."
        )

    return {
        "Authorization": Config.PEXELS_API_KEY
    }


def _calculate_resolution_distance(width: int, height: int) -> int:
    """
    Calculates how far a resolution is from the target 1080x1920 (9:16 portrait).

    Args:
        width: Video width in pixels.
        height: Video height in pixels.

    Returns:
        Distance score (lower is better).
    """
    return abs(width - TARGET_WIDTH) + abs(height - TARGET_HEIGHT)


def _find_best_video_file(video_files: list) -> Optional[dict]:
    """
    Finds the video file closest to 1080x1920 (9:16 portrait) resolution.

    Args:
        video_files: List of video file dictionaries from Pexels API.

    Returns:
        The video file dict closest to 9:16 portrait resolution, or None if empty.
    """
    if not video_files:
        return None

    best_file = None
    best_distance = float('inf')

    for vf in video_files:
        width = vf.get('width', 0)
        height = vf.get('height', 0)
        distance = _calculate_resolution_distance(width, height)

        if distance < best_distance:
            best_distance = distance
            best_file = vf

    return best_file


def _search_videos(query: str, per_page: int = 15) -> list:
    """
    Searches for videos on Pexels matching the query.

    Args:
        query: Search query string.
        per_page: Number of results per page (max 80).

    Returns:
        List of video dictionaries from the API response.

    Raises:
        PexelsAPIError: If the API request fails.
    """
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": "portrait",  # Portrait videos for 9:16 format
    }

    try:
        response = requests.get(
            PEXELS_VIDEO_SEARCH_URL,
            headers=_get_headers(),
            params=params,
            timeout=30
        )
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        raise PexelsAPIError(f"Failed to search Pexels API: {e}") from e

    data = response.json()
    return data.get("videos", [])


def _filter_portrait_videos(videos: list) -> list:
    """
    Filters videos to only include portrait (9:16) orientation.

    Args:
        videos: List of video dictionaries.

    Returns:
        Filtered list containing only portrait videos.
    """
    portrait_videos = []

    for video in videos:
        width = video.get("width", 0)
        height = video.get("height", 0)

        # Portrait means height > width (9:16 vertical format)
        if height > width:
            portrait_videos.append(video)

    return portrait_videos


def _download_file(url: str, output_path: Path) -> None:
    """
    Downloads a file from URL to the specified path.

    Args:
        url: The URL to download from.
        output_path: Where to save the downloaded file.

    Raises:
        requests.exceptions.RequestException: If download fails.
    """
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def download_video(
    queries: List[str],
    output_path: str = None
) -> Tuple[str, dict]:
    """
    Downloads a stock video from Pexels matching one of the queries.

    Loops through the queries list, appending "cinematic 4k" to each for quality.
    Searches for portrait (9:16) videos and validates duration > 5 seconds.
    If all queries fail, falls back to a random local video from assets/basevideos/.

    Args:
        queries: List of search queries (e.g., ['stormy ocean', 'dramatic waves']).
        output_path: Where to save the video. If None, saves to assets dir.

    Returns:
        Tuple of (file_path, metadata_dict).
        metadata_dict contains: width, height, duration, pexels_url, photographer.

    Raises:
        VideoNotFoundError: If no suitable video is found and no fallback exists.
    """
    # Set default output path using first query
    if output_path is None:
        first_query = queries[0] if queries else "video"
        safe_query = "".join(c if c.isalnum() or c in "_ -" else "_" for c in first_query)
        output_path = Config.ASSETS_DIR / "videos" / f"{safe_query[:50]}.mp4"
    else:
        output_path = Path(output_path)

    failed_queries = []

    # Loop through all queries
    for query in queries:
        # Append "cinematic 4k" to improve quality
        enhanced_query = f"{query} cinematic 4k"

        try:
            # Search for videos (landscape orientation)
            videos = _search_videos(enhanced_query)

            if not videos:
                failed_queries.append(f"'{query}': No videos found")
                continue

            # Filter for portrait (9:16) videos
            portrait_videos = _filter_portrait_videos(videos)

            # Fall back to all videos if no portrait ones found
            candidate_videos = portrait_videos if portrait_videos else videos

            # Filter by minimum duration (> 5 seconds)
            duration_filtered = [
                v for v in candidate_videos
                if v.get("duration", 0) > MIN_VIDEO_DURATION
            ]

            if not duration_filtered:
                failed_queries.append(f"'{query}': No videos with duration > {MIN_VIDEO_DURATION}s")
                continue

            candidate_videos = duration_filtered

            # Select the first video (Pexels returns most relevant first)
            selected_video = candidate_videos[0]

            # Find the best quality video file (closest to 1920x1080)
            video_files = selected_video.get("video_files", [])
            best_file = _find_best_video_file(video_files)

            if not best_file:
                failed_queries.append(f"'{query}': No downloadable video files")
                continue

            # Download the video
            download_url = best_file.get("link")
            if not download_url:
                failed_queries.append(f"'{query}': Video file has no download link")
                continue

            _download_file(download_url, output_path)

            # Build metadata
            metadata = {
                "width": best_file.get("width"),
                "height": best_file.get("height"),
                "duration": selected_video.get("duration"),
                "pexels_url": selected_video.get("url"),
                "photographer": selected_video.get("user", {}).get("name", "Unknown"),
                "query": query,
                "enhanced_query": enhanced_query,
            }

            return str(output_path), metadata

        except PexelsAPIError as e:
            failed_queries.append(f"'{query}': API error - {e}")
            continue

        except requests.exceptions.RequestException as e:
            failed_queries.append(f"'{query}': Network error - {e}")
            continue

    # All queries failed - use local fallback
    return _use_local_fallback(queries, failed_queries)


def _use_local_fallback(
    queries: List[str],
    failed_queries: List[str]
) -> Tuple[str, dict]:
    """
    Falls back to a random local video from assets/basevideos/ when all queries fail.

    Args:
        queries: The original list of search queries.
        failed_queries: List of failure reasons for each query.

    Returns:
        Tuple of (file_path, metadata_dict).

    Raises:
        VideoNotFoundError: If no fallback videos exist in assets/basevideos/.
    """
    # Check if fallback directory exists
    if not FALLBACK_VIDEO_DIR.exists():
        raise VideoNotFoundError(
            f"Pexels search failed for all queries and fallback directory does not exist.\n"
            f"Failed queries: {failed_queries}\n"
            f"Please create the directory: {FALLBACK_VIDEO_DIR}"
        )

    # Find all .mp4 files in the fallback directory
    mp4_files = list(FALLBACK_VIDEO_DIR.glob("*.mp4"))

    if not mp4_files:
        raise VideoNotFoundError(
            f"Pexels search failed for all queries and no fallback videos found.\n"
            f"Failed queries: {failed_queries}\n"
            f"Please add .mp4 files to: {FALLBACK_VIDEO_DIR}"
        )

    # Randomly select one fallback video
    selected_file = random.choice(mp4_files)

    logger.warning(f"Pexels search failed for all queries. Using local fallback: {selected_file.name}")

    metadata = {
        "width": None,
        "height": None,
        "duration": None,
        "pexels_url": None,
        "photographer": None,
        "queries": queries,
        "fallback": True,
        "fallback_file": selected_file.name,
        "failed_queries": failed_queries,
    }

    return str(selected_file), metadata
