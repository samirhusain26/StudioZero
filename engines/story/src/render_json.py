"""
render.json writer — the engine → packager hand-off (tools/RENDER_JSON.md, version 1).

One render.json per rendered episode, in the folder that holds the episode's MP4 and
cover.jpg:
  recap:  output/final/{safe_title}/{safe_title}.mp4 + cover.jpg + script.json + render.json
  series: {project}/episodes/episode_N/final.mp4 + cover.jpg + render.json

Costs are estimates (costEstimated=true): series counts the per-clip video spend from
spend_ledger.json; LLM, image and TTS calls are not priced yet (token counts are kept
in job.llmUsage where the SDK reports them).
"""

import hashlib
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import ffmpeg

from src.config import Config
from src.video_models import load_registry_file

logger = logging.getLogger(__name__)

RENDER_JSON = "render.json"
RENDER_JSON_VERSION = 1
KIT_VERSION = load_registry_file()["kitVersion"]
PROJECT = "originals"
TMDB_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB"
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"


# ── Small helpers ───────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Lowercase [a-z0-9-] slug."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def make_episode_id(prefix: str, name: str, suffix: str = "") -> str:
    """'{prefix}-{slug(name)}[-{suffix}]', at most 80 characters ([a-z0-9-])."""
    tail = f"-{suffix}" if suffix else ""
    room = 80 - len(prefix) - 1 - len(tail)
    slug = slugify(name)[:room].strip("-") or "untitled"
    return f"{prefix}-{slug}{tail}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def probe_video(path: Path) -> dict:
    """The render.json `video` block (without `file`) from ffprobe."""
    probe = ffmpeg.probe(str(path))
    streams = probe.get("streams", [])
    v = next(s for s in streams if s.get("codec_type") == "video")
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fps = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
    if fps in ("0/0", "0/1"):
        fps = v.get("r_frame_rate", "30/1")
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "durationSeconds": round(float(probe["format"]["duration"]), 3),
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": fps,
        "videoCodec": v.get("codec_name"),
        "audioCodec": a.get("codec_name") if a else None,
    }


def has_audio_stream(path: Path) -> bool:
    try:
        return any(s.get("codec_type") == "audio" for s in ffmpeg.probe(str(path)).get("streams", []))
    except Exception:
        return False


def grab_cover(video_path: Path, cover_path: Path, at_seconds: float) -> Optional[Path]:
    """Save one frame of the video as cover.jpg. Returns None if ffmpeg fails."""
    cmd = [
        "ffmpeg", "-y", "-ss", f"{max(0.0, at_seconds):.3f}", "-i", str(video_path),
        "-frames:v", "1", "-q:v", "3", str(cover_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not cover_path.exists():
        logger.warning(f"[render_json] Cover grab failed: {result.stderr[-300:]}")
        return None
    return cover_path


def credit(
    kind: str,
    title: str,
    license: str,
    creator: Optional[str] = None,
    source_url: Optional[str] = None,
    attribution: Optional[str] = None,
    path: Optional[Path] = None,
) -> dict:
    if source_url and not source_url.startswith("https://"):
        source_url = source_url.replace("http://", "https://", 1) if source_url.startswith("http://") else None
    return {
        "kind": kind,
        "title": title,
        "creator": creator or None,
        "sourceUrl": source_url or None,
        "license": license,
        "attribution": attribution or None,
        "sha256": sha256_file(path) if path and Path(path).is_file() else None,
    }


def write_render_json(
    folder: Path,
    video_file: Path,
    *,
    route: str,
    episode_id: str,
    job: dict,
    models: List[dict],
    cost_usd: float,
    cost_estimated: bool,
    credits: List[dict],
    disclosure: dict,
    cover_at: Optional[float] = None,
) -> Path:
    """Probe the video, grab cover.jpg and write folder/render.json."""
    folder = Path(folder)
    video_file = Path(video_file)
    video = {"file": video_file.relative_to(folder).as_posix(), **probe_video(video_file)}

    cover = None
    at = cover_at if cover_at is not None else min(1.0, video["durationSeconds"] / 2)
    cover_path = grab_cover(video_file, folder / "cover.jpg", at)
    if cover_path:
        cover = {"file": "cover.jpg", "sha256": sha256_file(cover_path), "bytes": cover_path.stat().st_size}

    seen = set()
    unique_models = []
    for m in models:
        key = (m["role"], m["id"])
        if m["id"] and key not in seen:
            seen.add(key)
            unique_models.append({"role": m["role"], "id": m["id"]})

    doc = {
        "renderJsonVersion": RENDER_JSON_VERSION,
        "engine": "story",
        "route": route,
        "kitVersion": KIT_VERSION,
        "project": PROJECT,
        "episodeId": episode_id,
        "createdAt": _utc_now(),
        "job": job,
        "video": video,
        "cover": cover,
        "models": unique_models,
        "costUsd": round(max(0.0, cost_usd), 4),
        "costEstimated": cost_estimated,
        "credits": credits,
        "disclosure": disclosure,
    }
    out = folder / RENDER_JSON
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(f"[render_json] Wrote {out}")
    return out


# ── Recap ───────────────────────────────────────────────────────────────────

def write_recap_render_json(
    final_video: Path,
    movie_name: str,
    movie_details: dict,
    script,
    scene_assets: list,
    music_path: Optional[str],
    llm: Optional[dict],
    tts_model: Optional[str],
    asr_model: Optional[str],
    subtitles_burned: bool,
) -> Path:
    """render.json for a recap, next to its final MP4."""
    folder = Path(final_video).parent
    title = movie_details.get("title") or movie_name
    year = str(movie_details.get("year") or "")
    plot_source = movie_details.get("source") or ""
    tmdb_id = movie_details.get("tmdb_id")
    poster_path_tmdb = movie_details.get("poster_path") or ""

    # The script the narration was made from, kept with the render
    script_file = folder / "script.json"
    script_file.write_text(json.dumps(script.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    from src.gemini_tts import _map_voice
    voice = _map_voice(script.selected_voice_id)

    llm = llm or {}
    models = []
    if llm.get("model"):
        models.append({"role": "llm", "id": llm["model"]})
    if tts_model:
        models.append({"role": "tts", "id": tts_model})
    if asr_model:
        models.append({"role": "asr", "id": asr_model})

    tmdb_attribution = f"Data and images from TMDB (themoviedb.org). {TMDB_NOTICE}."
    tmdb_url = f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else "https://www.themoviedb.org/"

    credits = [
        credit("text", f"Narration script for {title}", "generated",
               creator=f"{llm.get('provider') or 'llm'}:{llm.get('model') or 'unknown'}"),
        credit("voice", f"Narration voice ({voice})", "generated", creator=tts_model),
    ]

    # Plot text the script was written from
    if plot_source.startswith("Wikipedia") and "TMDB (plot)" not in plot_source:
        credits.append(credit(
            "text", f"Plot of {title} (Wikipedia)", "Wikipedia-CC-BY-SA",
            creator="Wikipedia contributors",
            source_url=movie_details.get("source_url"),
            attribution=(
                f"Plot adapted from the Wikipedia article \"{movie_details.get('wiki_title') or title}\" "
                f"by Wikipedia contributors, licensed under CC BY-SA 4.0."
            ),
        ))
    elif plot_source:
        credits.append(credit(
            "text", f"Plot overview of {title} (TMDB)", "TMDB",
            creator="TMDB", source_url=tmdb_url, attribution=tmdb_attribution,
        ))
    if tmdb_id or poster_path_tmdb:
        credits.append(credit(
            "data", f"Release year and tagline of {title} (TMDB)", "TMDB",
            creator="TMDB", source_url=tmdb_url, attribution=tmdb_attribution,
        ))

    # Footage and poster per scene
    for asset in scene_assets:
        meta = asset.video_metadata or {}
        if asset.poster_path:
            credits.append(credit(
                "poster", f"{title} poster", "TMDB",
                creator="TMDB",
                source_url=f"https://image.tmdb.org/t/p/original{poster_path_tmdb}" if poster_path_tmdb else tmdb_url,
                attribution=tmdb_attribution,
                path=Path(asset.poster_path),
            ))
        elif meta.get("fallback"):
            credits.append(credit(
                "footage", f"Stock fallback clip {meta.get('fallback_file')} (scene {asset.index})", "unknown",
                path=Path(asset.video_path),
            ))
        else:
            photographer = meta.get("photographer")
            credits.append(credit(
                "footage", f"Pexels video for \"{meta.get('query') or ', '.join(asset.visual_queries[:1])}\" (scene {asset.index})",
                "Pexels",
                creator=photographer,
                source_url=meta.get("pexels_url"),
                attribution=f"Video by {photographer} on Pexels" if photographer else "Video from Pexels",
                path=Path(asset.video_path),
            ))

    if music_path:
        # assets/music has no licence records yet: recorded honestly as unknown
        credits.append(credit("music", Path(music_path).name, "unknown", path=Path(music_path)))
    if subtitles_burned:
        credits.append(credit("font", "Arial Black (system font, captions)", "unknown"))

    has_footage = any(not a.poster_path for a in scene_assets)
    note = (
        "The narration script and the narrator's voice are AI-generated (LLM and TTS); "
        "the footage is " + ("stock video" if has_footage else "none") +
        (" and the closing poster comes from TMDB." if any(a.poster_path for a in scene_assets) else ".")
    )

    job = {
        "input": movie_name,
        "title": title,
        "year": year or None,
        "safeTitle": Config.safe_title(movie_name),
        # The recap route needs a film plot today (a story idea with no match fails), so
        # everything it renders is a movie recap; story-recap is reserved in registry.json.
        "format": "movie-recap",
        "plotSource": plot_source or None,
        "plotUrl": (movie_details.get("source_url") or None) if "TMDB" not in plot_source else tmdb_url,
        "tmdbId": tmdb_id,
        "script": script_file.name,
        "genre": script.genre,
        "mood": script.overall_mood,
        "voice": voice,
        "music": Path(music_path).name if music_path else None,
        "sceneCount": len(scene_assets),
        "llmProvider": llm.get("provider"),
        "llmUsage": llm.get("usage"),
        "subtitlesBurned": subtitles_burned,
    }

    return write_render_json(
        folder,
        Path(final_video),
        route="recap",
        episode_id=make_episode_id("originals-recap", f"{title} {year}".strip()),
        job=job,
        models=models,
        # TODO(costs): LLM tokens and TTS characters are not priced yet (docs/HEADLESS.md)
        cost_usd=0.0,
        cost_estimated=True,
        credits=credits,
        disclosure={
            "aiGenerated": True,
            "aiKinds": ["script", "voice"],
            "realisticSynthetic": False,
            "note": note,
        },
    )


# ── Series ──────────────────────────────────────────────────────────────────

_STYLISED_WORDS = ("animation", "animated", "pixar", "cartoon", "claymation", "stop-motion", "anime")


def write_series_render_json(project_dir: Path, episode_number: int, final_video: Path) -> Path:
    """render.json for a series episode, next to episodes/episode_N/final.mp4."""
    from src.budget_guard import SpendLedger
    from src.steps.director import load_director_shots
    from src.steps.writer import load_story

    project_dir = Path(project_dir)
    episode_dir = Path(final_video).parent
    story = load_story(project_dir)
    shots = load_director_shots(episode_dir)
    ledger = SpendLedger(project_dir)
    clips_dir = episode_dir / "clips"

    outline = next((o for o in story.episode_outlines if o.episode_number == episode_number), None)

    clips = []
    clip_credits = []
    video_models: List[str] = []
    for shot in shots.shots:
        clip = clips_dir / f"scene_{shot.scene_id}.mp4"
        if not clip.exists():
            continue  # skipped scene
        entry = ledger.clip_entry(episode_number, shot.scene_id) or {}
        model_id = entry.get("modelId") or "unknown"
        if model_id not in video_models:
            video_models.append(model_id)
        clip_has_audio = has_audio_stream(clip)
        clips.append({
            "sceneId": shot.scene_id,
            "modelId": model_id,
            "costUsd": round(sum(e.get("costUsd", 0.0) for e in ledger.entries_for(episode_number, shot.scene_id)), 4),
            "ledgerSource": entry.get("source"),
            "hasAudio": clip_has_audio,
        })
        clip_credits.append(credit(
            "footage", f"Scene {shot.scene_id} clip ({model_id})", "generated", creator=model_id, path=clip,
        ))

    image_credits = []
    seen_images = set()
    for shot in shots.shots:
        start = project_dir / "scene_starts" / f"{shot.primary_character_id}_{shot.location_id}.png"
        if start.exists() and start.name not in seen_images:
            seen_images.add(start.name)
            image_credits.append(credit(
                "image", f"Scene start {start.stem}", "generated", creator=Config.GEMINI_IMAGE_MODEL, path=start,
            ))

    final_has_audio = has_audio_stream(Path(final_video))
    ai_kinds = ["script", "image", "video"]
    if final_has_audio:
        ai_kinds.append("voice")  # native model audio (dialogue/sfx) made it into the final cut

    stylised = bool(shots.shots) and all(
        any(w in s.veo_prompt.lower() for w in _STYLISED_WORDS) for s in shots.shots
    )

    models = [
        {"role": "llm", "id": Config.GEMINI_MODEL_NAME},
        {"role": "image", "id": Config.GEMINI_IMAGE_MODEL},
    ] + [{"role": "video", "id": m} for m in video_models]

    job = {
        "projectTitle": story.project_title,
        "projectDir": project_dir.name,
        "episodeNumber": episode_number,
        "episodeTitle": outline.title if outline else None,
        "logline": story.logline,
        "format": "animated-short",
        "shotCount": len(shots.shots),
        "clips": clips,
        "projectSpendUsd": ledger.total(),
        "maxBudgetUsd": Config.VIDEO_MAX_BUDGET,
    }

    note = (
        "Everything in this episode is AI-generated: the story and shot prompts (LLM), "
        "the character and set images, and the video clips"
        + (" including their native audio." if final_has_audio else " (no audio track).")
    )

    return write_render_json(
        episode_dir,
        Path(final_video),
        route="series",
        episode_id=make_episode_id("originals-series", project_dir.name, f"ep{episode_number}"),
        job=job,
        models=models,
        # Video spend from the ledger (billed attempts, failed ones included); LLM and
        # image calls are not priced yet.
        cost_usd=ledger.total(episode_number),
        cost_estimated=True,
        credits=[credit("text", f"Story and shot prompts for {story.project_title}", "generated",
                        creator=Config.GEMINI_MODEL_NAME)] + image_credits + clip_credits,
        disclosure={
            "aiGenerated": True,
            "aiKinds": ai_kinds,
            "realisticSynthetic": not stylised,
            "note": note,
        },
    )
