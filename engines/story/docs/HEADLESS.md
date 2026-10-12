# Headless runs, the $0 smoke test and render.json

Run everything from `engines/story`. Paid generation (Gemini LLM/TTS/image, Veo, fal.ai) needs the owner's explicit OK for that run, with a cost estimate (`../../AGENTS.md`).

## Setup

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt     # openai-whisper pulls torch
.venv/bin/python -c "import src.cli"          # import check
```

## Headless commands

```bash
# recap (stock footage). PAID: Gemini script + TTS (Groq if Gemini fails); TMDB, Wikipedia, Pexels are free
.venv/bin/python -m src.cli --headless --route recap --title "The Dark Knight"

# recap re-render from output/temp/<title>/pipeline_cache.json: no API calls (Whisper and ffmpeg run locally)
.venv/bin/python -m src.cli --headless --route recap --title "The Dark Knight" --offline

# series (AI animation). PAID: Gemini LLM + image, Veo / fal.ai video. Resumes by default
.venv/bin/python -m src.cli --headless --route series --title "Galactic Garage" \
    --brief "Alien mechanics fix spaceships" --episodes 1 [--project-dir output/projects/<id>] [--no-resume]

.venv/bin/python -m src.cli --help             # all flags; no --headless = the interactive wizard
```

Headless recap takes the title as given (the wizard's `validate_input` / random-idea step is a paid Gemini call and is skipped). `--project-dir` runs a series in an existing project folder (for example a Story jobs project under `output/projects/<id>`); the default is `output/temp/<title>`.

## Outputs

- **recap**: `output/final/<safe_title>/` holds `<safe_title>.mp4`, `cover.jpg`, `script.json` and `render.json` (one folder per recap, so render.json never collides; Studio › Story renders lists every folder with a render.json).
- **series**: `episodes/episode_N/` holds `final.mp4`, `cover.jpg` and `render.json`; the editor still copies the MP4 to `output/final/<title>_ep<N>.mp4`. The project folder also holds `spend_ledger.json`.

## The $0 smoke test

```bash
.venv/bin/python -m unittest discover -s tests -v
```

It makes no paid or networked call: API keys are `dummy-not-a-key`, `.env` and `output/settings.json` are not read (`STORY_SETTINGS_FILE` points at a missing file), and every socket connect or DNS lookup raises, so a missed stub fails the test instead of spending money. All media is generated into temp dirs at test time.

- **recap** (`tests/test_smoke.py`, `RecapSmokeTest`): `python -m src.cli --headless --route recap` with TMDB/Wikipedia, the LLM script (3 scenes), TTS (silent WAV), Pexels (generated clips with Pexels-like metadata; scene 2 takes the generic-query fallback) and Whisper (synthetic word timings) stubbed; the fakes report token and audio usage, so the spend ledger and `costUsd` are exercised. Music comes from a one-track CC0 test catalog. ffmpeg, the contract conform step, the subtitles, render.json and the cover run for real. The run then goes through `tools/stage-story.mjs`, `tools/package.mjs --project=originals` and the contract validator (ffprobe media checks included) into a scratch v2 batch in a temp dir.
- **series** (`SeriesSmokeTest`): copies the local fixture `output/projects/Galactic_Garage` to a temp dir, resets episode 1's clips and final, and runs the headless series route with the video providers' network calls replaced by scripted fakes (fallback after a billed failure, a rejected and a refused submit, a reset download, a Veo clip with audio among silent ones: review B3). The final episode is checked for audio, 1080x1920, 30 fps, AAC 48 kHz stereo and fast start, then staged, packaged and validated as a v2 batch like the recap. The fixture is local, gitignored data: without it this test is skipped. A second run checks that resume spends nothing.
- `tests/test_video_client.py` (B6 retries, uncertain submits counted, fallback budget, each fal.ai request shaped to its model's verified schema, unverified models never called), `tests/test_budget.py` (B4 ledger), `tests/test_pricing.py` (LLM, image and TTS prices, the shared ledger), `tests/test_registry.py` (registry.json), `tests/test_agent.py` (the worker agent: auth, estimates and budget, cancel (B2), recap review gate (B1), settings reload (B5), scene decisions, files and paths).
- Every render.json is checked with `node tools/render-json.mjs` (run from the repo root by the test).

**ffmpeg caveat.** System ffmpeg on the owner's Mac is broken (missing Homebrew dylibs), so the tests put a shim on `PATH` that runs the Remotion-bundled ffmpeg from `../motion/node_modules/@remotion/compositor-*` (falling back to `remotion ffmpeg`). That build has no `setsar`, `fps`, `loop`, `asplit`, `aloop`, `sidechaincompress` or `ass` filters, so it cannot run the recap renderer's filter graph: the recap smoke test then swaps `VideoRenderer.render_from_scenes` for a test-only stand-in (scale/crop + concat, no music ducking, no captions), and `RealRendererTest` is skipped with the list of missing filters. With a full ffmpeg (with libass) on `PATH`, both run for real. The renderer itself already skips caption burn-in when libass is missing. Series assembly (scale/crop, libx264/aac, concat) and the contract conform step run on the bundled ffmpeg.

## Cost estimate before a paid run ($0)

```bash
.venv/bin/python -m src.cli --headless --route recap --title "<title>" --estimate
.venv/bin/python -m src.cli --headless --route series --title "<t>" --brief "<b>" --episodes N --video-model <id> --estimate
```

Prints the priced lines and the total (`src/estimates.py`, the same figures the worker shows before it asks for a confirmation) and exits without any network call. `--video-model` picks a verified model for a series run (refused when the model is not verified in `registry.json`). A CLI recap runs script and narration in one go, so its estimate covers both; the worker stops after the script for review and estimates each half separately.

## Story worker agent (Studio › Story jobs)

`src/agent.py` is the engine's API for the Pi UI (it replaced the old dashboard, `src/server.py` + `static/`, in Phase 3). It runs on this laptop, listens on `127.0.0.1:8911` only, and is reached solely through the Pi's studio proxy (`publisher/app/studio_proxy.py`), which forwards the UI's `/api/studio/*` after the UI's own sign-in. Keys stay in this folder's `.env`.

```bash
python3 scripts/agent-token.py                 # once: ~/.config/studiozero/agent-token (0600); never printed
.venv/bin/python -m src.agent                  # run it in a terminal, or at login:
sh scripts/install-agent.sh                    # launchd (macOS) / systemd user unit (Linux); --remove to undo
tailscale serve --bg --https=8911 http://127.0.0.1:8911            # expose it on the tailnet (this host only)
python3 scripts/agent-token.py --send-to-pi --url https://<laptop>.<tailnet>.ts.net:8911 --addr <laptop tailnet IP>
```

The last command pipes the token over ssh into `publisher/deploy/studio-worker.sh` on the Pi, which writes a root-only credential and a Pi-local drop-in for `scalar-social-studio-proxy.service` (the address and token never enter git). `--rotate` makes a new token (restart the agent, then send it again). Without the drop-in, or while the laptop sleeps, the Studio shows **Worker offline**.

- Every request needs the bearer token; no OpenAPI or docs pages are served.
- Paid work needs a server-side estimate token that the owner confirmed (`GET …/estimate`, then `POST …/run` with it) and a budget check against the project's `spend_ledger.json`. The estimate prices every call at list prices (script, narration, story, character and location sheets and images, shot lists, scene-start images, clips). **Paid runs stay off** unless the agent starts with `STUDIO_AGENT_ALLOW_PAID=1`, which the owner sets for a run they approved.
- One run at a time; Cancel stops before the next step and, in the scene generator, before the next clip's paid submit. Runs found "running" at start are reset to paused.
- Event text and errors replace this host's folders with `…` / `~`; the pipeline state sent to the UI has no paths.

## render.json

Format and checker: `../../tools/RENDER_JSON.md`, `node tools/render-json.mjs <file>` from the repo root. Written by `src/render_json.py`.

Before probing, `conform_for_contract` makes the MP4 meet the batch contract's media rules (H.264 yuv420p, AAC 48 kHz stereo, fast start, at most 24 MB): only what is off is redone, and `job.conformed` lists it.

- **recap**: `episodeId` (the engine's work id) `originals-recap-<title>-<year>`; `models` = the LLM that wrote the script (Gemini model, or `llama-3.3-70b-versatile` when Groq was the fallback), the TTS model and `openai-whisper-base`; credits for each Pexels clip (creator = photographer, sourceUrl = the Pexels page; a scene whose queries find nothing gets generic Pexels footage, never a local clip), the TMDB poster and metadata (with the TMDB notice), the plot text (Wikipedia, CC BY-SA, with the article URL; or the TMDB overview), the background music (a CC0 track from `../motion/music/catalog.json` with artist and page, `src/music.py`; `RECAP_MUSIC=none` for narration only; `assets/music` is never used) and the caption font when captions were burned in (Fraunces Black, OFL-1.1, `fonts/`); disclosure `script` + `voice`. Only a recap replayed from a cache made before 2026-10-12 can still carry an `unknown` stock clip; the staging step and the packager refuse it.
- **series**: `episodeId` `originals-series-<project>-ep<N>`; `models` = LLM, image model and every video model that actually produced a clip (from the ledger, after fallback or downgrade); credits for the scene-start images and each clip (`generated`); `job.audio` = the audio policy and how many clips had native audio; disclosure `script` + `image` + `video` (+ `voice` when a clip had native audio); `realisticSynthetic` is false only when every shot prompt asks for a stylised look (animation, Pixar, cartoon...).
- **Costs** (`costUsd`, `costEstimated: true`, `job.costByKind`) come from the project's `spend_ledger.json`: every Gemini/Groq text call, image and TTS call (`src/pricing.py`: list prices with their sources and check date; an unknown model is charged at the table's highest rate, never $0) and every video generation (registry.json prices). A recap counts all of its calls; a series episode counts its own calls plus an equal share of the project-level work (story, characters, worlds).
- **Into a batch**: the Originals playbook stages a render with `node tools/stage-story.mjs --batch=<batchId> <render folder>` (from the repo root): contract id `originals-<format>-<nnn>`, media copied to `review/jobs/<id>/`, `videos/`, `covers/`, `job.workId` = the engine's id.

## Series audio policy (review B3)

There is no narration or TTS step in a series. With `SERIES_NATIVE_AUDIO=1` (default) a model that has native audio is asked for it and priced with it; a model without audio makes silent clips. The editor normalises every clip (1080x1920 centre crop, 30 fps, H.264, AAC 48 kHz stereo, a silent track where a clip has none) before joining them, so a mix of clips never loses its audio or size. `SERIES_NATIVE_AUDIO=0` requests silent clips from every model.

## Budget and billing safety (series)

- `spend_ledger.json` (per project) records every video generation the provider accepted, at submit time, with the model that actually ran and its estimated cost; status `submitted` → `ok` or `failed`, or `uncertain` when the submit failed in a way that may have reached the provider (a timeout after sending, a 5xx, a dropped connection): counted, never retried. Text, image and TTS calls are in the same file (`kind`). `BudgetGuard` starts from the ledger total, so `VIDEO_MAX_BUDGET` is a per-project cap across episodes, resumes and retries. Clips that existed before the ledger are backfilled once (model from `project.json` step data, else the active model; `source: backfill`). A corrupt ledger stops the run instead of restarting at $0.
- `video_client` splits a generation into submit, wait and download. Only a submit that provably never reached the provider (connection refused, DNS failure) is retried; waits and downloads are retried on their own and never re-submit. Fallback tries the current model, then the tier's other verified models cheapest first, asks the budget before every model and skips the ones that no longer fit.
- Every shot is requested at its model's `clip_seconds` (5 s on fal.ai, 8 s for Veo, which always renders 8 s); Veo requests are spaced 35 s apart.

## Registry

`registry.json` (committed, data only) is the single source for the routes, the default model names and the video model registry (models, tier defaults, fallback order). `src/video_models.py` loads and validates it; `tools/export-catalog.mjs` reads it directly.

Each video model records `verified` (date and the fal.ai model pages or Gemini pricing page it was checked against, 2026-10-12) and, for fal.ai, `params`: which input names its schema uses (image `image_url` or `start_image_url`, audio `generate_audio`, references `image_urls`), whether it takes `aspect_ratio` (sent as 9:16) and `resolution`, and its allowed durations. A model without `verified` (today Sora 2 Pro: its fal.ai endpoints could not be confirmed) is never called, listed or offered as a fallback. Prices are per second at the requested resolution, with `cost_per_second_audio` where native audio costs more; `fallbackOrder` is each tier's verified models sorted by price (a test keeps it that way). Seedance 2.0 Fast/Standard cost $0.2419/$0.3034 a second at 720p, not the $0.052 the old registry assumed. `seedance-1.5-pro-fast` was renamed `seedance-1.5-pro` (its real endpoint); the old id still resolves.
