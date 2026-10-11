# Make a batch

Batches are made on the Mac by Claude Code with the `/video-batch` skill. You steer with the brief and approve at each checkpoint; Claude does the rest.

1. Open Terminal and start Claude in the marketing folder (Claude's memory is kept per folder, so always start here):

```bash
cd ~/Personal/code_projects/scalargame/marketing
claude
```

2. Paste the prompt from this Pi's Library › Make a batch ([Next batch](#next-batch)), or type it yourself:

```text
/video-batch brief 2026-11-b02
```

3. Put the feedback file from Make a batch in `library/_inbox/` first, so Claude can read it.
4. Answer Claude's questions and approve at each checkpoint.
5. When the batch is finalized, [upload it](#upload-a-batch).

Two more commands: `/video-batch status <batchId>` tells you where a batch is and what comes next; `/video-batch retro <batchId>` writes the retro.

## Brief

The brief says what this batch is: which games and formats, how many episodes, the difficulty mix, styles, music, things to avoid, experiments, and which feedback it addresses. It lives in `library/_briefs/<batchId>.md` (template: `library/_templates/BRIEF.md`). Claude drafts it from what you paste, your feedback file and the last retro, then shows it to you before writing any question.

Some rules never change, whatever the brief says: game facts come only from frozen snapshots, every fact is checked by an independent fact-checker, videos are rendered only through the pipeline, finalized batches are never edited, the batch must pass the contract validator, answers never appear before the reveal or in captions, and nothing is uploaded or posted from the Mac.

## Checkpoints

| Checkpoint | You see | You decide |
|---|---|---|
| 0 · Brief | The brief and any open questions | Scope, mix, styles, avoid list |
| 1 · Question pack | `library/<batchId>/review/question-pack.html` with answers, explanations, sources and the fact-check results | Which questions go ahead; how each fact-check concern is resolved |
| 2 · Pilots (only when the brief asks) | One finished video per game | Whether the look works before the rest is rendered |
| 3 · Final batch | `review/index.html` (every video, frames, captions), `review/checkpoint3.md`, `review/covers.png`, validator result | Approve the exact files, or ask for fixes |

Nothing moves past a checkpoint without your clear yes.

## Finalize

After you approve Checkpoint 3, Claude runs:

```bash
python3 contract/library_contract.py finalize library/<batchId>
```

It validates the batch again and writes `READY_FOR_UPLOAD`. From then on the folder is frozen: a correction becomes a new revision or a new batch, never an edit. `2026-10-pilots` and `2026-10-b01` are finalized.

## Retro

After finalizing, Claude writes `library/_retros/<batchId>.md` (template: `library/_templates/RETRO.md`): what shipped, what went well, problems with the episode they affect, fixes, and a "Carry forward" list for the next brief. Upload it here as the batch's retro note. Later you can ask for an update once posts have results: `/video-batch retro <batchId>`.

## Latest batches

| Batch | Episodes | Finalized | Notes |
|---|---|---|---|
| 2026-10-pilots | 4 (one per game) | 8 Oct 2026, 01:27 UTC | Retro: `library/_retros/2026-10-pilots.md` |
| 2026-10-b01 | 20 (rest of the first 24) | 8 Oct 2026, 02:11 UTC | Retro: `library/_retros/2026-10-b01.md` |

The next batch ID follows the pattern `YYYY-MM-bNN`; Make a batch suggests it.
