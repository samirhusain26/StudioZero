# Update the Pi

The Pi runs the code from GitHub `main`. When Claude has changed Pi code on the Mac and you have approved the commit and the push, update the Pi from here. Nothing changes until you confirm, and the Pi only ever moves forward to a commit that contains the one it runs.

1. Settings → Update → Check for updates. The Pi fetches from GitHub (in the background; the page shows progress).
2. Read what is new: the commits, and warnings such as "This update changes unit files" or "pi-package".
3. Press Update, review the full 40-character commit id in the confirmation dialog, then confirm.
4. The Pi copies the new version aside, runs its checks there, waits until no post is being sent, switches over and restarts itself. The page reloads by itself when the new version is running. If the UI cannot start on the new version within about 2 minutes, the Pi goes back to the old one by itself (see [Rollback](#rollback)).

The update is refused when the last check is more than 15 minutes old, when files on the Pi were changed by hand, when the Pi's copy and GitHub have diverged, when the branch or the GitHub address is wrong, or when it is already up to date. Each case has its own message; see [Failed update](#failed-update).

## First-time setup (git bootstrap)

Once only, before Update can work, the Pi's code must become a git checkout with a read-only deploy key. Until then Settings shows the install as a copy and Update stays off. Every Pi command on this page starts with logging in: `ssh scalar-pi`.

1. On the Mac, copy the repo's `publisher/` and `contract/` folders to a staging folder on the Pi:

```bash
cd ~/Personal/code_projects/StudioZero
COPYFILE_DISABLE=1 tar --no-xattrs -czf - --exclude node_modules --exclude dist publisher contract | ssh scalar-pi 'mkdir -p ~/.scalar-social-staging/git-bootstrap && tar -xzf - -C ~/.scalar-social-staging/git-bootstrap'
```

2. Log in (`ssh scalar-pi`), ideally start `tmux new -s bootstrap` first so a dropped connection cannot cut the script off halfway (tmux is optional: `sudo apt install tmux`; the script installs nothing), and run the bootstrap from that staged copy:

```bash
sudo bash ~/.scalar-social-staging/git-bootstrap/publisher/deploy/bootstrap-git.sh
```

3. The script prints a public key and waits. Open https://github.com/samirhusain26/StudioZero/settings/keys → Add deploy key, title `scalar-social-update@scout`, paste the key, leave **Allow write access unticked**, save, then press Enter in the script.
4. The script checks the key works, clones, and then proves the key is read-only: GitHub must refuse a test push with "marked as read only". If GitHub accepts it, the script stops and asks you to add the key again without write access; if the push fails for another reason (network, wrong repository name), it stops and asks you to re-run.
5. If the media tool packages (`pi-package*.json`) differ from the ones installed, the script says so and asks `Continue with the npm reinstall? [y/N]`. Answer `y` to reinstall them (a few minutes), or `N` to stop before any service changes and run it again later.
6. If anything fails after the services were changed, the script prints the exact commands to go back to the old copied install. Running it again is safe: a half-finished copy of the code is set aside and fetched again.
7. After the script finishes, the code runs from `/opt/scalar-social/repo` and future updates are Settings → Update. The script creates a separate system user, `scalar-social-update`, which alone can change the code; the publisher and this UI can only run it. The key and its SSH settings live in `/etc/scalar-social-update` (owned by root; only the update user can read the key).

## Failed update

The Update section shows the phase, the error and the last log lines. A failed update leaves the Pi on its old version (or puts it back there).

| Message (as the page shows it) | What to do |
|---|---|
| The last check is missing, failed or older than 15 minutes. | Check for updates again, then Update |
| origin changed after confirmation; check for updates again | Someone pushed again; check again and confirm the new commit |
| The Pi checkout has local changes. Nothing was changed. (or: the checkout has local changes; nothing was changed) | Files in `/opt/scalar-social/repo` were edited, or Python cache files (`__pycache__`, `.pyc`) were written there, for example by a `sudo python3` command without `-I -B`. See what with `ugit status --ignored` (below). Make code changes in the repo on the Mac instead, then ask Claude how to discard the Pi edit safely |
| The Pi checkout has commits that are not on GitHub main. Nothing was changed. | GitHub's `main` no longer contains the Pi's commit (history was rewritten). Ask Claude on the Mac for a recovery plan; never force anything on the Pi |
| The checkout is not on branch main. / The checkout does not point at the expected GitHub repository. | Ask Claude to check the bootstrap |
| runner.lock is missing or cannot be opened, so a post could start mid-switch; nothing was changed. … | The publisher's lock file is gone or has the wrong permissions. Re-run the [git bootstrap](#first-time-setup-git-bootstrap) (it recreates it), then update again |
| Publisher is running a post; try again later | The publisher was busy for the whole 10-minute wait; try again later |
| staged check failed (…): … | The new code failed its checks on the Pi and was never switched to. Tell Claude the error; fix on the Mac, push, update again |
| The UI did not come back on … within 120 s; rolled back to …. It restarts on the previous code. | The new code passed its checks but the UI could not start on it, so the Pi went back by itself. Tell Claude the error from `journalctl -u scalar-social-ui -n 50`; fix on the Mac, push, update again. See [Rollback](#rollback) |
| The update request is older than 15 minutes (or undated) and was ignored; nothing was changed. Check for updates again. | The Pi did not pick the request up in time (for example it was restarting). Check again, then Update |
| not enough time left before the update service time limit; nothing was changed | The checks took most of the hour. Try again; if it repeats, tell Claude |
| … (rolled back to …) | The switch itself failed (or the update service was stopped) and the Pi reset to its old commit. Tell Claude the message |
| The update service stopped before finishing. Nothing more will happen; check again. | The update service was killed (power loss, reboot). Check again; the next run cleans up |
| This Pi is not running from a git checkout. | Run the [git bootstrap](#first-time-setup-git-bootstrap) first |
| Already up to date. | Nothing to do |

Git on the Pi by hand always runs as the code's owner, `scalar-social-update`, reading only the root-owned settings. Log in with `ssh scalar-pi`, paste this line once per login, then use `ugit`:

```bash
ugit() { (cd / && sudo -u scalar-social-update env -i PATH=/usr/bin:/bin HOME=/etc/scalar-social-update GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_PAGER=cat GIT_SSH_COMMAND='ssh -F /etc/scalar-social-update/ssh_config' git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C /opt/scalar-social/repo "$@"); }
```

Seeing what changed on the Pi:

```bash
ugit status --ignored
```

## Rollback

- **During an update** rollback is automatic: if the checks fail nothing switches; if the switch itself fails the Pi resets to the commit it was on; and if the UI cannot start on the new code within about 2 minutes, the Pi resets to the previous commit and the UI comes back on it.
- **After a bad update that runs** the Pi only moves forward through Update, so the clean rollback is a new commit: ask Claude on the Mac to revert the change, approve the commit and push, then Settings → Update to that commit.
- If something is posting wrongly meanwhile, use Settings › Pause publishing first.
- Never force-push `main`: the Pi would report "diverged" and refuse to update.

**If the UI is down and did not come back by itself** (for example after a failed update, `systemctl status scalar-social-ui` shows it stopped or crash-looping), roll the code back by hand over SSH:

1. Log in: `ssh scalar-pi`
2. Define `ugit` (the line above), then find the previous commit in git's own record. Do not take it from the status page or `status.json`: those are for display, and the update request folder can be written by the Pi's services.

```bash
ugit reflog -n5 --format='%H %gs'
```

The newest line reads `merge <commit>: Fast-forward` (the update); the line below it is the commit the Pi ran before. Check that it really is an earlier point of the same history:

```bash
ugit merge-base --is-ancestor <previous full commit> HEAD && echo 'ancestor: safe to go back'
```

3. Reset to it and restart the UI:

```bash
ugit reset --hard <previous full commit>
sudo systemctl reset-failed scalar-social-ui.service
sudo systemctl restart scalar-social-ui.service
```

4. Reload this page. Settings → Update shows the Pi one or more commits behind GitHub; do not update again until the fix is on GitHub.

## Unit files changed

Service files (systemd units, including the credential drop-ins) and the media tool packages (`pi-package*.json`) need root, so the update itself never installs them. Instead, right after an update that changed them finishes, the Pi installs them by itself (`scalar-social-apply-units.path` runs `apply-units.sh --auto` as root). Settings → Update shows "Applying unit file changes automatically…", then the UI restarts once and the notice reads "applied automatically". Nothing to type.

If the automatic apply fails, Settings shows why, the last lines of the run, and the command to run once by hand after fixing the cause. You also need it once on a Pi that does not have `scalar-social-apply-units.path` yet (the screen then shows "Unit files changed" with the command):

```bash
sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh
```

Either way it lists service files on the Pi that are no longer in the repo, with the exact command to remove each; it never removes them itself.
