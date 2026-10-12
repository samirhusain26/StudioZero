# Brief · <batchId> (Originals)

<!-- Copy to library/_briefs/<batchId>.md. The /originals skill fills it from the pasted brief and the previous
     Originals retro, then asks Samir to confirm it before any paid run. Briefs are never published. -->

- **Batch:** <batchId> (`YYYY-MM-oNN`) · **Date:** YYYY-MM-DD · **Previous Originals batch:** <batchId or none>
- **Experiment ID:** <e.g. originals-baseline-2026-10>
- **Goal / hypothesis:** <one or two sentences: what this batch should learn or deliver>

## Episodes

| # | Title (year) or series brief | Format | Route | Models | Estimate (USD) |
|---|---|---|---|---|---|
| 1 | | movie-recap | recap | <llm>, <tts>, whisper | |

- **Total estimate:** $<n> · **Originals spend this month so far:** $<n> · **Monthly budget (`project.json`):** $<n> (0 = per-run approval only)
- **Estimates:** `python -m src.cli --headless --route … --estimate` on <date>; list prices from `engines/story/src/pricing.py` and `registry.json`.

## Credits and licences (per episode)

| # | Footage | Poster / data | Plot text | Music | Font | Generated |
|---|---|---|---|---|---|---|
| 1 | Pexels (creator per clip) | TMDB (notice) | Wikipedia CC BY-SA 4.0 | CC0 track (artist, page) | Fraunces Black (OFL) | script, voice |

## Disclosure and labels

| # | aiGenerated | aiKinds | realisticSynthetic | Instagram | TikTok | X | YouTube | Facebook | Threads | Bluesky |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | true | script, voice | false | label | label | label | no label | not supported | not supported | not supported |

## Platforms that will post

<!-- A recap's TMDB + Wikipedia attribution (about 260 characters) does not fit X or Bluesky with the caption:
     those platforms get no caption and skip the episode. Durations: Facebook Reels ≤ 90 s, Bluesky ≤ 60 s. -->

| # | Instagram | Facebook | Threads | TikTok | YouTube | X | Bluesky |
|---|---|---|---|---|---|---|---|
| 1 | yes | yes | yes | yes | yes | no (attribution length) | no (attribution length) |

## Mix and schedule

- **Mix:** <Originals' target share, once Samir sets `mix.target` in `projects/originals/project.json` (all projects need one). While every target is null the Pi drafts in game round-robin order and puts non-game episodes (Originals) after every approved Scalargame video, so approved Originals would wait behind the whole Scalargame backlog.>

## Feedback and carry forward

- 

## Open questions for Samir

- 
