# Session prompt: StudioZero consolidation (StudioZeroFlow studio)

Paste everything below the line into a new Claude Code session started in `~/Personal/code_projects` (the parent folder, because this work moves folders under it). Later sessions for this work start in `~/Personal/code_projects/StudioZero`.

---

You are taking on a multi-session restructuring. Turn **StudioZero** into the studio behind the **@studiozeroflow** social accounts, then move Scalargame marketing into it as the studio's first client project. Follow the phases in order. Stop at every **CHECKPOINT** and wait for my answer. Keep a running plan and status file (`docs/STUDIO_PLAN.md` in the new repo, created in Phase 0) so any later session can resume from it. Never re-derive or re-argue the decisions below.

## Read first (before doing anything)

1. `~/Personal/code_projects/scalargame/marketing/CLAUDE.md` (identical to `AGENTS.md`). These are the marketing repo's hard rules. They all still apply unless this prompt changes them explicitly.
2. In that repo: `README.md`, `docs/REBUILD_PLAN.md`, `docs/REBUILD_CONTRACTS.md`, `docs/PI_UI_REDESIGN_PLAN.md`, `docs/AUTOPILOT_PLAN.md`, `contract/BATCH_CONTRACT.md`, `studio/pipeline/README.md`, `publisher/docs/SELF_UPDATE.md`, `publisher/deploy/bootstrap-git.sh`, `publisher/deploy/sync-pi.sh`, `publisher/app/ui_server.py` (auth model), `publisher/ui/src/App.tsx`, `publisher/ui/src/lib/journey.ts`, `publisher/ui/src/lib/nextBatch.ts`, `.claude/skills/video-batch/SKILL.md`.
3. `~/Personal/code_projects/StudioZero/CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/*.md`, `src/server.py`, `static/app.js`, `src/animation_pipeline.py`, `src/pipeline.py`, `src/video_client.py`, `src/budget_guard.py`, `src/config.py`.
4. `~/Personal/code_projects/scalargame/CLAUDE.md` (the game repo; only touched in Phase 1).
5. Memory: `~/.claude/projects/-Users-samirhusain-Personal-code-projects-scalargame-marketing/memory/MEMORY.md` and the files it links, especially `studiozero_consolidation.md`, `autopilot.md`, `pi_access_policy.md`.
6. `git log --oneline -15` and `git status` in all three repos.

## Current state (verified 2026-10-11)

- **Marketing repo** `~/Personal/code_projects/scalargame/marketing` → GitHub `samirhusain26/scalargame-marketing-plan`, **private**. This is the live, tested system:
  - `studio/` (Mac): Remotion, renders quiz videos.
  - `publisher/` (Pi): stdlib Python 3.13 plus a React UI with a committed static bundle.
  - `contract/`: batch.json v1 and its validator.
  - `library/`: batches. Only `batch.json` and `_sources` are tracked; media is ignored and exists only on this Mac.
  - Autopilot is live (`scalar-social-autopilot.timer` runs at 05:15 and 17:15 Pi time).
  - Finalized batches `library/2026-10-pilots` and `library/2026-10-b01` are immutable.
- **Old StudioZero** `~/Personal/code_projects/StudioZero` → GitHub `samirhusain26/StudioZero`, **public**. It is a Python pipeline with two routes:
  - **stock footage**: movie/story recaps using LLM script, Gemini TTS, Pexels and TMDB posters, Hormozi captions, sidechain ducking.
  - **animation**: an 8-step series pipeline across 11 video models (Veo 3.1 via Gemini, fal.ai), with a budget guard.
  - It also has a FastAPI dashboard (`src/server.py` + `static/app.js`, port 8910, WebSockets), a CLI wizard, a Google Sheets batch runner, Drive/iCloud upload, Groq captions (`src/marketing.py`), and a Cloud Run deploy workflow (`.github/workflows/deploy.yml`).
  - Last commit was 2026-04-13. There are about 1,165 **uncommitted** lines of work worth keeping, mostly multi-model support in `director.py`, `scene_generator.py`, `server.py`, `static/app.js` and `config.py`.
  - Ignored local data: `.env`, `env.yaml` (contains a service-account key), `assets/` (738 MB, including `assets/creds/`), `output/` (144 MB), `StudioZero.app/`.
- **Game repo** `~/Personal/code_projects/scalargame` → `samirhusain26/scalargame`, **private**. Pushing main deploys production on Vercel. It currently ignores `/marketing/` in `.gitignore`, `.vercelignore`, ESLint, Vitest and Vite watch.
- **Pi**: Raspberry Pi **Zero 2 W, 415 MB RAM**. Reach it with `ssh scalar-pi` (user scout, passwordless sudo; agents may use it).
  - Checkout `/opt/scalar-social/repo`: partial + sparse (`publisher/`, `contract/`), owned by the `scalar-social-update` user, using a read-only deploy key and root-owned git/ssh config in `/etc/scalar-social-update`.
  - The updater's `originOk` check accepts only the `scalargame-marketing-plan` (or `scalargame-marketing`) origin.
  - Whoever can push to `main` decides what root runs on the Pi.
  - The UI is served on `127.0.0.1:8765` behind Tailscale Serve, with passcode Bearer auth and a same-origin mutation header.
  - Runtime names are `scalar-social` (units, `/var/lib/scalar-social`, `/etc/scalar-social`).
- **Privacy finding**: `library/_sources/<snapshot>/public/puzzles/` holds **future Whenabouts daily puzzles through 2029**, i.e. every future answer. The live site serves the same shards, but they would be far easier to find in a public repo.
- A quick history scan of the public StudioZero repo found no obvious keys, but commits named "Fixing OAUTH creds", "Base64 update" and "Token troubleshooting" deserve a proper scan.

## Owner decisions (locked)

1. **StudioZero becomes the studio.** Projects: **P0 Originals** (movie/story recaps and AI-generated videos, i.e. the existing StudioZero work) and **P1 Scalargame** (the marketing system). More projects come later, and the page should read as a healthy mixed content page, not only ads.
2. **The StudioZero GitHub repo is public.** Nothing private may become public; see the Phase 0 audit and the public-safety rules.
3. **Keep the old StudioZero work and build on it**, including the uncommitted multi-model work. The stock-footage and animation routes both stay.
4. **Recaps may use stock footage and posters as needed.** Every asset gets credits in the contract, including TMDB attribution where TMDB data or images are used.
5. **One UI.** Everything, including the StudioZero studio pages, is reachable from the Pi UI website. Add a sixth top-level section, **Studio**; this revises locked decision D1 (five sections) in `PI_UI_REDESIGN_PLAN.md`. Studio is the "Make" step of the journey loop (Make, Upload, Review, Schedule, Post, Learn).
6. **Re-pointing the Pi** to the new repo is approved, using the Pi's own scripts. Never hand-edit files in `/opt/scalar-social/repo`.
7. **Keep `scalar-social` runtime names on the Pi.** Change only the product name shown in the UI (StudioZero / StudioZeroFlow).

## Target architecture

### Three nouns

- **Engine**: *how* a video is made, with its own toolchain, render step and media QA. Engines know nothing about posting or any project's rules.
  - `motion`: today's Remotion `studio/`.
  - `story`: the old StudioZero Python package, with routes `recap` (stock footage) and `series` (AI animation). Keep it one package because the routes share TTS, captions, renderer and config.
- **Project**: *why and for whom*. Sources, fact and rights rules, voice, call to action, link policy, monthly budget, mix share, goals.
  - `originals` (P0).
  - `scalargame` (P1).
- **Channel**: *where*. The @studiozeroflow accounts. Owned by the publisher only.

A **format** is one project's reusable recipe on one engine, for example:
- `scalargame/progressive-clues` (motion)
- `originals/movie-recap` (story/recap)
- `originals/animated-short` (story/series)

Any project may use any engine.

### One flow for every project

Brief (prompt builder) → Make (engine, on the Mac) → Check (project checks and engine QA) → Package (shared packager → `batch.json`) → Approve (Pi, owner) → Schedule (mix policy) → Post → Learn (metrics by project/format/engine/experiment, feeding the next brief).

### Boundaries (these make it robust)

1. **Engine output.** Every engine writes the MP4, a cover and a `render.json`, containing:
   - file hashes, duration, resolution;
   - models used;
   - cost in USD;
   - per-asset credits and licenses;
   - `aiGenerated` with a short note on what was generated.

   Engines never write `batch.json`.
2. **Shared packager** (`tools/`). Takes `render.json` plus the project's captions and metadata and produces `batch.json`, which `contract/library_contract.py` then validates. The motion engine's existing `batch.mjs` either becomes this packager or calls it. Pick the smaller change; it must keep the 2026-10 regression outputs byte-identical.
3. **Contract v2** (`contract/`, stdlib, still synced to the Pi). Core fields:
   - `project`, `contentId` (generalizes `questionId` for per-project duplicate protection), `format`, `engine`;
   - captions per platform, cover, video;
   - optional link (URL + UTM; a project's manifest decides whether a link is required);
   - `credits[]` with licenses;
   - `disclosure.aiGenerated`;
   - tags/experiment.

   Each project's extra fields are validated by `contract/projects/<project>.py`, so the Pi checks everything. **v1 batches stay valid** and count as `project: scalargame`. A batch must never become invalid retroactively.
4. **Project manifest** `projects/<p>/project.json`: id, display name, order (P0, P1…), sources (scalargame: `../scalargame`, read only through the existing snapshot; committed files only), formats, link and call-to-action policy, monthly budget, mix share, caption defaults, required checks. A small root `studio.json` lists projects, engines and channels. The prompt builder and the Studio UI read their options from these files. Never hardcode games/formats in the UI again; derive `GAMES`/`FORMATS` from the catalog.
5. **Publisher**:
   - mix policy: per-project share plus spacing rules, e.g. no two from the same project back to back, configurable;
   - per-project duplicate protection;
   - platform AI labels when `aiGenerated` (YouTube altered/synthetic content, TikTok AIGC, Meta AI info, where the APIs or Buffer support it; record where they don't);
   - credits/attribution rendered into captions or descriptions where a license requires it;
   - autopilot refills according to the mix policy.

### Repo layout (target)

```
StudioZero/                         public GitHub samirhusain26/StudioZero
  AGENTS.md / CLAUDE.md             identical; rewritten for the studio
  README.md  LICENSE (owner decides at CHECKPOINT 1)
  studio.json
  docs/  STUDIO_PLAN.md  ARCHITECTURE.md  FLOW.md  PUBLIC_SAFETY.md  decisions/
  contract/                         v2 + projects/<p>.py (root: Pi sparse path)
  publisher/                        Pi; internal paths unchanged
  engines/
    motion/                         today's studio/ (Remotion kit, render.sh, mastering, sfx, music corpus)
      src/projects/scalargame/      Remotion templates/styles that must build with this toolchain
    story/                          old StudioZero package (src/ → story package), routes recap + series, CLI, studio agent API
  projects/
    originals/                      project.json, formats/, briefs/, retros/
    scalargame/                     project.json, pipeline/ (snapshot→candidates→check→pack→episodes), question sets, briefs/, retros/
  tools/                            packager, review sheet, prompt-catalog export
  library/<batchId>/                flat, unchanged paths; project recorded in batch.json
  .claude/                          generic make-batch skill → per-project playbooks (video-batch = scalargame's), fact-checker agent
```

The placement rule: code that has to build with an engine's toolchain lives in that engine, under `src/projects/<project>/`. Content and rules (what to say, whether it is true, whether we may use it) live in `projects/<project>/`.

### Unified UI ("everything from the Pi UI website")

The Pi cannot run generation: no Remotion, no FastAPI, no paid jobs on a 415 MB Pi Zero. Design:

**Studio agent (Mac).** Evolve `src/server.py` (FastAPI, Mac-only dependencies are fine) into the studio agent API.
- Endpoints:
  - health and Mac status;
  - projects, engines and formats (catalog);
  - story-route jobs: create, list, status, logs tail, the retry/edit/skip gate for failed scenes, model and budget settings, outputs, model-compare reports;
  - motion batch status (read-only, equivalent to `/video-batch status`);
  - optionally, package and send a finished batch to the Pi library through the Pi's existing upload API.
- Polling-friendly JSON. Replace WebSockets with status endpoints, because the Pi proxy is stdlib.
- Binds to localhost, reachable only over the tailnet.
- Requires a shared bearer token. Generate it with a script; never print or commit it; the Pi reads it through systemd `LoadCredential`.
- Runs under an opt-in `launchd` agent.
- Paid actions require a server-side budget-guard check plus explicit confirmation with a cost estimate in the UI.

**Pi proxy.** `publisher/app` gets `/api/studio/*`:
- passcode session required, as for every other API route;
- route allowlist;
- request-size cap and timeouts;
- streaming passthrough with Range support for media previews, with no buffering of whole files; measure memory on the Pi;
- a clear "Mac studio offline" response when the Mac is asleep;
- stdlib only.

**Studio section** in `publisher/ui`, the sixth tab:
- Overview: projects, engines, Mac online/offline, budgets used, runway per project.
- Prompt builder (below).
- Make a batch: moved from Library; the motion checklist, generalized per project.
- Story jobs: the old dashboard's features. Read `static/app.js` and `src/server.py`, list every feature, and port each one or explicitly drop it with a reason.
- Batch status.

Without the Mac, the prompt builder and checklists still work. Retire `static/app.js` only after a written parity check. One login, one origin.

**Prompt builder.**
- Pure TypeScript functions with Vitest tests, like `nextBatch.ts`. No backend writes. Presets are kept in browser storage, wrapped in try/catch.
- Options come from the catalog (`studio.json` + `project.json` + engine formats/styles/beds), exported by a tool into the static bundle or served by the Pi from the synced repo. Pick one and justify it. The builder must never offer an option the engine can't render.
- Mode 1, **batch from existing formats**:
  - inputs: project, formats per game/topic, count, difficulty mix, pilots, style, music, experiment, open feedback and last retro (reuse `buildBriefTemplate`);
  - output: a prompt for Claude Code in the StudioZero repo, e.g. `/video-batch brief <batchId>` for scalargame, or the originals playbook for originals.
- Mode 2, **new format / style / project**:
  - inputs: topic or project, engine, visual vocabulary (kinetic type, map zooms, counters, reveal style), structure (hook → body → thinking timer → reveal → call to action), length, audio mood, constraints;
  - output: a prompt for Claude Code to build the template plus a pilot render, which comes back to me for review.
- Every generated prompt includes the fixed safety lines: no finalize or upload without owner approval, facts only from frozen sources, credits required, paid generation only within budget and after confirmation.

## Public-safety rules (new, permanent)

Write these into `docs/PUBLIC_SAFETY.md` and both `CLAUDE.md`/`AGENTS.md`.

**Never committed:**
- credentials, tokens, passcodes, deploy keys, `.env*`, `env.yaml`, `assets/creds/`, `publisher/config.json`;
- media, renders, `studio/out`/QA screenshots (some show tokens);
- music or SFX sources without a recorded license;
- Pi or tailnet hostnames and `*.ts.net` names, IP addresses, personal phone or address details;
- unreleased or future game answers;
- private game-repo content beyond what the snapshot rules allow.

**Required:**
- A pre-commit-equivalent check script (stdlib, run in CI if CI exists, and by agents before every push) that greps for these patterns. CI must not upload anything.
- `config.example.json` carries placeholders only.
- Docs refer to hosts by alias (`scalar-pi`), never by real tailnet names.

## Phases

### Phase 0: audit and plan (read-only; nothing irreversible)

1. **Back up** both working folders, including ignored files, to a dated folder outside both repos (e.g. `~/Personal/backups/2026-10-studiozero/`). Check disk space first. Media may only ever be moved, never deleted.
2. **Inventory ignored local data** in both folders: library media, node_modules, `.venv`s, music/SFX sources, `.env`, `assets/`, `output/`. Plan where each item lands. Python venvs hold absolute paths and must be recreated after a move.
3. **Public-safety audit** of:
   - the marketing repo's tracked tree and its **full history**;
   - the old StudioZero repo's tracked tree and history (already public: if any secret was *ever* committed, tell me which provider to rotate; it cannot be unpublished).

   Use `gitleaks` or `trufflehog` only if already installed; otherwise ask before installing. Always also run a custom pattern pass: keys/tokens, private keys, `*.ts.net`, IPs, emails, phone numbers, Buffer/Meta/Cloudflare IDs, passcodes, Pi hostnames, test records with real post IDs.

   Check in particular:
   - `publisher/config.example.json`;
   - `publisher/docs/**` (test records, handoff notes);
   - `docs/prompts/**`;
   - `library/_sources/**` (future Whenabouts puzzles!);
   - `library/_briefs`/`_retros`;
   - `studio/music/rights.json` versus every committed music bed and SFX file;
   - font licenses;
   - `.claude/` settings.

   Never print secret values. Report locations and types only.
4. **Repo strategy recommendation.** My preferred default, unless the audit argues otherwise:
   - the public `samirhusain26/StudioZero` keeps its history;
   - marketing enters as **one audited import commit** (no private history made public);
   - `scalargame-marketing-plan` stays private and gets archived as the history of record;
   - `library/_sources/**` stays out of the public repo if it can't be made safe. Keep it locally (ignored) and in the private archive, and confirm the `check.mjs` regression (`questionsHash 5ab19d44…`) still runs locally.

   Do **not** rewrite or force-push any history.
5. **Pi cutover design.** Read `bootstrap-git.sh`, `SELF_UPDATE.md` and `updater.py`, then write a tested plan:
   - first ship an updater change that also accepts the new origin (`…/StudioZero`), through the normal flow while still on the old repo;
   - then move the checkout to the new origin with a migration script that keeps `/var/lib/scalar-social` and `/etc/scalar-social` untouched, preserves the security properties in `SELF_UPDATE.md` (dedicated user, read-only deploy key, pinned host keys, root-owned config), and accounts for the new repo's unrelated history;
   - schedule it between autopilot runs;
   - verify: services active, UI loads, update check green, next autopilot run scheduled, nothing published or paused that shouldn't be.

   Agents never pause, cancel or re-approve the live schedule.
6. **Unfinalized motion batches.** Check whether any exist. Moving `studio/` to `engines/motion/` changes `codeHash` paths and marks unfinished jobs `staleKit`.
7. Write `docs/STUDIO_PLAN.md`: the architecture above, audit findings, repo strategy, the contract v2 spec draft (field table and v1→v2 rules), the Pi cutover plan, the full feature-parity list for the old dashboard, phase checklist and status.

**CHECKPOINT 1.** Send me:
- the audit findings, including anything to rotate;
- the repo strategy;
- the `_sources` / future-puzzle decision;
- a LICENSE choice for the public repo (none / MIT / other);
- the contract v2 spec for approval (contract changes need owner approval);
- the Pi cutover plan.

Wait for my answers.

### Phase 1: repo consolidation (no behaviour change)

1. **Old StudioZero.** Commit the uncommitted work to a branch, review it with me if anything looks broken, merge it to main, tag `legacy-final`. Exclude `.DS_Store`.
2. **Retire duplicates.** Remove from the new tree (they stay in history):
   - Cloud Run `deploy.yml` and `Dockerfile` (unattended paid generation);
   - the Sheets batch runner and the Drive/iCloud upload;
   - Groq captions (captions now live in projects + `batch.json`);
   - `StudioZero.app`;
   - one-off token scripts, unless still needed.

   Keep anything the story routes need. Keep the FastAPI dashboard until the Phase 3 parity check.
3. **Build the new tree** with `git mv` where possible:
   - old `src/` → `engines/story/`;
   - marketing import as the single audited commit;
   - then the layout moves (`studio/` → `engines/motion/`, Scalar pipeline → `projects/scalargame/pipeline/`, etc.). Moving the pipeline can wait for Phase 2 if it is cleaner.

   Move ignored local data alongside, without deleting it. Recreate venvs.
4. **Swap local folders.** `~/Personal/code_projects/StudioZero` becomes the new repo; the old tree is kept as `StudioZero-old-2026-10` until I confirm deletion. The marketing folder leaves `scalargame/`.
5. **Game repo.**
   - Remove the `/marketing/` ignore entries (`.gitignore`, `.vercelignore`, ESLint, Vitest, Vite watch).
   - Add a short "Marketing" section to its `CLAUDE.md` and `AGENTS.md` (kept identical): videos about the game are made and published by `../StudioZero` (project `scalargame`); no marketing code goes here; StudioZero snapshots committed files only, and which paths it reads.
   - Commit only those changes; never stage my unrelated edits.
   - **Ask before pushing** (a push deploys production).
6. **GitHub.** Ask at CHECKPOINT 2 before each change:
   - archive or rename the private marketing repo;
   - add the Pi's read-only deploy key to StudioZero;
   - branch protection on `main` (no force-push, no deletion).
7. **Pi cutover** per the approved plan, after CHECKPOINT 2.
8. **Verify:**
   - all test suites green: publisher Python, contract, UI typecheck/lint/Vitest/build, `check:static`, motion `tsc`;
   - `node …/check.mjs` (path updated) reproduces `questionsHash 5ab19d44…`;
   - `git diff --exit-code` on regression outputs;
   - the public-safety check passes;
   - local main = GitHub main = Pi.
9. **Docs and memory.**
   - Rewrite `CLAUDE.md`/`AGENTS.md` for the studio (tree, commands, hard rules, public-safety rules).
   - Copy and update the memory files into `~/.claude/projects/-Users-samirhusain-Personal-code-projects-StudioZero/memory/` (fix paths) and add a pointer in the old memory folder.
   - Propose (don't apply) an update to the projects table in `~/CLAUDE.md`.

**CHECKPOINT 2** (before the GitHub changes, making anything public, and the Pi cutover): show me the exact import tree, the public-safety check output and the cutover script.

### Phase 2: layout, manifests, packager (no behaviour change)

`studio.json`; `projects/originals/project.json` and `projects/scalargame/project.json`; the catalog export; the shared packager producing **v1** output byte-identical to today's for the 2026-10 batches; `render.json` emitted by both engines; story engine routes still runnable through their CLI (mocked, low-cost smoke path; no paid generation without my explicit OK). Update `CLAUDE.md`, the `/video-batch` skill paths and the fact-checker agent paths.

### Phase 3: unified UI (Studio tab, studio agent, Pi proxy, prompt builder)

Build in this order:
1. prompt builder mode 1 (works without the Mac);
2. Studio tab shell + Make a batch move + journey/nav updates (including the e2e nav helper);
3. studio agent + Pi proxy + Story jobs pages, with the parity list worked through;
4. prompt builder mode 2.

Then:
- rebuild `publisher/app/static` (`build:static`, `check:static`);
- test the proxy on the Pi for memory and latency;
- retire `static/app.js` only after the parity list is fully ticked;
- run a security review of the proxy and agent (auth, allowlist, SSRF, path traversal, size limits, token handling).

Previous Pi work needed three reviews; expect the same rigour.

### Phase 4: contract v2 + publisher (behaviour change: needs the CHECKPOINT 1 approval)

- Validator v2 + tests (v1 still valid), Pi importer.
- Per-project duplicate protection.
- Mix policy in the schedule draft and autopilot.
- AI disclosure labels per platform.
- Credits/attribution in captions where required (TMDB: "This product uses the TMDB API but is not endorsed or certified by TMDB" wherever TMDB data or images appear, plus any image-specific credit; Pexels: credit the creator where possible).
- UI shows project/engine/format on episodes and in Learn metrics.
- Ship through commit → push → `sync-pi.sh`.

### Phase 5: Originals back online

- The story engine's recap and series routes produce `render.json` → packager → v2 batch.
- An `originals` playbook skill (brief → make → check: garbage/rights/visual QA → package → owner checkpoints → finalize only on my approval).
- The prompt builder supports originals.
- Plan the first small Originals batch and present the brief to me. **Do not run paid generation, finalize or upload without my explicit approval each time.**

## Standing rules for every phase

- All existing hard rules from the marketing `CLAUDE.md` apply:
  - finalized batches and `_sources` are immutable;
  - Pi Python is stdlib only;
  - no new dependencies without asking;
  - code reaches the Pi only via GitHub main + `sync-pi.sh`;
  - never force-push or rewrite history;
  - approval, finalize and upload stay with me;
  - never pause or modify the live schedule unless I ask.
- Pushing `main` of the StudioZero repo is approved **for shipping `publisher/` or `contract/` changes**, as before. Other pushes only after the CHECKPOINT 2 approval or when I ask. Before every push, run the public-safety check.
- Never start paid generation (Veo, fal.ai, Gemini video) without my explicit OK for that run, with a cost estimate.
- Each phase leaves every test suite green and the Pi on the same commit as main. Update `docs/STUDIO_PLAN.md` status at the end of each work block and save memory notes for decisions and non-obvious gotchas.
- Communicate concisely. Lead with what was done and what needs my decision. Flag blockers immediately rather than working around them.
