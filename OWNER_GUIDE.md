# Owner guide (short)

The full guide is in the Pi UI behind the **?** in the header (the Pi's Tailscale Serve address, `https://<pi>.<tailnet>.ts.net`). Its source is `publisher/ui/content/guide/*.md` in this repo, bundled into the UI build, so the Pi and the repo never disagree. This page covers only the Mac side.

## Make the next batch

1. In the Pi UI, Library → **Make a batch** (Home's loop points there): press **Download feedback.json** and move `feedback-<batchId>.json` into `library/_inbox/` here (ignored by git), then edit the brief and press **Copy prompt for Claude**.
2. Start Claude Code in this folder. Claude's memory is keyed by folder path, so always start here:

   ```bash
   cd ~/Personal/code_projects/scalargame/marketing
   claude
   ```

3. Paste the prompt. It starts with `/video-batch brief <batchId>` (for example `/video-batch brief 2026-11-b02`); you can also type that yourself.
4. Approve at each checkpoint (0 brief, 1 question pack, 2 pilots if any, 3 final batch); tick them off in Make a batch step 3 if you like. Claude finalizes only after your explicit OK, then writes the retro.
5. Upload `library/<batchId>/` in the Pi UI: drop it on the Library page (or Make a batch step 4) → Upload batch. Add `library/_briefs/<batchId>.md` and `library/_retros/<batchId>.md` as the batch notes (Make a batch step 5).

Other forms: `/video-batch status <batchId>` (where a batch is, what's next) and `/video-batch retro <batchId>`.

## Publishing runs by itself

Since 2026-10-09 the Pi's autopilot schedules and publishes approved videos: twice a day it checks the approved schedule, and when fewer than 7 days are left it approves the next 21-day recommended draft and keeps publishing on. Nothing is typed and no activation command is needed. Your part is making, approving and uploading batches before the library runs out (Pi UI → Schedule › Content calendar shows the run-out date).

To stop everything: Pi UI → Settings › **Pause publishing**. To resume, on the Pi (or ask Claude here, which reaches it as `ssh scalar-pi`):

```bash
sudo rm /var/lib/scalar-social/PAUSED
```

Details: the guide's Autopilot section, and `docs/AUTOPILOT_PLAN.md`.

## Where things are

- Batches: `library/<batchId>/` (only `batch.json` is in git; videos, covers and `review/` stay on this Mac).
- Briefs `library/_briefs/`, retros `library/_retros/`, templates `library/_templates/`, inbox `library/_inbox/`.
- Skill: `.claude/skills/video-batch/`; fact-checker agent: `.claude/agents/fact-checker.md`.

## Before committing

Run the tests, and rebuild the Pi's UI bundle if anything under `publisher/ui/` changed (the guide text included):

```bash
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
(cd publisher/ui && npm run typecheck && npm run lint && npm test && npm run build:static && npm run check:static)
(cd engines/motion && ./node_modules/.bin/tsc --noEmit)
```

Then commit and push (Claude does this only when you ask), and update the Pi: Pi UI → Settings › Update → review the full SHA and confirm.
