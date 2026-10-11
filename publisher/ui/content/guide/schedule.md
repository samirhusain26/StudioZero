# Schedule

A schedule decides which approved videos go to which platform and when. It is built as a draft you can check before anything is fixed.

1. Schedule → New draft shows the recommended plan: one post per platform per day for 21 days, at a fixed time per platform; blocked platforms are left out. Pick the start date (and the timezone if needed).
2. Press Generate draft. To change days, times, maximum per day, minimum gap, stagger or companion posts, open **Customize** first: every field is there, already filled with the plan. The same inputs and library always give the same draft, whichever way you filled them in.
3. Check every job: local time with timezone and UTC, platform, video, the exact caption, title, poll and comment, warnings, exclusions (for example a question already posted on that account) and "N of M requested slots fillable".
4. Edit or remove entries; each change makes a new draft.
5. [Approve the schedule](#approve-a-schedule).

After that the [autopilot](#autopilot) keeps the schedule filled by itself; you only generate a draft by hand to change the plan.

## Content calendar

Schedule › Content calendar shows how long the Pi has content for.

- **Scheduled through** is the last day with a post in the approved schedule. **Runs out** is the first day any platform has no post, and names that platform.
- The table lists, per platform: the last scheduled day (Through), posts still to go (Left), approved videos not yet scheduled there (Spare: one per question, skipping any already posted or queued on that account), and how far those would reach at one a day (Could reach). Spare videos post only after you generate and approve a new draft.
- In the month grid each dot is one post: blue scheduled, green published, red failed or missed. Days with a dashed outline could be filled by spare videos. Tap a day to see its posts and times.

Make the next batch before the run-out date: a batch takes a session on the Mac plus review and approval here. The autopilot can only schedule videos you have approved; when none are left it says so in Activity and posting stops at the run-out date.

## Approve a schedule

Press **Approve schedule** (it is enabled when nothing blocks the draft; nothing is typed). The approval service checks everything again, deploys the referenced media to the static host once, verifies every public link by hash and writes the approved manifest; then the [autopilot](#autopilot) runs the activation checklist and **publishing starts automatically** (not while paused). If the approval fails, the message says why (busy publisher, stale draft, media check, deployment budget…); nothing changed, so fix the cause and approve again.

Changing an approved schedule (cancel or edit a job that has not been sent) creates a new draft that must be approved again; the old approval stands until then.

## Autopilot

Since 2026-10-09 publishing runs by itself. Twice a day (05:15 and 17:15 on the Pi) the autopilot:

1. records the posting test of a Buffer channel whose identity is verified once it has a confirmed post (it never enables a channel by itself);
2. when fewer than 7 days are left in the approved schedule, generates the recommended draft (every verified platform, one post a day for 21 days from tomorrow, first comment and answer reply) and approves it, exactly as the Approve button does;
3. runs the activation checklist and, if everything except the timer item passes, enables exactly the approved channels and the publisher timer. Any other FAIL item holds it, with nothing changed, until the next run.

It does nothing while publishing is paused, while another approval is being processed, when the draft is blocked, or when no approved video is left (make the next batch). Its runs appear in Activity as "Autopilot (schedule refill)". Uploading, reviewing and finalizing batches stay with you.

## Activation

The owner's first activation (done on 2026-10-09) turned publishing on; after that the [autopilot](#autopilot) runs the same checklist after every approval and twice a day. Settings › Activation shows that checklist and the commands; it never runs anything itself. Once publishing is live the item "Publisher timer is currently disabled" shows FAIL; that is expected, and the autopilot ignores it.

For the record, the first activation was:

1. Fix every FAIL item on the checklist.
2. On the Pi, run the check command shown on the page, then the apply command shown on the page. After the [git bootstrap](#first-time-setup-git-bootstrap) they are:

```bash
sudo python3 -I -B /opt/scalar-social/repo/publisher/app/activate.py --check
sudo python3 -I -B /opt/scalar-social/repo/publisher/app/activate.py --apply --confirm-zero-spend
```

Before the bootstrap the code is in `/opt/scalar-social/scripts/social/` instead; always copy the command from Settings › Activation. `-I` makes root ignore Python settings and add-ons from the publisher's folder; `-B` keeps root from writing Python cache files into the checkout. `--confirm-zero-spend` is you confirming no paid plan, product or add-on is in use.

3. Check the next run appears (Settings › System → Timers; or `systemctl list-timers scalar-social.timer` on the Pi).

To stop posting at once: Settings › Pause publishing. It stops the publisher and the autopilot. To resume, remove the pause on the Pi (or ask Claude on the Mac to): publishing continues on the next 15-minute tick and the autopilot on its next run.

```bash
sudo rm /var/lib/scalar-social/PAUSED
```
