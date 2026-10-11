# Brief · <batchId>

<!-- Copy to library/_briefs/<batchId>.md. The /video-batch skill fills it from the pasted brief, the feedback file
     (library/_inbox/feedback-<batchId>.json) and the previous retro, then asks Samir to confirm it before writing
     questions. Briefs are never published, so they may name answers. -->

- **Batch:** <batchId> (`YYYY-MM-bNN`) · **Date:** YYYY-MM-DD · **Previous batch:** <batchId or none>
- **Experiment ID:** <e.g. baseline-2026-10, or a new one when the creative recipe changes on purpose>
- **Goal / hypothesis:** <one or two sentences: what this batch should learn or deliver>

## Scope

| Game | Format | Episodes | Approachable / moderate / challenging |
|---|---|---|---|
| scalar | progressive-clues | 3 | |
| scalar | candidate-elimination | 3 | |
| continuum | head-to-head | 3 | |
| continuum | missing-slot | 3 | |
| whenabouts | guess-the-year | 3 | |
| whenabouts | before-after | 3 | |
| tectonic | missing-country | 3 | |
| tectonic | neighbor-clues | 3 | |

<!-- Formats must be one of the eight in contract/BATCH_CONTRACT.md; a new format needs a contract change first.
     Delete rows that are not in this batch. Spares: say how many per format (2026-10 used one or two). -->

- **Spares:** <n per format>
- **Pilots first?** <yes: one pilot per game before the rest (like 2026-10-pilots) / no: render the whole batch>

## Creative

- **Styles:** <reuse scalar-notebook-1, continuum-poster-1, whenabouts-almanac-1, tectonic-ocean-1 / new recipe per game: describe>
- **Music beds:** <reuse current beds (studio/public/episodes/music/beds.json) / changes>
- **Timing:** <unchanged (studio/src/episodes/timing.ts) / changes; the thinking window stays ≥ 6 s>
- **Hooks, CTA, captions:** <unchanged / changes>
- **Variants:** <none / style variants of the same questionId (variantId)>

## Content rules for this batch

- **Snapshot:** <new snapshot of committed scalargame HEAD / reuse 2026-10-06-3921b9e>
- **Whenabouts freshness:** <strict (default) / waived, with reason (2026-10 waived it: decision B05)>
- **Avoid:** <subjects, countries, events, metrics or question styles to avoid; earlier questionIds are always excluded>
- **Prefer:** <subjects or question styles to lean into>

## Feedback addressed

<!-- One line per open feedback item used (episodeId · tags · what changes), plus items from the last retro's
     "Carry forward" list. Say which are deliberately not addressed and why. -->

- 

## Open questions for Samir

- 
