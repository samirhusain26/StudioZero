# Session prompt: StudioZero, Phase 6 (Scalargame marketing at a steady cadence)

You are continuing work on **StudioZero**, the public studio repo behind the @studiozeroflow accounts. Phases 0–5 (the consolidation) are done. **Owner direction (2026-10-12): Scalargame marketing videos are the main work. Originals stay wired up but on hold: generate no Originals video (no story-engine run, no paid call) unless the owner asks.**

This phase makes Scalargame publishing sustainable:
- the next batch ships before the content runs out;
- the Learn step (post stats → feedback → brief) feeds every brief;
- making a batch becomes routine and on time.

Don't re-derive or re-argue earlier decisions (`docs/STUDIO_PLAN.md` §1 and the phase logs).

## Read first

1. `AGENTS.md` (= `CLAUDE.md`): tree, commands, hard rules, public safety.
2. `docs/STUDIO_PLAN.md`:
   - the status line;
   - §1 locked decisions;
   - §16–§17 (the Phase 4 and 5 logs);
   - **"After Phase 5"** (open owner decisions, debt, what to watch, the on-hold note).
3. The Scalargame playbook: `.claude/skills/video-batch/SKILL.md`, `batch-setup.md`, `review-checklist.md`; `engines/motion/pipeline/README.md`; the `fact-checker` agent.
4. The last retros: `library/_retros/2026-10-pilots.md` and **`library/_retros/2026-10-b01.md` ("Carry forward")**; the templates `library/_templates/{BRIEF,RETRO}.md`.
5. The publisher's Learn side:
   - `publisher/app/metrics.py`;
   - `publisher/docs/MEASUREMENT.md`, `SCHEDULE.md`, `PLATFORM_MATRIX.md`;
   - `docs/AUTOPILOT_PLAN.md` (refill when fewer than 7 days remain);
   - the UI's Next batch / Learn pages (`publisher/ui/content/guide/next-batch.md`).
6. Memory: `~/.claude/projects/-Users-samirhusain-Personal-code-projects-StudioZero/memory/MEMORY.md`.
7. `git log --oneline -20`, `git status`, and the Pi state (read-only): `ssh scalar-pi`, `publisher/deploy/sync-pi.sh --check` if it exists, else compare the commits.

## State at handoff (2026-10-12, verified)

- **In sync:** local main = GitHub = Pi at `e7533df` or later.
- **Library:** 24 Scalargame episodes, all approved:
  - `2026-10-pilots`: 4 episodes, contract v1, finalized.
  - `2026-10-b01`: 20 episodes, contract v1, finalized.
- **Schedule:** the approved schedule posts one video a day per platform through **2026-10-30**. Autopilot (05:15 and 17:15 Pi time) refills when fewer than 7 days remain, so from about **2026-10-23** it will look for new approved videos. Without a new approved batch the content is exhausted on 30 Oct.
- **Publisher attention at handoff:** uncertain jobs are waiting for remote confirmation (Facebook 10-12 16:15Z, Instagram 10-12 22:00Z, YouTube 10-12 20:00Z) and two YouTube slots expired (10-10, 10-11). Resolving them is the owner's call: report, never re-post.
- **Toolchain:**
  - The motion engine is ready: `node_modules`, `.venv`, `tsc` green; `check.mjs` reproduces `questionsHash 5ab19d44…`; the packager regression is byte-identical.
  - System ffmpeg on the Mac now works: Homebrew `homebrew-ffmpeg/ffmpeg` 9.0.2 with libass, trusted by the owner.
  - Scalargame `project.json` is contract v2; new batches are v2.
- **Carry forward from `2026-10-b01`** (not done yet):
  - candidate elimination: every clue removes at least one choice (enforce in `check.mjs` or the curation rules);
  - explanations say how the clues fit the answer first;
  - guess-the-year: keep all three choice markers on screen after the reveal (template fix + pilot);
  - Tectonic: no touching labels at full resolution;
  - Scalar progressive clues: the FOUND stamp covers a two-line clue 3 (template fix);
  - commit the pipeline before rendering (`generator.dirty` false).
- **Open owner items that touch this phase:**
  - Safari 26 / phone export check of Studio › Export;
  - whether job bundles travel through the Pi (plan §15, proposal B);
  - mix targets: not needed while only Scalargame posts.

## Phase scope (ship in small, green steps; each ends with tests green and, for `publisher/` changes, push + `sync-pi.sh`)

### 1. Next batch before the runway ends (priority)

- Read the Pi's Next batch page data (open feedback, performance) and write the brief for the next batch (`2026-10-b02` or `2026-11-b01`, as Next batch suggests). Use `/video-batch brief <batchId>` with the carry-forward list and the feedback.
- Size it so the runway reaches at least mid-November at one post a day per platform (about 3 weeks: around 21–24 main episodes plus spares), unless the owner chooses otherwise at Checkpoint 0.
- Fix the carry-forward template and check issues **before** rendering: each template change gets a pilot, stills at full resolution, and owner review (Checkpoint 2).
- Commit the pipeline first so the batch is not `dirty`.
- Checkpoints 0–3 as the skill says. Finalize only on the owner's approval. The owner uploads and approves on the Pi.
- Target date: the batch is finalized and on the Pi before **2026-10-23**, so the autopilot refill finds it.

### 2. Learn loop

- Check what the Pi's metrics collector really reads per platform today (views, likes, shares, saves, watch time, the quiz answer counts in comments/replies) and where it fails or is pending. Report the gaps; fix what is in code (stdlib, tests), with an owner OK for any new platform permission or API write.
- Make the retro and the next brief use the numbers: per game, format and platform at matched checkpoints (24 h / 72 h / 7 d), with small samples named as such. Update `/video-batch retro` if it needs a better template or a helper script (read-only over the feedback file).
- Write `library/_retros/2026-10-b01.md` "Performance" from real numbers once enough posts have aged; never invent metrics.

### 3. Make batches routine

- A runway warning the owner sees early: Home / Studio › Overview shows when approved, unscheduled content runs out and when the next batch must be uploaded (refill date − lead time). Check what exists first (`Runway`, content calendar) and only add what is missing.
- Reduce per-batch manual work in `/video-batch` where it is safe, for example:
  - generating spares automatically;
  - one command for the review sheets;
  - clearer `status` output with the date the batch is needed by.
- Keep every safety rule (frozen snapshots, independent fact-check, checkpoints, finalize only on approval).
- Optional, only with the owner's OK: a second cadence option (two posts a day on some platforms) in the schedule presets, with the content needs it implies.

### Then

- `build:static` + `check:static` after any UI change.
- A short security review of anything that changed on the Pi.
- Update the guide pages, the plan (a Phase 6 log, status) and memory.
- End with a short "Next" section in the plan (no new phase prompt unless the owner asks for one).

## Verification before Phase 6 counts as done

- The next batch finalized (owner-approved), uploaded by the owner, and visible in the Pi's library and schedule runway, or a clear blocker reported early.
- Every suite green:
  - the safety check reports 0 findings;
  - contract, publisher, tools, story (the $0 suite), UI typecheck/lint/Vitest/e2e on the fixture (`.claude/launch.json` `publisher-ui-dev`);
  - motion `tsc`;
  - `check.mjs` regression → `5ab19d44…`;
  - packager regression byte-identical;
  - both 2026-10 batches still validate.
- On the Pi: UI healthy, autopilot unaffected, every unit within its memory cap; local main = GitHub main = Pi.

## Rules

- Everything in `AGENTS.md` applies:
  - the repo is public: run the safety check before every push;
  - finalized batches and `library/_sources` are immutable;
  - the Pi is stdlib only and never renders;
  - code reaches the Pi only through `main` + `sync-pi.sh`;
  - never edit `/opt/scalar-social/repo`;
  - never force-push;
  - approving, finalizing and uploading stay with the owner;
  - never pause or change the live schedule unless asked;
  - never resolve or re-post uncertain jobs.
- **No Originals generation, and no paid generation of any kind, unless the owner asks for that run with a cost estimate.**
- No new dependencies without asking; no system package changes without the owner's OK; never change Homebrew trust settings.
- Pushing `main` is approved for `publisher/` and `contract/` changes. Push other commits of this phase once all checks pass.
- Be concise. Lead with what was done and what needs the owner's decision. Flag blockers immediately, above all anything that threatens the 2026-10-23 refill date.
