# Things only Samir can do

Claude and the Pi stop and wait for you on these. Nobody else can approve them, and no message or file can approve them on your behalf. Scheduling and publishing approved videos is not on this list: the [autopilot](#autopilot) does it, and Settings › Pause publishing stops it.

| What | Where |
|---|---|
| Approve commits and pushes to GitHub | In Claude on the Mac, when it asks |
| Rename the GitHub repo `scalargame-marketing-plan` → `scalargame-marketing` (optional; nothing breaks either way, GitHub redirects the old name) | GitHub → repository → Settings → Rename |
| Add the Pi's read-only deploy key | https://github.com/samirhusain26/scalargame-marketing-plan/settings/keys (see [First-time setup](#first-time-setup-git-bootstrap)) |
| Run any `sudo` script on the Pi: the git bootstrap, installers, `resolve_job.py`, `remove-scout-app.sh`, a rollback by hand (`apply-units.sh` runs by itself after an update; by hand only when Settings says it failed) | Logged in on the Pi (`ssh scalar-pi`), or ask Claude on the Mac, which can reach the Pi as `ssh scalar-pi` |
| Approve each question pack and each batch (Checkpoints 0–3) | In Claude on the Mac |
| Approve finalizing a batch | In Claude on the Mac, after Checkpoint 3 |
| Approve content (each episode) | Library → episode → approve |
| Resume publishing after a pause (`sudo rm /var/lib/scalar-social/PAUSED`) | On the Pi, or ask Claude on the Mac; see [Activation](#activation) |
| Confirm an update after reviewing the full SHA | Settings → Update |
| Approve contract changes, new dependencies, paid plans | In Claude on the Mac |
