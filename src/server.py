"""
StudioZero Web Server — FastAPI backend with WebSocket pipeline streaming.

Run via: python -m src.app
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import Config
from src.project_manager import (
    Project, list_projects, get_project, create_project,
    update_project, delete_project, get_project_dir,
)

# ── Retry endpoint request model ─────────────────────────────────────────────

class RetrySceneRequest(BaseModel):
    action: str  # "retry" | "edit" | "skip"
    new_prompt: str = ""  # only used when action == "edit"

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="StudioZero", docs_url="/docs")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Active pipeline runs (project_id -> asyncio.Queue) ──────────────

_active_runs: Dict[str, asyncio.Queue] = {}


# ── Models ───────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    mode: str  # movie | animated | animation-series
    params: dict = {}


class UpdateScriptRequest(BaseModel):
    script: dict  # the edited script payload


class RunStepRequest(BaseModel):
    pass  # placeholder — step is in the URL path


# ── HTML entry ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# ── Project CRUD ─────────────────────────────────────────────────────

@app.get("/api/projects")
async def api_list_projects():
    return [p.model_dump() for p in list_projects()]


@app.post("/api/projects")
async def api_create_project(req: CreateProjectRequest):
    try:
        p = create_project(req.name, req.mode, req.params)
        return p.model_dump()
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p.model_dump()


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    if project_id in _active_runs:
        raise HTTPException(409, "Cannot delete a project while its pipeline is running. Pause it first.")
    if not delete_project(project_id):
        raise HTTPException(404, "Project not found")
    return {"ok": True}


# ── Sheet-based project creation ──────────────────────────────────────

@app.post("/api/projects/from-sheet")
async def api_create_from_sheet():
    """Create a project from the next pending row in Google Sheet."""
    # Resolve sheet URL from settings.json, then env var
    sheet_url = None
    if Config.SETTINGS_FILE.exists():
        data = json.loads(Config.SETTINGS_FILE.read_text(encoding="utf-8"))
        sheet_url = data.get("integrations", {}).get("BATCH_SHEET_URL")
    if not sheet_url:
        sheet_url = Config.BATCH_SHEET_URL
    if not sheet_url:
        raise HTTPException(400, "No Google Sheet URL configured. Set it in Settings → Integrations.")

    try:
        from src.cloud_services import get_pending_jobs
        pending = get_pending_jobs(sheet_url)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch from Google Sheet: {e}")

    if not pending:
        raise HTTPException(404, "No pending movies in the sheet. Set a row's Status to 'Pending'.")

    job = pending[0]
    # Support common column name variants
    movie_name = (
        job.get("movie_title") or job.get("Movie Name") or
        job.get("Movie Title") or job.get("movie_name") or ""
    ).strip()
    if not movie_name:
        raise HTTPException(400, f"First pending row has no movie name. Found columns: {list(job.keys())}")

    row_index = job.get("_row_index")
    params = {}
    if row_index:
        params["sheet_row_index"] = row_index
        params["sheet_url"] = sheet_url

    try:
        p = create_project(movie_name, "movie", params)
        return p.model_dump()
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Random idea generator ─────────────────────────────────────────────

@app.get("/api/generate-random-idea")
async def api_generate_random_idea():
    """Use Groq to generate a random animated series concept."""
    if not Config.GROQ_API_KEY:
        raise HTTPException(400, "GROQ_API_KEY not configured. Set it in Settings or .env.")

    import groq
    client = groq.Groq(api_key=Config.GROQ_API_KEY)
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    "Generate a creative, unique animated series concept. "
                    "Return ONLY valid JSON with two keys: "
                    '"name" (a short catchy title, 2-5 words) and '
                    '"brief" (a 1-3 sentence story premise that is fun and visual). '
                    "No markdown, no explanation."
                ),
            }],
            temperature=1.0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        import json as _json
        data = _json.loads(resp.choices[0].message.content)
        return {"name": data.get("name", ""), "brief": data.get("brief", "")}
    except Exception as e:
        raise HTTPException(500, f"Groq generation failed: {e}")


# ── Script editing ───────────────────────────────────────────────────

@app.put("/api/projects/{project_id}/script")
async def api_update_script(project_id: str, req: UpdateScriptRequest):
    """Save user-edited script back into project state."""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    p.step_data["edited_script"] = req.script
    update_project(p)
    return {"ok": True}


# ── File serving (generated assets) ─────────────────────────────────

@app.get("/api/projects/{project_id}/files/{file_path:path}")
async def api_serve_file(project_id: str, file_path: str):
    # Try project dir first, then legacy temp dir
    for base in [get_project_dir(project_id), Config.TEMP_DIR / project_id]:
        base_resolved = base.resolve()
        target = (base_resolved / file_path).resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError:
            continue
        if target.exists():
            return FileResponse(target)
    raise HTTPException(404, "File not found")


# ── Pipeline execution via POST ──────────────────────────────────────

@app.post("/api/projects/{project_id}/run")
async def api_run_pipeline(project_id: str):
    """
    Start (or continue) the pipeline for a project.
    The actual work runs in a background thread. Progress is streamed
    over the WebSocket at /ws/{project_id}.
    """
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    if project_id in _active_runs:
        raise HTTPException(409, "Pipeline already running for this project")

    queue: asyncio.Queue = asyncio.Queue()
    _active_runs[project_id] = queue
    loop = asyncio.get_event_loop()

    def _run_in_thread():
        try:
            _execute_pipeline(p, queue, loop)
        except Exception as exc:
            logger.exception("Pipeline thread crashed")
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "done"}), loop
            )

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()

    p.status = "running"
    update_project(p)
    return {"ok": True, "message": "Pipeline started"}


def _execute_pipeline(project: Project, queue: asyncio.Queue, loop):
    """
    Run the appropriate pipeline generator, pushing each PipelineStatus
    onto the asyncio queue for WebSocket broadcast.
    """
    from src.pipeline import VideoGenerationPipeline, PipelineStatus

    def _put(msg: dict):
        asyncio.run_coroutine_threadsafe(queue.put(msg), loop)

    project_id = project.id
    mode = project.mode
    params = project.params

    # Use edited script if available
    edited_script = project.step_data.get("edited_script")

    if mode == "animation-series":
        from src.animation_pipeline import run_animation_pipeline
        gen = run_animation_pipeline(
            project_title=params.get("project_title", project.name),
            brief=params.get("brief", ""),
            num_episodes=params.get("num_episodes", 1),
            resume=True,
            progress_callback=_put,
            project_dir=get_project_dir(project_id),
        )
    elif mode == "animated":
        from src.animation_pipeline import run_animation_pipeline
        gen = run_animation_pipeline(
            project_title=project.name,
            brief=params.get("brief", project.name),
            num_episodes=params.get("num_episodes", 1),
            resume=True,
            progress_callback=_put,
            project_dir=get_project_dir(project_id),
        )
    else:
        # Movie recap
        pipeline = VideoGenerationPipeline(offline=False, clean=False)
        gen = pipeline.run(project.name, mode="movie")

    try:
        while True:
            status: PipelineStatus = next(gen)
            msg = {
                "type": "status",
                "step": status.step,
                "message": status.message,
                "data": status.data,
                "is_error": status.is_error,
                "review_gate": status.review_gate,
            }
            _put(msg)

            # Persist step data when we have it
            if status.data:
                p = get_project(project_id)
                if p:
                    p.step_data[f"step_{status.step}"] = status.data
                    p.current_step = str(status.step)
                    update_project(p)

            if status.retry_gate:
                # Veo scene failure — push details to client and pause
                p = get_project(project_id)
                if p:
                    p.status = "scene_failed"
                    p.step_data["failed_scene"] = status.data
                    update_project(p)
                _put({
                    "type": "scene_failed",
                    "step": status.step,
                    "message": status.message,
                    "data": status.data,
                })
                _active_runs.pop(project_id, None)
                return

            if status.review_gate:
                # Pause: update project status and stop consuming generator
                p = get_project(project_id)
                if p:
                    p.status = "paused"
                    update_project(p)
                _put({"type": "paused", "step": status.step, "data": status.data})
                # We stop here. The user will POST /run again after review.
                # The generator is lost — the pipeline's cache will resume from
                # the last completed step on next invocation.
                return

            if status.is_error:
                p = get_project(project_id)
                if p:
                    p.status = "error"
                    p.error = status.message
                    update_project(p)
                    # Update sheet row on error
                    sheet_url = p.params.get("sheet_url")
                    row_idx = p.params.get("sheet_row_index")
                    if sheet_url and row_idx:
                        try:
                            from src.cloud_services import update_row
                            update_row(sheet_url, row_idx, {
                                "Status": "Failed",
                                "Error": status.message,
                            })
                        except Exception:
                            pass
                _put({"type": "error", "message": status.message})
                return  # stop consuming — pipeline has halted

    except StopIteration as e:
        # Pipeline completed
        p = get_project(project_id)
        if p:
            p.status = "completed"
            if e.value:
                # Store final result
                if isinstance(e.value, tuple) and len(e.value) >= 3:
                    p.step_data["final_video"] = e.value[2]
                elif isinstance(e.value, str):
                    p.step_data["final_video"] = e.value
            update_project(p)

            # Update Google Sheet row if this was a sheet-sourced movie
            sheet_url = p.params.get("sheet_url")
            row_idx = p.params.get("sheet_row_index")
            if sheet_url and row_idx:
                try:
                    from src.cloud_services import update_row
                    update_row(sheet_url, row_idx, {
                        "Status": "Done",
                        "Output Path": p.step_data.get("final_video", ""),
                    })
                except Exception as sheet_err:
                    logger.warning(f"Failed to update sheet row: {sheet_err}")

        _put({"type": "completed", "data": p.step_data if p else {}})
    finally:
        _active_runs.pop(project_id, None)


# ── Veo scene retry ──────────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/retry-scene")
async def api_retry_scene(project_id: str, req: RetrySceneRequest):
    """
    Handle user action after a Veo scene failure.
    action=retry  → re-run pipeline as-is
    action=edit   → write prompt override file, then re-run
    action=skip   → write skip marker file, then re-run
    """
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    failed_scene = p.step_data.get("failed_scene", {})
    override_file = failed_scene.get("override_file", "")
    skip_marker = failed_scene.get("skip_marker", "")

    if req.action == "edit":
        if not req.new_prompt:
            raise HTTPException(400, "new_prompt is required for action=edit")
        if override_file:
            from pathlib import Path as _P
            _P(override_file).parent.mkdir(parents=True, exist_ok=True)
            _P(override_file).write_text(req.new_prompt, encoding="utf-8")
            logger.info(f"[server] Prompt override written for scene {failed_scene.get('scene_id')}")

    elif req.action == "skip":
        if skip_marker:
            from pathlib import Path as _P
            _P(skip_marker).parent.mkdir(parents=True, exist_ok=True)
            _P(skip_marker).touch()
            logger.info(f"[server] Skip marker written for scene {failed_scene.get('scene_id')}")

    # Clear the failure state and restart the pipeline (it will resume from state)
    p.status = "running"
    p.step_data.pop("failed_scene", None)
    update_project(p)

    return await api_run_pipeline(project_id)


# ── WebSocket — real-time log streaming ──────────────────────────────

@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    await websocket.accept()

    queue = _active_runs.get(project_id)
    if not queue:
        await websocket.send_json({"type": "info", "message": "No active run. Start pipeline first."})
        # Wait up to 30s for a run to appear (e.g. page refresh mid-start).
        # After that, close — prevents an indefinite coroutine leak.
        try:
            deadline = asyncio.get_event_loop().time() + 30
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.5)
                queue = _active_runs.get(project_id)
                if queue:
                    break
            else:
                await websocket.send_json({"type": "info", "message": "No pipeline started within 30s. Closing."})
                return
        except WebSocketDisconnect:
            return

    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
            if msg.get("type") in ("done", "completed", "paused"):
                break
    except WebSocketDisconnect:
        pass


# ── Pause ────────────────────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/pause")
async def api_pause_pipeline(project_id: str):
    """
    Pause an active pipeline run. The pipeline thread is cancelled and state
    is saved as 'paused'. On next /run call, the pipeline resumes from the
    last completed step via pipeline_state.json.
    """
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    # Signal the thread to stop by removing its queue — the WS will close naturally
    queue = _active_runs.pop(project_id, None)
    if queue:
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(queue.put({"type": "done"}), loop)
        logger.info(f"[server] Paused pipeline for project '{project_id}'")

    p.status = "paused"
    update_project(p)
    return {"ok": True, "message": "Pipeline paused — progress is saved"}


# ── Finals library ───────────────────────────────────────────────────────────

@app.get("/api/finals")
async def api_list_finals():
    """List all files in output/final/, newest first."""
    Config.ensure_directories()
    finals = []
    for f in sorted(Config.FINAL_DIR.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        finals.append({
            "filename": f.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 1),
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return finals


@app.get("/api/finals/{filename}")
async def api_serve_final(filename: str):
    """Serve a file from output/final/ by filename only (no path traversal)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(403, "Invalid filename")
    target = Config.FINAL_DIR / filename
    if not target.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(target, media_type="video/mp4")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_state_file(project_id: str) -> Optional[Path]:
    """Find pipeline_state.json — check project dir first, then legacy TEMP_DIR."""
    primary = get_project_dir(project_id) / "pipeline_state.json"
    if primary.exists():
        return primary
    # Legacy: old runs stored state in output/temp/{safe_title}/
    legacy = Config.TEMP_DIR / project_id / "pipeline_state.json"
    if legacy.exists():
        return legacy
    return None


# ── Step artifact browser ─────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/step-artifacts")
async def api_step_artifacts(project_id: str, step: str, episode: Optional[int] = None):
    """
    Return the artifact URLs for a completed pipeline step.
    step: 'writer' | 'screenwriter' | 'casting' | 'world_builder' | 'director' | 'scene_generator' | 'editor'
    episode: episode number (required for director / scene_generator / editor)
    """
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    state_file = _find_state_file(project_id)
    if not state_file:
        return {"artifacts": []}

    state = json.loads(state_file.read_text(encoding="utf-8"))

    if episode is not None:
        ep_state = state.get("episodes", {}).get(str(episode), {})
        step_state = ep_state.get("steps", {}).get(step, {})
    else:
        step_state = state.get("series_steps", {}).get(step, {})

    artifact_paths = step_state.get("artifact_paths", [])
    # Use the directory containing pipeline_state.json as the base for relative paths
    state_dir = state_file.parent.resolve()

    artifacts = []
    for path_str in artifact_paths:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            rel = path.relative_to(state_dir)
        except ValueError:
            continue
        artifacts.append({
            "filename": path.name,
            "url": f"/api/projects/{project_id}/files/{rel.as_posix()}",
            "ext": path.suffix.lower(),
            "size_kb": round(path.stat().st_size / 1024, 1),
        })

    return {"artifacts": artifacts}


# ── Pipeline state (for episodic step rail) ───────────────────────────────────

@app.get("/api/projects/{project_id}/state")
async def api_get_pipeline_state(project_id: str):
    """Return the raw pipeline_state.json for a project (used by UI step rail)."""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    state_file = _find_state_file(project_id)
    if not state_file:
        return {}
    return json.loads(state_file.read_text(encoding="utf-8"))


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsPayload(BaseModel):
    credentials: dict = {}
    models: dict = {}
    integrations: dict = {}


@app.get("/api/settings")
async def api_get_settings():
    """Return current settings (credentials masked, models shown)."""
    Config.ensure_directories()
    if Config.SETTINGS_FILE.exists():
        data = json.loads(Config.SETTINGS_FILE.read_text(encoding="utf-8"))
    else:
        data = {"credentials": {}, "models": {}}

    # Mask credential values — only show whether they are set
    masked_creds = {k: "********" if v else "" for k, v in data.get("credentials", {}).items()}
    # Also expose which env-var keys are set but not in file
    for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "TMDB_API_KEY", "PEXELS_API_KEY",
                "VERTEX_PROJECT_ID", "VERTEX_LOCATION"):
        if key not in masked_creds and os.getenv(key):
            masked_creds[key] = "(from .env)"

    # Integrations (not secrets — return actual values)
    integrations = dict(data.get("integrations", {}))
    if "BATCH_SHEET_URL" not in integrations and os.getenv("BATCH_SHEET_URL"):
        integrations["BATCH_SHEET_URL"] = "(from .env)"

    return {"credentials": masked_creds, "models": data.get("models", {}), "integrations": integrations}


@app.put("/api/settings")
async def api_save_settings(payload: SettingsPayload):
    """Save settings to output/settings.json. Empty string values are dropped."""
    Config.ensure_directories()

    # Load existing file to merge (preserve existing masked values)
    existing: dict = {}
    if Config.SETTINGS_FILE.exists():
        existing = json.loads(Config.SETTINGS_FILE.read_text(encoding="utf-8"))

    existing_creds = existing.get("credentials", {})
    new_creds = {}
    for k, v in payload.credentials.items():
        if v and v != "********" and v != "(from .env)":
            new_creds[k] = v
        elif k in existing_creds:
            # Keep existing value if user left it masked
            new_creds[k] = existing_creds[k]

    new_models = {k: v for k, v in payload.models.items() if v}

    # Integrations — merge with existing, drop empty values
    existing_int = existing.get("integrations", {})
    new_int = {}
    for k, v in payload.integrations.items():
        if v and v != "(from .env)":
            new_int[k] = v
        elif k in existing_int:
            new_int[k] = existing_int[k]

    merged = {"credentials": new_creds, "models": new_models, "integrations": new_int}
    Config.SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return {"ok": True}


# ── Startup hook ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    Config.ensure_directories()
    # Any project stuck in "running" from a previous server session is unreachable —
    # reset to "paused" so the user can resume via the Continue button.
    for p in list_projects():
        if p.status == "running":
            p.status = "paused"
            update_project(p)
            logger.info(f"[server] Reset stale 'running' project to 'paused': {p.id}")
    logger.info("StudioZero server started on http://localhost:8910")
