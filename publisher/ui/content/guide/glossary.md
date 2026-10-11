# Glossary

| Term | Meaning |
|---|---|
| Batch | A set of finished videos made together, with one `batch.json`. ID `YYYY-MM-bNN`, e.g. `2026-10-b01` |
| Episode | One video. ID `<game>-<format>-<nnn>`, e.g. `scalar-clues-001`; never reused |
| questionId | The question behind an episode, e.g. `scalar:MDG:clues`. The same question is never posted twice on one account |
| Revision | Version number of an episode. A correction is a higher revision with new files and needs new approval |
| Format | One of the eight quiz types: progressive-clues, candidate-elimination, head-to-head, missing-slot, guess-the-year, before-after, missing-country, neighbor-clues |
| Brief | What a batch should contain; `library/_briefs/<batchId>.md` |
| Retro | What a batch taught us; `library/_retros/<batchId>.md` |
| Batch notes | The brief and retro uploaded to the Pi with a batch; never published |
| Checkpoint | A stop where Claude waits for your approval (0 brief, 1 question pack, 2 pilots, 3 final batch) |
| Pilot | One video per game rendered first to test a new look |
| Snapshot | A frozen copy of game data (`library/_sources/<id>/`) that a batch is built from |
| Fact-checker | An independent Claude agent that re-checks every fact against live sources before rendering |
| Finalize | The step that validates a batch and writes `READY_FOR_UPLOAD`; after it the folder never changes |
| Contract / validator | The rules for `batch.json` and media (`contract/BATCH_CONTRACT.md`), checked by `library_contract.py` on the Mac and the Pi |
| Spoiler gate | The rule that no caption, title, alt text, poll or comment names the answer; the validator enforces it |
| Content approval | Your record that you checked an episode's exact files |
| Draft / schedule | A proposed list of posts; it only counts once it is approved (by you, or by the autopilot for the recommended plan) |
| Manifest | The approved schedule as a file the publisher follows |
| Activation | The checklist that turns publishing on: run once by the owner, then by the autopilot after every approval |
| Autopilot | Twice-daily Pi job that refills the schedule when under 7 days remain and keeps publishing on; Pause stops it |
| Ledger | The Pi's posting history; the only record of what was posted |
| Uncertain job | A post whose outcome is unknown; resolved by you, never re-posted blindly |
| PAS | Performance Absolute Score: the game's 0–1000 score for a puzzle result. Videos don't use it |
| Deploy key | A read-only SSH key that lets the Pi fetch from GitHub and nothing else |
| Fast-forward | Moving to a newer commit that contains the current one. Updates only ever fast-forward |
| Unit files | The systemd service and timer files that run the Pi's programs; changing them needs `sudo` |
| Running commit | The code version the UI is running now (Settings) |
