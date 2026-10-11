# StudioZero analysis (read-only), for the move into the studio repo "story" engine

Repo: `StudioZero` (old tree). HEAD is `dc12780`. There are uncommitted multi-model changes in the working tree.
Nothing was modified. py_compile ran with `PYTHONPYCACHEPREFIX` pointed at the scratchpad. No pipeline, paid API or network call was made.
`.env`, `env.yaml` and `assets/creds/` were not read. `output/settings.json` was read for key names and model choices only; its credentials dict is empty.

Route names used below: **recap** is `src/pipeline.py`, called "movie" mode in the code. **series** is `src/animation_pipeline.py`, called "animation-series" mode.

---

## 1. Feature parity list for the old dashboard

Sources: `src/server.py` (756 lines), `static/app.js` (2306 lines), `static/index.html` (Tailwind CDN shell). The SPA has 5 views: dashboard, setup, pipeline, finals and settings.

### 1a. HTTP/WS endpoints

| # | Method + path | What it does | Pipeline fn / module | Costs $? | Verdict |
|---|---|---|---|---|---|
| E1 | `GET /` | Serves index.html | none | no | DROP: the React Studio tab replaces it |
| E2 | `GET /static/*` | Static mount | none | no | DROP |
| E3 | `GET /api/projects` | Lists projects (project.json under output/projects/*) | `project_manager.list_projects` | no | PORT as `GET /studio/projects` |
| E4 | `POST /api/projects` | Creates a project `{name, mode: movie or animation-series, params}` | `project_manager.create_project` | no | PORT (rename modes to recap/series) |
| E5 | `GET /api/projects/{id}` | Returns one project | `get_project` | no | PORT |
| E6 | `DELETE /api/projects/{id}` | Deletes the project dir plus output/temp/{id}. Refused (409) while it is running | `delete_project` (rmtree) | no | PORT, with a confirm step in the UI |
| E7 | `POST /api/projects/from-sheet` | Takes the next "Pending" row from a Google Sheet and creates a movie project | `cloud_services.get_pending_jobs` | no ($0, but Google API) | DROP: Sheets is retired |
| E8 | `GET /api/generate-random-idea` | Groq llama-3.3-70b returns a JSON `{name, brief}` series idea ("Surprise me") | inline `groq` call | yes (Groq, tiny) | PORT, but switch to Gemini (Groq is being retired). `narrative.generate_random_story_idea` already uses Gemini |
| E9 | `PUT /api/projects/{id}/script` | Saves the edited recap script to `step_data.edited_script` | none. **The value is never consumed** (see bug B1) | no | PORT and fix: the pipeline must use the edited script |
| E10 | `GET /api/projects/{id}/files/{path}` | Serves a file from the project dir or the legacy output/temp/{id}. Path-traversal guarded | none | no | PORT (needed for media previews through the Pi proxy) |
| E11 | `POST /api/projects/{id}/run` | Starts or continues the pipeline in a daemon thread and streams progress over the WS | `VideoGenerationPipeline.run(name, mode="movie")` or `run_animation_pipeline(..., resume=True, project_dir=…)` | **YES** (LLM, TTS, image, video) | PORT as `POST /studio/projects/{id}/run`. Add a cost preflight/confirm and a dryRun flag |
| E12 | `POST /api/projects/{id}/retry-scene` | After a series scene failure: `retry`, `edit` (writes `scene_N_override.txt`), `skip` (writes `scene_N.skip`) or `change_model` (changes the **global** active model), then calls run again | the same as E11 | **YES** | PORT. Make change_model per-project |
| E13 | `WS /ws/{id}` | Pushes queue messages of type `status`, `paused`, `completed`, `done`, `scene_failed`, `error`, `veo_polling`, `cost_update`, `info`. Waits 30 s for a run to appear | none | no | PORT as polling: `GET /studio/projects/{id}/events?since=N` (ring buffer or log file) plus `GET …/status` |
| E14 | `POST /api/projects/{id}/pause` | Sets status=paused and drops the queue. **It does not stop the worker thread** (bug B2) | none | (spend continues!) | PORT with real cancellation: a cancel flag checked between steps and scenes |
| E15 | `GET /api/finals` | Lists output/final/*.mp4 (name, size, mtime) | none | no | PORT as a library of renders that reads render.json |
| E16 | `GET /api/finals/{filename}` | Serves one final MP4 | none | no | PORT (range requests through the proxy) |
| E17 | `GET /api/projects/{id}/step-artifacts?step=&episode=` | Lists the artifact files of one series step from pipeline_state.json | none | no | PORT |
| E18 | `GET /api/projects/{id}/state` | Returns the raw pipeline_state.json (drives the step rail) | none | no | PORT |
| E19 | `GET /api/settings/video-models` | Video model registry grouped by tier, plus an estimated cost per episode | `video_models.VIDEO_MODEL_REGISTRY`, `estimate_episode_cost` | no | PORT |
| E20 | `GET /api/settings/active-model` | Active video model, tier, max_budget and auto_downgrade from settings.json | none | no | PORT |
| E21 | `POST /api/settings/active-model` | Saves the above and calls `Config.reload_settings()` | none | no | PORT |
| E22 | `GET /api/settings` | Masked credentials (`********` / `(from .env)`), LLM/image/TTS models, integrations | none | no | PORT the models part only. DROP credential display (keys stay on the Mac in .env) |
| E23 | `PUT /api/settings` | Writes credentials, models, integrations and video_generation into `output/settings.json` (keys stored in **plaintext**) | none | no | PORT models and video_generation. DROP credential writes and integrations |
| E24 | startup hook | Resets any project stuck in `running` to `paused` | none | no | PORT (agent boot) |
| (dead) | `mode == "animated"` branch in `_execute_pipeline` | Cannot be reached, because `create_project` only accepts movie and animation-series | none | none | DROP |

### 1b. User-facing features (UI). Tick these off during the port.

- **F1: Project list / dashboard.** Shows name, brief, mode, episodes, date and current step, a status badge with a pulse while running, and a Delete button with confirm. Uses E3 and E6. **PORT**
- **F2: New project, mode picker** (Movie Recap or Animation Series cards). Uses E4. **PORT** (as recap / series)
- **F3: Recap create, manual title.** Free text for a movie name or story idea. The CLI path calls `validate_input` and falls back to a random story; the dashboard path does neither. **PORT**, and add the validate-plus-random fallback to the API so both paths match
- **F4: Recap create from Google Sheet** ("next pending row"). Uses E7. **DROP**: Sheets is retired
- **F5: Series create form.** Name, brief, episode count (1–10) and a tier badge with a link to Settings. **PORT**
- **F6: "Surprise me" random series idea.** Uses E8, Groq. **PORT**, re-implemented on Gemini
- **F7: Start / Continue pipeline button.** Uses E11. **PORT**, with a cost estimate and confirm before the run
- **F8: Live log panel.** Timestamped lines with All/Steps/Errors filters, auto-scroll and a "Last update Ns ago" timer. Uses E13. **PORT**, fed by polling
- **F9: Series step rail.** Pre-production steps (writer, screenwriter, casting, world_builder) plus a per-episode block (director, scene_generator, editor). Each step shows pending/running/done/error, duration and an inline error. Episode icons summarise status. Built from E18 and updated by parsing WS messages like `[ep1/director] Starting…`. **PORT**. Note that **set_designer is missing from the JS `EPISODE_STEPS`** (bug B7)
- **F10: Step artifact modal.** Click a completed step to see its artifacts, with pretty renderers for story.json, all_episodes.json, `*_sheet.json`, director_shots.json and `*_layout.json`, plus image grids and video players. Uses E17 and E10. **PORT**, because it is the main review UI
- **F11: Project info panel.** Mode, episodes, created/updated, step progress X/Y, total step time, and counts of generated videos and images. Computed client-side from pipeline_state. **PORT**
- **F12: Budget panel (series).** Spent vs limit with a bar, % used and remaining, and "N scenes via model". Live updates come from `cost_update` messages; initial values come from `project.step_data`. **PORT**, driven by render.json/cost ledger and not by the WS
- **F13: Active quality tier badge** on the pipeline and setup views. Uses E20. **PORT**
- **F14: Review gate (recap).** After the script is generated, the pipeline pauses and shows the script as editable JSON. "Approve & Continue" saves it (E9) and runs again (E11). **PORT, but it is broken today** (B1: the edited script is ignored and the script is regenerated, so the gate loops forever)
- **F15: Scene-failed dialog (series).** Shows the error detail and the prompt (editable, with word count) and a model dropdown. Buttons are Retry, Save edits & retry, Change model & retry, and Skip scene. Uses E12, E19 and E20. Restored on page reload from `step_data.failed_scene`. **PORT**
- **F16: Video polling indicator** (a badge plus a log row saying "Veo scene N — 1m 20s"), from `veo_polling` messages. **PORT**, folded into the polled status (current scene and elapsed time)
- **F17: Pause button.** Uses E14. **PORT, with real cancellation**
- **F18: Error state with a Retry button.** **PORT**
- **F19: Finals library.** A grid of every MP4 in output/final with a video player, size, date and Download. Uses E15 and E16. **PORT**, merged into the Studio renders list with render.json metadata and credits
- **F20: Settings, quality presets** (Budget / Balanced / Premium). One click sets the LLM, image, TTS and video models plus the tier. A badge shows the detected preset or "Custom". **PORT**
- **F21: Settings, model pickers** for the LLM (4 Gemini options), image (3) and TTS (2). **PORT**. Note bug B5: changes only take effect after a restart, although the UI says "next run"
- **F22: Settings, video tier and model picker.** Three tier cards and radio cards per model showing $/s, resolution, max duration, audio and ref-image flags, and ~$/episode. Also max budget per project, an auto-downgrade checkbox and a cost estimate (6 shots × 8 s). Uses E19–E21. **PORT**
- **F23: Settings, API keys tab.** Masked inputs for GEMINI, GROQ, TMDB, PEXELS, FAL, VERTEX_PROJECT_ID and VERTEX_LOCATION, saved in plaintext to output/settings.json. **DROP**: keys belong in the Mac .env only. Show only "configured yes/no" per provider, read-only
- **F24: Settings, Integrations tab** (Google Sheet URL). **DROP**: Sheets is retired
- **F25: Startup reset of stale "running" projects.** **PORT**
- **F26: Auto-open browser on launch** (app.py, server_launcher.py, launch.sh, StudioZero.app). **DROP**

Summary: PORT is E3–E6, E9–E19, E20–E21 and parts of E22–E23 and E24; F1–F3, F5–F22 and F25. DROP is E1, E2, E7 and the credential/integration parts of E22–E23; F4, F23, F24 and F26.

---

## 2. Review of the uncommitted WIP

`git diff --stat`: 20 tracked files, +1165/−193. The big ones are `static/app.js` (+752/−92), `src/steps/scene_generator.py` (+215), `src/steps/director.py` (+86) and `src/server.py` (+79), plus `src/config.py`, `src/animation_pipeline.py` (docstring and an `error_detail` field), `src/steps/__init__.py` (set_designer added to EPISODE_STEPS), `requirements.txt` (+fal-client), several docs, and tracked `.DS_Store` files (these are in .gitignore but already tracked; untrack them).

Untracked: `AGENTS.md` (agent rules, worth keeping), `src/budget_guard.py`, `src/steps/set_designer.py`, `src/tools/{__init__,model_compare}.py`, `src/video_client.py`, `src/video_models.py`, `.playwright-mcp/`.

### What the multi-model work does
- **`video_models.py`**: a pydantic registry of **11 models in 3 tiers**:
  - cheapest: veo-3.1-lite, wan-2.5, kling-2.5-turbo-pro, wan-2.2
  - recommended: veo-3.1-fast, seedance-2.0-fast, seedance-1.5-pro-fast
  - high_fidelity: veo-3.1, kling-3.0-pro, seedance-2.0, sora-2-pro

  Providers are `gemini_api` (Veo through the google-genai SDK) and `fal.ai`. No model uses `vertex_ai` any more. The module also holds `cost_per_second` (None for the Seedance 2.0 models, which are estimated at $0.052/s), `TIER_FALLBACK_ORDER`, `estimate_cost` and `estimate_episode_cost`.
- **`video_client.py`**: `UnifiedVideoClient` routes to Gemini API Veo (generate_videos polled every 10 s up to 300 s; 9:16; ref images up to 3, or image-to-video), fal.ai (`fal_client.upload_file` and `subscribe`; t2v, i2v or ref2v endpoint; `enable_audio=False`) or the legacy Vertex path through `veo_client`. It also does tenacity retries, a cost/generation counter, and `generate_with_fallback` (tries the tier's models round-robin and switches the model).
- **`budget_guard.py`**: `BudgetGuard(max_budget, auto_downgrade)`. `check_budget` estimates a model's cost. If that exceeds the remaining budget it downgrades within the tier, then to the cheapest tier, or raises `BudgetExceeded`. `record_spend` and `summary` are also provided.
- **`steps/set_designer.py`**: a new per-episode step between director and scene_generator. It uses the Gemini image model to composite the character reference with the world reference and writes `scene_starts/{char}_{loc}.png`, cached across episodes.
- **`scene_generator.py`**: now driven by `Config.ACTIVE_VIDEO_MODEL`. It prefers the scene_start image and falls back to the character reference. It runs a budget check before each scene, uses fallback for fal models, emits `cost_update` messages and returns `{model_id, model_name, generation_count, estimated_cost, budget}`.
- **`director.py`**: the prompt style adapts to the model family (veo, kling, seedance, wan, sora) and a `model_hint` field was added.
- **server/app.js**: adds the video-model settings endpoints, the `change_model` retry action, presets, the budget panel and the project info panel.
- **`tools/model_compare.py`**: a CLI that generates one prompt on N models within a budget and writes `output/model_comparison/<ts>/report.html`. **Paid.** `--models all` runs only the fal models.

### Static checks
- `python3 -m py_compile` passes on **all 40 .py files** (src/**, generate_token.py, test_veo.py, verify_token.py) under Python 3.14.0.
- `node --check static/app.js` passes.
- An AST import resolver over every `from src.… import X` / `import src.…` statement found **0 missing modules or names**. Every `Config.X` attribute referenced exists.
- `.playwright-mcp/` (80 KB) holds only Playwright MCP console logs and page snapshots (`console-*.log`, `page-*.yml` from 2026-04-13). **Do not commit it**; add it to .gitignore.
- `src/tools/` contains only `__init__.py` (empty) and `model_compare.py`.

### Bugs, broken parts and half-finished work (B-numbers)
- **B1 (recap via the dashboard never finishes).** `pipeline.run` yields `review_gate=True` right after the script, and the server stops consuming the generator. On "Approve & Continue", `/run` starts a fresh `VideoGenerationPipeline.run()`. The recap route has **no resume**: `pipeline_cache.json` is only written after a successful render, and `edited_script` is read in `_execute_pipeline` but never passed in. So it regenerates the script, a paid LLM call, and pauses again, forever. Evidence: `output/projects/The_Dark_Knight` is `paused` at step 1 with `edited_script`, and `output/pipeline_logs` has 3 script generations for The Dark Knight. The CLI and headless paths are unaffected because `consume_generator` ignores review_gate.
- **B2 (pause does not stop spending).** `/pause` only pops the queue. The daemon thread keeps generating, and a later `/run` can start a **second concurrent thread** on the same project, which means double spend and state races.
- **B3 (series output has no audio on fal models).** `include_audio=False` and `enable_audio=False` are passed "to use our own TTS pipeline", but **no TTS or voice step exists** in `src/steps`. Only a stale `__pycache__/voice_director.cpython-312.pyc` remains. Veo (gemini_api) clips do carry audio. Mixing fallback clips with and without audio makes the editor's stream-copy concat fail, and the re-encode fallback may drop audio.
- **B4 (the budget is not per project).** A new `BudgetGuard` starts at $0 on every `scene_generator.run()`, which means per episode **and** per resume or retry. Clips that already exist are not counted. Set designer, casting and world-builder images, LLM calls and TTS are never counted. Spend uses the estimate at `max_duration_sec`, not the actual duration. For gemini_api models, `client.generate_video` is called without a duration, so the client counts 5 s while the guard counts 8 s. The two cost numbers disagree, and `StepResult.estimated_cost` uses the client's number.
- **B5 (settings do not apply as the UI says).** `Config.reload_settings()` refreshes only the video_generation keys. The LLM, image and TTS models and the API keys are read once at import, so the "applies to next run" message is wrong until a restart. **`FAL_KEY` saved through Settings is never exported to `os.environ`**; `fal_client` reads only the env var, so it works only when set in `.env`.
- **B6 (retries can bill twice).** The `@retry` on OSError, ConnectionError and TimeoutError wraps the whole `_generate_fal` and `_generate_gemini_api` (submit, poll, download), so a download or network error re-submits a paid generation. `generate_with_fallback` also silently switches to another (possibly pricier) model in the same tier without a budget re-check.
- **B7 (UI and docs drift).** `app.js` `EPISODE_STEPS` lacks `set_designer`, so the rail never shows it (although `refreshEpIcon` counts it). The server step-artifacts docstring also lacks it. headless says "9-step"; the docs say 8.
- **B8 (registry inconsistencies).** Descriptions contradict the prices (veo-3.1-fast says $0.12/s but `cost_per_second` is 0.10; veo-3.1 says $0.60/s 4K vs 0.40; veo-3.1-lite says $0.08/s vs 0.05). The Seedance 2.0 endpoints use the `bytedance/…` namespace, which is unverified. The fallback order is not sorted by price. `change_model` writes the **global** active model, which then affects every project.
- **B9 (dead code).** `veo_client.py` is reachable only through `_generate_vertex`, and no registry model has `provider="vertex_ai"` (`test_veo.py` uses it too). `Config.VEO_MODEL`, `VERTEX_*` and the `_RATE_LIMIT_VERTEX` branch are dead. The gemini_api Veo models get only a 5 s gap between requests, which may hit Veo rate limits. headless also has dead modes `animated`, `animation-script` and `animation-render`; anything other than animation-series falls through to the recap flow.
- **B10 (minor).** The Gemini video URI download appends `&key=` even if the URI has no `?`, and it puts the API key in a URL. `get_fallback_errors()` and `_last_error` can be stale across scenes.

---

## 3. Module map

| File | Purpose | Route | External services | Needed after the retirements? |
|---|---|---|---|---|
| `config.py` | Reads .env (dotenv) and output/settings.json; directory constants; `validate()`; `reload_settings` | both | none | **yes** (strip Drive, Sheet and iCloud fields) |
| `config_mappings.py` | Music by genre (files in assets/music), voice and mood tables | recap | none | yes |
| `narrative.py` | `StoryGenerator` (Gemini primary, **Groq fallback**) produces the `VideoScript`. Also `validate_input`, `generate_random_story_idea`, `generate_character_blueprint` (Gemini image, used by series casting and world_builder), and Anthropomorphic* models (legacy) | both | Gemini, Groq | **yes**. Groq is a hard import (`import groq`), so it stays a dependency unless the fallback is removed |
| `moviedbapi.py` | Wikipedia plot search (Wikipedia-API) then the TMDB search, details, metadata and poster download | recap | Wikipedia, TMDB, image.tmdb.org | yes |
| `gemini_tts.py` | Gemini TTS to WAV, 30 voices, mood style prompts, retries | recap | Gemini | yes |
| `stock_media.py` | Pexels video search (portrait filter), download, and fallback to assets/basevideos | recap | Pexels | yes |
| `subtitles.py` | Hormozi-style ASS karaoke subs (pysubs2, Arial Black 80) | recap | none | yes |
| `renderer.py` | `VideoRenderer` (ffmpeg: normalise, Ken Burns for the poster, concat, **sidechaincompress ducking**, ASS burn-in) and `assemble_veo_clips` (series editor) | both | ffmpeg (local) | yes |
| `pipeline.py` | Recap orchestrator plus local Whisper transcription. Also `PipelineStatus` and `SceneAssets` (imported by series) and `run_pipeline` (the batch wrapper) | recap (and series imports PipelineStatus) | through the modules above; openai-whisper locally (downloads the model on first run) | yes |
| `animation_pipeline.py` | Series orchestrator: 4 pre-production steps plus 4 episode steps, resume, retry_gate | series | Gemini | yes |
| `pipeline_state.py` | Series pipeline_state.json model | series | none | yes |
| `steps/__init__.py` | StepContext, StepResult, step lists | series | none | yes |
| `steps/writer.py` | Brief to story.json | series | Gemini LLM | yes |
| `steps/screenwriter.py` | Story to all_episodes.json | series | Gemini LLM | yes |
| `steps/casting.py` | Character sheets plus `_reference.png` | series | Gemini LLM and image | yes |
| `steps/world_builder.py` | Location layouts plus `_reference.png` | series | Gemini LLM and image | yes |
| `steps/director.py` | director_shots.json (prompts in the model family's style) | series | Gemini LLM | yes |
| `steps/set_designer.py` | scene_starts composites (WIP) | series | Gemini image | yes |
| `steps/scene_generator.py` | Video clip per shot, budget guard (WIP) | series | Gemini Veo, fal.ai | yes |
| `steps/editor.py` | Trims 0.2 s and concatenates into final.mp4, copied to output/final/{title}_ep{N}.mp4 | series | ffmpeg | yes |
| `video_models.py` | Model registry and costs (WIP) | series, dashboard | none | yes |
| `video_client.py` | Unified video client (WIP) | series, tools | Gemini, fal.ai, (Vertex) | yes |
| `budget_guard.py` | Budget enforcement (WIP) | series | none | yes (needs a rework, see B4) |
| `veo_client.py` | Legacy Veo client (Vertex or Gemini API key) | none live (dead) | Gemini, Vertex | retire candidate (B9) |
| `tools/model_compare.py` | Paid multi-model comparison CLI | tooling | Gemini, fal.ai | optional (keep as an agent "compare" job behind a budget) |
| `logging_utils.py` | `setup_logging` | headless, batch | none | yes, if headless is kept |
| `headless.py` | `RunConfig` and `run_single`: a non-interactive runner for recap and series (not wired to argv) | both (CLI) | none | **yes**: this is the natural seed for the agent's job runner |
| `cli.py` | Interactive wizard. Recap: Sheet (batch) or manual; series: wizard with a retry/edit/skip loop. `--headless` only prints an error | both (CLI) | Gemini (validate_input) | keep or replace. **It imports `batch_runner` at module top**, so deleting batch_runner breaks the CLI unless that import is removed |
| `app.py` | Menu choosing CLI or web server (uvicorn on 8910 plus browser open) | dashboard | none | **remove** |
| `server_launcher.py` | Starts uvicorn src.server:app on 8910 and opens the browser | dashboard | none | **remove** |
| `server.py` | FastAPI dashboard backend (section 1) | dashboard | Groq; Sheets through cloud_services | evolve into the studio agent API, then remove |
| `project_manager.py` | Project CRUD under output/projects/{id}/project.json | dashboard | none | **keep** for the agent (project store) |
| `batch_runner.py` | Sheets queue: run_pipeline, then a Groq caption, a .txt next to the mp4, a copy to iCloud, an upload to Drive, and the sheet row update. It is the Cloud Run entrypoint | recap (retired) | Sheets, Drive, Groq, iCloud | **remove** |
| `cloud_services.py` | gspread and Drive v3 auth (env GOOGLE_TOKEN_JSON, assets/creds/token.json, GOOGLE_APPLICATION_CREDENTIALS_JSON) plus get_pending_jobs, update_row, upload_to_drive | batch, dashboard | Google Sheets, Drive | **remove** |
| `marketing.py` | Groq-generated social caption with genre hashtags | batch | Groq | **remove** |

**Safe to delete without breaking the recap or series routes through headless:** `batch_runner.py`, `cloud_services.py`, `marketing.py`, `app.py`, `server_launcher.py`, `veo_client.py` (also drop `_generate_vertex`), plus `generate_token.py`, `verify_token.py`, `test_veo.py`, `Dockerfile`, `.dockerignore`, `.github/workflows/deploy.yml`, `StudioZero.app/` and `launch.sh`. **Caveats:**
1. `cli.py` must drop `from src.batch_runner import main as run_batch` and the Sheet sub-menu.
2. `server.py` references `cloud_services` (lazily, inside functions), so it still imports after the deletion, but E7 and the sheet-row updates must go.
3. `pipeline.run_pipeline` is used only by batch_runner and can go too.

### Import graph

```
RECAP (CLI):  src.cli ──► src.headless.run_single ──► src.pipeline.VideoGenerationPipeline.run
              src.cli ──► src.narrative.validate_input / generate_random_story_idea (Gemini)
              src.cli ──► src.batch_runner ──► cloud_services, marketing  (to be cut)
src.pipeline ─┬─► src.config (dotenv, settings.json)
              ├─► src.moviedbapi (wikipediaapi, requests → TMDB)
              ├─► src.narrative ─► config_mappings; google.genai; groq
              ├─► src.gemini_tts (google.genai)
              ├─► src.stock_media (requests → Pexels; assets/basevideos)
              ├─► src.subtitles (pysubs2)
              ├─► src.renderer (ffmpeg-python + ffmpeg CLI; assets/music)
              └─► whisper (lazy, local)

SERIES (CLI): src.cli._run_animation_loop / src.headless(mode=animation-series)
              ──► src.animation_pipeline.run_animation_pipeline
src.animation_pipeline ─┬─► src.config, src.pipeline_state, src.pipeline (PipelineStatus only → pulls whole recap import tree)
                        ├─► src.steps (StepContext; google.genai)
                        └─► importlib src.steps.{writer, screenwriter, casting, world_builder,
                                                director, set_designer, scene_generator, editor}
   casting/world_builder ─► src.narrative.generate_character_blueprint
   director ─► screenwriter, casting, world_builder loaders
   set_designer ─► director loader
   scene_generator ─► video_models, video_client (fal_client lazy, google.genai lazy, veo_client lazy), budget_guard
   editor ─► renderer.assemble_veo_clips, writer.load_story

DASHBOARD: src.app / src.server_launcher ──► uvicorn src.server:app ──► project_manager, config,
           (lazy) pipeline, animation_pipeline, video_models, cloud_services, groq
```
Note: `animation_pipeline` imports `PipelineStatus` from `src.pipeline`, which pulls the whole recap import tree (groq, wikipediaapi, pysubs2, ffmpeg) into series runs. Move `PipelineStatus` to a small shared module.

---

## 4. CLI entry points (today)

| Route | Command | Notes |
|---|---|---|
| Recap, interactive | `python -m src.cli` → `1` (Stock) → `2` (User Entry) → enter a title | Calls `validate_input` (Gemini) and maybe a random idea, then `run_single(RunConfig(movie=…, mode="movie", verbose=True))`. **Paid** |
| Recap, non-interactive | `python -c "from src.headless import RunConfig, run_single; run_single(RunConfig(movie='Inception'))"` | `cli --headless` is a stub that prints an error, so headless is reachable only programmatically. Output: `output/final/{safe_title}.mp4` |
| Recap, Sheets batch | `python -m src.batch_runner [--sheet-url …] [--limit N] [-v]` (also the Docker CMD) | retired |
| Series, interactive | `python -m src.cli` → `2` → title, brief, episodes → confirm | Retry/edit/skip loop in the terminal. Writes to `output/temp/{safe_title}/` (not output/projects) |
| Series, non-interactive | `python -c "from src.headless import RunConfig, run_single; run_single(RunConfig(movie='Title', mode='animation-series', storyline='brief', num_episodes=1))"` | Resumes by default (`no_resume=False`) |
| Model compare | `python -m src.tools.model_compare --prompt "…" --models a,b [--budget 5] [--duration 5] [--image p]` | Paid |
| Dashboard | `python -m src.app` (menu), `python -m src.server_launcher`, `uvicorn src.server:app --port 8910`, `./launch.sh`, StudioZero.app | retired as a UI |

**Existing no-cost or dry-run paths:**
- **Recap `offline=True`** (`RunConfig(movie=…, offline=True)`) skips `Config.validate`, TMDB, Wikipedia, the LLM, TTS and Pexels, and replays `output/temp/{title}/pipeline_cache.json`. Whisper and ffmpeg still run locally. The cache is written only after a **successful** render, and **none exists right now** (`output/temp/The_Dark_Knight` has only poster.jpg).
- **Series resume / file caching**: every step skips its work if its artifact exists (story.json, all_episodes.json, `*_sheet.json` and `*_reference.png`, `*_layout.json`, director_shots.json, scene_starts/*.png, clips/scene_N.mp4, final.mp4). `output/projects/Galactic_Garage` is a complete set of fixtures, including scene_starts and 5 clips, and makes a good seed.
- `.skip` markers skip scenes. **There is no dry-run or mock flag anywhere and no estimate-only mode.**

**A mocked $0 smoke test would need these stubs or seeds:**
- *Recap:*
  - Set dummy env keys so `Config.validate` passes; `MovieDBClient` and `StoryGenerator` are constructed in `__init__` without network calls.
  - Stub `MovieDBClient.search_movie`, `get_movie_details`, `get_tmdb_metadata` and `download_poster` with a fixture dict plus a local jpg.
  - Stub `StoryGenerator.generate_script` with a fixture `VideoScript` (2–3 scenes, an existing music file).
  - Stub `src.pipeline.generate_audio` with silent WAV via the existing `_create_silent_audio`, returning `(path, dur)`.
  - Stub `src.pipeline.download_video` with a copy of `assets/basevideos/videoN.mp4` and metadata `{pexels_url, photographer, fallback}`.
  - Stub `src.pipeline.whisper_transcribe` with synthetic word timestamps; otherwise `whisper.load_model("base")` downloads the model.
  - ffmpeg and renderer run for real.
  - Alternatively, write a fixture `pipeline_cache.json` and run `offline=True`.
- *Series:*
  - Copy `output/projects/Galactic_Garage` to a temp dir; a dummy `GEMINI_API_KEY` is enough for `genai.Client()` construction.
  - Delete `episodes/episode_1/clips/*` and `final.mp4` and reset those steps in pipeline_state.json.
  - Monkeypatch `UnifiedVideoClient.generate_video` and `generate_with_fallback` to ffmpeg-generate a 1–2 s testsrc clip, with and without audio to exercise B3.
  - Monkeypatch `set_designer._generate_scene_start`, or keep the cached scene_starts.
  - For a full fresh run, also stub `ctx.gemini_client.models.generate_content`, which writer, screenwriter, casting, world_builder and director all call; pre-seeding the JSON files is simpler.

---

## 5. Config and secrets surface (names only)

**Env vars read** (`load_dotenv()`, with `output/settings.json` `credentials` overriding through `_get`):
- Keys: `GEMINI_API_KEY`, `GROQ_API_KEY`, `TMDB_API_KEY`, `PEXELS_API_KEY`, `FAL_KEY` (Config only; fal_client itself reads `os.environ['FAL_KEY']`), `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`
- Models: `GEMINI_MODEL_NAME`, `GEMINI_IMAGE_MODEL`, `VEO_MODEL`, `TTS_MODEL`, `VERTEX_VEO_MODEL`, `ACTIVE_VIDEO_MODEL`, `ACTIVE_VIDEO_TIER`, `VIDEO_MAX_BUDGET`. settings.json `models.{llm_model,image_model,tts_model,video_model}` and `video_generation.{active_model,active_tier,max_budget,auto_downgrade}` take precedence.
- Retired: `DRIVE_APPLICATION_CREDENTIALS`, `DRIVE_VIDEO_FOLDER_ID`, `DRIVE_LOGS_FOLDER_ID`, `BATCH_SHEET_URL`, `ICLOUD_EXPORT_PATH`, and in cloud_services `GOOGLE_TOKEN_JSON` and `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

**Files:**
- `.env`, `.env.template` and `env.yaml` (Cloud Run env, gitignored).
- `output/settings.json`, which can hold **plaintext API keys** written by the dashboard. It is gitignored through output/.
- `assets/creds/{token.json, client_secret.json, drive_credentials.json, api_credentials.json}` (Google OAuth/SA, retired, gitignored).

**Output layout:**
```
output/
  settings.json
  final/                      {safe_title}.mp4 (recap) and {story_title}_ep{N}.mp4 (series)
  pipeline_logs/              {ts}_{title}_video_script.json (recap script plus provider used)
  temp/{safe_title}/          recap working dir: poster.jpg, scene_N_audio.wav, scene_N_video.mp4,
                              ending_audio*.wav, subtitles.ass, pipeline_cache.json; also the CLI series project dir
  projects/{id}/              dashboard projects: project.json (status, step_data incl. budget),
                              pipeline_state.json, story.json, all_episodes.json, characters/, worlds/,
                              scene_starts/, episodes/episode_N/{director_shots.json, clips/, final.mp4}
  model_comparison/{ts}/      model_compare outputs and report.html
```
Note: the CLI series writes to `output/temp/{title}` while the dashboard series writes to `output/projects/{id}`. Recap from the dashboard still uses `output/temp/{name}` rather than the project dir.

**Assets used at runtime:**
- `assets/music/*.mp3` (15 files, 81 MB, git-tracked). Picked by the LLM from `config_mappings.MUSIC_GENRES` and mixed by `renderer` (recap). Every referenced file exists. The names look like Pixabay, but there is **no license or provenance file**.
- `assets/basevideos/video1..24.mp4` (656 MB, **git-tracked**). The `stock_media` fallback when Pexels fails. **No provenance.**
- `assets/videos/`: the default download dir if no output_path is given (the pipeline always passes one).
- `assets/image.png` and `assets/creds/` are not used by the routes.
- Fonts: none bundled. Subtitles ask for system "Arial Black" (the Dockerfile substituted fonts-freefont).

---

## 6. Cost and budget

- **`budget_guard.py`**: an in-memory `_cumulative_spend` per instance, created fresh in each `scene_generator.run()`. `check_budget(model_id, duration=max_duration_sec, include_audio=False)` uses `estimate_cost`. When the cost exceeds the remaining budget, auto_downgrade looks for a cheaper model later in `TIER_FALLBACK_ORDER[tier]`, then the first affordable model in the cheapest tier; otherwise it raises `BudgetExceeded`, which becomes a `SceneGenerationError` and so a retry gate. `summary()` returns `{max_budget, cumulative_spend, remaining, utilization_pct}`. See B4 for why this is not a real per-project cap.
- **Where costs are defined:** only `video_models.VIDEO_MODEL_REGISTRY[*].cost_per_second`, plus `estimate_cost` (None means $0.052/s; ×1.5 only for kling-3.0-pro with audio on fal). **There are no cost tables for Gemini LLM tokens, Gemini image, Gemini TTS, Groq, TMDB or Pexels** (the last two are free with attribution).
- **What is recorded today:**
  - series: `project.json` → `step_data["step_N"]` holds the scene_generator data `{model_id, model_name, generation_count, estimated_cost, budget}` (e.g. Galactic_Garage: veo-3.1-lite, $1.50). This exists only for dashboard runs, is estimate-only, and covers video only.
  - recap: **nothing**.
  - model_compare: per-model cost inside report.html only.

**Data available to fill a `render.json` (costUsd, models, credits/licenses, aiGenerated):**

| Field | Recap: where it is | Series: where it is |
|---|---|---|
| title / input | `movie_details.title`, `year`, `tagline`, `genres`, `actors`, `source` (TMDB or Wikipedia), `tmdb_id` (only when `get_tmdb_metadata` ran) → `pipeline_cache.json` | story.json `project_title`, logline, brief (project params) |
| LLM model | `Config.GEMINI_MODEL_NAME`, or Groq `llama-3.3-70b-versatile` on fallback; `provider` is logged in `pipeline_logs/*_video_script.json` | `Config.GEMINI_MODEL_NAME` (writer, screenwriter, casting, world, director) |
| Image model | none | `Config.GEMINI_IMAGE_MODEL` (casting, world_builder, set_designer), not recorded per artifact |
| TTS | `Config.TTS_MODEL`, `script.selected_voice_id` mapped to a Gemini voice, `overall_mood`, `lang_code` | none (no TTS step, B3) |
| Video model(s) | none (stock) | `ACTIVE_VIDEO_MODEL` at start; **the actual per-clip model after fallback or downgrade is not recorded per scene**, only the final `client.model_id` for the episode; `director_shots[*].model_hint` |
| Stock footage credits | per scene `video_metadata`: `pexels_url` (contains the Pexels id), `photographer` (name only; no profile URL or video id stored), `query`, `enhanced_query`, `width`/`height`/`duration`, or `fallback` + `fallback_file` for basevideos (no license info) → kept in `cache_data.scene_assets` | n/a |
| Poster | `movie_details.poster_path` (TMDB path) to `image.tmdb.org/t/p/original{path}` and a local `poster.jpg`; requires the TMDB attribution line | n/a |
| Plot text source | Wikipedia (CC BY-SA; the page URL is **not** stored, though `page.fullurl` is available) or the TMDB overview | n/a |
| Music | `script.selected_music_file` (filename only; no license metadata) | none |
| costUsd | must be computed: TTS chars, LLM tokens (not captured; the genai `usage_metadata` is ignored) | `estimated_cost` and the budget summary (video only, estimated) |
| aiGenerated | script, narration voice (TTS) and subtitles timing are AI-made; footage is stock | everything (story, images, video) |

**Gaps:** there is no token or usage capture, no per-clip model or cost ledger, no Pexels id or photographer URL, no Wikipedia URL, and no license data for the music and basevideos.

---

## 7. Dependencies (requirements.txt)

```
groq>=0.37.1, google-genai>=1.0.0, tenacity>=9.1.2, ffmpeg-python>=0.2.0, python-dotenv>=1.2.1,
requests>=2.32.5, openai-whisper>=20231117, pydantic>=2.0.0, pysubs2>=1.7.0, Wikipedia-API>=0.6.0,
gspread>=6.0.0, google-api-python-client>=2.100.0, google-auth>=2.23.0, rich>=13.0.0,
uvicorn>=0.44.0, fastapi>=0.135.0, fal-client>=0.5.0
```

**Only used by retired features:**
- `gspread`, `google-api-python-client`, `google-auth`: cloud_services. `google-auth` arrives transitively with google-genai anyway.
- `rich`: **not imported anywhere**.
- `uvicorn` and `fastapi`: the old dashboard. Keep them only if the studio agent stays FastAPI, which is likely.
- `groq`: the Groq captions in marketing, the server random idea, and the narrative fallback. It is still a **hard import in `narrative.py`**, so it stays unless the Groq fallback is removed.

**Undeclared:** `google-api-core` (imported by gemini_tts and veo_client; transitive), `google-auth-oauthlib` (generate_token.py only; retired). The system needs **ffmpeg with libass**, and Whisper needs torch (heavy).

---

## 8. Tests

**None.** There is no tests/ directory, no pytest config, no conftest and no CI test step; `deploy.yml` only builds and deploys. `test_veo.py` is a manual, **paid** Veo diagnostic script, not a test. The verification rules in `AGENTS.md` call for a low-cost or mocked smoke path and resume validation, but neither exists yet (see section 4 for what one would need).
