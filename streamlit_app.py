"""
StudioZero - Video Generation Dashboard

A Streamlit frontend for the StudioZero video generation pipeline.
Run with: streamlit run streamlit_app.py
"""

import json
import re
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = OUTPUT_DIR / "temp"
FINAL_DIR = OUTPUT_DIR / "final"
HISTORY_FILE = OUTPUT_DIR / "job_history.json"

SERIES_STEPS = ["world_builder", "character_designer"]
EPISODE_STEPS = [
    "episode_writer", "storyboard", "voice_director",
    "scene_generator", "sound_designer", "editor", "publisher",
]

STEP_META = {
    "world_builder":      {"label": "World Builder",      "desc": "Generate series bible, setting, and tone",        "icon": "🌍"},
    "character_designer":  {"label": "Character Designer",  "desc": "Create character blueprints and reference images", "icon": "🎨"},
    "episode_writer":     {"label": "Episode Writer",     "desc": "Write episode script with scene breakdowns",     "icon": "📝"},
    "storyboard":         {"label": "Storyboard",         "desc": "Plan shots and generate Veo prompts",            "icon": "🎬"},
    "voice_director":     {"label": "Voice Director",     "desc": "Generate TTS voiceover audio",                   "icon": "🎙️"},
    "scene_generator":    {"label": "Scene Generator",    "desc": "Render video clips with Veo 3.1",               "icon": "🎥"},
    "sound_designer":     {"label": "Sound Designer",     "desc": "Generate background music and SFX",              "icon": "🎵"},
    "editor":             {"label": "Editor",             "desc": "Assemble final video with FFmpeg",               "icon": "✂️"},
    "publisher":          {"label": "Publisher",          "desc": "Generate marketing materials and export",         "icon": "📤"},
}

_RE_STEP_LOG = re.compile(
    r"\[Step\s+\d+\]\s+\[(?:ep(\d+)/)?(\w+)\]\s+(.*)", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_history(history: list):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def add_history_entry(entry: dict):
    history = load_history()
    history.insert(0, entry)
    save_history(history[:100])


def list_animation_projects() -> list:
    projects = []
    if not TEMP_DIR.exists():
        return projects
    for d in sorted(TEMP_DIR.iterdir()):
        if not d.is_dir():
            continue
        state_file = d / "pipeline_state.json"
        bible_file = d / "series_bible.json"
        project_file = d / "project.json"

        if state_file.exists():
            info = {"name": d.name, "dir": str(d), "pipeline": "9-step"}
            try:
                state_data = json.loads(state_file.read_text())
                info["title"] = state_data.get("project_title", d.name)
                info["state"] = state_data
                ep_keys = state_data.get("episodes", {})
                info["num_episodes"] = len(ep_keys) if ep_keys else 0
                if info["num_episodes"] == 0 and bible_file.exists():
                    bible = json.loads(bible_file.read_text())
                    info["num_episodes"] = bible.get("episode_count", 0)
            except Exception:
                info["title"] = d.name
                info["num_episodes"] = 0
                info["state"] = {}
            projects.append(info)
        elif project_file.exists():
            info = {"name": d.name, "dir": str(d), "pipeline": "legacy"}
            try:
                project_data = json.loads(project_file.read_text())
                info["title"] = project_data.get("project_title", d.name)
                info["num_episodes"] = len(project_data.get("episodes", []))
            except Exception:
                info["title"] = d.name
                info["num_episodes"] = 0
            info["state"] = {}
            projects.append(info)
    return projects


def list_completed_videos() -> list:
    if not FINAL_DIR.exists():
        return []
    videos = []
    for f in sorted(FINAL_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix == ".mp4":
            videos.append({
                "name": f.stem,
                "path": str(f),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                "created": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return videos


def _step_icon(step_data: dict) -> str:
    if step_data.get("completed"):
        return "✅"
    if step_data.get("error"):
        return "❌"
    if step_data.get("started_at"):
        return "🔄"
    return "⏳"


def _get_project_bible(project_dir: str) -> dict | None:
    bible_path = Path(project_dir) / "series_bible.json"
    if bible_path.exists():
        try:
            return json.loads(bible_path.read_text())
        except Exception:
            return None
    return None


def _get_project_state(project_dir: str) -> dict:
    state_file = Path(project_dir) / "pipeline_state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def _build_step_list(num_episodes: int) -> list:
    steps = []
    for s in SERIES_STEPS:
        meta = STEP_META[s]
        steps.append({"key": s, "step_name": s, "ep": None, "label": meta["label"], "desc": meta["desc"], "icon": meta["icon"]})
    for ep in range(1, num_episodes + 1):
        for s in EPISODE_STEPS:
            meta = STEP_META[s]
            steps.append({"key": f"ep{ep}/{s}", "step_name": s, "ep": ep, "label": f"Ep {ep} — {meta['label']}", "desc": meta["desc"], "icon": meta["icon"]})
    return steps


def _parse_step_event(line: str):
    m = _RE_STEP_LOG.search(line)
    if not m:
        return None
    ep_num, step_name, message = m.group(1), m.group(2), m.group(3)
    key = f"ep{ep_num}/{step_name}" if ep_num else step_name
    msg_lower = message.lower()
    if "starting" in msg_lower:
        event = "starting"
    elif "complete" in msg_lower:
        event = "complete"
    elif "already completed" in msg_lower or "skipping" in msg_lower:
        event = "skipped"
    elif "failed" in msg_lower:
        event = "failed"
    else:
        event = "info"
    return key, event, message


def run_pipeline_subprocess(cmd: list, status_label, log_placeholder):
    log_lines = deque(maxlen=500)
    env = {**__import__("os").environ, "PYTHONUNBUFFERED": "1"}
    start = time.time()
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, cwd=str(PROJECT_ROOT), env=env,
    )
    st.session_state["running_process"] = process
    st.session_state["running"] = True

    for line in process.stdout:
        line = line.rstrip()
        if line:
            log_lines.append(line)
            elapsed = time.time() - start
            mins, secs = divmod(int(elapsed), 60)
            status_label.markdown(f"**Running...** ({mins}m {secs}s) — `{line[:80]}`")
            log_placeholder.code("\n".join(log_lines), language="log")

    process.wait()
    st.session_state["running"] = False
    st.session_state["log_lines"] = list(log_lines)
    st.session_state["exit_code"] = process.returncode

    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    if process.returncode == 0:
        status_label.success(f"Completed in {mins}m {secs}s")
    else:
        status_label.error(f"Failed after {mins}m {secs}s (exit code {process.returncode})")
    log_placeholder.code("\n".join(log_lines), language="log")
    return process.returncode


def run_animation_pipeline(cmd: list, num_episodes: int):
    step_list = _build_step_list(num_episodes)
    step_status = {s["key"]: "pending" for s in step_list}
    step_errors = {}
    step_times = {}

    col_steps, col_log = st.columns([1, 2])
    with col_steps:
        st.markdown("### Pipeline Steps")
        tracker_placeholder = st.empty()
    with col_log:
        status_label = st.empty()
        status_label.markdown("**Starting pipeline...**")
        log_container = st.container(height=500)
        log_placeholder = log_container.empty()

    def _render_tracker():
        lines = []
        current_ep = None
        for s in step_list:
            if s["ep"] is not None and s["ep"] != current_ep:
                current_ep = s["ep"]
                lines.append(f"\n**Episode {current_ep}**")
            status = step_status[s["key"]]
            icon = {"done": "✅", "skipped": "⏭️", "running": "🔄", "failed": "❌"}.get(status, "⬜")
            elapsed_str = ""
            if s["key"] in step_times and status in ("done", "failed"):
                dt = step_times[s["key"]]
                elapsed_str = f" ({int(dt // 60)}m {int(dt % 60)}s)" if dt >= 60 else f" ({dt:.0f}s)"
            label = s["label"] if s["ep"] is not None else f"**{s['label']}**"
            line = f"{icon} {label}{elapsed_str}"
            if status == "failed" and s["key"] in step_errors:
                line += f"  \n> {step_errors[s['key']][:80]}"
            lines.append(line)
        tracker_placeholder.markdown("\n".join(lines))

    _render_tracker()

    log_lines = deque(maxlen=500)
    env = {**__import__("os").environ, "PYTHONUNBUFFERED": "1"}
    start = time.time()
    active_step_key = None
    active_step_start = None

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, cwd=str(PROJECT_ROOT), env=env,
    )
    st.session_state["running_process"] = process
    st.session_state["running"] = True

    for line in process.stdout:
        line = line.rstrip()
        if not line:
            continue
        log_lines.append(line)
        elapsed = time.time() - start
        mins, secs = divmod(int(elapsed), 60)
        status_label.markdown(f"**Running...** ({mins}m {secs}s)")

        event = _parse_step_event(line)
        if event:
            key, evt, msg = event
            if key in step_status:
                if evt == "starting":
                    step_status[key] = "running"
                    active_step_key = key
                    active_step_start = time.time()
                elif evt == "complete":
                    step_status[key] = "done"
                    if active_step_key == key and active_step_start:
                        step_times[key] = time.time() - active_step_start
                    active_step_key = None
                elif evt == "skipped":
                    step_status[key] = "skipped"
                elif evt == "failed":
                    step_status[key] = "failed"
                    step_errors[key] = msg
                    if active_step_key == key and active_step_start:
                        step_times[key] = time.time() - active_step_start
                    active_step_key = None
                _render_tracker()
        log_placeholder.code("\n".join(log_lines), language="log")

    process.wait()
    st.session_state["running"] = False
    st.session_state["log_lines"] = list(log_lines)
    st.session_state["exit_code"] = process.returncode

    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    if process.returncode != 0 and active_step_key:
        step_status[active_step_key] = "failed"
        if active_step_start:
            step_times[active_step_key] = time.time() - active_step_start
    _render_tracker()

    if process.returncode == 0:
        status_label.success(f"Completed in {mins}m {secs}s")
    else:
        status_label.error(f"Failed after {mins}m {secs}s (exit code {process.returncode})")
    log_placeholder.code("\n".join(log_lines), language="log")
    return process.returncode


def _run_and_record(cmd: list, job_name: str, mode: str, num_episodes: int = 0):
    st.session_state["log_lines"] = []
    st.session_state["exit_code"] = None
    start_time = datetime.now()
    st.session_state["current_job"] = {
        "name": job_name, "mode": mode,
        "started": start_time.isoformat(), "cmd": " ".join(cmd),
    }
    st.divider()

    if mode == "animation-series" and num_episodes > 0:
        exit_code = run_animation_pipeline(cmd, num_episodes)
    else:
        status_label = st.empty()
        status_label.markdown(f"**Starting:** {job_name}...")
        log_container = st.container(height=450)
        log_placeholder = log_container.empty()
        exit_code = run_pipeline_subprocess(cmd, status_label, log_placeholder)

    entry = st.session_state["current_job"].copy()
    entry["completed"] = datetime.now().isoformat()
    entry["status"] = "completed" if exit_code == 0 else "failed"
    entry["exit_code"] = exit_code
    add_history_entry(entry)
    return exit_code


# ---------------------------------------------------------------------------
# Page config & session state
# ---------------------------------------------------------------------------
st.set_page_config(page_title="StudioZero", page_icon="🎬", layout="wide")

for key in ("running", "log_lines", "exit_code"):
    if key not in st.session_state:
        st.session_state[key] = False if key == "running" else ([] if key == "log_lines" else None)

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("StudioZero")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    [
        "Generate",
        "World & Characters",
        "Episodes & Scripts",
        "Render & Publish",
        "Gallery",
        "History",
    ],
    index=0,
)

# Show active projects in sidebar
projects = list_animation_projects()
if projects:
    st.sidebar.markdown("---")
    st.sidebar.caption("Active Projects")
    for p in projects[:5]:
        state = p.get("state", {})
        series_done = sum(1 for s in state.get("series_steps", {}).values() if s.get("completed"))
        total_series = len(SERIES_STEPS)
        ep_count = len(state.get("episodes", {}))
        st.sidebar.text(f"  {p.get('title', p['name'])} ({series_done}/{total_series} + {ep_count} ep)")


# ═══════════════════════════════════════════════════════════════════════════
# GENERATE PAGE — All modes in one place
# ═══════════════════════════════════════════════════════════════════════════
if page == "Generate":
    st.title("Generate Video")

    mode = st.selectbox(
        "Pipeline Mode",
        ["Movie Recap", "Animated Parody", "Animation Series"],
        help="Movie Recap: narrated recap video. Animated Parody: one-shot parody with Veo 3.1. Animation Series: multi-episode 9-step pipeline.",
    )

    # ── Movie Recap ─────────────────────────────────────────────────────
    if mode == "Movie Recap":
        st.subheader("Movie Recap Video")
        movie_name = st.text_input("Movie Name", placeholder="e.g. The Matrix")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            verbose = st.checkbox("Verbose logging", value=True)
        with col2:
            offline = st.checkbox("Offline (use cache)")
        with col3:
            clean = st.checkbox("Clean temp after render")
        with col4:
            assets_only = st.checkbox("Assets only (skip render)")

        st.divider()
        st.subheader("Or: Batch from Google Sheet")
        run_batch = st.checkbox("Run batch from Google Sheet instead")
        batch_limit = None
        if run_batch:
            batch_limit = st.number_input("Limit (0 = all)", min_value=0, value=0, step=1)
            if batch_limit == 0:
                batch_limit = None

        st.divider()
        if st.button("Generate", type="primary", disabled=st.session_state["running"]):
            if run_batch:
                cmd = [sys.executable, "-m", "src.batch_runner"]
                if verbose:
                    cmd.append("--verbose")
                if batch_limit:
                    cmd.extend(["--limit", str(batch_limit)])
                job_name = f"Batch ({batch_limit or 'all'})"
            else:
                if not movie_name:
                    st.error("Enter a movie name.")
                    st.stop()
                cmd = [sys.executable, "-m", "src.app", movie_name, "--mode", "movie"]
                if verbose:
                    cmd.append("--verbose")
                if offline:
                    cmd.append("--offline")
                if clean:
                    cmd.append("--clean")
                if assets_only:
                    cmd.append("--assets-only")
                job_name = movie_name

            exit_code = _run_and_record(cmd, job_name, "movie")
            if exit_code == 0:
                st.success(f"Done! {job_name}")
            else:
                st.error(f"Failed with exit code {exit_code}")

    # ── Animated Parody ─────────────────────────────────────────────────
    elif mode == "Animated Parody":
        st.subheader("Animated Parody")
        st.caption("Generates a single parody video with Gemini + Veo 3.1.")
        theme = st.text_input("Theme / Movie Name", placeholder="e.g. Game of Thrones")
        verbose_os = st.checkbox("Verbose", value=True, key="verbose_anim_parody")

        if st.button("Generate Parody", type="primary", disabled=st.session_state["running"]):
            if not theme:
                st.error("Enter a theme or movie name.")
                st.stop()
            cmd = [sys.executable, "-m", "src.app", theme, "--mode", "animated"]
            if verbose_os:
                cmd.append("--verbose")
            exit_code = _run_and_record(cmd, f"Animated: {theme}", "animated")
            if exit_code == 0:
                st.success(f"Parody video generated for '{theme}'!")
            else:
                st.error(f"Generation failed (exit code {exit_code})")

    # ── Animation Series ────────────────────────────────────────────────
    elif mode == "Animation Series":
        st.subheader("New Animation Series")
        st.caption("Creates a new multi-episode series and runs the full 9-step pipeline.")

        anim_title = st.text_input("Project Name", placeholder="e.g. Kitchen Wars")
        storyline = st.text_area("Storyline", placeholder="e.g. A brave spatula must unite the kitchen utensils...")
        char_desc = st.text_area("Character Descriptions", placeholder="e.g. Sir Spatula: a dented but noble kitchen spatula...")
        num_episodes = st.slider("Number of Episodes", min_value=1, max_value=10, value=3)
        verbose_anim = st.checkbox("Verbose", value=True, key="verbose_anim_series")

        if st.button("Generate Series", type="primary", disabled=st.session_state["running"]):
            if not anim_title:
                st.error("Enter a project name.")
                st.stop()
            if not storyline:
                st.error("Storyline is required.")
                st.stop()
            if not char_desc:
                st.error("Character descriptions are required.")
                st.stop()

            cmd = [
                sys.executable, "-m", "src.app", anim_title,
                "--mode", "animation-series",
                "--episodes", str(num_episodes),
                "--storyline", storyline,
                "--char-desc", char_desc,
                "--no-resume",
            ]
            if verbose_anim:
                cmd.append("--verbose")

            exit_code = _run_and_record(cmd, f"Series: {anim_title}", "animation-series", num_episodes=num_episodes)
            if exit_code == 0:
                st.success(f"Series '{anim_title}' generated!")
                st.rerun()
            else:
                st.error(f"Pipeline failed (exit code {exit_code}). Resume from World & Characters page.")

    # Show last run logs
    if not st.session_state.get("running") and st.session_state.get("log_lines"):
        st.divider()
        with st.expander("Last Run Output", expanded=False):
            st.code("\n".join(st.session_state["log_lines"][-500:]), language="log")


# ═══════════════════════════════════════════════════════════════════════════
# WORLD & CHARACTERS PAGE — Series-level steps
# ═══════════════════════════════════════════════════════════════════════════
elif page == "World & Characters":
    st.title("World & Characters")
    st.caption("View and manage series-level assets: world bible, characters, and reference images.")

    projects = list_animation_projects()
    if not projects:
        st.info("No animation projects found. Create one from the Generate page.")
    else:
        project_names = [p.get("title", p["name"]) for p in projects]
        selected_idx = st.selectbox(
            "Select Project",
            range(len(project_names)),
            format_func=lambda i: f"{project_names[i]} ({projects[i].get('num_episodes', '?')} ep)",
        )
        selected = projects[selected_idx]
        project_dir = Path(selected["dir"])
        state = selected.get("state", {})

        # --- Series Steps Status ---
        st.markdown("### Pipeline Status")
        series_steps = state.get("series_steps", {})
        for step_name in SERIES_STEPS:
            step = series_steps.get(step_name, {})
            icon = _step_icon(step)
            meta = STEP_META[step_name]
            extra = ""
            if step.get("error"):
                extra = f" — `{step['error'][:60]}`"
            elif step.get("completed_at"):
                extra = f" — done {step['completed_at'][:16]}"
            st.markdown(f"{icon} **{meta['label']}** — {meta['desc']}{extra}")

        # --- Series Bible ---
        bible = _get_project_bible(selected["dir"])
        if bible:
            st.markdown("---")
            st.markdown("### Series Bible")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Setting:** {bible.get('setting', 'N/A')}")
                st.markdown(f"**Tone:** {bible.get('tone', 'N/A')}")
                st.markdown(f"**Episodes:** {bible.get('episode_count', 'N/A')}")
            with col2:
                st.markdown(f"**Series Arc:**")
                st.text(bible.get("series_arc_outline", "N/A")[:300])

            # Characters
            roster = bible.get("character_roster", [])
            if roster:
                st.markdown("### Characters")
                cols = st.columns(min(len(roster), 4))
                for i, char in enumerate(roster):
                    with cols[i % len(cols)]:
                        st.markdown(f"**{char.get('display_name', '?')}**")
                        st.caption(char.get("base_object", ""))
                        if char.get("personality"):
                            st.text(char["personality"][:100])

        # --- Character Reference Images ---
        chars_dir = project_dir / "characters"
        if chars_dir.exists():
            refs = list(chars_dir.glob("*_reference.png"))
            if refs:
                st.markdown("---")
                st.markdown("### Character References")
                cols = st.columns(min(len(refs), 4))
                for i, ref in enumerate(refs):
                    with cols[i % len(cols)]:
                        st.image(str(ref), caption=ref.stem.replace("_reference", ""), width=200)

        # --- Resume / Re-run controls ---
        st.markdown("---")
        st.markdown("### Resume Pipeline")
        st.caption("Resume from last completed step or start fresh.")

        col_a, col_b = st.columns(2)
        with col_a:
            verbose_resume = st.checkbox("Verbose", value=True, key="verbose_wc_resume")
        with col_b:
            fresh_start = st.checkbox("Fresh start (ignore saved state)", key="fresh_wc")

        resume_storyline = ""
        resume_char_desc = ""
        if bible:
            resume_storyline = bible.get("series_arc_outline", "")
            resume_char_desc = ", ".join(
                f"{c['display_name']}: {c['base_object']}"
                for c in bible.get("character_roster", [])
            )

        if not resume_storyline:
            resume_storyline = st.text_area("Storyline (needed if bible not yet generated)", key="wc_storyline")
            resume_char_desc = st.text_area("Character Descriptions", key="wc_char_desc")

        num_eps = st.number_input("Episodes", min_value=1, max_value=10, value=selected.get("num_episodes", 3) or 3, key="wc_eps")

        if st.button("Resume Pipeline", type="primary", disabled=st.session_state["running"], key="btn_wc_resume"):
            if not resume_storyline:
                st.error("Storyline is required.")
                st.stop()
            cmd = [
                sys.executable, "-m", "src.app", selected["name"],
                "--mode", "animation-series",
                "--episodes", str(num_eps),
                "--storyline", resume_storyline,
                "--char-desc", resume_char_desc or "See series bible",
            ]
            if fresh_start:
                cmd.append("--no-resume")
            if verbose_resume:
                cmd.append("--verbose")
            exit_code = _run_and_record(cmd, f"Resume: {selected.get('title', selected['name'])}", "animation-series", num_episodes=num_eps)
            if exit_code == 0:
                st.success("Pipeline completed!")
                st.rerun()
            else:
                st.error(f"Pipeline failed (exit code {exit_code}). Re-run to resume.")


# ═══════════════════════════════════════════════════════════════════════════
# EPISODES & SCRIPTS PAGE — Per-episode writing/storyboard
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Episodes & Scripts":
    st.title("Episodes & Scripts")
    st.caption("View episode scripts, storyboards, and per-episode pipeline progress.")

    projects = list_animation_projects()
    if not projects:
        st.info("No animation projects found. Create one from the Generate page.")
    else:
        project_names = [p.get("title", p["name"]) for p in projects]
        selected_idx = st.selectbox(
            "Select Project",
            range(len(project_names)),
            format_func=lambda i: f"{project_names[i]} ({projects[i].get('num_episodes', '?')} ep)",
            key="ep_project_select",
        )
        selected = projects[selected_idx]
        project_dir = Path(selected["dir"])
        state = selected.get("state", {})
        episodes = state.get("episodes", {})

        if not episodes:
            st.info("No episodes generated yet. Run the pipeline from the Generate or World & Characters page first.")
        else:
            for ep_key in sorted(episodes.keys(), key=lambda k: int(k)):
                ep = episodes[ep_key]
                ep_num = ep.get("episode_number", ep_key)
                steps = ep.get("steps", {})

                # Summary line
                done_count = sum(1 for s in steps.values() if s.get("completed"))
                total = len(EPISODE_STEPS)
                with st.expander(f"Episode {ep_num} — {done_count}/{total} steps complete", expanded=True):

                    # Step progress for writing/storyboard steps
                    for step_name in ["episode_writer", "storyboard", "voice_director"]:
                        step = steps.get(step_name, {})
                        icon = _step_icon(step)
                        meta = STEP_META[step_name]
                        extra = ""
                        if step.get("error"):
                            extra = f" — `{step['error'][:60]}`"
                        elif step.get("completed_at"):
                            extra = f" — done {step['completed_at'][:16]}"
                        st.markdown(f"{icon} **{meta['label']}** {extra}")

                    # Show script if it exists
                    script_file = project_dir / "episodes" / f"ep{ep_num}" / "script.json"
                    if script_file.exists():
                        try:
                            script_data = json.loads(script_file.read_text())
                            st.markdown("**Script:**")
                            scenes = script_data.get("scenes", [])
                            for i, scene in enumerate(scenes):
                                st.text(f"  Scene {i+1}: {scene.get('description', scene.get('narration', ''))[:100]}")
                        except Exception:
                            pass

                    # Show storyboard if it exists
                    storyboard_file = project_dir / "episodes" / f"ep{ep_num}" / "storyboard.json"
                    if storyboard_file.exists():
                        try:
                            sb_data = json.loads(storyboard_file.read_text())
                            shots = sb_data if isinstance(sb_data, list) else sb_data.get("shots", [])
                            if shots:
                                st.markdown(f"**Storyboard:** {len(shots)} shots planned")
                        except Exception:
                            pass


# ═══════════════════════════════════════════════════════════════════════════
# RENDER & PUBLISH PAGE — Scene generation, assembly, publishing
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Render & Publish":
    st.title("Render & Publish")
    st.caption("Track scene generation, video assembly, and publishing for each episode.")

    projects = list_animation_projects()
    if not projects:
        st.info("No animation projects found. Create one from the Generate page.")
    else:
        project_names = [p.get("title", p["name"]) for p in projects]
        selected_idx = st.selectbox(
            "Select Project",
            range(len(project_names)),
            format_func=lambda i: f"{project_names[i]} ({projects[i].get('num_episodes', '?')} ep)",
            key="render_project_select",
        )
        selected = projects[selected_idx]
        project_dir = Path(selected["dir"])
        state = selected.get("state", {})
        episodes = state.get("episodes", {})

        if not episodes:
            st.info("No episodes to render yet. Complete the scripting steps first.")
        else:
            for ep_key in sorted(episodes.keys(), key=lambda k: int(k)):
                ep = episodes[ep_key]
                ep_num = ep.get("episode_number", ep_key)
                steps = ep.get("steps", {})

                render_steps = ["scene_generator", "sound_designer", "editor", "publisher"]
                done_count = sum(1 for s in render_steps if steps.get(s, {}).get("completed"))

                with st.expander(f"Episode {ep_num} — Render: {done_count}/{len(render_steps)} steps", expanded=True):
                    for step_name in render_steps:
                        step = steps.get(step_name, {})
                        icon = _step_icon(step)
                        meta = STEP_META[step_name]
                        extra = ""
                        if step.get("error"):
                            extra = f" — `{step['error'][:60]}`"
                        elif step.get("completed_at"):
                            extra = f" — done {step['completed_at'][:16]}"
                        st.markdown(f"{icon} **{meta['label']}** — {meta['desc']}{extra}")

                    # Show final video if available
                    final_video = project_dir / "episodes" / f"ep{ep_num}" / "final.mp4"
                    if final_video.exists():
                        st.markdown("**Final Video:**")
                        st.video(str(final_video))

                    # Show generated clips
                    clips_dir = project_dir / "episodes" / f"ep{ep_num}" / "clips"
                    if clips_dir.exists():
                        clips = list(clips_dir.glob("*.mp4"))
                        if clips:
                            st.markdown(f"**Generated Clips:** {len(clips)}")
                            clip_cols = st.columns(min(len(clips), 3))
                            for i, clip in enumerate(clips[:6]):
                                with clip_cols[i % len(clip_cols)]:
                                    st.video(str(clip))
                                    st.caption(clip.stem)


# ═══════════════════════════════════════════════════════════════════════════
# GALLERY PAGE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Gallery":
    st.title("Video Gallery")
    videos = list_completed_videos()
    if not videos:
        st.info("No completed videos found yet.")
    else:
        for i in range(0, len(videos), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(videos):
                    break
                v = videos[idx]
                with col:
                    st.markdown(f"**{v['name']}**")
                    st.caption(f"{v['size_mb']} MB — {v['created']}")
                    st.video(v["path"])


# ═══════════════════════════════════════════════════════════════════════════
# HISTORY PAGE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "History":
    st.title("Job History")
    history = load_history()
    if history:
        for entry in history[:30]:
            status_icon = "✅" if entry.get("status") == "completed" else "❌"
            cols = st.columns([1, 3, 2, 1])
            cols[0].text(status_icon)
            cols[1].text(entry.get("name", "?"))
            cols[2].text(entry.get("started", "")[:16])
            cols[3].text(entry.get("mode", ""))
    else:
        st.caption("No job history yet.")
