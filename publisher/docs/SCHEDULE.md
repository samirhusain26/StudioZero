# Recommended posting schedule

Chosen 8 October 2026. The schedule generator still starts empty: **Schedule → Use recommended schedule** fills this
in with one tap, and every field stays editable before you generate the draft.

| Platform | Time (America/New_York) | Why |
|---|---|---|
| Threads | 09:00 | Midweek mornings perform best; matches the morning daily-puzzle habit |
| X | 09:30 | The morning puzzle and Wordle sharing crowd |
| Bluesky | 10:30 | Daytime, mostly US audience |
| Facebook Reels | 12:15 | Lunchtime scroll, older audience |
| YouTube Shorts | 16:00 | The 4–7 PM window is strongest |
| Instagram Reels | 18:00 | The 6–9 PM evening window is the most consistent for Reels |
| TikTok (Buffer, see [TIKTOK.md](TIKTOK.md)) | 19:00 | Evening peak |

- **One video per platform per day, every day, for 21 days.** The library is the limit, not the platforms: each video
  posts once per account, so 24 videos (ep01 and ep03 already used on most accounts) last about 20 days at one a day.
  Move Instagram and YouTube to two a day only once the next batch is approved.
- **The same video everywhere on a given day** (the generator's default round-robin does this), so platforms can be
  compared on identical content in the stats.
- **First comments and answer replies are on.** Answer replies only appear for episodes that have an
  `answerReply`; a reply 24 hours later gives people a reason to come back.
- **Stagger 0, minimum gap 2 h.** The times are already apart. Keep two posts on one account at least about 2 hours
  apart: an uncertain post waits an hour and holds later posts on that account, which expire after 120 minutes late.

## Runner constraints behind the times

- The publisher runs every 15 minutes (`scalar-social.timer`), so a time between ticks waits for the next one. Every
  time above is on a quarter hour, and staggers or delays under 15 minutes have no effect.
- Spreading platforms over the day keeps several video uploads out of one tick. A tick that runs past 15 minutes
  makes the next one fail on the runner lock.
- Avoid 04:30–04:50: the Threads (04:30) and Instagram (04:45) token renewals run then.
- The post stats timer runs at :20 past each hour, between publisher ticks.
- Clock changes are handled: times that do not exist at spring-forward are skipped with a warning, and repeated
  times at fall-back use the first occurrence (only 01:00–02:59 is affected).

## Sources

General industry studies, not this audience: check them against the post stats after two weeks and move times toward
what performs.

- [Metricool: best time to post 2026](https://metricool.com/best-time-to-post-social-networks/)
- [Buffer: best time to post 2026](https://buffer.com/resources/best-time-to-post-social-media/)
- [Later: best time to post 2026](https://later.com/blog/best-time-to-post-on-social-media/)
- [Emplifi: best times to post](https://emplifi.io/resources/blog/best-times-to-post-on-social-media/)
