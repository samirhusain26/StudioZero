# Health

Where to look when you want to know whether things are fine:

- **Home**: the loop with the one next step, anything that needs attention, and one row per platform with three separate marks: posting test passed, currently signed in, recurring publishing on. A passed test does not mean publishing is on; tap a platform for details.
- **Activity**: one timeline of every event (queued, sent, confirmed with link, uncertain, blocked, expired, cancelled, resolved by you), approvals, uploads, and the last run of the publisher, monitor, token renewals and approval service. Phone-friendly; refreshes every 30 seconds while open.
- **Activity › Posts**: every posting job with status, link and error; search, more filters and CSV or JSON export under ⋯.
- **Settings**: publishing control (Pause), Activation, Update, System (timers, monitor, budgets, storage, issues and jobs needing reconciliation), and Backup (downloads the posting history, the library index, approved manifests, batch metadata and config; no videos and no credentials).

The Pi also sends a heartbeat to an outside monitor every 15 minutes; if it stops, you get a "DOWN | Scalar Pi health" email.

## Recovery

| Problem | What to do |
|---|---|
| Something is posting wrongly | Settings › Pause publishing (also stops the autopilot). On the Pi, the manual equivalent is `sudo touch /var/lib/scalar-social/PAUSED` and `sudo systemctl stop scalar-social.timer`; the autopilot turns the timer back on only after the pause is removed |
| A job is "uncertain" | It may or may not have posted. Check the platform's profile, then record what happened with `resolve_job.py` on the Pi (below). Never post it again by hand |
| A platform shows "not signed in" or a token renewal failed | That platform cannot post until it is signed in again; Home and Activity show the blocker. Ask Claude on the Mac for that platform's renewal steps |
| Upload stopped | See [Failed upload](#failed-upload) |
| Schedule approval failed | The message says why; nothing changed. Fix and approve again |
| Update failed | See [Failed update](#failed-update) and [Rollback](#rollback) |
| The Pi rebooted | Services restart by themselves; partial uploads are cleaned up; interrupted posts are reconciled before anything is retried |
| The UI does not load | Check Tailscale is on, then on the Pi: `systemctl status scalar-social-ui.service`. Right after an update, see [Rollback](#rollback) |

Recording an uncertain job's outcome (job ID from Activity › Posts or Settings › System; the job detail shows the same commands with the right path):

```bash
sudo python3 -I -B /opt/scalar-social/repo/publisher/app/resolve_job.py <job> --confirmed --permalink <post URL> --evidence "<what you saw>"
sudo python3 -I -B /opt/scalar-social/repo/publisher/app/resolve_job.py <job> --not-published --evidence "<what you saw>"
```

`-I` makes root ignore Python settings and add-ons from the publisher's folder; `-B` keeps root from writing Python cache files into the checkout (an update would refuse them as local changes). Before the one-time [git bootstrap](#first-time-setup-git-bootstrap), the Pi still has the copied install: use `/opt/scalar-social/scripts/social/resolve_job.py` instead.

## Freeing space

Each video is at most 24 MB, and uploads are refused below 2 GB free. To free space, use Library → Free space → **Remove posted videos**. It only offers videos where every post using them has finished (confirmed, failed or expired), at least one was confirmed, and nothing approved still needs them. Covers, episode records, stats and history stay; the card shows "Posted; video removed to free space". A removed video is not offered to new schedules (for example a platform added later) until you upload the same file again, which restores it. The files also leave the public media site at the next schedule approval.

## Post and account stats

The Pi reads how each post did at 1 h, 24 h, 3 days, 7 days and 30 days after it went out, and logs each account once a day (followers, views, engagements, link clicks). It only reads; it never posts. The numbers show under each post in an episode's review screen and in Library › Make a batch → How the posts did.

At the top of How the posts did, the **Post stats** panel has the controls:

- **Hourly reads: On / Off**: whether the Pi reads by itself every hour (at :20). Off means it reads nothing on its own; publishing is not affected either way. If hourly reads were already running before this switch existed, they stay on.
- **Read stats now**: one read straight away, even with hourly reads off. It also refreshes the follower counts. To fill in older account days too, open **Also read past days** and enter up to 93 days (only where the platform keeps that history).
- While the Pi works, the panel says "Waiting for the Pi…", usually for under a minute. If it still waits after 5 minutes, or the panel says the Pi is not picking up read requests, the Pi is missing the read-request unit: run `sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh` once (Settings › Update says "Unit files changed" after the update that adds it). Hourly reads keep working meanwhile.

The status line shows when the last read finished, whether the hourly timer or you started it, and one word per platform:

| Word | Meaning |
|---|---|
| read | Numbers came in |
| not set up | No token or key for this platform on the Pi yet |
| access refused | The token lacks the stats permission or has expired. Ask Claude on the Mac for that platform's steps |
| can't be read | The platform refused to give these numbers |
| can't be read (posted through Buffer) | A post that went out through Buffer before the direct connection. Expected for the one early Instagram post; later posts read normally |
| read failed | The platform did not answer or the post is gone; a passing problem is tried again next hour |
| not readable by the Pi | The platform offers no stats the Pi can read |

Under the panel, one row per episode: **Views → Avg watch → Engaged → Answered → Follows that day**.

- **Views**: platform views (plays on Facebook). Views are not people.
- **Avg watch**: average seconds watched (Instagram and Facebook report it).
- **Engaged**: likes, comments, shares, saves and similar.
- **Answered**: A–D replies in the comments, one per person. 0 can also mean the replies could not be read.
- **Follows that day**: the account's new followers on the day the video was posted. This is the whole account's day, not followers that video brought in.

Open a row to see each platform. "—" means no number yet. Totals add only the platforms that have a number and say which ones they counted. X and TikTok come through Buffer: the Pi reads Buffer's numbers, which Buffer refreshes once a day, so they can lag by up to a day ("waiting for Buffer's daily numbers" until Buffer has read a new post). Buffer gives no replies, so Answered stays "—" for them.

You need the terminal on the Pi for two things only: storing the YouTube key (the panel shows the command with Copy, `sudo /opt/scalar-social/repo/publisher/deploy/enable-metrics.sh --youtube-key`, and says "already stored" once YouTube reads), and installing a new token after a platform's stats permission is added. Details and the CSV export are in `publisher/docs/MEASUREMENT.md`.
