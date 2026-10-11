# Measurement and attribution

The game already captures acquisition UTMs and emits normalized `acquisition_touch_captured`, `game_started` and `game_completed` events through its existing analytics path. This implementation reuses those URL parameters; it does not replace analytics or invent conversion data.

Clickable post links use `utm_source=<platform>`, `utm_medium=organic_social`, `utm_campaign=social_puzzles_v1`, `utm_content=<episode>_<format>`. Stable profile links use platform source and a profile-link content label. Instagram/TikTok and YouTube Shorts captions cannot supply reliable clickable episode links; traffic from a stable profile link cannot be attributed to a specific video or A/B format without additional evidence. Do not rotate bios daily and claim exact attribution.

Report separately:

- Confirmed publications: unique platform remote IDs and public permalinks in the ledger.
- Platform views/impressions/engagement: platform-reported metrics with source, window and retrieval time; views are not unique people or visitors.
- Site visits with social UTMs: available site analytics, subject to consent/ad blockers and missing/referrer attribution.
- Game starts and completions: existing events within an explicit attribution window. Do not divide all game events by social views and call the result conversion.
- Return play: dated repeat play for consented/available identifiers, with timezone and retention window specified; anonymous identity resets create measurement gaps.

Profile branding changes, differing puzzle difficulty and platforms confound format comparisons; use matched windows and disclose limitations.

## Post stats on the Pi (`publisher/app/metrics.py`)

`scalar-social-metrics.timer` runs hourly at :20 and, while hourly reads are on (below), reads every confirmed post (companions excluded) at **1 h, 24 h, 72 h, 7 days and 30 days** after it was published. It fetches only the newest due checkpoint, so a Pi that was off catches up with one late read, and stops reading a post after 45 days. It never publishes and never writes the ledger. Snapshots go to `/var/lib/scalar-social/metrics.sqlite3` (table `snapshots`: job, checkpoint, platform, remote id, fetch time, status, metrics JSON). Each run prints a one-line JSON summary to its journal (`journalctl -u scalar-social-metrics.service`): `checkedAt`, `trigger`, `outcome`, `reads`, `accounts`.

The newest read of each post appears in an episode's review screen (Posts and captions) and in Library › Make a batch → How the posts did, and travels in the feedback export to the retro.

### Controls (UI)

Library › Make a batch → How the posts did starts with the **Post stats** panel; Settings › System has a read-only "Post stats" block (hourly reads on/off, last run, next timer run, whether read requests are picked up, a waiting request). Owner wording: Guide › [Post and account stats](../ui/content/guide/health.md).

- **Hourly reads: On/Off** (`PUT /api/metrics/enabled {enabled}`) creates or removes the flag file. A timer run without the flag records `stats-off` and fetches nothing. Publishing is never affected.
- **Read stats now** (`POST /api/metrics/read {backfill?}`, 0–93) writes a request file; `scalar-social-metrics.path` starts the service for it. A manual read works with the flag off, reads due post checkpoints like a timer run, and always re-reads each account's point-in-time counts (otherwise every 6 h). `backfill` N also reads the last N account days. The panel polls every 4 s for up to 5 minutes ("Waiting for the Pi…"), then says it is still waiting.

The UI has no tokens and no network: it only writes the flag, the request and its own switch records. The timer and path unit run `metrics.py`, which does the reading.

State in `/var/lib/scalar-social/metrics/` (scalar-social, 0700):

| File | Written by | Content |
|---|---|---|
| `enabled` | UI switch (`apply-units.sh` migration, `enable-metrics.sh`) | flag: present = hourly reads on |
| `request.json` | UI | `{requestedAt, backfill}`; one at a time (409 while one waits) |
| `last-run.json` | `metrics.py`, after every run | `{startedAt, finishedAt, trigger: timer\|request, backfill, outcome: ok\|stats-off\|bad-request\|error, platforms: {<p>: {status, postsRead, accountsRead, reason}}}`; never tokens or response bodies |
| `history/request-<stamp>-<hex>.json` | `metrics.py` | consumed requests, moved here before any fetch so the path unit cannot loop; an invalid one is moved too and the run records `bad-request` |
| `history/switch-<stamp>-<hex>.json` | UI | `{at, enabled}`, only when the switch changes |

`history/` keeps the newest 200 files. Run platform statuses: `ok`, `not-configured`, `authorization`, `rejected`, `unsupported`, and `error` for every other stored status (`uncertain`, `rate_limit`, `gone`, …); the worst of a platform's reads wins. `reason: "buffer"` marks a `rejected` Meta post whose remote id is not a platform id (posted through Buffer before the direct connection; expected for one early Instagram post). A platform with no reads in a run keeps its previous status with zero counts. Activity (System) shows `system.metrics-on` "Post stats turned on", `system.metrics-off` "Post stats turned off" and `system.metrics-read-requested` "Post stats read requested" (detail "Also past N day(s).").

### Funnel (How the posts did)

`GET /api/next-batch` → `funnel` (`metrics.funnel`, read-only): one row per episode, newest 30 first, from confirmed non-companion posts. Per platform the episode's newest-published post counts.

| Column | Field | From |
|---|---|---|
| Views | `views` | `impressions` (views, or plays on Facebook) |
| Avg watch | `avgWatchSeconds` | Instagram `ig_reels_avg_watch_time`, Facebook `total_video_avg_time_watched` or `post_video_avg_time_watched` (ms → s) |
| Engaged | `engaged` | `engagements` |
| Answered | `answered` | sum of `answers.A–D`; 0 for an `ok` read with none (unreadable comments look the same) |
| Follows that day | `followsThatDay` | Instagram `follows_and_unfollows.FOLLOWER` (follows only, not net); Facebook `page_daily_follows_unique`; otherwise the follower-count change from the previous day (Threads, Bluesky, YouTube); else none. `followsSource`: `day-metric` or `follower-change` |

Follows are the account's, for the post's local publish day (config timezone); they are not attributed to the video. Each row also has `episode`, `publishedDates`, `platforms` (`status` plus the five values) and `counted` (which platforms each total includes). Totals skip missing values; the Avg watch total is view-weighted. "—" in the table means no value. X and TikTok come from Buffer (below); Answered stays empty for them because Buffer gives no reply text.

| Platform | Values | Needs |
|---|---|---|
| Instagram | views, reach, likes, comments, saved, shares, total_interactions, average and total watch time (ms), `answers.A–D` | `instagram_business_manage_insights` on the token (likely already granted; a failed read shows "needs the insights permission"); comments use the held `instagram_business_manage_comments` |
| Threads | views, likes, replies, reposts, quotes, shares, `answers.A–D` | `threads_manage_insights` (re-authorize); answer counts also need `threads_read_replies` or `threads_manage_replies` |
| Facebook Reels | whatever `video_insights` returns (plays, reach, average watch time, reactions), `answers.A–D` | `read_insights` on the Page token; comments use the held `pages_read_engagement` |
| Bluesky | likes, reposts, replies, quotes, `answers.A–D` (Bluesky publishes no view counts) | nothing: public AppView |
| YouTube Shorts | views, likes, comments, `answers.A–D` | a YouTube Data API key (free, 10,000 units a day; each read uses 2) |
| X, TikTok | Buffer GraphQL `post(input:{id}){metricsUpdatedAt metrics{type unit value}}` with the publisher's `BUFFER_API_KEY` (verified on Buffer Free, 9 October 2026) | TikTok: views, reactions→likes, comments, shares, reach, averageTimeWatched (s)→`avg_watch_seconds`, totalTimeWatched (min). X: impressions→`post_impressions` (counts as impressions), reposts, clicks, reactions, comments. Buffer reads each network once a day; until its `metricsUpdatedAt` is after the post's `sentAt` the read is stored as `pending` (retried hourly, shown as "waiting for Buffer's daily numbers"). No reply text, so no A–D answers. Unknown metric types are kept as `buffer.<type>` |

Every read also gets three derived values: `impressions` (views, or plays on Facebook), `engagements` (the platform's total interactions where it gives one, otherwise likes + comments + replies + shares + saves + reposts + quotes) and `engagement_rate` (engagements ÷ impressions). Bluesky has no impressions, so it has engagements but no rate.

`answers.<letter>` counts one A–D reply per commenter (their first), excluding our own account. A reply counts only if it is just the letter (punctuation or emoji after it allowed) or a letter followed by `)`; "A great puzzle" is not a vote. Stored statuses other than `ok`: `authorization` and `not_configured` (missing permission or key; not retried until the next checkpoint), `unsupported`, `gone` (post deleted), `rejected`, and the transient `uncertain` and `rate_limit` (retried next hour).

### Account log

The same timer keeps one row per account per local day (`accounts` table, config timezone), never pruned:

| Platform | Day totals (re-read every 6 h until 3 days after the day ends, then final) | Point-in-time, on today's row |
|---|---|---|
| Instagram | views, reach, accounts_engaged, total_interactions, likes, comments, shares, saves, replies, profile_links_taps, follows_and_unfollows (total, plus `breakdown=follow_type`: `.FOLLOWER` follows, `.NON_FOLLOWER` unfollows, `.UNKNOWN`) | followers, following, posts |
| Threads | views, likes, replies, reposts, quotes, clicks (link clicks) | followers |
| Facebook Page | page_media_view, page_total_media_view_unique, page_post_engagements, page_daily_follows_unique | followers, page likes |
| Bluesky | none (no history API) | followers, following, posts |
| YouTube | none without the YouTube Analytics API (own Google sign-in) | subscribers, channel views, videos |

Each day metric is its own request, so a metric a platform renames or retires is simply missing from the row. Meta reports days on its own day boundaries (Pacific time); each platform day is matched to the local day whose end is closest, never counted twice. Instagram notes up to 48 hours' delay and omits some metrics for accounts under 100 followers. Reach and other unique counts are not added across days.

**Time range.** The log starts when hourly reads are first on. A backfill of N days (N ≤ 93: Read stats now → Also read past days, or `enable-metrics.sh --backfill N`) reads the last N days once where the platform keeps history: Instagram about 90 days (30 days for reach), Threads back to 13 April 2024, Facebook Pages about two years (93 days per request). Bluesky and YouTube counts cannot be backfilled. Next batch → "Accounts, last 7 days" shows followers and their change, impressions, engagements, rate and link clicks, and the same rows go into the feedback export.

**CSV.** On the Pi: `sudo -u scalar-social python3 /opt/scalar-social/repo/publisher/app/metrics.py export --kind accounts > accounts.csv` (or `--kind posts`): one row per account day or post checkpoint, one column per metric.

### Owner setup (once, after the Pi runs from the git checkout)

1. Settings → Update, then `sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh` once (the UI reports "Unit files changed": the new `scalar-social-metrics.path`). It installs the stats units, creates empty 0600 placeholders for missing `INSTAGRAM_ACCESS_TOKEN`, `THREADS_ACCESS_TOKEN`, `FACEBOOK_PAGE_TOKEN` and `YOUTUBE_API_KEY` (an empty file reads as "not configured"; it never overwrites one, and an empty file never installs a publishing drop-in), creates the metrics folder and enables `scalar-social-metrics.timer` and `.path`. First run only: if the timer was enabled before, it creates `metrics/enabled` so hourly reads stay on, then records `/etc/scalar-social/metrics-switch-migrated` so a re-run never turns them back on. It never touches `scalar-social.timer`, the pause state or channels. A masked stats unit is left masked, with a message.
2. In the UI: Library › Make a batch → How the posts did → **Hourly reads: On**, then **Read stats now** for a first read (add past days there for history).
3. YouTube (terminal): `sudo /opt/scalar-social/repo/publisher/deploy/enable-metrics.sh --youtube-key` stores the key (input hidden). It needs step 1 first and also turns hourly reads on; the switch can turn them off again. `--backfill N` still works there too.
4. Threads and Facebook (terminal): add `threads_manage_insights` (plus `threads_read_replies` for answers) and `read_insights` to the apps and re-authorize; the existing token installers replace the tokens.

Check a run from the terminal if needed: `journalctl -u scalar-social-metrics.service -n 5`.

Site-side conversion (visits, game starts and completions by `utm_source` and `utm_content`) still comes from the game's analytics, not from the Pi.
