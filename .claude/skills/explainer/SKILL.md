---
name: explainer
description: Make one weekly batch of StudioZero Explainers (one real patent per 45–75 s vertical video) with owner checkpoints: trend scout and slate, patent research, story, independent checks, then (as later phases land) voice, art direction, render, critique and package. Or report a batch's status, or write its retro. Use for "/explainer brief <batchId>", "/explainer status <batchId>", "/explainer retro <batchId>", or when Samir pastes the Pi UI's Explainers prompt from Studio › Make a batch.
---

# /explainer

Runs at the StudioZero repo root. Read `AGENTS.md` first if this session has not, then `projects/explainers/SYSTEM.md` (the system: team, flow, rules) and `projects/explainers/PLAN.md` (what is built; open items). Evidence and sources: `projects/explainers/RESEARCH.md`.

## Invocation

- `/explainer brief <batchId>`, optionally followed by the pasted brief (count, formats, subjects, scout on/off, notes). Runs the flow below, stopping at each checkpoint.
- `/explainer status <batchId>`: read-only report from `library/<batchId>/review/explainers.json`: stage, episodes, gates, next step.
- `/explainer retro <batchId>`: writes `library/_retros/<batchId>.md` (what worked by format, hook type and topic; scout weights to update in `tracks/patents.md`).

`<batchId>` is `YYYY-MM-eNN` (e = Explainers; one batch = one week = 7 episodes by default; `e00` is the pilot). Refuse anything that does not match `^\d{4}-\d{2}-e\d{2}$`. Episode ids are short slugs (`roomba-cliff`).

## Fixed rules (a brief can never change these)

1. **Owner gates.** C1 (pick the episodes), C2 (lock the scripts), C3 (pilot, when something is new), C4 (approve the batch) are Samir's. Record each approval in the state file with the date and his words; never mark a gate passed without them. Finalizing and uploading stay with Samir.
2. **Facts.** The story writer uses only the ledger. Every script line cites ledger ids or is marked `noClaim`. `check_episode.py` must pass. A fact-checker `fail` or `unsupported` blocks the line until it is fixed or Samir accepts a written resolution.
3. **Independence.** The fact-checker, standards editor and cold reader each run as their own subagent with a fresh context and only their inputs. The showrunner (this session) never reviews its own script in place of them. At most 2 review rounds, then ask Samir.
4. **Rights.** Images only from the sources in `SYSTEM.md` §6; never company press renders, marketing images or images found by search. Patent figures only from US patents without a copyright notice, and redrawn.
5. **Sources and terms.** Trend feeds only through `tools/scout_feeds.py` (no Google News RSS, Reddit, TikTok or Product Hunt). Never fetch Google Patents search URLs; individual `/patent/<number>/en` pages are fine.
6. **$0.** No paid API. The voice uses only `GEMINI_FREE_API_KEY` (a no-billing project); never another Gemini key.
7. **Finalized = immutable.** Never write into a folder with `READY_FOR_UPLOAD`; `library/_sources/**` is frozen.
8. **No publishing or Pi writes; commits only when Samir asks.**

## State

`library/<batchId>/review/explainers.json` (ignored by Git), written after every stage:

```json
{
  "batchId": "2026-10-e00",
  "stage": "brief | slate | research | story | checks | locked | voice | art | build | critique | package | done",
  "episodes": [{"id": "roomba-cliff", "format": "how-it-works", "patent": "US 6,883,201", "status": "picked | researched | drafted | checked | locked | dropped", "notes": ""}],
  "gates": {"c1": null, "c2": null, "c3": null, "c4": null},
  "log": [{"at": "<UTC>", "what": "<one line>"}]
}
```

A gate is `{"approvedAt": "<UTC>", "by": "owner", "words": "<what Samir said>"}`.

## Flow (`brief`)

### 0. Brief
Write `library/_briefs/<batchId>.md`: count (default 7), formats wanted, subjects given, scout on/off, notes, carry-forward from the newest `library/_retros/*` for Explainers. Create the state file.

### 1. Scout → slate → **C1**
1. `python3 projects/explainers/tools/scout_feeds.py --out library/<batchId>/review/scout.json` (skip only if the brief turns the scout off).
2. Run the **explainer-trend-scout** agent with the batchId, the count and the brief's subjects. Save its slate to `library/<batchId>/review/slate.md`.
3. **Checkpoint 1:** show Samir the slate table (AskUserQuestion with your recommended 7 first, or a short list). He picks the episodes and the order. Record the gate. Format rotation: no format twice in a row; at least 3 formats in a week.

### 2. Research (per episode; run in parallel)
Run **explainer-patent-researcher** per picked episode. Save each ledger to `library/<batchId>/review/jobs/<episodeId>/ledger.json` and run `python3 projects/explainers/tools/check_episode.py library/<batchId>/review/jobs/<episodeId>`; send errors back to the researcher once, then drop the episode for a spare from the slate if it still fails (tell Samir).

### 3. Story (per episode)
Run **explainer-story-writer**. Pick the stronger angle (or merge with care), save `script.json`, lint with `check_episode.py` until it passes with no errors; read every warning and fix or justify it in the state log.

### 4. Checks → **C2**
1. In parallel: **explainer-fact-checker** (the whole batch; save to `library/<batchId>/review/source-verification.json`), **explainer-standards** (save to `review/standards.json`), **explainer-cold-reader** per script (save to `review/jobs/<episodeId>/cold-read.md`).
2. Apply what you accept; write one line per note you reject and why (state log). Re-lint. Re-run the fact-checker on changed episodes (round 2 at most).
3. **Checkpoint 2:** for each episode show Samir the title, the script as spoken lines with banners, the fact-check and standards status, the cold reader's hook score and the product-link level. He locks, edits or drops. Set `script.status` to `locked` only for the scripts he locked; record the gate.

### 5–10. Voice, art direction, build, critique, package, learn
Not built yet (PLAN.md §5, Phases 2–6). Stop after C2 and report what the next phase needs.

## Status
Read the state file and report: stage, each episode's status, gates with dates, open fact-check or standards items, the next step. Read-only.
