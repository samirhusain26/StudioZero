# Meta App Review: Facebook Page Reels

Draft submission for the publisher's Meta app ("Scalar Social Publisher"), so that reels it posts to the Scalargame Page are visible to the public. Status on 25 October 2026: the app is in Live mode, but every reel it publishes is shown only to people with a role on the app. Logged-out visitors get "This content isn't available right now", while a reel posted by hand to the same Page is visible. The post objects are identical (public, published, not hidden, normal timeline visibility); the only difference is `application: Scalar Social Publisher`. The leading explanation is that the permissions have no Advanced Access. Check App Review → Permissions and Features before submitting.

Fill in the placeholders in angle brackets. Never paste account IDs, tokens or the Pi's tailnet address into this file (public repository).

## Before submitting

1. **Business verification** (Business settings → Security Center). Advanced Access requires it. Use the legal or trading name that appears on the privacy policy.
2. **App settings → Basic**: privacy policy URL, user data deletion URL, app icon (1024 × 1024), category, contact e-mail. Already saved, per the owner (24 October).
3. **Request only what the publisher uses**. Requesting more is a common reason for rejection.

| Permission | What the publisher does with it | Code |
|---|---|---|
| `pages_manage_posts` | Uploads one approved video a day and publishes it as a Reel on the Scalargame Page (`POST /{page}/video_reels`, start → upload → finish). Never edits or deletes posts. | `publisher/app/facebook_adapter.py` |
| `pages_read_engagement` | Reads the reel back after publishing to confirm it (`status`, `permalink_url`, description, author) before marking it posted. Reads the reel's comments to count A–D answers to the puzzle; it stores one count per letter, never comment text or names. Reads the Page's follower count (every 6 hours). | `facebook_adapter.py` (`reconcile`), `publisher/app/metrics.py` |
| `pages_show_list` | Lets the owner choose the Scalargame Page when authorizing, so a Page access token can be issued. | token setup |
| `read_insights` | Reads each reel's `video_insights` (plays, average watch time, reactions) at 1 h, 24 h, 72 h, 7 d and 30 d, plus the Page's daily insights, for the owner's private performance dashboard. | `metrics.py` |

## Use-case text (one per permission)

Paste each block into that permission's "Tell us how you'll use this permission" box.

### pages_manage_posts

> Scalar Social Publisher is a private, single-operator publishing tool used only by the owner of the Scalargame Facebook Page to post its own videos. Scalargame is a set of free daily geography and history puzzle games (scalargame.com). Each day the tool publishes one short quiz video, which the Page owner has reviewed and approved in advance, as a Reel on the Scalargame Page using the Reels Publishing API (`/{page-id}/video_reels`: upload start, resumable upload, finish with `video_state=PUBLISHED`). The caption is the owner-approved text, unchanged.
>
> The tool publishes only to the one Page its owner administers. It has no other users, offers no login to the public and does not post to profiles, groups or other Pages. It never edits or deletes posts, and it posts at most one Reel per day, well under the 30-per-24-hours limit. Without this permission the Page cannot receive the scheduled videos. Reels published today are visible only to app role users, so the Page's audience cannot see them.

### pages_read_engagement

> After publishing a Reel, the tool reads it back (`status`, `permalink_url`, `description`, `from`, `created_time`) to confirm that the post exists on the right Page with the approved caption before it records the post as published. This prevents duplicate posts after a network error.
>
> Each video asks viewers to answer a multiple-choice puzzle by commenting A, B or C. Once in each reporting window (1 hour, 24 hours, 3 days, 7 days and 30 days after posting), the tool reads the Reel's comments and counts one letter answer per commenter. It excludes the Page's own comments, stores only the per-letter totals, and does not keep comment text, names or user IDs. It also reads the Page's follower count a few times a day. All of this is shown only to the Page owner in a private dashboard.

### pages_show_list

> When the Page owner authorizes the tool, this permission lists the Pages they manage so they can select the Scalargame Page and the tool can obtain that Page's access token. The tool uses the list only during authorization and keeps only the selected Page's ID and token, which are stored on the owner's own server in a file readable only by its administrator account and are never shared.

### read_insights

> The Page owner uses a private dashboard to see how each daily puzzle video performs, so future videos can be improved (for example, which puzzle formats people watch longest). The tool reads each Reel's `video_insights` (plays, average watch time, reactions) at fixed checkpoints after posting, and the Page's daily insights (media views, post engagements, daily follows). The numbers are stored only on the owner's server, shown only to the owner, and never sold or shared.

### Data handling answers

- **Who uses the app:** only the Page owner, an admin of the app. No other users; no public login.
- **Where data lives:** on the owner's own server (a Raspberry Pi at home), in local databases readable only by the service account. The Page token is stored as a root-only system credential.
- **What is stored:** reel IDs, permalinks, publish times, numeric insights and A–D answer totals. No comment text, names or user IDs.
- **Shared with third parties:** no. **Sold:** no. **Retention:** stats are read for 45 days after a post; the totals are kept as the owner's history.
- **Deletion:** the owner can delete the server's data at any time; requests go to the address on the privacy policy (<data deletion URL>).

## Screencast script

Meta wants one recording per permission, or one recording that clearly covers every permission, showing the permission being granted and then used. Record at 1080p, with the UI in English, captions on screen (no voice needed), and about 2–4 minutes in total.

**Privacy while recording:** hide the browser address bar while the Pi UI is on screen (it shows the private tailnet address), and keep tokens off screen: Graph API Explorer's token field, terminals, `/etc/scalar-social`. Blur anything that slips through before uploading.

**Recording the publish:** don't create an extra post for the recording. Record around the normal daily Facebook slot (16:15 UTC) so the scheduled reel is the one shown, or hold it with an existing approved video. Recording the Pi UI's activity screen just before and after the slot is enough.

| # | On screen | Caption to overlay | Covers |
|---|---|---|---|
| 1 | Title card: "Scalar Social Publisher: posts the Scalargame Page's own daily puzzle videos" | "Private tool, one user: the Page owner" | context |
| 2 | Log out of Facebook, then open the authorization flow for the app (Graph API Explorer → app "Scalar Social Publisher" → Get Page Access Token, or the token installer's login link) and log in as the Page owner | "The Page owner logs in with Facebook" | login |
| 3 | The consent dialog listing `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `read_insights`; select only the Scalargame Page; Continue | "Owner grants access to the Scalargame Page only" | `pages_show_list` + all grants |
| 4 | Pi UI → Schedule: today's approved post for Facebook, with its approved caption | "Videos are approved by the owner before scheduling" | context |
| 5 | Pi UI → activity at the slot: the Facebook post goes from scheduled to posted | "At the scheduled time the tool publishes the Reel" | `pages_manage_posts` |
| 6 | Facebook → Scalargame Page → Reels: the new reel with the same caption; open it | "The Reel is live on the Scalargame Page" | `pages_manage_posts` |
| 7 | Pi UI → episode → Posts and captions: Facebook shown as confirmed, with its permalink | "The tool reads the Reel back to confirm it before marking it posted" | `pages_read_engagement` |
| 8 | (Optional, from a second account) comment "B" on the reel; then show the Pi UI's Answered count for that episode | "Viewers answer A/B/C; the tool counts letters only and stores no comment text" | `pages_read_engagement` |
| 9 | Pi UI → Library › Make a batch → How the posts did: the Facebook row (views, average watch, follows that day) | "Private dashboard: performance of the Page's own videos" | `read_insights` |
| 10 | End card | "No other Pages, users or data. Never edits or deletes posts." | — |

**If the reviewer asks for an in-app Facebook Login:** the publisher has none; tokens are created once by the owner. Answer that it is a server-side tool for one Page owned by the developer. If they still require one, a minimal login page has to be built before resubmitting; record steps 2–3 there instead.

## After approval

1. Re-authorize so the Page token carries the approved access (token installer), then restart nothing else; the publisher reads the credential on each run.
2. The day after the next scheduled reel, open it logged out (built-in browser or a private window): it must load, not show "This content isn't available right now". Check one older reel too: Meta's docs say content that was restricted becomes visible once the restriction lifts.
3. Facebook numbers count in post analysis only from the first visible reel onward.
