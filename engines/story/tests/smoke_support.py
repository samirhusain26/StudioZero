"""
Isolation and fixtures for the story engine's $0 tests. Import this module BEFORE any
`src.*` module: it runs at import time.

- API keys are dummy values; engines/story/.env and output/settings.json are never read.
- Every socket connect / DNS lookup raises NetworkBlocked, so a missed stub fails the
  test instead of spending money.
- ffmpeg: the one on PATH if it runs, else a shim around the Remotion-bundled ffmpeg in
  engines/motion/node_modules (system ffmpeg on the owner's Mac is broken). That build
  lacks filters the recap renderer needs (setsar, fps, loop, asplit, aloop,
  sidechaincompress, ass); see FULL_RENDERER and the stand-in renderer below.
- All media is generated at test time into temp dirs (nothing is committed).
"""

import atexit
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = ENGINE_DIR.parent.parent
DUMMY_KEY = "dummy-not-a-key"

# ── 1. Dummy keys, no model overrides from the environment ──────────────────
for _key in ("GEMINI_API_KEY", "GROQ_API_KEY", "TMDB_API_KEY", "PEXELS_API_KEY", "FAL_KEY"):
    os.environ[_key] = DUMMY_KEY
for _key in (
    "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_GENAI_USE_VERTEXAI",
    "GEMINI_MODEL_NAME", "GEMINI_IMAGE_MODEL", "TTS_MODEL", "SERIES_NATIVE_AUDIO", "RECAP_MUSIC",
    "ACTIVE_VIDEO_MODEL", "ACTIVE_VIDEO_TIER", "VIDEO_MAX_BUDGET",
):
    os.environ.pop(_key, None)

# ── 2. Never read engines/story/.env or output/settings.json ────────────────
import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False  # src.config binds this at import

TMP_ROOT = Path(tempfile.mkdtemp(prefix="story-smoke-"))
atexit.register(shutil.rmtree, TMP_ROOT, True)
os.environ["STORY_SETTINGS_FILE"] = str(TMP_ROOT / "no-settings.json")

# ── 3. No network ────────────────────────────────────────────────────────────
NETWORK_ATTEMPTS = []


class NetworkBlocked(AssertionError):
    """Raised on any network access attempt (not an OSError, so no retry swallows it)."""


def _blocked(*args, **kwargs):
    NETWORK_ATTEMPTS.append(repr(args)[:200])
    raise NetworkBlocked(f"network access attempted in a $0 test: {args!r:.200}")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked


# ── 4. ffmpeg ────────────────────────────────────────────────────────────────

def _runs(cmd: str) -> bool:
    try:
        return subprocess.run([cmd, "-version"], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def _make_remotion_shim(shim_dir: Path):
    """ffmpeg/ffprobe scripts that run the Remotion-bundled binaries (or `remotion ffmpeg`)."""
    node_modules = REPO_ROOT / "engines" / "motion" / "node_modules"
    shim_dir.mkdir(parents=True, exist_ok=True)
    compositors = sorted((node_modules / "@remotion").glob("compositor-*/ffmpeg")) if (node_modules / "@remotion").exists() else []
    if compositors:
        lib_dir = compositors[0].parent
        for tool in ("ffmpeg", "ffprobe"):
            script = shim_dir / tool
            script.write_text(
                "#!/bin/sh\n"
                f'DYLD_LIBRARY_PATH="{lib_dir}" LD_LIBRARY_PATH="{lib_dir}" exec "{lib_dir / tool}" "$@"\n'
            )
            script.chmod(0o755)
        return shim_dir
    remotion = node_modules / ".bin" / "remotion"
    if remotion.exists():
        for tool in ("ffmpeg", "ffprobe"):
            script = shim_dir / tool
            script.write_text(f'#!/bin/sh\nexec "{remotion}" {tool} "$@"\n')
            script.chmod(0o755)
        return shim_dir
    return None


FFMPEG_SOURCE = None
if _runs("ffmpeg") and _runs("ffprobe"):
    FFMPEG_SOURCE = "PATH"
else:
    _shim = _make_remotion_shim(TMP_ROOT / "ffmpeg-shim")
    if _shim:
        os.environ["PATH"] = f"{_shim}{os.pathsep}{os.environ.get('PATH', '')}"
        if _runs("ffmpeg") and _runs("ffprobe"):
            FFMPEG_SOURCE = "remotion"


def _filters() -> set:
    if not FFMPEG_SOURCE:
        return set()
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and "->" in parts[2]:
            names.add(parts[1])
    return names


FFMPEG_FILTERS = _filters()
# Filters src/renderer.py's recap render uses (VideoRenderer.render_from_scenes)
RENDERER_FILTERS = {"scale", "crop", "setsar", "fps", "loop", "aformat", "asplit", "aloop", "sidechaincompress", "amix"}
MISSING_RENDERER_FILTERS = sorted(RENDERER_FILTERS - FFMPEG_FILTERS)
FULL_RENDERER = FFMPEG_SOURCE is not None and not MISSING_RENDERER_FILTERS
HAS_LIBASS = "ass" in FFMPEG_FILTERS


def ff(*args: str) -> None:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg {' '.join(args)} failed: {result.stderr[-500:]}")


# ── 5. Generated media ──────────────────────────────────────────────────────

def make_clip(path, seconds: float = 1.5, size: str = "360x640", audio: bool = False) -> str:
    """A tiny H.264 clip (blank frames), optionally with an AAC tone."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-f", "lavfi", "-i", f"nullsrc=s={size}:r=30:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=48000"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-shortest"]
    ff(*args, str(path))
    return str(path)


def make_image(path, size: str = "500x750") -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", f"nullsrc=s={size}:d=1", "-frames:v", "1", str(path))
    return str(path)


def make_tone_wav(path, seconds: float = 4.0, freq: float = 220.0, rate: int = 44100) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(seconds * rate))
        )
        wf.writeframes(frames)
    return str(path)


def wav_duration(path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


# ── 6. Recap fakes ──────────────────────────────────────────────────────────

SMOKE_TITLE = "Smoke Test Film"
PEXELS_URL = "https://www.pexels.com/video/smoke-test-clip-{n}/"


def fake_search_movie(self, query):
    return {"source": "wiki", "data": {"title": SMOKE_TITLE}}


def fake_get_movie_details(self, search_result):
    return {
        "title": SMOKE_TITLE,
        "plot": "A test pattern learns to render itself in under a minute, at no cost.",
        "actors": "",
        "year": "",
        "tagline": "",
        "source": "Wikipedia",
        "source_url": "https://en.wikipedia.org/wiki/Smoke_Test_Film",
        "wiki_title": SMOKE_TITLE,
        "categories": [],
    }


def fake_get_tmdb_metadata(self, movie_title):
    return {"poster_path": "/smoke-poster.jpg", "year": "2001", "tagline": "Nothing to see here.", "tmdb_id": 4242}


def fake_download_poster(self, poster_path, output_path):
    return make_image(output_path)


SCRIPT_TOKENS = (4000, 2000)  # usage the fake script call reports (priced into the ledger)


def fake_generate_script(self, movie_title, plot, callback=None):
    """A 3-scene VideoScript (the schema requires 6; model_construct skips that check)."""
    from src.narrative import Scene, VideoScript
    scenes = [
        Scene(
            scene_index=i,
            narration=text,
            visual_queries=[f"query {i} a", f"query {i} b", f"query {i} c"],
            visual_style_modifiers=["4k"],
            mood="calm",
            tts_speed=1.2,
        )
        for i, text in enumerate([
            "So this test pattern wakes up inside a render farm.",
            "Turns out nobody is paying for any of it.",
            "It renders three scenes and calls it a day.",
        ])
    ]
    self.last_provider = "gemini"
    self.last_model = self.gemini_model
    self.last_usage = {"promptTokens": SCRIPT_TOKENS[0], "outputTokens": SCRIPT_TOKENS[1], "totalTokens": sum(SCRIPT_TOKENS)}
    from src.pricing import charge
    charge("llm", self.gemini_model, "recap script", input_tokens=SCRIPT_TOKENS[0], output_tokens=SCRIPT_TOKENS[1])
    return VideoScript.model_construct(
        title=movie_title,
        genre="sci-fi",
        overall_mood="calm",
        selected_voice_id="am_adam",
        selected_music_file="smoke_bed.wav",
        lang_code="a",
        bpm=120,
        scenes=scenes,
    )


def fake_generate_audio(text, output_path, voice="af_bella", speed=1.0, lang_code=None, mood=None):
    """Silent narration: 0.3 s per word, 1-2 s."""
    from src.config import Config
    from src.pipeline import _create_silent_audio
    from src.pricing import charge
    seconds = max(1.0, min(2.0, 0.3 * len(text.split())))
    charge("tts", Config.TTS_MODEL, "narration", input_tokens=len(text) // 4, audio_seconds=seconds)
    return _create_silent_audio(str(output_path), duration_seconds=seconds), seconds


def fake_download_video(queries, output_path=None):
    """A generated clip with Pexels-like metadata; scene 2 found nothing and took generic Pexels footage."""
    n = int(Path(output_path).stem.split("_")[1])
    make_clip(output_path, seconds=1.0)
    if n == 2:
        return str(output_path), {
            "width": 360, "height": 640, "duration": 1, "pexels_url": PEXELS_URL.format(n=2000 + n),
            "photographer": "Generic Photographer", "query": "city lights at night", "enhanced_query": "city lights at night",
            "generic": True, "failed_queries": ["'query 2 a': No videos found"],
        }
    return str(output_path), {
        "width": 360, "height": 640, "duration": 1,
        "pexels_url": PEXELS_URL.format(n=1000 + n),
        "photographer": f"Smoke Photographer {n}",
        "query": queries[0],
        "enhanced_query": queries[0],
    }


def fake_whisper_transcribe(audio_path):
    """Synthetic word timings over the clip's duration."""
    duration = wav_duration(audio_path)
    words = ["smoke", "test", "words", "here"]
    step = duration / len(words)
    return [{
        "text": " ".join(words),
        "start": 0.0,
        "end": duration,
        "words": [{"word": f" {w}", "start": i * step, "end": (i + 1) * step} for i, w in enumerate(words)],
    }]


def standin_render_from_scenes(self, scene_assets, output_path, subtitle_path=None,
                               background_music_path=None, music_volume=0.3):
    """
    Test-only replacement for VideoRenderer.render_from_scenes when the available ffmpeg
    lacks the renderer's filters. Same inputs and output format (1080x1920, 30 fps, H.264
    + AAC), built only from scale/crop and the concat demuxer. No music, no captions.
    """
    work = Path(tempfile.mkdtemp(dir=TMP_ROOT, prefix="standin-"))
    segments = []
    for i, scene in enumerate(scene_assets):
        seg = work / f"seg_{i}.mp4"
        if scene.poster_path:
            src = ["-loop", "1", "-t", f"{scene.audio_duration:.3f}", "-i", scene.poster_path]
        else:
            src = ["-stream_loop", "-1", "-t", f"{scene.audio_duration:.3f}", "-i", scene.video_path]
        ff(*src, "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
           "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", str(seg))
        segments.append(seg)
    vlist = work / "videos.txt"
    vlist.write_text("".join(f"file '{p}'\n" for p in segments))
    alist = work / "audios.txt"
    alist.write_text("".join(f"file '{s.audio_path}'\n" for s in scene_assets))
    ff("-f", "concat", "-safe", "0", "-i", str(vlist), "-c", "copy", str(work / "video.mp4"))
    ff("-f", "concat", "-safe", "0", "-i", str(alist), "-c:a", "pcm_s16le", str(work / "voice.wav"))
    ff("-i", str(work / "video.mp4"), "-i", str(work / "voice.wav"), "-map", "0:v", "-map", "1:a",
       "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_path))
    return output_path


def make_music_catalog(root) -> Path:
    """A one-track CC0 catalog shaped like engines/motion/music/catalog.json, with its audio file."""
    import hashlib
    import json
    root = Path(root)
    audio = make_tone_wav(root / "motion" / "music" / "sources" / "test" / "smoke_bed.wav", seconds=3.0)
    catalog = root / "motion" / "music" / "catalog.json"
    catalog.write_text(json.dumps({"version": 1, "tracks": {"test-smoke-bed": {
        "id": "test-smoke-bed", "title": "Smoke Bed", "artist": "Test Artist", "source": "test",
        "file": "music/sources/test/smoke_bed.wav", "sha256": hashlib.sha256(Path(audio).read_bytes()).hexdigest(),
        "license": "CC0-1.0", "page": "https://opengameart.org/content/smoke-bed", "calm": 0.4,
    }}}))
    return catalog


def run_node(*args) -> subprocess.CompletedProcess:
    """Run a repo Node tool from the repo root."""
    return subprocess.run(["node", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def stage_package_validate(render_folder, batch_root, batch_id: str, number: int) -> dict:
    """
    tools/stage-story.mjs → review/originals.json (every check passed) → tools/package.mjs (which runs the
    contract validator). Returns {"stage", "package", "batch", "batchDir"}.
    """
    import json
    batch_dir = Path(batch_root) / batch_id
    staged = run_node("tools/stage-story.mjs", f"--batch={batch_id}", f"--dir={batch_dir}", f"--number={number}",
                      f"--library={batch_root}", str(render_folder))
    out = {"stage": staged, "batchDir": batch_dir, "package": None, "batch": None}
    if staged.returncode != 0:
        return out
    review_file = batch_dir / "review" / "originals.json"
    review = json.loads(review_file.read_text())
    review["reviewer"] = "smoke-test"
    for entry in review["episodes"].values():
        entry["checks"] = {k: True for k in entry["checks"]}
    review_file.write_text(json.dumps(review, indent=2))
    out["package"] = run_node("tools/package.mjs", "--project=originals", f"--batch={batch_id}", f"--dir={batch_dir}")
    if (batch_dir / "batch.json").exists():
        out["batch"] = json.loads((batch_dir / "batch.json").read_text())
    return out


def check_render_json(path) -> subprocess.CompletedProcess:
    """Run the repo's render.json checker (node tools/render-json.mjs) from the repo root."""
    return subprocess.run(
        ["node", "tools/render-json.mjs", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def node_available() -> bool:
    return shutil.which("node") is not None and (REPO_ROOT / "tools" / "render-json.mjs").exists()


def describe_ffmpeg() -> str:
    if not FFMPEG_SOURCE:
        return "no working ffmpeg"
    return (
        f"ffmpeg from {FFMPEG_SOURCE}; renderer filters "
        + ("all present" if FULL_RENDERER else f"missing {', '.join(MISSING_RENDERER_FILTERS)}")
        + ("; libass present" if HAS_LIBASS else "; no libass (captions are not burned in)")
    )


print(f"[smoke_support] {describe_ffmpeg()}", file=sys.stderr)
