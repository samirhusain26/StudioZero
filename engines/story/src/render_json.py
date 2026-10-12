"""
render.json writer — the engine → packager hand-off (tools/RENDER_JSON.md, version 1).

One render.json per rendered episode, in the folder that holds the episode's MP4 and
cover.jpg:
  recap:  output/final/{safe_title}/{safe_title}.mp4 + cover.jpg + script.json + render.json
  series: {project}/episodes/episode_N/final.mp4 + cover.jpg + render.json

Before the probe, the MP4 is conformed to the batch contract's media rules (H.264
yuv420p, AAC 48 kHz stereo, fast-start, at most 24 MB); a file that already meets them
is not touched.

costUsd comes from the project's spend_ledger.json (budget_guard.SpendLedger): every
LLM, image, TTS and video call, priced by src/pricing.py and registry.json. It is an
estimate (costEstimated=true): the ledger prices usage at list prices, not invoices.
A series episode carries its own spend plus an equal share of the project-level work.

episodeId here is the engine's work id (originals-recap-<title-year>,
originals-series-<project>-ep<n>); the Originals playbook's staging step
(tools/stage-story.mjs) assigns the contract id when it copies a render into a batch.
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

from src.budget_guard import LEDGER_FILENAME, SpendLedger
from src.config import Config
from src.video_models import load_registry_file

logger = logging.getLogger(__name__)

RENDER_JSON = "render.json"
RENDER_JSON_VERSION = 1
KIT_VERSION = load_registry_file()["kitVersion"]
PROJECT = "originals"
TMDB_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB"
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"
MAX_VIDEO_BYTES = 24_000_000  # contract/library_contract.py MAX_VIDEO_BYTES
AUDIO_BITRATE = 192_000


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


def mp4_faststart(path: Path) -> bool:
    """True when the moov box precedes mdat (the contract's fast-start rule)."""
    with open(path, "rb") as f:
        while True:
            header = f.read(8)
            if len(header) < 8:
                return False
            size = int.from_bytes(header[:4], "big")
            kind = header[4:8]
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                size = int.from_bytes(f.read(8), "big")
                f.seek(size - 16, 1)
            elif size == 0:
                return False
            else:
                f.seek(size - 8, 1)


def conform_for_contract(path: Path) -> List[str]:
    """
    Re-mux or re-encode `path` in place so it meets the contract's media rules. Only what
    is off is redone: audio not AAC 48 kHz stereo, video not H.264 yuv420p, moov after
    mdat, or more than 24 MB (then the video bitrate is set to fit). Returns what changed.
    """
    path = Path(path)
    probe = ffmpeg.probe(str(path))
    streams = probe.get("streams", [])
    v = next(s for s in streams if s.get("codec_type") == "video")
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(probe["format"]["duration"])
    fix_audio = a is not None and (a.get("codec_name") != "aac" or int(a.get("sample_rate") or 0) != 48000
                                   or int(a.get("channels") or 0) != 2)
    too_big = path.stat().st_size > MAX_VIDEO_BYTES
    fix_video = v.get("codec_name") != "h264" or v.get("pix_fmt") != "yuv420p" or too_big
    changes = (["audio"] if fix_audio else []) + (["video"] if fix_video else []) + \
              ([] if mp4_faststart(path) else ["faststart"])
    if not changes:
        return []
    tmp = path.with_suffix(".conform.mp4")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:v:0"]
    if a is not None:
        cmd += ["-map", "0:a:0"]
    if fix_video:
        # Fit under the cap with 8% headroom for the container
        kbps = int((MAX_VIDEO_BYTES * 0.92 * 8 / max(duration, 0.1) - AUDIO_BITRATE) / 1000)
        kbps = max(500, min(kbps, 4000))
        cmd += ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k",
                "-bufsize", f"{2 * kbps}k", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "copy"]
    if a is not None:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"] if fix_audio else ["-c:a", "copy"]
    cmd += ["-movflags", "+faststart", str(tmp)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Could not conform {path.name} to the contract: {result.stderr[-400:]}")
    tmp.replace(path)
    logger.info(f"[render_json] Conformed {path.name} to the contract ({', '.join(changes)})")
    return changes


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
    conformed = conform_for_contract(video_file)
    if conformed:
        job = {**job, "conformed": conformed}
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
    music: Optional[dict],
    llm: Optional[dict],
    tts_model: Optional[str],
    asr_model: Optional[str],
    subtitles_burned: bool,
    ledger_dir: Optional[Path] = None,
) -> Path:
    """render.json for a recap, next to its final MP4. `music` is src.music.pick_track's track or None."""
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
            # Only from a pre-2026-10-12 cache (assets/basevideos): no licence record, so the
            # packager refuses it; re-render the recap to replace the clip.
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

    if music:
        credits.append(credit(
            "music", f"\"{music['title']}\" (background music)", music["license"],
            creator=music["artist"], source_url=music["page"], path=Path(music["path"]),
        ))
    if subtitles_burned:
        font = Config.FONTS_DIR / "fraunces-latin-900-normal.woff"
        credits.append(credit(
            "font", f"{Config.CAPTION_FONT} (captions)", "OFL-1.1", creator="The Fraunces Project Authors",
            source_url="https://github.com/undercasetype/Fraunces", path=font,
        ))

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
        "music": music["id"] if music else None,
        "sceneCount": len(scene_assets),
        "llmProvider": llm.get("provider"),
        "llmUsage": llm.get("usage"),
        "subtitlesBurned": subtitles_burned,
    }

    ledger = SpendLedger(Path(ledger_dir)) if ledger_dir else None
    if ledger is not None and (Path(ledger_dir) / LEDGER_FILENAME).exists():
        job["costByKind"] = ledger.by_kind()
    return write_render_json(
        folder,
        Path(final_video),
        route="recap",
        episode_id=make_episode_id("originals-recap", f"{title} {year}".strip()),
        job=job,
        models=models,
        # Script, narration and any other paid call of this recap, from its spend ledger
        cost_usd=ledger.total() if ledger is not None else 0.0,
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

    native_audio = any(c["hasAudio"] for c in clips)
    ai_kinds = ["script", "image", "video"]
    if native_audio:
        ai_kinds.append("voice")  # native model audio (dialogue, sound) made it into the final cut

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
        "costByKind": ledger.by_kind(),
        "maxBudgetUsd": Config.VIDEO_MAX_BUDGET,
        "audio": {
            "policy": "native" if Config.SERIES_NATIVE_AUDIO else "silent",
            "clipsWithNativeAudio": sum(1 for c in clips if c["hasAudio"]),
            "clips": len(clips),
        },
    }

    note = (
        "Everything in this episode is AI-generated: the story and shot prompts (LLM), "
        "the character and set images, and the video clips"
        + (" including their native audio." if native_audio else "; the soundtrack is silent.")
    )

    return write_render_json(
        episode_dir,
        Path(final_video),
        route="series",
        episode_id=make_episode_id("originals-series", project_dir.name, f"ep{episode_number}"),
        job=job,
        models=models,
        # This episode's text, image and video spend (billed failures included) plus its
        # share of the project-level work (story, characters, worlds)
        cost_usd=ledger.episode_cost(episode_number, max(1, len(story.episode_outlines))),
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
