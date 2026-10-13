# StudioZero — agent and developer context

`AGENTS.md` and `CLAUDE.md` are identical; edit both together.

## What this repo is

StudioZero is the studio behind the @studiozeroflow social accounts. Three nouns:

- **Engine**: how a video is made (toolchain, render, media QA; no posting, no project rules). `motion` = the Remotion project in `engines/motion/`; `story` = `engines/story/`, the Python package with the routes `recap` (stock footage) and `series` (AI animation).
- **Project**: why and for whom (sources, fact and rights rules, voice, call to action, link policy, budget, mix share). `originals` (P0, the story engine's recaps and shorts) and `scalargame` (P1, quiz videos for scalargame.com).
- **Channel**: where. The @studiozeroflow accounts, owned by the publisher only.

Every project follows one flow: Brief → Make (engine, Mac) → Check → Package (`batch.json`) → Approve (Pi, owner) → Schedule → Post → Learn. Root `studio.json` lists projects, engines and channels; each project has `projects/<p>/project.json` (formats, sources, link and call-to-action policy, caption defaults, budget, mix share, required checks). Engines write one `render.json` per episode (`tools/RENDER_JSON.md`) and never `batch.json`; the shared packager `tools/package.mjs` turns `render.json` + the project's captions into `batch.json`. Placement rule: code that must build with an engine's toolchain lives in that engine under `src/projects/<project>/`; content and rules live in `projects/<project>/`. The **publisher** runs on a Raspberry Pi (stdlib Python, systemd units, a private React management UI) and posts approved videos; the **contract** (`batch.json` per batch, one validator on both sides) is the only interface between Mac and Pi. Batches live in `library/`.

This repository is **public**. Read the public-safety rules below before every commit. The consolidation is in progress: `docs/STUDIO_PLAN.md` is the running plan (phases, decisions, status); resume from it.

## Tree

```
AGENTS.md / CLAUDE.md            this file (identical copies)
README.md  LICENSE  CREDITS.md   entry point; MIT for code with an asset/brand carve-out; asset licences
docs/                            STUDIO_PLAN (running plan), PUBLIC_SAFETY, plan/ (Pi cutover design, story engine review),
                                 prompts/ (the consolidation brief), marketing plans: REBUILD_PLAN, REBUILD_CONTRACTS,
                                 PI_UI_REDESIGN_PLAN, AUTOPILOT_PLAN, AUDIO_CORPUS_PLAN, MARKETING_VIDEO_PLAN, UPLOAD_PLAN (historical)
studio.json                      projects, engines, channels (public facts only)
projects/                        <p>/{project.json, package.mjs + package-core.mjs (contract v2 episodes; scalargame: captions, links)}
tools/                           public_safety_check.py (run before every push, stdlib); retro_stats.py (feedback export → matched-checkpoint post stats); stage-story.mjs (story render → batch); package.mjs (shared packager) +
                                 package-regression.mjs; render-json.mjs + RENDER_JSON.md (engine → packager format);
                                 export-catalog.mjs (→ publisher/catalog.json)
engines/motion/                  motion engine, Mac only. Its own Node project (package.json, tsconfig, remotion.config.ts)
  src/                           index.ts, Root.tsx (one composition: LibraryEpisode), fonts.ts, kit/sfx.tsx
  src/projects/scalargame/       Scalargame's quiz kit-1: LibraryEpisode, timing, kit/, styles/, templates/<game>/, types, sample-props.json
  public/                        sfx/ (procedural WAVs), episodes/fonts (OFL), episodes/music (cut beds + beds.json)
  pipeline/                      Scalargame: snapshot → candidates → check → pack → episodes → render (+ render.json) → batch (→ tools/package.mjs) → review (.mjs), music tools, README.md
  render/                        render.sh (the only way to ship an MP4), master_audio.py, check_sync.py, qa_media.py, contact.py
  tools/                         make_sfx.py (public/sfx), make_calm_sfx.py
  music/                         TRACKS.md, rights.json, catalog.json; sources/ (ignored, Mac only)
  node_modules/ .venv/ .audio-work/ out/ sfx/sources/   ignored local toolchains, scratch audio, renders, downloaded packs
engines/story/                   story engine, Mac only (run commands from here)
  src/                           the package: cli.py, headless.py, pipeline.py (recap), animation_pipeline.py + steps/ (series),
                                 video_models.py / video_client.py / budget_guard.py (multi-model video, per-project spend ledger),
                                 render_json.py, agent.py (the story worker agent behind the Pi's studio proxy)
  registry.json                  routes, default model names, video models, tiers (read by video_models.py and the catalog)
  tests/                         unittest: mocked $0 smoke test of both routes (network blocked), billing/budget/registry tests
  scripts/                       agent-token.py (worker token, --send-to-pi), install-agent.sh (opt-in launchd/systemd user unit)
  docs/  requirements.txt  .env.template   engine docs (HEADLESS.md: headless CLI, smoke test, render.json); .env, assets/, output/, .venv/ are local and ignored
publisher/                       Pi. Everything the Pi runs
  app/                           runtime: runner, adapters, ui_server + ui_* modules, approval, activation, autopilot, operations, metrics,
                                 identities.py (channel ID pins read from the Pi config), studio_proxy.py (UI → story worker) (stdlib Python 3.13)
  app/static/                    committed UI bundle + MANIFEST.json (built on the Mac, served on the Pi; never hand-edit)
  catalog.json                   generated by tools/export-catalog.mjs (never hand-edit; served at /api/catalog from Phase 3)
  ui/                            management UI source (React 19, Vite, strict TS); scripts/build-static.mjs builds app/static
  deploy/                        installers (sudo), systemd units, sync-pi.sh (Mac-side), migrate-origin.sh (one-time repo move)
  tests/                         Python tests for app/ (+ fixtures/)
  docs/                          operator guide (PI_UI), publishing plan, platform matrix, schedule, measurement, self-update, TikTok
  profile-assets/  config.example.json (placeholders only)  pi-package.json  pi-package-lock.json
contract/                        shared: library_contract.py (validate/finalize; v1 and v2), projects/<p>.py (v2 project rules), BATCH_CONTRACT.md, tests/
library/                         <batchId>/ (only batch.json tracked), _sources/<snapshot>/ (tracked, frozen), _templates/ _briefs/ _retros/ (tracked notes), _inbox/ _dev/ (ignored)
.claude/                         skills/video-batch/ (Scalargame batch skill), skills/originals/ (Originals playbook), agents/fact-checker.md,
                                 agents/originals-fact-checker.md, launch.json
```

## Mac, Pi, shared

- **Mac (engines/motion/)**: question generation and checking, music beds, rendering, QA, `batch.json`, review sheet, finalize. Needs `engines/motion/node_modules` (`npm ci`) and `engines/motion/.venv` (numpy, scipy, librosa, soundfile, pyloudnorm, Pillow).
- **Mac (engines/story/)**: `.venv/bin/python -m src.cli` from `engines/story` (venv python3.12 from `requirements.txt`, keys in `engines/story/.env`). Paid generation (Gemini, Veo, fal.ai) only with the owner's explicit OK for that run, with a cost estimate. The mocked $0 smoke test runs both routes with every key dummy and sockets blocked. System ffmpeg (Homebrew, `homebrew-ffmpeg/ffmpeg` tap formula, 9.0.2 with libass) runs every filter the recap renderer needs; the $0 suite runs the real renderer. Originals are on hold (owner, 2026-10-12): Scalargame marketing is the main work; generate no Originals video until the owner asks.
- **Pi (publisher/)**: runs from a git checkout at `/opt/scalar-social/repo` (partial + sparse: `publisher/`, `contract/`), updated from the UI (Settings → Update; design in `publisher/docs/SELF_UPDATE.md`). State in `/var/lib/scalar-social`, config and credentials in `/etc/scalar-social` (the channel ID pins under `identities` in `config.json`, the UI's tailnet origin in `ui.env`), UI on `127.0.0.1:8765` behind Tailscale Serve. Python is stdlib only. No npm build on the Pi: it serves the committed `publisher/app/static`. Unit or `pi-package*.json` changes are applied automatically after a completed update (`apply-units.sh --auto`). The Mac reaches the Pi as `ssh scalar-pi` (an alias in the owner's ssh config); agents (Claude, Codex) may use it without asking. Publishing runs on autopilot (`docs/AUTOPILOT_PLAN.md`): `scalar-social-autopilot.timer` (05:15, 17:15 Pi time) refills the schedule when fewer than 7 days remain and activates it. A pause in the UI (`/var/lib/scalar-social/PAUSED`) stops it. Runtime names stay `scalar-social`.
- **Shared (contract/)**: the `ui_*` modules add `<repo>/contract` to `sys.path`.
- **Game data**: `engines/motion/pipeline/lib.mjs` `GAME_DIR` = `$SCALARGAME_DIR`, else `../scalargame` next to this repo (whichever has `src/games/registry.ts`). Only `snapshot.mjs` reads the game repo (committed files only); everything else reads `library/_sources/<snapshot>/`.

## Commands (from the repo root unless noted)

```bash
# Public safety: before every commit that will be pushed, and before every push
python3 tools/public_safety_check.py

# Tests
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
(cd publisher/ui && npm run typecheck && npm run lint && npm test && npm run build)
(cd engines/motion && ./node_modules/.bin/tsc --noEmit)
node --test tools/tests/*.test.mjs                  # render.json checker
node tools/package-regression.mjs                   # packager regression: both 2026-10 batches re-packaged byte-identical + valid

# UI bundle and studio catalog for the Pi: rebuild after any publisher/ui, manifest or engine-registry change, and check before committing
(cd publisher/ui && npm run build:static)            # also runs node tools/export-catalog.mjs
(cd publisher/ui && npm run check:static)            # also runs node tools/export-catalog.mjs --check

# Contract
python3 contract/library_contract.py validate library/<batchId>
python3 contract/library_contract.py finalize library/<batchId>    # only after owner approval

# Scalargame pipeline (details: engines/motion/pipeline/README.md)
node engines/motion/pipeline/snapshot.mjs --id=<YYYY-MM-DD-commit>
node engines/motion/pipeline/candidates.mjs --snapshot=<id> --today=<date>
node engines/motion/pipeline/check.mjs                      # no --set: the 2026-10 regression (questionsHash 5ab19d44…), byte-identical output
node engines/motion/pipeline/episodes.mjs --batch=<batchId>
node engines/motion/pipeline/render.mjs --batch=<batchId>   # resumable; --only=a,b; --rerender
node engines/motion/pipeline/batch.mjs --batch=<batchId>    # = node tools/package.mjs --project=scalargame …; validates; --dry checks captions → library/_dev/batch-dry.json
node tools/render-json.mjs <render.json>...                 # check render.json files
node engines/motion/pipeline/review.mjs --batch=<batchId>

# Pi: after pushing main, bring the Pi to the same commit (check → UPDATE TO <sha> → apply, as Settings → Update)
publisher/deploy/sync-pi.sh

# Calm audio corpus (docs/AUDIO_CORPUS_PLAN.md; from engines/motion/)
.venv/bin/python pipeline/music_catalog.py
.venv/bin/python pipeline/music_beds.py --picks
.venv/bin/python pipeline/audio_review.py

# Render (from engines/motion/)
./render/render.sh LibraryEpisode <out.mp4>         # needs LIBRARY_PROPS_FILE=<props.json>
./node_modules/.bin/remotion still src/index.ts LibraryEpisode out.png --props=<props.json> --frame=<n>
npm run studio                                       # Remotion Studio (.claude/launch.json "remotion-studio")

# Story engine (from engines/story; paid steps need the owner's OK; details: engines/story/docs/HEADLESS.md)
.venv/bin/python -m unittest discover -s tests -v    # mocked $0 smoke test of both routes + billing tests
.venv/bin/python -m src.cli                          # interactive: recap (title) or series (brief, episodes)
.venv/bin/python -m src.cli --headless --route recap --title "<title>" [--offline]                    # PAID unless --offline
.venv/bin/python -m src.cli --headless --route series --title "<t>" --brief "<b>" --episodes N        # PAID
.venv/bin/python -m src.cli --headless --route recap|series … --estimate        # $0: the run's cost estimate
node tools/stage-story.mjs --batch=<batchId> <render folder>...   # (repo root) stage story renders into an Originals batch
.venv/bin/python -m src.agent                       # story worker agent for Studio › Story jobs (setup: docs/HEADLESS.md; paid runs off unless STUDIO_AGENT_ALLOW_PAID=1)
```

Gotchas: run Remotion from `engines/motion/` (it resolves `public/` from the working directory's project). Use `./node_modules/.bin/remotion`, not `npx remotion` (the shell hook intercepts it). The contract validator falls back to `remotion ffprobe` when system ffprobe is missing. Ship MP4s only through `render/render.sh`. Keep `engines/motion/src/fonts.ts` (Fraunces 700 for Whenabouts). `render.mjs` stamps a `codeHash` over the kit paths (paths included), so any move or edit there marks earlier jobs `staleKit`. The shell hook (rtk) rewrites `git`, `grep`, `find` and `diff` output in agent shells: use `/usr/bin/git` etc. when exact output matters.

## Skill and guide

- **`/video-batch`** (`.claude/skills/video-batch/SKILL.md`): Scalargame's batch playbook: `brief <batchId>` runs brief → write → check → pack (Checkpoint 1) → pilots (Checkpoint 2) → render → review → package (Checkpoint 3) → finalize (owner approval only) → retro; `status <batchId>` is read-only; `retro <batchId>` writes `library/_retros/<batchId>.md`. Counts, games, formats and styles come from the brief via the set's `CONFIG` (`engines/motion/pipeline/README.md`); the safety rules are fixed.
- **`fact-checker` agent** (`.claude/agents/fact-checker.md`): independent live-source verification; writes only `library/<batchId>/review/source-verification.json` for an unfinalized batch.
- **`/originals`** (`.claude/skills/originals/SKILL.md`): the Originals playbook: `brief <batchId>` (`YYYY-MM-oNN`) runs brief with per-run cost estimates (Checkpoint 0) → make (story engine; every paid run approved with its estimate) → stage (`tools/stage-story.mjs`) → check (script against its sources, rights, visual QA, disclosure; Checkpoint 1) → package (`tools/package.mjs --project=originals`; Checkpoint 2) → finalize (owner approval only) → retro; `status`, `retro` as above. Brief template `library/_templates/ORIGINALS_BRIEF.md`.
- **`originals-fact-checker` agent** (`.claude/agents/originals-fact-checker.md`): checks each recap script against its plot sources; read-only (no write tool): returns the `review/source-verification.json` content for the playbook to save.
- **Notes**: `library/_templates/{BRIEF,RETRO}.md`; briefs `library/_briefs/<batchId>.md`; retros `library/_retros/<batchId>.md`; the Pi's `feedback-<batchId>.json` goes in `library/_inbox/` (ignored).
- **Owner guide**: `publisher/ui/content/guide/*.md` + `meta.json` (anchors fixed by `docs/REBUILD_CONTRACTS.md` §4), bundled into the UI (Pi UI → Guide); rebuild `publisher/app/static` after editing. `OWNER_GUIDE.md` is the short Mac-side pointer.

## Hard rules

- **Public repository** (`docs/PUBLIC_SAFETY.md`). Never commit credentials, tokens, passcodes, keys, `.env*` (except `.env.template`), `env.yaml`, `assets/creds/`, `publisher/config.json`; media, renders, `out/`/`output/`, QA screenshots; music or SFX without a recorded licence; `*.ts.net` names, IP addresses, e-mail addresses, home paths; platform account IDs (they live in the Pi config under `identities`). `library/_sources/**` may be public (owner decision 2026-10-11). Run `python3 tools/public_safety_check.py` before every push; it must report 0 findings. Docs name the Pi `scalar-pi` and its address `https://<pi>.<tailnet>.ts.net`.
- Finalized batches (folders with `READY_FOR_UPLOAD`: `library/2026-10-pilots`, `library/2026-10-b01`) are immutable: never write into them. `library/_sources/**` are frozen evidence: never edit them.
- Pi access is open to agents: inspect, update, restart services, run `publisher/deploy` scripts with sudo, fix what is broken. Code reaches the Pi only through GitHub: commit on main → `git push origin main` → `publisher/deploy/sync-pi.sh`. Local main, GitHub main and the Pi stay on the same commit. Never edit files in `/opt/scalar-social/repo` or change git config on the Pi. Whoever can push to `main` decides what root runs on the Pi.
- Autopilot schedules and publishes approved library videos. Agents never pause, cancel or re-approve the live schedule unless asked; only the owner resumes. Approving episodes, finalizing and uploading batches stay with the owner: ask before each.
- Never start paid generation (Veo, fal.ai, Gemini video/image/TTS) without the owner's explicit OK for that run, with a cost estimate.
- Contract changes need owner approval (`contract/BATCH_CONTRACT.md`), a validator update and tests; a new project needs a module in `contract/projects/` (a contract change). A batch must never become invalid retroactively. The packager writes every required attribution into the text that posts; the Pi only verifies it and publishes the approved text unchanged.
- No new dependencies without asking. Pi Python stays stdlib only.
- Pushing `main` is approved for shipping `publisher/` or `contract/` changes; other pushes only when the owner asks. Never force-push or rewrite history.

## Claude Code memory

Memory is keyed by the folder path: start sessions in `~/Personal/code_projects/StudioZero`.
