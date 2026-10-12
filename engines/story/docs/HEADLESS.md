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

Headless recap takes the title as given (the wizard's `validate_input` / random-idea step is a paid Gemini call and is skipped). `--project-dir` runs a series in an existing project folder (for example a dashboard project under `output/projects/<id>`); the default is `output/temp/<title>`.

## Outputs

- **recap**: `output/final/<safe_title>/` holds `<safe_title>.mp4`, `cover.jpg`, `script.json` and `render.json` (one folder per recap, so render.json never collides; the old dashboard's finals list only shows `output/final/*.mp4`, so it no longer lists recaps).
- **series**: `episodes/episode_N/` holds `final.mp4`, `cover.jpg` and `render.json`; the editor still copies the MP4 to `output/final/<title>_ep<N>.mp4`. The project folder also holds `spend_ledger.json`.

## The $0 smoke test

```bash
.venv/bin/python -m unittest discover -s tests -v
```

It makes no paid or networked call: API keys are `dummy-not-a-key`, `.env` and `output/settings.json` are not read (`STORY_SETTINGS_FILE` points at a missing file), and every socket connect or DNS lookup raises, so a missed stub fails the test instead of spending money. All media is generated into temp dirs at test time.

- **recap** (`tests/test_smoke.py`, `RecapSmokeTest`): `python -m src.cli --headless --route recap` with TMDB/Wikipedia, the LLM script (3 scenes), TTS (silent WAV), Pexels (generated clips with Pexels-like metadata; scene 2 takes the basevideos fallback) and Whisper (synthetic word timings) stubbed. ffmpeg, the subtitles, render.json and the cover run for real.
- **series** (`SeriesSmokeTest`): copies the local fixture `output/projects/Galactic_Garage` to a temp dir, resets episode 1's clips and final, and runs the headless series route with the video providers' network calls replaced by scripted fakes (fallback after a billed failure, a refused submit, a reset download, a Veo clip with audio). The fixture is local, gitignored data: without it this test is skipped. A second run checks that resume spends nothing.
- `tests/test_video_client.py` (B6 retries and fallback budget), `tests/test_budget.py` (B4 ledger), `tests/test_registry.py` (registry.json), `tests/test_server_pause.py` (B2, partial).
- Every render.json is checked with `node tools/render-json.mjs` (run from the repo root by the test).

**ffmpeg caveat.** System ffmpeg on the owner's Mac is broken (missing Homebrew dylibs), so the tests put a shim on `PATH` that runs the Remotion-bundled ffmpeg from `../motion/node_modules/@remotion/compositor-*` (falling back to `remotion ffmpeg`). That build has no `setsar`, `fps`, `loop`, `asplit`, `aloop`, `sidechaincompress` or `ass` filters, so it cannot run the recap renderer's filter graph: the recap smoke test then swaps `VideoRenderer.render_from_scenes` for a test-only stand-in (scale/crop + concat, no music ducking, no captions), and `RealRendererTest` is skipped with the list of missing filters. With a full ffmpeg (with libass) on `PATH`, both run for real. The renderer itself already skips caption burn-in when libass is missing. Series assembly (concat + libx264/aac) runs on the bundled ffmpeg.

## render.json

Format and checker: `../../tools/RENDER_JSON.md`, `node tools/render-json.mjs <file>` from the repo root. Written by `src/render_json.py`.

- **recap**: `episodeId` `originals-recap-<title>-<year>`; `models` = the LLM that wrote the script (Gemini model, or `llama-3.3-70b-versatile` when Groq was the fallback), the TTS model and `openai-whisper-base`; credits for each Pexels clip (creator = photographer, sourceUrl = the Pexels page), basevideos fallback clips (`unknown`), the TMDB poster and metadata (with the TMDB notice), the plot text (Wikipedia, CC BY-SA, with the article URL; or the TMDB overview), the music file (`unknown`: assets/music has no licence records) and the caption font when captions were burned in (`unknown`); disclosure `script` + `voice`.
- **series**: `episodeId` `originals-series-<project>-ep<N>`; `models` = LLM, image model and every video model that actually produced a clip (from the ledger, after fallback or downgrade); `costUsd` = the episode's ledger total (billed failed attempts included); credits for the scene-start images and each clip (`generated`); disclosure `script` + `image` + `video` (+ `voice` when the final cut has an audio track); `realisticSynthetic` is false only when every shot prompt asks for a stylised look (animation, Pixar, cartoon...).
- **Costs** are estimates (`costEstimated: true`). TODO: LLM tokens, TTS and Gemini image calls are not priced yet, so recap `costUsd` is 0 and series `costUsd` covers video only. Gemini/Groq token counts for the recap script are kept in `job.llmUsage`.

## Budget and billing safety (series)

- `spend_ledger.json` (per project) records every video generation the provider accepted, at submit time, with the model that actually ran and its estimated cost; status `submitted` → `ok` or `failed`. `BudgetGuard` starts from the ledger total, so `VIDEO_MAX_BUDGET` is a per-project cap across episodes, resumes and retries. Clips that existed before the ledger are backfilled once (model from `project.json` step data, else the active model; `source: backfill`). A corrupt ledger stops the run instead of restarting at $0.
- `video_client` splits a generation into submit, wait and download. Only a submit that provably never reached the provider (connection refused, DNS failure) is retried; waits and downloads are retried on their own and never re-submit. Fallback asks the budget before every model and skips the ones that no longer fit.

## Registry

`registry.json` (committed, data only) is the single source for the routes, the default model names and the video model registry (models, tier defaults, fallback order). `src/video_models.py` loads and validates it; `tools/export-catalog.mjs` reads it directly.
