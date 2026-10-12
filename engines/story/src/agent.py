"""
Story worker agent: the story engine's API for the Studio (docs/STUDIO_PLAN.md §1 decision 8, §6).

Runs on the owner's laptop (or any macOS/Linux host with this engine and its .env): binds to 127.0.0.1, is exposed on
the tailnet by that host's Tailscale Serve, and is reached only through the Pi's stdlib proxy
(publisher/app/studio_proxy.py), which forwards the Pi UI's /api/studio/* after the UI's own passcode/session check.
Replaces the old dashboard backend (src/server.py); parity list: docs/STUDIO_PLAN.md (story jobs).

    .venv/bin/python -m src.agent                 # from engines/story; token file made by scripts/agent-token.py

- Every request needs `Authorization: Bearer <token>` (STUDIO_AGENT_TOKEN_FILE, default ~/.config/studiozero/agent-token,
  0600). The token is never logged or returned.
- Polling JSON only: GET …/events?since=N. One run at a time on this host; cancel stops before the next step and,
  in the scene generator, before the next scene's paid submit (review B2).
- Paid work (runs, the random idea) needs a server-side estimate token the caller confirms, plus a budget check
  against the project's spend ledger; it is refused without them. Paid runs are off unless STUDIO_AGENT_ALLOW_PAID=1
  (open engine bugs block paid runs until fixed: docs/STUDIO_PLAN.md §14).
- API keys stay in this host's .env: they are never read from or written by requests, only reported as present.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from src.budget_guard import SpendLedger
from src.config import Config
from src.project_manager import Project, create_project, delete_project, get_project, get_project_dir, list_projects, update_project
from src.video_models import VIDEO_MODEL_REGISTRY, estimate_cost, estimate_episode_cost, get_model

logger = logging.getLogger(__name__)

VERSION = "agent-2026.10.12"
TOKEN_FILE = Path(os.getenv("STUDIO_AGENT_TOKEN_FILE") or Path.home() / ".config/studiozero/agent-token")
ROUTES = {"recap": "movie", "series": "animation-series"}  # API route name -> project_manager mode
MODES = {v: k for k, v in ROUTES.items()}
EVENTS_MAX = 2000
EVENT_TEXT_MAX = 2000
SHOTS_PER_EPISODE = 6  # estimate for episodes whose director step has not run yet (video_models.estimate_episode_cost)
PROJECT_ID = r"[A-Za-z0-9_-]{1,120}"
PRIVATE_FILES = {"spend_ledger.json", "project.json", "pipeline_state.json"}
FILE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4",
              ".json": "application/json", ".txt": "text/plain; charset=utf-8"}
TEXT_FILE_MAX = 2_000_000
STEP_NAMES = ("writer", "screenwriter", "casting", "world_builder", "director", "set_designer", "scene_generator", "editor")
PRESETS = {  # F20: one click sets the LLM, image, TTS and video tier
    "budget": {"llm_model": "gemini-2.5-flash-lite", "image_model": "gemini-2.5-flash-image", "tts_model": "gemini-2.5-flash-preview-tts", "tier": "cheapest"},
    "balanced": {"llm_model": "gemini-2.5-flash", "image_model": "gemini-2.5-flash-image", "tts_model": "gemini-2.5-flash-preview-tts", "tier": "recommended"},
    "premium": {"llm_model": "gemini-2.5-pro", "image_model": "gemini-2.5-flash-image", "tts_model": "gemini-2.5-pro-preview-tts", "tier": "high_fidelity"},
}
LLM_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro-preview"]
IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-3-pro-image-preview", "imagen-4.0-generate-001"]
TTS_MODELS = ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_token() -> Optional[str]:
    try:
        if TOKEN_FILE.stat().st_mode & 0o077:
            logger.error("[agent] Token file is readable by others; refusing to use it (chmod 600)")
            return None
        value = TOKEN_FILE.read_text().strip()
    except OSError:
        return None
    return value if len(value) >= 32 else None


# ── Jobs (one per project; one running on this host) ──────────────────────────


class Job:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.cancel = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.events: Deque[dict] = deque(maxlen=EVENTS_MAX)
        self.seq = 0
        self.lock = threading.Lock()

    def add(self, kind: str, message: str, **extra: Any) -> None:
        with self.lock:
            self.seq += 1
            self.events.append({"seq": self.seq, "at": utc(), "kind": kind, "message": _redact(str(message))[:EVENT_TEXT_MAX], **extra})

    def since(self, seq: int) -> List[dict]:
        with self.lock:
            return [e for e in self.events if e["seq"] > seq]

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class Runner:
    """Turns a project into a PipelineStatus generator. Tests replace it; nothing here is called at import."""

    def recap(self, project: Project, cancel: threading.Event, approved_script: Optional[dict]) -> Iterator:
        from src.pipeline import VideoGenerationPipeline
        return VideoGenerationPipeline(offline=False, clean=False).run(project.name, mode="movie", approved_script=approved_script)

    def series(self, project: Project, cancel: threading.Event, progress: Callable[[dict], None]) -> Iterator:
        from src.animation_pipeline import run_animation_pipeline
        params = project.params
        return run_animation_pipeline(
            project_title=params.get("project_title", project.name), brief=params.get("brief", ""),
            num_episodes=int(params.get("num_episodes", 1)), resume=True, progress_callback=progress,
            project_dir=get_project_dir(project.id), cancel_event=cancel,
        )

    def random_idea(self) -> dict:
        from google import genai
        from src.narrative import generate_random_story_idea
        text = generate_random_story_idea(genai.Client(api_key=Config.GEMINI_API_KEY))
        name, _, brief = text.partition(" - Summary:")
        return {"name": name.replace("Title:", "").strip()[:120], "brief": brief.strip()[:600] or text[:600]}


# ── Request bodies ────────────────────────────────────────────────────────────


class CreateBody(BaseModel):
    route: str
    name: str = Field(min_length=1, max_length=120)
    brief: str = Field(default="", max_length=2000)
    episodes: int = Field(default=1, ge=1, le=10)


class Confirm(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    estimateUsd: float = Field(ge=0)


class RunBody(BaseModel):
    confirm: Optional[Confirm] = None


class ScriptBody(BaseModel):
    script: dict


class SceneBody(BaseModel):
    action: str  # retry | edit | skip | change_model
    prompt: str = Field(default="", max_length=8000)
    modelId: str = Field(default="", max_length=80)


class DeleteBody(BaseModel):
    confirm: str


class SettingsBody(BaseModel):
    llm_model: Optional[str] = None
    image_model: Optional[str] = None
    tts_model: Optional[str] = None
    active_tier: Optional[str] = None
    active_model: Optional[str] = None
    max_budget: Optional[float] = Field(default=None, ge=0, le=1000)
    auto_downgrade: Optional[bool] = None


class IdeaBody(BaseModel):
    confirm: Optional[Confirm] = None


# ── The app ────────────────────────────────────────────────────────────────────


def create_app(token: Optional[str] = None, runner: Optional[Runner] = None, allow_paid: Optional[bool] = None,
               studio_root: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="StudioZero story worker agent", docs_url=None, redoc_url=None, openapi_url=None)
    state: Dict[str, Any] = {
        "token": token if token is not None else load_token(),
        "runner": runner or Runner(),
        "allow_paid": (os.getenv("STUDIO_AGENT_ALLOW_PAID") == "1") if allow_paid is None else allow_paid,
        "secret": secrets.token_bytes(32),  # signs estimates for this process only
        "jobs": {},
        "busy": threading.Lock(),
        "root": studio_root or Config.PROJECT_ROOT.parents[1],
    }
    jobs: Dict[str, Job] = state["jobs"]

    def authorized(request: Request) -> bool:
        expected = state["token"]
        supplied = request.headers.get("authorization", "")
        return bool(expected) and hmac.compare_digest(supplied.encode(), f"Bearer {expected}".encode())

    def auth(request: Request) -> None:
        if not authorized(request):
            raise HTTPException(401, "Not authorized.")

    @app.middleware("http")
    async def auth_first(request: Request, call_next):  # before routing and body parsing (security review F8)
        if not authorized(request):
            return JSONResponse({"error": "Not authorized."}, status_code=401)
        return await call_next(request)

    def job(project_id: str) -> Job:
        if project_id not in jobs:
            jobs[project_id] = Job(project_id)
        return jobs[project_id]

    def project_or_404(project_id: str) -> Project:
        if not re.fullmatch(PROJECT_ID, project_id):
            raise HTTPException(404, "Project not found.")
        p = get_project(project_id)
        if not p:
            raise HTTPException(404, "Project not found.")
        return p

    def video_model(p: Project) -> str:
        return p.params.get("video_model") or Config.ACTIVE_VIDEO_MODEL

    def max_budget(p: Project) -> float:
        return float(p.params.get("max_budget", Config.VIDEO_MAX_BUDGET))

    def originals_budget() -> dict:
        try:
            manifest = json.loads((state["root"] / "projects/originals/project.json").read_text())
            return manifest.get("budget") or {}
        except (OSError, ValueError):
            return {}

    def project_dir(p: Project) -> Path:
        return get_project_dir(p.id)

    def spend(p: Project) -> float:
        return SpendLedger(project_dir(p)).total() if (project_dir(p) / "spend_ledger.json").exists() else 0.0

    # ── Estimates: what the next run may cost, signed so the confirmation matches what was shown ──

    def remaining_scenes(p: Project) -> List[dict]:
        """Series: shots still to render (director output known), else SHOTS_PER_EPISODE per episode."""
        out = []
        base = project_dir(p)
        for ep in range(1, int(p.params.get("num_episodes", 1)) + 1):
            clips = base / "episodes" / f"episode_{ep}" / "clips"
            shots_file = base / "episodes" / f"episode_{ep}" / "director_shots.json"
            if shots_file.exists():
                try:
                    shots = json.loads(shots_file.read_text()).get("shots", [])
                except (OSError, ValueError):
                    shots = []
                for s in shots:
                    sid = s.get("scene_id")
                    if not (clips / f"scene_{sid}.mp4").exists() and not (clips / f"scene_{sid}.skip").exists():
                        out.append({"episode": ep, "scene": sid})
            else:
                out.extend({"episode": ep, "scene": None} for _ in range(SHOTS_PER_EPISODE))
        return out

    def estimate(p: Project) -> dict:
        route = MODES.get(p.mode, p.mode)
        unpriced: List[str] = []
        lines: List[dict] = []
        if route == "series":
            model_id = video_model(p)
            model = get_model(model_id)
            scenes = remaining_scenes(p)
            per = estimate_cost(model_id, model.max_duration_sec)
            if scenes:
                lines.append({"what": f"{len(scenes)} video clip(s) with {model.display_name}", "usd": round(per * len(scenes), 4)})
            unpriced += ["Gemini text and image calls (story, casting, worlds, set images)"]
        else:
            approved = bool(p.step_data.get("approved_script"))
            unpriced += (["Gemini text-to-speech narration"] if approved
                         else ["Gemini script (LLM)", "then, after you approve the script, Gemini text-to-speech"])
        total = round(sum(l["usd"] for l in lines), 4)
        fingerprint = json.dumps({"p": p.id, "u": p.updated_at, "l": lines, "m": video_model(p)}, sort_keys=True)
        sig = hmac.new(state["secret"], f"{fingerprint}|{total}".encode(), hashlib.sha256).hexdigest()[:32]
        spent = spend(p)
        return {"estimateUsd": total, "lines": lines, "unpriced": unpriced, "token": f"est-{sig}",
                "spentUsd": round(spent, 4), "maxBudgetUsd": max_budget(p), "paidRunsEnabled": state["allow_paid"],
                "originalsBudget": originals_budget()}

    def require_confirmation(p: Project, confirm: Optional[Confirm]) -> dict:
        """Refuses paid work without a matching, current estimate and a budget that covers it."""
        if not state["allow_paid"]:
            raise HTTPException(403, "Paid runs are switched off on this worker (open engine bugs: docs/STUDIO_PLAN.md §14).")
        if confirm is None:
            raise HTTPException(428, "Confirm the cost estimate first (GET …/estimate).")
        current = estimate(p)
        if not hmac.compare_digest(confirm.token, current["token"]) or abs(confirm.estimateUsd - current["estimateUsd"]) > 1e-9:
            raise HTTPException(409, "The estimate changed; review the new one and confirm again.")
        if current["spentUsd"] + current["estimateUsd"] > current["maxBudgetUsd"] + 1e-9:
            raise HTTPException(409, f"Over budget: ${current['spentUsd']:.2f} spent + ${current['estimateUsd']:.2f} estimated "
                                     f"exceeds the project budget of ${current['maxBudgetUsd']:.2f}.")
        return current

    # ── Running ──

    def start(p: Project) -> None:
        if not state["busy"].acquire(blocking=False):
            raise HTTPException(409, "Another run is in progress on this worker.")
        j = job(p.id)
        if j.running:
            state["busy"].release()
            raise HTTPException(409, "This project is already running.")
        j.cancel = threading.Event()
        p.status, p.error = "running", None
        update_project(p)
        j.add("status", "Run started")
        j.thread = threading.Thread(target=run_project, args=(p.id, j), daemon=True, name=f"story-{p.id}")
        j.thread.start()

    def run_project(project_id: str, j: Job) -> None:
        saved_model = Config.ACTIVE_VIDEO_MODEL
        final = "completed"
        try:
            p = get_project(project_id)
            if p is None:
                return
            Config.ACTIVE_VIDEO_MODEL = video_model(p)  # per project (review B8): never the global setting
            runner_ = state["runner"]
            if MODES.get(p.mode) == "series":
                gen = runner_.series(p, j.cancel, lambda msg: j.add(msg.get("type", "info"), msg.get("message", ""), data=_small(msg)))
            else:
                gen = runner_.recap(p, j.cancel, p.step_data.get("approved_script"))
            try:
                for status in gen:
                    j.add("error" if status.is_error else "step", status.message, step=status.step)
                    p = get_project(project_id) or p
                    p.current_step = str(status.step)
                    if status.data and isinstance(status.data, dict) and "script" in status.data:
                        p.step_data["script"] = status.data["script"]
                    if getattr(status, "retry_gate", False):
                        p.step_data["failed_scene"] = status.data
                        final = "scene_failed"
                    elif getattr(status, "review_gate", False):
                        final = "review"
                    elif status.is_error:
                        final = "paused" if j.cancel.is_set() else "error"
                        p.error = None if j.cancel.is_set() else str(status.message)[:2000]
                    elif j.cancel.is_set():
                        final = "paused"
                    update_project(p)
                    if final != "completed":
                        break
            finally:
                close = getattr(gen, "close", None)
                if close:
                    close()  # GeneratorExit at the pipeline's current yield: no more work starts
        except Exception as exc:  # noqa: BLE001 (any engine failure ends the run with a message, never a crash)
            logger.exception("[agent] Run crashed")
            final = "error"
            j.add("error", f"Run failed: {type(exc).__name__}")
            p = get_project(project_id)
            if p:
                p.error = f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            Config.ACTIVE_VIDEO_MODEL = saved_model
            p = get_project(project_id)
            if p:
                p.status = final
                update_project(p)
            j.add("status", {"completed": "Run completed", "review": "Script ready for review", "paused": "Run cancelled; resume to continue",
                             "scene_failed": "A scene failed; choose retry, edit, skip or another model", "error": "Run stopped with an error"}[final])
            state["busy"].release()

    # ── Views ──

    def view(p: Project) -> dict:
        j = jobs.get(p.id)
        out = {"id": p.id, "name": p.name, "route": MODES.get(p.mode, p.mode), "params": p.params, "status": p.status,
               "running": bool(j and j.running), "currentStep": p.current_step, "createdAt": p.created_at, "updatedAt": p.updated_at,
               "error": p.error, "videoModel": video_model(p), "spentUsd": round(spend(p), 4), "maxBudgetUsd": max_budget(p)}
        if MODES.get(p.mode) == "recap":
            out["script"] = p.step_data.get("approved_script") or p.step_data.get("script")
            out["scriptApproved"] = bool(p.step_data.get("approved_script"))
        if p.error:
            out["error"] = _redact(p.error)
        out["failedScene"] = _scene_view(p.step_data.get("failed_scene"))
        return out

    def pipeline_state(p: Project) -> Optional[dict]:
        f = project_dir(p) / "pipeline_state.json"
        try:
            return json.loads(f.read_text()) if f.exists() else None
        except (OSError, ValueError):
            return None

    # ── Endpoints ──

    def keys_present() -> Dict[str, bool]:
        """Which provider keys this host's .env has (never the values)."""
        return {name: bool(getattr(Config, attr, "")) for name, attr in
                (("gemini", "GEMINI_API_KEY"), ("tmdb", "TMDB_API_KEY"), ("pexels", "PEXELS_API_KEY"), ("fal", "FAL_KEY"), ("groq", "GROQ_API_KEY"))}

    @app.get("/studio/health")
    def health(_: None = Depends(auth)) -> dict:
        running = [pid for pid, j in jobs.items() if j.running]
        return {"ok": True, "version": VERSION, "engine": "story", "running": running, "keys": keys_present(),
                "paidRunsEnabled": state["allow_paid"], "originalsBudget": originals_budget()}

    @app.get("/studio/projects")
    def projects(_: None = Depends(auth)) -> dict:
        return {"projects": [view(p) for p in list_projects() if p.mode in MODES]}

    @app.post("/studio/projects")
    def create(body: CreateBody, _: None = Depends(auth)) -> dict:
        if body.route not in ROUTES:
            raise HTTPException(422, "route must be recap or series")
        if body.route == "series" and not body.brief.strip():
            raise HTTPException(422, "A series needs a brief.")
        params = {"project_title": body.name, "brief": body.brief, "num_episodes": body.episodes} if body.route == "series" else {}
        if not re.fullmatch(PROJECT_ID, Config.safe_title(body.name)):  # an id the API can reach again (review F2)
            raise HTTPException(422, "Use letters A–Z, digits, spaces, hyphens or underscores in the name.")
        try:
            p = create_project(body.name, ROUTES[body.route], params)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        return view(p)

    @app.get("/studio/projects/{project_id}")
    def one(project_id: str, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        return {**view(p), "pipelineState": _state_view(pipeline_state(p))}

    @app.delete("/studio/projects/{project_id}")
    def remove(project_id: str, body: DeleteBody, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        if body.confirm != p.id:
            raise HTTPException(422, "Type the project id to confirm.")
        if (j := jobs.get(p.id)) and j.running:
            raise HTTPException(409, "Cancel the run first.")
        delete_project(p.id)
        jobs.pop(p.id, None)
        return {"ok": True}

    @app.get("/studio/projects/{project_id}/events")
    def events(project_id: str, since: int = 0, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        j = job(p.id)
        return {"events": j.since(max(0, since)), "last": j.seq, "running": j.running, "status": p.status}

    @app.get("/studio/projects/{project_id}/estimate")
    def get_estimate(project_id: str, _: None = Depends(auth)) -> dict:
        return estimate(project_or_404(project_id))

    @app.post("/studio/projects/{project_id}/run")
    def run(project_id: str, body: RunBody, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        if p.status == "review":
            raise HTTPException(409, "Approve the script first.")
        require_confirmation(p, body.confirm)
        start(p)
        return view(get_project(p.id) or p)

    @app.post("/studio/projects/{project_id}/cancel")
    def cancel(project_id: str, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        j = job(p.id)
        if j.running:
            j.cancel.set()
            j.add("status", "Cancel requested: stopping before the next paid step")
        return {**view(p), "cancelling": j.running}

    @app.put("/studio/projects/{project_id}/script")
    def save_script(project_id: str, body: ScriptBody, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        if MODES.get(p.mode) != "recap" or p.status not in ("review", "paused", "error"):
            raise HTTPException(409, "Only a recap script waiting for review can be edited.")
        from src.narrative import VideoScript
        try:
            script = VideoScript.model_validate(body.script).model_dump()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"The script is not valid: {str(e)[:300]}") from None
        p.step_data["script"] = script
        p.step_data.pop("approved_script", None)
        update_project(p)
        return view(p)

    @app.post("/studio/projects/{project_id}/approve-script")
    def approve_script(project_id: str, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        if not p.step_data.get("script"):
            raise HTTPException(409, "There is no script to approve yet.")
        p.step_data["approved_script"] = p.step_data["script"]  # the next run renders exactly this (review B1)
        p.status = "paused"
        update_project(p)
        return view(p)

    @app.post("/studio/projects/{project_id}/scene")
    def scene(project_id: str, body: SceneBody, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        failed = p.step_data.get("failed_scene") or {}
        if p.status != "scene_failed" or not failed:
            raise HTTPException(409, "No scene is waiting for a decision.")
        base = project_dir(p).resolve()
        ep, sid = int(failed.get("episode_number", 0)), int(failed.get("scene_id", -1))
        clips = base / "episodes" / f"episode_{ep}" / "clips"
        if body.action == "edit":
            if not body.prompt.strip():
                raise HTTPException(422, "Write the new prompt.")
            clips.mkdir(parents=True, exist_ok=True)
            (clips / f"scene_{sid}_override.txt").write_text(body.prompt.strip(), encoding="utf-8")
        elif body.action == "skip":
            clips.mkdir(parents=True, exist_ok=True)
            (clips / f"scene_{sid}.skip").touch()
        elif body.action == "change_model":
            try:
                get_model(body.modelId)
            except KeyError:
                raise HTTPException(422, "Unknown video model.") from None
            p.params["video_model"] = body.modelId  # this project only (review B8)
        elif body.action != "retry":
            raise HTTPException(422, "action must be retry, edit, skip or change_model")
        p.step_data.pop("failed_scene", None)
        p.status = "paused"
        update_project(p)
        # The decision only: the run that follows is a separate, confirmed POST …/run with the new estimate.
        return {**view(p), "estimate": estimate(p)}

    @app.get("/studio/projects/{project_id}/artifacts")
    def artifacts(project_id: str, step: str, episode: Optional[int] = None, _: None = Depends(auth)) -> dict:
        p = project_or_404(project_id)
        if step not in STEP_NAMES:
            raise HTTPException(422, "Unknown step.")
        st = pipeline_state(p) or {}
        if episode:
            ep = st.get("episodes", {}).get(str(episode), {})
            node = (ep.get("steps", ep) or {}).get(step, {})
        else:
            node = st.get("series_steps", {}).get(step, {})
        base = project_dir(p).resolve()
        files = []
        for raw in node.get("artifact_paths", []) or []:
            path = _inside(base, p.id, raw)
            if path is not None and path.is_file() and path.name.lower() not in PRIVATE_FILES:
                rel = path.relative_to(base).as_posix()
                files.append({"path": rel, "bytes": path.stat().st_size, "kind": _kind(path),
                              "json": _json_preview(path) if path.suffix == ".json" else None})
        return {"step": step, "episode": episode, "files": files}

    @app.get("/studio/projects/{project_id}/files/{file_path:path}")
    def files(project_id: str, file_path: str, _: None = Depends(auth)):
        p = project_or_404(project_id)
        base = project_dir(p).resolve()
        target = (base / file_path).resolve()
        # Only the artifact kinds the Studio shows, never the job's own state files (security review F1, F4; names compared lower-cased).
        if not target.is_relative_to(base) or not target.is_file() or target.name.lower() in PRIVATE_FILES or _kind(target) == "file":  # APFS ignores case
            raise HTTPException(404, "File not found.")
        if target.suffix.lower() in (".json", ".txt"):
            if target.stat().st_size > TEXT_FILE_MAX:
                raise HTTPException(404, "File not found.")
            return Response(_redact(target.read_text(encoding="utf-8", errors="replace")), media_type=FILE_TYPES[target.suffix.lower()])
        return FileResponse(target, media_type=FILE_TYPES[target.suffix.lower()])  # Starlette answers Range requests

    @app.get("/studio/renders")
    def renders(_: None = Depends(auth)) -> dict:
        out = []
        for f in sorted(Config.FINAL_DIR.glob("*/render.json")) + sorted(Config.PROJECTS_DIR.glob("*/episodes/episode_*/render.json")):
            try:
                doc = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            out.append({"id": _render_id(f), "episodeId": doc.get("episodeId"), "route": doc.get("route"), "createdAt": doc.get("createdAt"),
                        "video": doc.get("video"), "costUsd": doc.get("costUsd"), "credits": doc.get("credits"), "disclosure": doc.get("disclosure")})
        out.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
        return {"renders": out}

    @app.get("/studio/renders/{render_id}/{name}")
    def render_file(render_id: str, name: str, _: None = Depends(auth)):
        if name not in ("video.mp4", "cover.jpg") or not re.fullmatch(r"[A-Za-z0-9_.~-]{1,300}", render_id):
            raise HTTPException(404, "File not found.")
        folder = _render_folder(render_id)
        if folder is None:
            raise HTTPException(404, "File not found.")
        doc = json.loads((folder / "render.json").read_text())
        rel = doc.get("video", {}).get("file") if name == "video.mp4" else (doc.get("cover") or {}).get("file")
        target = (folder / str(rel)).resolve() if rel else None
        if not target or not target.is_relative_to(folder.resolve()) or not target.is_file():
            raise HTTPException(404, "File not found.")
        return FileResponse(target)

    @app.get("/studio/settings")
    def settings(_: None = Depends(auth)) -> dict:
        tiers: Dict[str, list] = {}
        for m in VIDEO_MODEL_REGISTRY.values():
            tiers.setdefault(m.tier, []).append({"id": m.model_id, "name": m.display_name, "provider": m.provider, "costPerSecondUsd": m.cost_per_second,
                                                  "maxResolution": m.max_resolution, "maxDurationSeconds": m.max_duration_sec, "audio": m.has_audio,
                                                  "referenceImages": m.has_reference_images, "description": m.description,
                                                  "episodeUsd": estimate_episode_cost(m.model_id, SHOTS_PER_EPISODE, m.max_duration_sec)})
        return {"models": {"llm_model": Config.GEMINI_MODEL_NAME, "image_model": Config.GEMINI_IMAGE_MODEL, "tts_model": Config.TTS_MODEL},
                "choices": {"llm_model": LLM_MODELS, "image_model": IMAGE_MODELS, "tts_model": TTS_MODELS},
                "video": {"active_model": Config.ACTIVE_VIDEO_MODEL, "active_tier": Config.ACTIVE_VIDEO_TIER,
                          "max_budget": Config.VIDEO_MAX_BUDGET, "auto_downgrade": Config.VIDEO_AUTO_DOWNGRADE},
                "tiers": tiers, "presets": PRESETS, "keys": keys_present()}

    @app.put("/studio/settings")
    def save_settings(body: SettingsBody, _: None = Depends(auth)) -> dict:
        if body.llm_model and body.llm_model not in LLM_MODELS or body.image_model and body.image_model not in IMAGE_MODELS \
                or body.tts_model and body.tts_model not in TTS_MODELS:
            raise HTTPException(422, "Unknown model.")
        if body.active_model:
            try:
                get_model(body.active_model)
            except KeyError:
                raise HTTPException(422, "Unknown video model.") from None
        if body.active_tier and body.active_tier not in ("cheapest", "recommended", "high_fidelity"):
            raise HTTPException(422, "Unknown tier.")
        path = Path(os.getenv("STORY_SETTINGS_FILE") or Config.SETTINGS_FILE)
        try:
            current = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, ValueError):
            current = {}
        models = current.setdefault("models", {})
        video = current.setdefault("video_generation", {})
        for key in ("llm_model", "image_model", "tts_model"):
            if getattr(body, key):
                models[key] = getattr(body, key)
        for key in ("active_model", "active_tier", "max_budget", "auto_downgrade"):
            if getattr(body, key) is not None:
                video[key] = getattr(body, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, indent=2))  # credentials, if any, are kept as they were and never returned
        os.replace(tmp, path)
        Config.reload_settings()
        return settings()

    @app.post("/studio/ideas/random")
    def idea(body: IdeaBody, _: None = Depends(auth)) -> dict:
        if not state["allow_paid"]:
            raise HTTPException(403, "Paid calls are switched off on this worker.")
        if body.confirm is None or body.confirm.token != "idea-llm-call" or body.confirm.estimateUsd != 0:
            raise HTTPException(428, "Confirm the Gemini call first (one short LLM request, unpriced).")
        return state["runner"].random_idea()

    @app.exception_handler(HTTPException)
    def errors(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    # E24/F25: nothing is running when the agent starts.
    for p in list_projects():
        if p.status == "running":
            p.status = "paused"
            update_project(p)

    app.state.studio = state
    return app


def _inside(base: Path, project_id: str, raw: str) -> Optional[Path]:
    """An artifact path inside the project folder. Paths recorded before a folder move are mapped by their part after
    /<project id>/; anything that still resolves outside the folder is ignored."""
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    resolved = path.resolve()
    if not resolved.is_relative_to(base):
        parts = path.parts
        if project_id not in parts:
            return None
        resolved = (base / Path(*parts[len(parts) - parts[::-1].index(project_id):])).resolve()
    return resolved if resolved.is_relative_to(base) else None


def _redact(text: str) -> str:
    """Local folder names stay on this host: the engine folder becomes "…", the home folder "~"."""
    for prefix, short in ((str(Path(__file__).resolve().parents[1]), "…"), (str(Path.home()), "~")):
        text = text.replace(prefix, short)
    return text


def _small(msg: dict) -> dict:
    data = msg if msg.get("type") in ("veo_polling", "cost_update") else msg.get("data") if isinstance(msg.get("data"), dict) else {}
    return {k: v for k, v in data.items() if k != "type" and isinstance(v, (int, float, str, bool)) and len(str(v)) < 300}


def _state_view(st: Optional[dict]) -> Optional[dict]:
    """pipeline_state.json for the step rail: timings, errors and artifact counts (never this host's paths)."""
    if not st:
        return None

    def steps(nodes: dict) -> dict:
        return {name: {"completed": bool(n.get("completed")), "startedAt": n.get("started_at"), "completedAt": n.get("completed_at"),
                       "error": _redact(str(n["error"]))[:2000] if n.get("error") else None, "artifacts": len(n.get("artifact_paths") or [])}
                for name, n in (nodes or {}).items() if name in STEP_NAMES and isinstance(n, dict)}

    episodes = {}
    for key, ep in (st.get("episodes") or {}).items():
        if isinstance(ep, dict) and str(key).isdigit():
            episodes[str(key)] = steps(ep.get("steps", ep))
    return {"seriesSteps": steps(st.get("series_steps", {})), "episodes": episodes}


def _scene_view(failed: Optional[dict]) -> Optional[dict]:
    if not failed:
        return None
    return {"episode": failed.get("episode_number"), "scene": failed.get("scene_id"), "prompt": failed.get("veo_prompt"),
            "error": str(failed.get("error_detail") or "")[:2000]}


def _kind(path: Path) -> str:
    return {".png": "image", ".jpg": "image", ".jpeg": "image", ".mp4": "video", ".json": "json", ".txt": "text"}.get(path.suffix.lower(), "file")


def _json_preview(path: Path) -> Any:
    try:
        if path.stat().st_size > 512_000:
            return None
        return json.loads(_redact(path.read_text()))
    except (OSError, ValueError):
        return None


def _render_id(render_json: Path) -> str:
    return render_json.parent.resolve().relative_to(Config.OUTPUT_DIR.resolve()).as_posix().replace("/", "~")


def _render_folder(render_id: str) -> Optional[Path]:
    folder = (Config.OUTPUT_DIR / render_id.replace("~", "/")).resolve()
    if not folder.is_relative_to(Config.OUTPUT_DIR.resolve()) or not (folder / "render.json").is_file():
        return None
    return folder


def main() -> int:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if load_token() is None:
        print("Agent locked: no token file (run scripts/agent-token.py) or it is readable by others.")
        return 1
    port = int(os.getenv("STUDIO_AGENT_PORT", "8911"))
    # Loopback only: Tailscale Serve on this host is the only way in from the tailnet.
    uvicorn.run(create_app(), host="127.0.0.1", port=port, access_log=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
