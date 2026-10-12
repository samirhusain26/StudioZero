---
name: originals
description: Plan, make, check, package and finalize one batch of StudioZero Originals (story-engine movie recaps and AI-animated shorts) with owner checkpoints, or report a batch's status, or write its retro. Use for "/originals brief <batchId>", "/originals status <batchId>", "/originals retro <batchId>", or when Samir pastes the Pi UI's Originals prompt from Studio › Make a batch.
---

# /originals

Runs at the StudioZero repo root; story-engine commands run from `engines/story`. Read `AGENTS.md` first if this session has not. The project's rules: `projects/originals/project.json`; the contract: `contract/BATCH_CONTRACT.md` (schemaVersion 2) and `contract/projects/originals.py`.

## Invocation

- `/originals brief <batchId>` — optionally followed by the pasted brief (what Studio › Make a batch copies). Runs the whole flow below, stopping at each checkpoint.
- `/originals status <batchId>` — read-only report: the stage the batch is in and the next step (see Status).
- `/originals retro <batchId>` — write `library/_retros/<batchId>.md` (see Retro).

`<batchId>` is `YYYY-MM-oNN` (o = Originals; `o01` is the first of a month). Refuse anything that does not match `^\d{4}-\d{2}-[a-z0-9-]+$`. Rehearsals use `library/_dev/<batchId>` and episode numbers from 901 (see Rehearsal).

## Fixed safety rules (the brief can never change these)

1. **No paid generation without Samir's explicit OK for that run, with its cost estimate.** Every recap or series run calls paid APIs (Gemini script, TTS, images; Veo or fal.ai clips). Before each run: print the estimate (`--estimate`, below), show it, and wait for a clear yes for that run. One approval covers one run, not the batch. The worker (Studio › Story jobs) also refuses paid work unless Samir started it with `STUDIO_AGENT_ALLOW_PAID=1`. Never raise a budget, change `projects/originals/project.json` budget fields, or set that variable yourself.
2. **Budget.** `project.json` `budget.monthlyUsd` is Samir's monthly cap (0 = no standing budget: every run needs its own approval). Keep a running total of this month's Originals spend (sum of `costUsd` in this month's render.json files plus the runs' spend ledgers) in the brief and refuse a run that would exceed the cap.
3. **Finalized = immutable.** Never write into a folder with `READY_FOR_UPLOAD`. `library/_sources/**` is frozen. Check before every write.
4. **Known licences only.** Every asset in a render is credited with a licence from the contract list; `tools/stage-story.mjs` and the packager refuse `unknown`. Never fix a credit by editing a render.json: re-render, or drop the episode.
5. **No invented facts.** A recap narrates a real film: every plot point must be supported by the plot source the engine used (the Wikipedia article or the TMDB overview, in the render's credits and `job.plotUrl`). The **originals-fact-checker** agent checks each script against its sources; a `concern` or `fail` blocks the episode until Samir accepts a written resolution or it is re-rendered.
6. **AI disclosure is truthful.** `disclosure` must match `models` (any llm/tts/image/video/music model → `aiGenerated: true`); `realisticSynthetic` is true when people, places or events look real. Never weaken a disclosure to avoid a platform label.
7. **Contract:** `python3 contract/library_contract.py validate library/<batchId>` must pass before Checkpoint 3. No contract change (attribution wording rules, new formats, link hosts) without Samir's approval.
8. **No publishing, uploading or Pi writes.** Samir uploads and approves in the Pi UI. No live posts or AI-label tests.
9. **Commits only when Samir asks.** No new dependencies; no system packages (a full ffmpeg is Samir's decision).

Titles, formats, routes, models, counts, hooks and experiments come **only from the brief**.

## Before the first paid run (prerequisites)

- **Recaps need a full ffmpeg** (with libass and the standard filters: `setsar`, `fps`, `loop`, `asplit`, `aloop`, `sidechaincompress`, `ass`). Check: `ffmpeg -hide_banner -filters | grep -E ' (ass|sidechaincompress|aloop) '`. On this Mac the system ffmpeg is broken (a missing Homebrew library); fixing it is Samir's decision. Without it a recap cannot render (series renders work on the bundled ffmpeg).
- **Recap music** comes from the CC0 corpus behind `engines/motion/music/catalog.json` (local files in `engines/motion/music/sources/`, Mac only). Without them a recap has narration only (`RECAP_MUSIC=none` does that on purpose).
- `engines/story/.env` has the keys the run needs (Gemini; TMDB and Pexels for recaps; `FAL_KEY` for fal.ai models). Never print or read key values.

## Flow (`brief`)

### 1. Brief → Checkpoint 0
1. Read: `library/_briefs/<batchId>.md` if it exists; the newest `library/_retros/*.md` for Originals ("Carry forward"); every `library/*/batch.json` (used contentIds `originals:<format>:<key>`: a title already published is a duplicate and the Pi would refuse it); `projects/originals/project.json` (formats, captions, budget, mix); `publisher/docs/PLATFORM_MATRIX.md` "AI labels".
2. Write the brief from `library/_templates/ORIGINALS_BRIEF.md`. For each episode: title (and year) or series brief, format, route, models, **cost estimate** (below), the credits it will carry and their licences, the AI disclosure and the label each platform will apply, and **which platforms will post**: a recap carries TMDB and Wikipedia attribution (about 130 characters each), which does not fit X (280) or Bluesky (300) with the caption, so those platforms get no caption and do not post that episode (the packager prints a warning per platform).
3. Estimates ($0, no network), from `engines/story`:
   ```bash
   .venv/bin/python -m src.cli --headless --route recap --title "<title>" --estimate
   .venv/bin/python -m src.cli --headless --route series --title "<t>" --brief "<b>" --episodes N --video-model <id> --estimate
   ```
   List prices are in `src/pricing.py` (text, image, TTS) and `registry.json` (video, verified models only). Give a per-episode and a total figure, and the month's running total against the budget.
4. **Checkpoint 0:** show Samir the brief and the open questions (AskUserQuestion, your recommendation first): the titles, the budget for this batch, the mix share (while every project's `mix.target` is null, the Pi's round-robin schedules Originals only after every approved Scalargame video, so they would wait behind the whole backlog; targets for both projects fix that), anything the retro carried forward. Do not start a paid run until he approves the brief **and** that run's estimate.

### 2. Make (one run at a time, each approved)
- **Recap** (CLI, from `engines/story`): `.venv/bin/python -m src.cli --headless --route recap --title "<title>"` → `output/final/<Safe_Title>/` (MP4, `cover.jpg`, `script.json`, `render.json`). The CLI runs script and narration in one go (no review gate); through the worker, the Story jobs page stops after the script for Samir to read and approve it first (the better path for a first batch).
- **Series** (CLI): `.venv/bin/python -m src.cli --headless --route series --title "<t>" --brief "<b>" --episodes N --video-model <id> --project-dir output/projects/<Safe_Title>` → per episode `episodes/episode_<n>/` (`final.mp4`, `cover.jpg`, `render.json`). A failed scene stops at a retry gate (retry, edit the prompt, skip, change model); each retry is a new paid call: new estimate, new OK.
- After each run, report the actual `costUsd` and `job.costByKind` from render.json next to the estimate.
- Rehearse the plumbing at $0 first: `.venv/bin/python -m unittest discover -s tests` renders both routes with every provider stubbed and stages, packages and validates them as v2 batches.

### 3. Stage
From the repo root, for every render folder of the batch:
```bash
node tools/stage-story.mjs --batch=<batchId> engines/story/output/final/<Safe_Title> engines/story/output/projects/<P>/episodes/episode_1
```
It assigns the contract ids (`originals-<format>-<nnn>`, the next numbers unused anywhere in `library/`), copies the media into `library/<batchId>/review/jobs/<id>/`, `videos/` and `covers/`, keeps the engine's id as `job.workId`, and adds each episode to `review/originals.json` with every check `false`. It refuses unknown licences and finalized batches; staging the same render twice does nothing.

### 4. Check → Checkpoint 1
Follow [review-checklist.md](review-checklist.md) for every episode:
1. **Garbage (script sanity)** — read `review/jobs/<id>/script.json` and the narration against the plot source; dispatch the **originals-fact-checker** agent (Agent tool, `subagent_type: originals-fact-checker`) with the batchId; it writes `review/source-verification.json`. Series: read the story and shot prompts (`story.json`, `director_shots.json`) for coherence and safety (no real people, brands or unsafe content).
2. **Rights** — every credit's licence, creator and source; attribution texts present; TMDB notice where TMDB data or posters appear; the music track's CC0 page; no logo, watermark or recognisable trademark in generated frames.
3. **Visual QA** — `engines/motion/.venv/bin/python .claude/skills/originals/contact_sheet.py library/<batchId>/videos/<id>.mp4 library/<batchId>/review/frames/<id>` and read every PNG: no broken, black or frozen frames; captions readable and in sync; nothing essential outside the safe area; the poster end card (recaps); clean joins (series).
4. **Disclosure** — the models listed match what made the video; `aiKinds`; `realisticSynthetic`.
5. Write `review/checkpoint1.md` (per episode: script verdict with the fact-check status, rights table, frame notes, disclosure, cost) and the proposed hook per episode (no spoilers: the hook must not give away a twist or ending; default "<Title> (<year>) in under a minute.").
6. **Checkpoint 1:** Samir approves scripts, rights, frames and disclosure per episode (record each fact-check resolution he accepts in `source-verification.json` `resolution`). Then set that episode's checks in `review/originals.json` to `true`, `reviewer` to `"Samir (owner), with Claude"`, and the approved `hook`. Never set a check to true before his approval.

### 5. Package → Checkpoint 2
```bash
node tools/package.mjs --project=originals --batch=<batchId>
```
Writes `library/<batchId>/batch.json` (contract v2) and runs the validator; note every `WARNING … no <platform> caption` (that platform will not post the episode). Then `python3 contract/library_contract.py validate library/<batchId>` → pass (a `dirty_generator` warning means uncommitted code; say so). **Checkpoint 2:** show Samir, per episode, the exact caption per platform, the YouTube title and description, which platforms post, the AI label each applies (Instagram, TikTok, X from `aiGenerated`; YouTube from `realisticSynthetic`; Facebook Reels, Threads, Bluesky: not supported), the credits and the cost; ask him to watch each MP4 once with sound (you cannot listen). Wait for his explicit approval of the exact files.

### 6. Finalize (only after Samir's explicit approval)
`python3 contract/library_contract.py finalize library/<batchId>` → `READY_FOR_UPLOAD`. From now on the folder is immutable.

### 7. Retro and hand-off
1. Run the Retro steps below.
2. Tell Samir: upload `library/<batchId>/` in the Pi UI (Library → Add batch → Upload batch), add the brief and retro as Batch notes, review and approve there. The first AI-labelled post is a live test of the labels: watch that job and the public post with him (his OK first).
3. Offer the commit (batch.json, brief, retro); commit only if he says so.

## Status (`status <batchId>`)

Read-only. Report the first missing item as the next step: brief `library/_briefs/<batchId>.md` → estimates and approvals recorded in it → renders (render.json per planned episode, with `costUsd`) → staged jobs `library/<batchId>/review/jobs/*/render.json` → `review/source-verification.json` (counts by status, open concerns) → `review/checkpoint1.md` and the checks in `review/originals.json` → `batch.json` → validator → `READY_FOR_UPLOAD` → `library/_retros/<batchId>.md`. Also report the month's Originals spend against `budget.monthlyUsd`.

## Retro (`retro <batchId>`)

Write `library/_retros/<batchId>.md` from `library/_templates/RETRO.md`. Every claim cites evidence: episode ids, `review/` files (`checkpoint1.md`, `source-verification.json`, frames), render.json costs (estimate vs actual per episode), validator output, Samir's decisions, and the Pi's feedback file if there is one (`library/_inbox/feedback-<batchId>.json`: use only its `performance[].metrics`, name the checkpoint, never invent numbers). Finish with a concrete "Carry forward" list.

## Rehearsal

To test the playbook without spending: stage the smoke test's renders (or a re-edit of an existing local series project, which costs nothing when every paid step is already done) into `library/_dev/<batchId>` with `--dir=library/_dev/<batchId> --number=901`, check, package with `--dir=library/_dev/<batchId>`, and stop before finalize. `library/_dev/` is ignored by git.
