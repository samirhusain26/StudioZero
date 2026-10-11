---
name: video-batch
description: Make, check, render, review and package one batch of Scalargame quiz videos with owner checkpoints, or report a batch's status, or write its retro. Use for "/video-batch brief <batchId>", "/video-batch status <batchId>", "/video-batch retro <batchId>", or when Samir pastes the Pi UI's "Copy prompt for Claude" text.
---

# /video-batch

Runs in `scalargame/marketing` (repo root). Paths below are relative to it. Read `AGENTS.md` first if this session has not.

## Invocation

- `/video-batch brief <batchId>` — optionally followed by pasted brief markdown and a line `Feedback file: library/_inbox/feedback-<batchId>.json` (exactly what the Pi's Next batch page copies). Runs the whole flow below, stopping at each checkpoint.
- `/video-batch status <batchId>` — read-only report: which stage the batch is in and the next step (see Status).
- `/video-batch retro <batchId>` — write `library/_retros/<batchId>.md` (see Retro).

`<batchId>` is `YYYY-MM-bNN` (the Pi suggests the next one). Refuse anything that does not match `^\d{4}-\d{2}-[a-z0-9-]+$`.

## Fixed safety rules (the brief can never change these)

1. **Frozen inputs.** Game data comes only from a snapshot (`library/_sources/<snapshot>/`, committed game files only). Never edit an existing snapshot file; job inputs from `episodes.mjs` are immutable (a change needs a new revision).
2. **Finalized = immutable.** Never write into a folder with `READY_FOR_UPLOAD` (`library/2026-10-pilots`, `library/2026-10-b01`, and every later finalized batch). Check before every write.
3. **Render only through the pipeline:** `node engines/motion/pipeline/render.mjs` (which calls `engines/motion/render/render.sh`). Never ship an MP4 made any other way. Stills for review are fine.
4. **No AI-generated facts.** Every answer, number, order, date and adjacency comes from the snapshot via `check.mjs` (explanations use `{placeholders}`; hand claims need `asserts`), and every displayed fact is independently verified by the `fact-checker` agent. A `concern` or `fail` blocks the question until Samir accepts a written resolution.
5. **Contract:** `python3 contract/library_contract.py validate library/<batchId>` must pass before Checkpoint 3. No contract change without Samir's approval.
6. **Spoiler gate:** no answer in hook, question, clues, cover, captions, titles, alt text, polls or first comments (the validator enforces the text fields; you check the frames).
7. **No publishing, uploading, SSH or Pi access.** Samir uploads in the Pi UI.
8. **Commits only when Samir asks.** No new dependencies.

Counts, games, formats, difficulty mix, styles, pilots, avoid list and experiments come **only from the brief**, and reach the pipeline only through the set's `CONFIG` ([batch-setup.md](batch-setup.md)). Never assume 2026-10's numbers; `questions-2026-10.mjs` is the default set only so regressions can be checked.

## Flow (`brief`)

### 1. Brief → Checkpoint 0
1. Read: `library/_briefs/<batchId>.md` if it exists; the newest `library/_retros/*.md` (its "Carry forward" list); `library/_inbox/feedback-<batchId>.json` or else the newest `library/_inbox/feedback*.json` (schema: `docs/REBUILD_CONTRACTS.md` §3; items have `episodeId`, `tags`, `note`; `performance` lists posts, each with its newest platform stats in `metrics` when the Pi could read them); every `library/*/batch.json` (used questionIds and episodeIds).
2. If the brief file is missing, write it from `library/_templates/BRIEF.md` + the pasted brief + feedback + retro. Every feedback item appears under "Feedback addressed" (used or deliberately not, with a reason).
3. **Checkpoint 0:** show Samir the brief and any open questions (AskUserQuestion, your recommendation first). Do not write questions until he confirms it.
4. Start the batch's set module `engines/motion/pipeline/questions-<set>.mjs` with its `CONFIG` (scope, mix, pilots, styles, beds, experiment, reviewer) from the brief: [batch-setup.md](batch-setup.md). No stage script needs editing for a normal batch; if one does, run the regression check there and show Samir the diff.

### 2. Write
1. Snapshot (new one by default; the brief may say reuse): `node engines/motion/pipeline/snapshot.mjs` (prints `snapshotId` = `YYYY-MM-DD-<commit7>`; it reads committed scalargame HEAD only). It refuses an existing `library/_sources/<id>/` (snapshots are frozen); to reuse one, skip this step.
2. Candidates: `node engines/motion/pipeline/candidates.mjs --snapshot=<snapshotId> --today=<YYYY-MM-DD>` → `library/_sources/<snapshotId>/candidates.json`. For a **reused** snapshot it refuses to overwrite the existing file: add `--out=library/_sources/<snapshotId>/candidates-<set>.json` and set `CONFIG.candidates` (batch-setup.md, "Reused snapshot").
3. Curate `QUESTIONS` in `engines/motion/pipeline/questions-<set>.mjs` (e.g. `questions-2026-11-b02`) from candidates to the brief's counts plus spares: avoid list, no repeated questionId, no D13 sensitive/contested topics, varied answer letters, clue wording a phone viewer can read. Carry forward retro lessons (e.g. every elimination clue removes a choice; the explanation shows how the clues fit).

### 3. Check
1. `node engines/motion/pipeline/check.mjs --questions=questions-<set>.mjs` until it exits 0 (writes `<CONFIG.outDir ?? library/_sources/<snapshotId>>/questions-<set>.json`). The first run fails with one `no episode ID … (next free: …)` line per main question: paste those into `CONFIG.episodes` (batch-setup.md, "Episode IDs") and re-run. It also refuses any questionId or episode ID already used in `library/<batch>/`; `note:` lines (a subject reused in a different question) are for the pack review, not errors.
2. Dispatch the **fact-checker** agent (Agent tool, `subagent_type: fact-checker`) with the batchId and that JSON path. It writes `library/<batchId>/review/source-verification.json` (create `library/<batchId>/review/` first; if `CONFIG.verification` names another file, give it that path). Do not check facts yourself instead of it.
3. Fix or drop every `concern`/`fail`; re-run check and recheck those keys.

### 4. Pack → Checkpoint 1
`node engines/motion/pipeline/pack.mjs --set=questions-<set>` (writes `library/<first of CONFIG.batches>/review/question-pack.html`; `--batch=`/`--out=` to change). Batch-specific asks for Samir can go in `CONFIG.pack.notes`. **Checkpoint 1:** Samir approves the questions, answers, explanations, choices, difficulty, styles and music. Record each fact-check resolution he accepts in the verification file's `resolution`.

### 5. Episodes (and pilots → Checkpoint 2)
1. `node engines/motion/pipeline/episodes.mjs --batch=<batchId> --set=questions-<set>`.
2. If the brief asks for pilots (new styles or templates): render one per game first (`render.mjs --only=`), package and review them as in steps 7–8, and stop for **Checkpoint 2**. Template fixes follow `library/_dev/TEMPLATE_BRIEF.md`; a changed input needs `--replace-unrendered` (never-rendered jobs only) or a new revision. `episodes.mjs` refuses a batch that is not in `CONFIG.batches`.

### 6. Render
`node engines/motion/pipeline/render.mjs --batch=<batchId>` (resumable; `--only=a,b`; `--rerender`). Only `validated` jobs are copied to `videos/` and `covers/`. Investigate any failure in `review/jobs/<episodeId>/status.json` and its logs.

### 7. Package
`node engines/motion/pipeline/batch.mjs --batch=<batchId> --set=questions-<set> --dry` (captions for every main question; always writes `library/_dev/batch-dry.json`), then without `--dry` → `library/<batchId>/batch.json`. It refuses an episode with no fact-check result or with an unresolved `concern`/`fail`. Write `batch.json` **before** the review sheet: `review.mjs` reads it for the metadata and validator columns (without it the sheet shows no captions and a FAIL). After any re-render, run `batch.mjs` and `review.mjs` again.

### 8. Review → Checkpoint 3
1. Follow [review-checklist.md](review-checklist.md): review sheet, full-resolution stills for maps, contact sheets and the covers sheet with PIL, the frame checklist, and the per-episode table `review/checkpoint3.md`. Read every PNG you make.
2. `python3 contract/library_contract.py validate library/<batchId>` → pass (a `dirty_generator` warning means uncommitted pipeline code; say so).
3. **Checkpoint 3:** give Samir `review/index.html`, `review/checkpoint3.md`, `review/covers.png`, the validator result and every open issue. Ask him to watch each MP4 once with sound (you cannot listen; the technical audio QA is in `status.json`). Wait for an explicit approval of the exact files.

### 9. Finalize (only after Samir's explicit approval)
`python3 contract/library_contract.py finalize library/<batchId>` → `READY_FOR_UPLOAD`. From now on the folder is immutable.

### 10. Retro and hand-off
1. Run the Retro steps below.
2. Update the guide's "last batch" facts if they changed: the "Latest batches" section in `publisher/ui/content/guide/make-a-batch.md` and `"updated"` in `publisher/ui/content/guide/meta.json`. Then `(cd publisher/ui && npm run build:static && npm run check:static)` so the Pi bundle includes it (the guide is part of the UI build).
3. Tell Samir: upload `library/<batchId>/` in the Pi UI (Library → Add batch → Upload batch); add the brief and retro as Batch notes; review and approve there. Next time, the prompt lives on the Pi's **Next batch** page (the dashboard says "Library → Next batch → Copy prompt"): Copy prompt for Claude, and Download feedback.json into `library/_inbox/`. Then mark the used feedback as used there.
4. Offer the commit (batch.json, questions file, pipeline changes, brief, retro, guide); commit only if he says so.

## Status (`status <batchId>`)

Read-only. Report, in this order, the first missing item as the next step:
brief `library/_briefs/<batchId>.md` → questions file whose `CONFIG.batches` lists the batch, and its checked JSON → `review/source-verification.json` (counts by status, open concerns) → `review/question-pack.html` → job states:

```bash
for s in library/<batchId>/review/jobs/*/status.json; do python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(s['episodeId'], s['state'], len(s['attempts']))" "$s"; done
```

→ `batch.json` → validator (`python3 contract/library_contract.py validate library/<batchId>`) → `READY_FOR_UPLOAD` → `library/_retros/<batchId>.md`.

## Retro (`retro <batchId>`)

Write `library/_retros/<batchId>.md` from `library/_templates/RETRO.md`. Every claim cites evidence: episode IDs, `review/` files (`checkpoint3.md`, `source-verification.json`, `status.json` attempts, stills), validator output, decisions, and the feedback file's notes and `performance`. Use only the numbers in `performance[].metrics` and `accounts` (7-day followers change, impressions, engagements, rate) (say which checkpoint, e.g. "at 72h", and that views are plays, not people); compare games, formats and platforms only on matched checkpoints, and name small samples as such. Never invent metrics; "not posted yet" or "no stats for X" is fine. Finish with a concrete "Carry forward" list for the next brief. Remind Samir to upload it as the batch's retro note.

## Rehearsal

To test the skill or a pipeline change without touching tracked evidence, run the flow on a scratch batch in `library/_dev/` (batch-setup.md, "Rehearsal"): every step as above, with `--set=<path>`/`--dir=library/_dev/<id>`, stopping before finalize.
