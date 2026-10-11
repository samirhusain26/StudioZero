# Scalar marketing — agent and developer context

`AGENTS.md` and `CLAUDE.md` are identical; edit both together.

## What this repo is

Marketing for scalargame.com: a Remotion **studio** on the owner's Mac that renders 1080×1920 quiz videos from frozen game data, a **publisher** that runs on a Raspberry Pi (stdlib Python runtime, systemd units, a private React management UI) and posts approved videos to social platforms, and the **contract** between them (`batch.json` per batch, one validator used on both sides). Batches live in `library/`.

The repo lives at `scalargame/marketing/` inside the game repo's folder (moved from the sibling `scalar-video/` on 2026-10-08) and is its own git repo; the game repo ignores it (`/marketing/` in its `.gitignore`, `.vercelignore`, ESLint and Vitest excludes). Claude Code memory is keyed by folder path, so start sessions in `scalargame/marketing`.

## Tree

```
AGENTS.md / CLAUDE.md            this file (identical copies)
README.md                        short entry point
docs/                            plans (MARKETING_VIDEO_PLAN, UPLOAD_PLAN: historical launch set), REBUILD_PLAN, prompts/ (the StudioZero consolidation brief)
studio/                          Mac only. Its own Node project (package.json, tsconfig, remotion.config.ts)
  src/                           index.ts, Root.tsx (one composition: LibraryEpisode), fonts.ts, kit/sfx.tsx
  src/episodes/                  episode kit-1: LibraryEpisode, timing, kit/, styles/, templates/<game>/, types, sample-props.json
  public/                        sfx/ (procedural WAVs), episodes/fonts (OFL), episodes/music (cut beds + beds.json)
  pipeline/                      snapshot → candidates → check → pack → episodes → render → batch → review (.mjs), music_beds.py, README.md
                                 music_catalog.py + audio_review.py: calm corpus catalog and audition sheet (docs/AUDIO_CORPUS_PLAN.md)
  render/                        render.sh (the only way to ship an MP4), master_audio.py, check_sync.py, qa_media.py, contact.py
  tools/make_sfx.py              regenerates public/sfx
  tools/make_calm_sfx.py         calm procedural SFX candidates → sfx/sources/procedural
  sfx/sources/                   downloaded CC0 SFX packs (Kenney) + procedural candidates (ignored, Mac only; LICENSE.txt per source)
  music/                         TRACKS.md, rights.json, catalog.json (calm corpus); sources/ = owner's six Gemini tracks + holizna/ CC0 lo-fi (ignored, Mac only)
  node_modules/ .venv/ .audio-work/ out/   ignored local toolchains, scratch audio, renders and QA output
publisher/                       Pi. Everything the Pi runs
  app/                           runtime: runner, adapters, ui_server + ui_* modules, approval, activation, autopilot, operations, metrics (post stats reader) (stdlib Python 3.13)
  app/static/                    committed UI bundle + MANIFEST.json (built on the Mac, served on the Pi; never hand-edit)
  ui/                            management UI source (React 19, Vite, strict TS); scripts/build-static.mjs builds app/static
  deploy/                        installers (sudo), systemd units, sync-pi.sh (Mac-side: Pi to the pushed main commit)
  tests/                         Python tests for app/ (+ fixtures/)
  docs/                          operator guide (PI_UI), publishing plan, handoff, platform matrix, test records
  profile-assets/  config.example.json  pi-package.json  pi-package-lock.json
contract/                        shared: library_contract.py (validate/finalize), BATCH_CONTRACT.md (v1), tests/
library/                         <batchId>/ (only batch.json tracked), _sources/<snapshot>/ (tracked, frozen), _templates/ _briefs/ _retros/ (tracked notes), _inbox/ _dev/ (ignored)
.claude/                         skills/video-batch/ (batch skill), agents/fact-checker.md
OWNER_GUIDE.md                   short Mac-side owner pointer (full guide: publisher/ui/content/guide, shown in the Pi UI)
```

## Mac, Pi, shared

- **Mac (studio/)**: question generation and checking, music beds, rendering, QA, `batch.json`, review sheet, finalize. Needs `studio/node_modules` and `studio/.venv` (numpy, scipy, librosa, soundfile, pyloudnorm, Pillow).
- **Pi (publisher/)**: runs from a git checkout at `/opt/scalar-social/repo` (partial + sparse: `publisher/`, `contract/`), created once by `publisher/deploy/bootstrap-git.sh` and updated from the UI (Settings → Update; design in `publisher/docs/SELF_UPDATE.md`). Before that bootstrap it runs the older copied install (`/opt/scalar-social/scripts/social/`, `/opt/scalar-social/ui`). State in `/var/lib/scalar-social`, config and credentials in `/etc/scalar-social`, UI on `127.0.0.1:8765` behind Tailscale Serve. Python is stdlib only. No npm build on the Pi: it serves the committed `publisher/app/static`. Unit or `pi-package*.json` changes are applied automatically after a completed update (`scalar-social-apply-units.path` runs `apply-units.sh --auto` as root; status on Settings → Update); `sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh` by hand only when that reports a failure. The Mac reaches the Pi as `ssh scalar-pi` (an alias in the owner's ssh config); agents (Claude, Codex) may use it without asking. Publishing runs on autopilot (`docs/AUTOPILOT_PLAN.md`): `scalar-social-autopilot.timer` (05:15, 17:15) records Buffer posting tests, refills the schedule with the recommended draft when fewer than 7 days remain, and runs `activate.py --auto`, which `scalar-social-approve.service` also runs after each approval. A pause in the UI (`/var/lib/scalar-social/PAUSED`) stops it.
- **Shared (contract/)**: the installers copy `contract/library_contract.py` next to the app files on the Pi. In the repo, the `ui_*` modules that import it add `<repo>/contract` to `sys.path` when that folder exists.
- **Game data**: `studio/pipeline/lib.mjs` `GAME_DIR` = `$SCALARGAME_DIR`, else the parent folder, else `../scalargame` (whichever has `src/games/registry.ts`). Only `snapshot.mjs` reads the game repo (committed files only); everything else reads `library/_sources/<snapshot>/`.

## Commands (from the repo root unless noted)

```bash
# Tests
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
(cd publisher/ui && npm run typecheck && npm run lint && npm test && npm run build)
(cd studio && ./node_modules/.bin/tsc --noEmit)

# UI bundle for the Pi: rebuild after any publisher/ui change, and check before committing
(cd publisher/ui && npm run build:static)   # vite build → publisher/app/static + MANIFEST.json
(cd publisher/ui && npm run check:static)   # fails if the committed bundle or source hash is stale

# Contract
python3 contract/library_contract.py validate library/<batchId>
python3 contract/library_contract.py finalize library/<batchId>    # only after owner approval

# Pipeline (details: studio/pipeline/README.md)
node studio/pipeline/snapshot.mjs --id=<YYYY-MM-DD-commit>
node studio/pipeline/candidates.mjs --snapshot=<id> --today=<date>
node studio/pipeline/check.mjs                      # rewrites questions-<set>.json; must be byte-identical when nothing changed
node studio/pipeline/episodes.mjs --batch=<batchId>
node studio/pipeline/render.mjs --batch=<batchId>   # resumable; --only=a,b; --rerender
node studio/pipeline/batch.mjs --batch=<batchId>    # --dry checks captions → library/_dev/batch-dry.json
node studio/pipeline/review.mjs --batch=<batchId>

# Pi: after pushing main, bring the Pi to the same commit (check → UPDATE TO <sha> → apply, as Settings → Update)
publisher/deploy/sync-pi.sh

# Calm audio corpus (docs/AUDIO_CORPUS_PLAN.md; from studio/)
.venv/bin/python pipeline/music_catalog.py           # measure music/sources → music/catalog.json (quizFit, 15 picks per game)
.venv/bin/python pipeline/music_beds.py --picks      # cut calm beds for the picks → public/episodes/music + beds.json
.venv/bin/python pipeline/audio_review.py            # audition sheet → out/audio-review/index.html (launch config "audio-review")

# Render (from studio/)
./render/render.sh LibraryEpisode <out.mp4>         # needs LIBRARY_PROPS_FILE=<props.json>
./node_modules/.bin/remotion still src/index.ts LibraryEpisode out.png --props=<props.json> --frame=<n>
npm run studio                                       # Remotion Studio (.claude/launch.json "remotion-studio")
```

Gotchas: run Remotion from `studio/` (it resolves `public/` from the working directory's project). Use `./node_modules/.bin/remotion`, not `npx remotion` (the shell hook intercepts it). System ffmpeg is broken: use `remotion ffmpeg` / `remotion ffprobe`. Ship MP4s only through `render/render.sh` (fdk-AAC edit list, mastering, sync check). Keep `studio/src/fonts.ts`: it registers Fraunces 700, which Whenabouts episodes use. `render.mjs` stamps a `codeHash` over `src/episodes`, `public/episodes`, `kit/sfx.tsx`, `src/fonts.ts`, `src/Root.tsx`, `public/sfx` and `render/render.sh` (paths included), so any move or edit there marks earlier jobs `staleKit`.

## Skill and guide

- **`/video-batch`** (`.claude/skills/video-batch/SKILL.md`, with `batch-setup.md`, `review-checklist.md`, `covers_sheet.py`): `brief <batchId>` runs brief → write → check → pack (Checkpoint 1) → pilots (Checkpoint 2, if the brief asks) → render → review → package (Checkpoint 3) → finalize (owner approval only) → retro; `status <batchId>` is read-only; `retro <batchId>` writes `library/_retros/<batchId>.md`. Counts, games, formats, mix and styles come from the brief, and land in the set's `CONFIG` export (`questions-<set>.mjs`: scope, mix, pilots, styles, beds, episode IDs, experimentId, verification path; see `studio/pipeline/README.md`); the safety rules are fixed. `node studio/pipeline/check.mjs` with no `--set` is the 2026-10 regression check (questionsHash `5ab19d44…`).
- **`fact-checker` agent** (`.claude/agents/fact-checker.md`): independent live-source verification; writes only `library/<batchId>/review/source-verification.json` for an unfinalized batch.
- **Notes**: templates `library/_templates/{BRIEF,RETRO}.md`; briefs `library/_briefs/<batchId>.md`; retros `library/_retros/<batchId>.md` (tracked, never inside a batch folder); the Pi's `feedback-<batchId>.json` goes in `library/_inbox/` (ignored).
- **Owner guide**: `publisher/ui/content/guide/*.md` + `meta.json` (anchors fixed by `docs/REBUILD_CONTRACTS.md` §4) is the single source, bundled into the UI (Pi UI → Guide). After editing it, rebuild `publisher/app/static` (`npm run build:static`). `OWNER_GUIDE.md` is the short Mac-side pointer.

## Hard rules

- Finalized batches (folders with `READY_FOR_UPLOAD`: `library/2026-10-pilots`, `library/2026-10-b01`) are immutable: never write into them; create a new batch or revision. `library/_sources/**` are frozen evidence: never edit them.
- Pi access is open to agents: inspect, update, restart services, run `publisher/deploy` scripts with sudo, fix what is broken. Code reaches the Pi only through GitHub: commit on main → `git push origin main` → `publisher/deploy/sync-pi.sh` (the Pi's own updater; it refuses a dirty or diverged checkout). Local main, GitHub main and the Pi stay on the same commit. Never edit files in `/opt/scalar-social/repo` or change git config on the Pi; change the repo and sync instead.
- Autopilot schedules and publishes approved library videos (owner decision, 2026-10-09): no typed `APPROVE <hash>`, no activation command after the owner's first one. The owner pauses in the UI; only the owner resumes (`sudo rm /var/lib/scalar-social/PAUSED`), and agents never pause, cancel or re-approve the live schedule unless asked. Approving episodes, finalizing and uploading batches stay with the owner: ask before each.
- Contract changes need owner approval (`contract/BATCH_CONTRACT.md`), a validator update and tests.
- No new dependencies without asking. Pi Python stays stdlib only.
- Never commit media, credentials, `publisher/config.json`, or anything from `studio/out/` (some QA screenshots show tokens).
- Shipping a `publisher/` or `contract/` change to the Pi includes committing it on main and pushing (above). Other commits and pushes only on the owner's request. Never force-push or rewrite history.

## Claude Code memory

Claude Code keys project memory by the folder path. Moving the repo (to `scalargame/marketing/` in Phase 2) starts a new, empty memory folder for it; carry over anything worth keeping from the old one.
