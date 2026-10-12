# Glossary

| Term | Meaning |
|---|---|
| Batch | A set of finished videos made together, with one `batch.json`. ID `YYYY-MM-bNN`, e.g. `2026-10-b01` |
| Episode | One video. ID `<prefix>-<format>-<nnn>`, e.g. `scalar-clues-001` or `originals-recap-001`; never reused |
| Content ID (questionId) | What an episode is about, e.g. `scalar:MDG:clues` or `originals:movie-recap:the-film-1999`. The same content is never posted twice on one account; each project has its own prefixes, so projects never collide |
| Project | Why and for whom a video is made: Originals (the studio's own recaps and shorts) or Scalargame (quiz videos) |
| Engine / renderer | How it was made: Motion (quiz templates; rendered by the Mac's `render.sh` or in the browser) or Story (recaps and animated series on the laptop worker) |
| Credits and attribution | Every asset in a video is credited with its licence; licences that require it (CC BY, Wikipedia, TMDB) put their attribution text in every caption that posts |
| AI disclosure | What in a video is AI-made. The Pi sets the platform's own AI label where its API has one (Instagram, TikTok, X; YouTube for realistic content) and records "not supported" elsewhere |
| Content mix | Each project's target share of scheduled posts. Until you set targets, drafts use the game round-robin order |
| Revision | Version number of an episode. A correction is a higher revision with new files and needs new approval |
| Format | A project's kind of episode: Scalargame's eight quiz types (progressive-clues, candidate-elimination, head-to-head, missing-slot, guess-the-year, before-after, missing-country, neighbor-clues); Originals' movie-recap, story-recap and animated-short |
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
