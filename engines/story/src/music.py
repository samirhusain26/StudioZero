"""
Recap background music from tracks with a recorded licence.

The source is the motion engine's music catalog (engines/motion/music/catalog.json):
CC0 tracks from OpenGameArt and HoliznaCC0 with artist, page and sha256, whose audio
files live in engines/motion/music/sources/ on the Mac (ignored by git). A track is
used only when its licence is CC0-1.0 and the local file matches the catalog's sha256.
The old assets/music files are never used: their licences are unknown.

The pick is deterministic: the genre sets how energetic the bed should be, and the
title chooses among the best fits, so a re-render gets the same track.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from src.config import Config

logger = logging.getLogger(__name__)

LICENSE = "CC0-1.0"
# Genres that want a driving bed; the rest get a calm one.
ENERGETIC = {"action", "thriller", "horror", "sci-fi", "mystery", "adventure", "war", "crime", "fantasy",
             "western", "sport"}
TOP_N = 5


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_track(genre: str, title: str, catalog: Optional[Path] = None) -> Optional[dict]:
    """
    A licensed track for a recap, or None (narration only).

    Returns {id, title, artist, license, page, path, sha256}.
    """
    if Config.RECAP_MUSIC == "none":
        return None
    catalog = Path(catalog or Config.MUSIC_CATALOG)
    if not catalog.exists():
        logger.warning(f"[music] No music catalog at {catalog.name}; the recap has narration only")
        return None
    tracks = json.loads(catalog.read_text(encoding="utf-8")).get("tracks", {})
    base = catalog.parent.parent  # catalog paths are relative to the motion engine folder
    energetic = (genre or "").lower() in ENERGETIC

    def fit(t: dict) -> float:
        calm = float(t.get("calm") or 0.5)
        return (1 - calm) if energetic else calm

    candidates = sorted(
        (t for t in tracks.values() if t.get("license") == LICENSE and t.get("page") and t.get("artist")
         and (base / t["file"]).is_file()),
        key=lambda t: (-fit(t), t["id"]),
    )[:TOP_N]
    if not candidates:
        logger.warning("[music] No CC0 track with a local file; the recap has narration only")
        return None
    index = int(hashlib.sha256((title or "").encode("utf-8")).hexdigest(), 16) % len(candidates)
    track = candidates[index]
    path = base / track["file"]
    digest = _sha256(path)
    if digest != track.get("sha256"):
        logger.warning(f"[music] {track['id']}: local file differs from the catalog; narration only")
        return None
    return {
        "id": track["id"],
        "title": track.get("title") or track["id"],
        "artist": track["artist"],
        "license": LICENSE,
        "page": track["page"],
        "path": str(path),
        "sha256": digest,
    }
