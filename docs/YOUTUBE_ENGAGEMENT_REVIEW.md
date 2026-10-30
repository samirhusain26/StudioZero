# YouTube publishing and engagement review — 14 October 2026

## Finding and evidence

The recurring YouTube publisher sends an unsupported Buffer input field, then mistakes the API's rejection for an uncertain upload. The unresolved job holds subsequent YouTube posts. Other platforms continue independently.

Read-only checks against the Pi ledger, Buffer and YouTube found:

- The configured YouTube channel matches `@StudioZeroflow`. Buffer reports it connected, unlocked and not queue-paused. The publisher is not paused.
- The latest public upload is the [country quiz Short](https://www.youtube.com/shorts/FyfAPpdg0vs), published 5 October at 11:46 p.m. Eastern (6 October UTC). YouTube reports 35 views, zero likes and zero comments. Older videos also exist; the channel is not completely empty.
- The 10 October attempt was previously verified absent; 11 October expired. The 12 October, 4 p.m. Eastern attempt remains `uncertain` with no Buffer post ID. The 13 and 14 October jobs were never dispatched because of that blocker. There are 21 ready YouTube jobs, including those two overdue jobs.
- A complete one-page Buffer listing contained 11 historical posts, none after the successful test. YouTube's public uploads listing likewise contained no newer video.
- The successful test payload has no `metadata.youtube.description`. All 24 recurring YouTube payloads include that field, duplicating the approved `caption` exactly.
- Buffer's live schema and [official input reference](https://developers.buffer.com/types/YoutubePostMetadataInput.html) contain eight YouTube metadata fields; `description` is not one of them. The approved description already travels in the request's top-level `text`.

A non-executing schema check used synthetic values and an unconditional `@skip(if:true)` on `createPost`. No post was created. With `description`, Buffer returned HTTP 200 and a variable-coercion error (no data or execution path, extension code `INTERNAL_SERVER_ERROR`). Without it, the same skipped operation returned an empty data object and no errors. This proves the invalid input and the HTTP-200 error-handling gap without a test publication.

## Local correction and live recovery

**Recovery completed, 14 October at 9:18 p.m. Eastern:** the owner authorized commit, push, deployment and resolution, then explicitly requested one immediate Short through Buffer. Commit `7e0f5ea` is on local main, GitHub main and the Pi; the Pi's staged checks and UI restart succeeded. The 12 October failed job was resolved as not published after a fresh complete Buffer/YouTube absence check.

The untouched, approved 14 October job was published once under the publisher lock using the deployed Buffer adapter, with current content eligibility, approval hash, scope, identity, media and duplicate checks. Its original slot and payload were preserved and the owner's immediate-publication instruction recorded in the ledger. [Three clues, one country. Which is it?](https://www.youtube.com/watch?v=rE3Nz9a0uK8) is independently verified **processed and public on the configured channel**, with title/description matching the approved text. Buffer reports sent/automatic; the ledger reports confirmed, one attempt and a saved receipt. No unresolved YouTube jobs remain. Configuration and approved manifest hashes are unchanged; the next normal slot is 15 October at 4 p.m. Eastern. The 4:30 follow-up was deleted at the owner's request.

The adapter correction removes only the redundant YouTube description from an outgoing copy, preserving the approved caption, title, metadata and stored payload. A disagreement between description and caption must fail closed. Existing approval hashes and finalized batches need no changes. Pre-execution GraphQL validation/coercion errors must be recognized under HTTP 200 as well as HTTP 400; execution failures, partial results and ambiguous responses must remain uncertain.

The original recovery plan, before the owner additionally requested immediate publication, was:

1. Commit only the reviewed fix and its tests, push main, and update the Pi to that exact commit through the supported updater. Preserve unrelated uncommitted work. The convenience `sync-pi.sh` refuses any uncommitted publisher files; do not include unrelated changes just to satisfy it.
2. Recheck Buffer and YouTube immediately before resolving the 12 October, 4 p.m. Eastern job. Use the existing locked `resolve_job.py --not-published --evidence ...` path to record the verified outcome. Never automatically retry a job merely because a listing does not show it.
3. Let the ordinary runner expire the two overdue slots and process the next approved future slot. Do not bulk-post missed videos, edit approved payloads, or re-approve the schedule.
4. Acceptance requires a saved Buffer receipt, a public YouTube permalink with processed/public status, and a confirmed ledger row for the next upload. Schema validation and local tests do not establish successful live publication.

The initial investigation was read-only. The subsequent authorized recovery changed the failed job's outcome and the single immediate upload's ledger state; it did not change the approved schedule or channel configuration.

Verification: the full publisher suite ran 521 tests successfully (one skipped). After a review cleanup and added error-priority coverage, all 12 adapter tests passed. The public-safety check reported zero findings. The Pi's staged publisher/contract checks and bundle check passed. Successful live publication was verified as described above.

## Engagement: a small audience, with some response

These are matched **24-hour checkpoints** for the four daily episodes published 10–13 October, not lifetime totals or unique people. Platform definitions differ; do not combine their views into a conversion denominator.

| Episode | Instagram views | Instagram average watch | TikTok views | TikTok average watch | TikTok likes / comments |
|---|---:|---:|---:|---:|---:|
| Country clues | 180 | 4.81 s | 93 | 2.53 s | 0 / 0 |
| Spain/Japan area comparison | 186 | 4.32 s | 306 | 4.83 s | 10 / 0 |
| Mario / Berlin Wall chronology | 134 | 4.20 s | 65 | 1.65 s | 0 / 0 |
| Missing country map | 170 | 6.80 s | 308 | 7.28 s | 8 / 2 |

- Instagram: 670 views, five likes and two shares. The four reported comments cannot be treated as audience responses: the publisher posts its own first comment, and the API's comments listing returned no items, a known limitation here.
- TikTok: 772 views, 18 likes and two comments. Comment text is unavailable through Buffer, so these are not verified puzzle answers.
- X and Facebook report zero views/impressions for these four posts. Threads reports 2, 1, 0 and 3 views. Bluesky provides no view counts and reports zero interactions on these four posts. Verify native analytics before interpreting zeros as a complete reach measurement.
- At the separate 72-hour checkpoint, the comparison video has 447 TikTok views, 19 likes and one comment. Instagram reports 231 views and **75 shares**. A direct reread confirmed the same Instagram API values; the outlier is not a local parsing discrepancy, but should be checked in native Insights before using it to choose a format.

This is four posts per platform over four days. It does not establish a winning game, posting time or causal explanation. Average watch time also does not reveal the exact second at which most viewers leave.

## Recommended next creative test

The strongest hypothesis is that the puzzle becomes fully playable too late for a new viewer. Current videos last 20–24 seconds; complete information arrives after 3.5–7.5 seconds, answers at 10–14 seconds and the play CTA at 17.5–21.5 seconds. See `engines/motion/src/projects/scalargame/timing.ts`. The finalized b02 brief explicitly keeps this timing and has no experimental variants.

Start with two local opening previews for phone review: the current head-to-head opening and a version with the specific question and readable A/B choices visible immediately. Keep the same 20-second length, 10-second reveal, music and caption. Preserve at least six seconds to think. Use a new draft; finalized batches remain immutable.

If the opening is approved, test six matched pairs of fresh questions, balancing difficulty and alternating baseline/test order at the normal cadence. Compare within each platform at 72 hours and again at seven days. Use average watch time as the primary measure for equal-length clips; inspect native retention/completion where available, then audience replies, shares and saves per 1,000 reported views. Report each post and variant medians. Twelve posts give directional evidence, with topic, day and distribution still confounding the comparison.

Focus creative analysis on Instagram and TikTok while repairing YouTube. Do not increase posting volume or buy traffic to compensate for an untested opening. A shorter 12–15-second format is a separate later proposal: it changes current duration rules and should not be slipped into this fix.

## Measurement and conversion follow-through

- On YouTube, inspect Stayed to watch, engaged views and average percentage viewed in Studio after posting works. The Pi's public Data API collection does not supply these retention measures. [YouTube metric definitions](https://support.google.com/youtube/answer/12220281?hl=en).
- For future packages, use a clear profile-link CTA where the caption URL is not clickable. YouTube Shorts descriptions/comments do not offer clickable external URLs; a stable profile link cannot attribute a visit to an exact episode. [YouTube link guidance](https://support.google.com/youtube/answer/13748639?hl=en).
- Measure attributed site visits, game starts and completions separately from social views. Actual current links use `utm_campaign=social_library_v1`; the stale `social_puzzles_v1` example in `publisher/docs/MEASUREMENT.md` was corrected locally. Retain both when analyzing historical campaigns instead of renaming historical data.
- Keep missing metrics distinct from zero, exclude known owner comments when describing audience responses, and flag anomalous platform values rather than silently correcting them.

Official guidance supports testing the opening without promising reach: [Instagram's watch-time explanation](https://about.fb.com/news/2023/04/instagram-reels-trending-audio-and-gifts-updates/) and [TikTok's recommendation factors](https://support.tiktok.com/en/using-tiktok/exploring-videos/how-tiktok-recommends-content).
