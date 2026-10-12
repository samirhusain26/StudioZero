# Pi self-update from GitHub

Status: built and tested on the Mac 8 October 2026 (Phase 3 of [REBUILD_PLAN.md](../../docs/REBUILD_PLAN.md)); hardened the same day after two security reviews (L15: a dedicated `scalar-social-update` user owns the checkout and runs the update unit; root-owned git/ssh config; `python3 -I` for root; automatic rollback of a UI that cannot start). Not yet installed on the Pi: the owner runs `bootstrap-git.sh` once (below). Interface: [REBUILD_CONTRACTS.md §1](../../docs/REBUILD_CONTRACTS.md). Publishing stays paused throughout; nothing here enables channels or the publishing timer.

## What it does

The Pi runs from a git checkout of this repo at `/opt/scalar-social/repo` (partial clone, sparse to `publisher/` and `contract/`, branch `main`). In the UI, **Settings > Update** shows the running commit, checks GitHub, lists the incoming commits and changed areas, and applies an update after you review the full SHA in a confirmation dialog. The UI sends the existing exact `UPDATE TO <full sha>` value to the backend. A failed update changes nothing. Unit-file and `pi-package*.json` changes are never applied automatically: the UI shows the one owner command for them.

## Why a separate update unit and user

The UI service has `IPAddressDeny=any` and a read-only `/opt`, so it cannot fetch or write code. That stays true. The update runs as its own system user, `scalar-social-update` (no login, home `/nonexistent`), which alone owns and writes the checkout. A separate *unit* is not enough: two processes of the same user can reach into each other (`/proc/<pid>/cwd` and `/proc/<pid>/root` only need the same UID), so a scalar-social process could have written into the checkout through an update unit running as scalar-social.

| Piece | Runs as | Network | Writes |
|---|---|---|---|
| `scalar-social-ui.service` (`ui_server.py`, `Type=notify`) | scalar-social | none | `/var/lib/scalar-social-update/inbox/request.json` and `inbox/ui.json` (its restart reports); never `status.json` or the checkout |
| `scalar-social-update.path` | systemd | none | starts the service when `inbox/request.json` exists |
| `scalar-social-update.service` (`updater.py run-request`) | scalar-social-update, oneshot, `MemoryMax=256M`, `TimeoutStartSec=60min`, `HOME=/etc/scalar-social-update`, `UMask=0022` | yes (GitHub over SSH) | `/opt/scalar-social/repo` (staging worktrees in its `.git/scalar-update-stage/`), `/var/lib/scalar-social-update/` |

| Path | Owner, mode | Who writes, who reads |
|---|---|---|
| `/opt/scalar-social/repo` | scalar-social-update, 0755 / files 0644 | update user writes; everyone reads (the services run and serve it) |
| `/var/lib/scalar-social-update/` | scalar-social-update, 0755 | update user writes `status.json`, `units-applied.json` (0644); the UI reads them |
| `/var/lib/scalar-social-update/inbox/` | scalar-social-update:scalar-social, 1730 | the UI (group) creates and replaces its own `request.json` / `ui.json` (0644) but cannot list, read or delete the update user's files; the update user (owner) consumes requests |
| `/var/lib/scalar-social/runner.lock` | scalar-social, 0644 (folder 0711: `StateDirectoryMode=0711` in `scalar-social.service`, so systemd keeps `o+x`) | the publisher locks it; the update user flocks it read-only |
| `/etc/scalar-social-update/` | root:scalar-social-update, 0750 | root only; the update user reads `deploy_key` (0640) and the configs; scalar-social cannot enter |

The service's first step renames `request.json` to `request.taken.json` (the update user owns the inbox), so the path unit cannot loop; the taken file is deleted when the run ends. A request queued while a run is finishing (the path unit cannot start an already active service) is handled by the same run. If the state folder or inbox is not a real directory (only root or the update user could cause that) the service refuses without touching the request; the path unit's `TriggerLimitBurst=20` per 60 s then stops it instead of looping (recover: fix the folders, `sudo systemctl reset-failed scalar-social-update.path && sudo systemctl restart scalar-social-update.path`).

## Sequence

Check (`POST /api/system/update/check`): the UI queues `{action: "check"}` (202). The unit fetches `origin main` (`pack.threads=1`, small window/delta caches, no tags), then records in `status.check`: `head`, `origin` (full SHAs), `behind`/`ahead` (`rev-list --count`), `diverged` (`ahead > 0` or HEAD not an ancestor), `dirty` (`status --porcelain --ignored`: tracked changes, untracked files, and ignored bytecode (`__pycache__/`, `*.py[co]`) under `publisher/` or `contract/`, which Python would execute; other ignored files do not count), `branchOk` (`symbolic-ref` = `main`), `originOk` (`remote get-url` is exactly `git@github.com-scalar:samirhusain26/<name>(.git)` for `StudioZero`, the public repository, or the old names `scalargame-marketing-plan` (the private repository it replaced, now archived) and `scalargame-marketing`; see [Moving the checkout to another GitHub repository](#moving-the-checkout-to-another-github-repository)), up to 30 incoming commits, and the changed files under `publisher/` and `contract/` with flags for units (`publisher/deploy/*.service|path|timer|conf`), `pi-package*.json`, `contract/` and the UI (`publisher/ui/`, `publisher/app/static/`).

Apply (`POST /api/system/update/start {confirm: "UPDATE TO <sha>"}`): the server re-validates against the last check (≤ 15 min old, fetch succeeded, HEAD unchanged since, clean, not diverged, right branch and origin, behind > 0, sha = `check.origin`) and queues `{action: "apply", sha}` (202). The unit then:

0. A request whose `requestedAt` is more than 15 minutes old (or missing) is ignored with a `failed` status ("The update request is older than 15 minutes …"); nothing is fetched.
1. **staging**: removes a `.git/index.lock` older than 40 minutes (left by a killed run; the unit is single-instance) and stage leftovers; fetches; refuses unless `origin/main` still equals the confirmed sha ("origin changed after confirmation"), and re-checks branch, origin, clean and fast-forward. `git worktree add --detach <repo>/.git/scalar-update-stage/stage-<requestId> <sha>` (sparse like the checkout; inside `.git`, so only the update user can write it) and the staged checks, each in a subprocess with only `PATH`, `LANG`, `TMPDIR`, `HOME=/etc/scalar-social-update`, `PYTHONDONTWRITEBYTECODE=1`, and `python3 -I` (isolated) plus `-B`:
   - `python3 -I -m compileall -q publisher/app contract`
   - import every `publisher/app/*.py` with the stage (and its `contract/`) on `sys.path`
   - the contract tests and a quick publisher subset (`updater.QUICK_TESTS`: runner, operations, activation, credentials, ui_views/health/activity/schedule/approval/library/feedback and `test_updater` itself, which runs real git). None of them needs `engines/motion/` or `library/`; the selfupdate demo runs them in a sparse (`publisher/` + `contract/`) checkout.
   - `publisher/app/static` matches its `MANIFEST.json` exactly (no symlinks)
2. **waiting**: opens `/var/lib/scalar-social/runner.lock` (the publisher's own flock; 0644) read-only with `O_NOFOLLOW|O_NONBLOCK` and a regular-file check (the update user cannot write that folder; bootstrap creates the file; if it is missing or unopenable the update fails with "runner.lock is missing …" and nothing switches) and takes it, retrying for up to 600 s, and holds it through the switch. Timeout: "Publisher is running a post; try again later". The switch never starts with less than 5 minutes left before the unit's 60-minute limit ("not enough time left …").
3. **switching**: re-checks HEAD, `git merge --ff-only <sha>`, verifies HEAD = sha and a clean tree. Any failure, including SIGTERM from systemd (the handler raises once, then ignores further SIGTERMs so cleanup finishes): remove our own `index.lock` if the killed merge left one, `git reset --hard <old>`, and the error says "rolled back to …".
4. **switched**: the stage worktree is removed and pruned in a `finally` on every path. `status.check` is refreshed (behind 0).
5. **restarting**: the UI's watcher thread sees `switched` with on-disk HEAD ≠ the commit it loaded (full SHAs; HEAD is read from `.git/HEAD` and the ref files, no git process), writes `inbox/ui.json` `{requestId, phase: "restarting"}` and exits 86. `Restart=on-failure` starts it again on the new code. The UI never writes `status.json`; `updater.current_status()` overlays its report, so the API shows `restarting`.
6. **complete / failed**: `ui_server.py` reads the running commit at import, before the other app modules load. Once the HTTP socket is listening, `reconcile()` writes `ui.json` `{phase: "serving", running}` and the UI sends systemd `READY=1` (`Type=notify`, `TimeoutStartSec=90`). The API shows `complete` when it runs `toCommit`, otherwise `failed`.
7. **verify (automatic rollback, S4)**: the update unit stays up after the switch. If the old UI does not report `restarting` within 30 s (UI not running), it leaves `switched` (closed when the UI next starts and reports `serving`). If it does, the unit waits up to 120 s for `serving` and writes `complete`. If that never comes (the new code crashes at start, cannot bind or never becomes ready), it resets the checkout to `fromCommit` (no fetch; SIGTERM ignored during the reset), writes `failed` with "The UI did not come back on … within 120 s; rolled back to …", and systemd's next restart of the UI runs the previous code. `scalar-social-ui.service` allows 30 starts in 5 minutes (`StartLimitBurst`/`StartLimitIntervalSec`), enough to outlast that window, then stops instead of looping forever. A UI that came up late on the new commit after the rollback sees `failed` with `toCommit` = its own commit and HEAD = `fromCommit`, and restarts itself (exit 86) on the old code.

Phases: `idle, checking, checked, staging, waiting, switching, switched, restarting, complete, failed`. A run that sits in a busy phase for 40 minutes (service killed) no longer blocks new requests and is shown as failed.

## Files

| Path | What |
|---|---|
| `publisher/app/updater.py` | CLI (`run-request`, `info`) and the functions `ui_server.py` uses |
| `/var/lib/scalar-social-update/inbox/request.json` → `request.taken.json` | queued request (single flight), written by the UI |
| `/var/lib/scalar-social-update/inbox/ui.json` | the UI's restart reports (`restarting`, `serving`) for the current request |
| `/var/lib/scalar-social-update/status.json` | `UpdateStatus`, written only by the update user, atomic write + rename, last 40 log lines |
| `/opt/scalar-social/repo/.git/scalar-update-stage/stage-*` | staging worktrees, always removed |
| `/var/lib/scalar-social-update/units-applied.json` | `{commit, appliedAt}` written (as the update user) by `apply-units.sh`; drives `unitsChanged` / `piPackageChanged` |
| `/etc/scalar-social-update/` (root:scalar-social-update 0750) | `deploy_key` (root:scalar-social-update 0640), `deploy_key.pub`, `ssh_config` (`Host github.com-scalar`) and `known_hosts` (GitHub's published keys), both root:root 0644. The update unit's `HOME`. |
| `publisher/deploy/scalar-social-update.{path,service}` | the update unit |
| `publisher/deploy/bootstrap-git.sh`, `apply-units.sh` | owner scripts (sudo) |
| `publisher/deploy/migrate-origin.sh` | one-time move of the checkout to the StudioZero repository (sudo) |
| `publisher/tests/test_updater.py`, `selfupdate_demo.py` | tests against real git; Mac end-to-end demo |

## Security

- **Users**: the checkout belongs to `scalar-social-update`, which runs nothing but the update unit. scalar-social (UI, publisher, approval, monitor) can read and run the checkout but cannot write it, cannot read the deploy key, and cannot ptrace, signal or enter (`/proc/<pid>/cwd`) the update process, because it is another UID. The update user is in no scalar-social group and can write only its own state folder and the checkout.
- **Who can start an update**: the session-gated API (mutations need `X-Scalar-Request: 1` and the allowed `Origin`; an apply needs the exact `UPDATE TO <full sha>` value, re-checked by the UI server against the last check). The UI shows and pins the full SHA for review, then sends that value automatically. Any process running as scalar-social (the UI, the publisher, the approval unit) can write `inbox/request.json` itself, including an apply. The update unit then still fetches and fast-forwards only to the commit that is the tip of GitHub `main` at that moment, and only after the staged checks pass. The reviewed SHA guards against UI mistakes; it does not stop code that already runs as scalar-social from applying whatever is on GitHub `main`. Possible future hardening, not done: signed commits, checked by the update unit (`git verify-commit` against an owner key pinned in `/etc/scalar-social-update/allowed_signers`) before staging.
- **What it can fetch**: a read-only deploy key (bootstrap proves it: a `git push --dry-run` must be refused with GitHub's "marked as read only" message; any other failure stops the bootstrap), used only for `github.com-scalar`, with GitHub's published host keys pinned (`StrictHostKeyChecking yes`, `UpdateHostKeys no`, `GlobalKnownHostsFile /dev/null`, `IdentityAgent none`, `BatchMode yes`). Fingerprints are listed in `bootstrap-git.sh`.
- **What git and ssh read**: nothing a scalar-social process can write. Every git call (`updater.git()`, and the git in `bootstrap-git.sh`/`apply-units.sh`) runs with `HOME=/etc/scalar-social-update`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_ATTR_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, `-c core.hooksPath=/dev/null -c core.fsmonitor=false -c protocol.allow=never -c protocol.ssh.allow=always -c protocol.file.allow=never` (`user` only when the Mac tests or demo list a file:// origin in `SCALAR_UPDATE_ORIGINS`, never set on the Pi), and `GIT_SSH_COMMAND="ssh -F /etc/scalar-social-update/ssh_config"`; with `-F`, ssh reads neither `~/.ssh/config` nor `/etc/ssh/ssh_config`, and every key/known_hosts path in that file is root-owned. `test_updater.HardeningTests` plants `core.fsmonitor`, `core.hooksPath`, `core.sshCommand`, `url.insteadOf` and a `ProxyCommand` in scalar-social's home, shows a plain git runs them, and shows check and apply do not. Files the update user reads from scalar-social (`inbox/request.json`, `inbox/ui.json`, `runner.lock`) are opened with `O_NOFOLLOW|O_NONBLOCK`, must be regular files and are size-capped; a symlinked inbox or state folder is refused; files it writes use `O_EXCL|O_NOFOLLOW` temp files and an explicit mode.
- **The UI's own git**: the UI reads HEAD from the files (no git) and runs git only for `units-applied..HEAD` diffs, offline (`GIT_NO_LAZY_FETCH`, `GIT_OPTIONAL_LOCKS=0`), with `-c safe.directory=/opt/scalar-social/repo` (git ≥ 2.38 honours it on the command line; the Pi has 2.47) because the checkout belongs to another user.
- **What it can change**: fast-forward only to GitHub `main`'s tip named in the request (no merges, rebases, `git pull` or force), after the staged checks pass, never mid-post (runner lock), with `reset --hard` back to the old commit on failure or when the new UI never serves. Unit files, credentials, `/etc/scalar-social`, `/etc/scalar-social-update`, `/var/lib/scalar-social`, `node_modules` and the pause state are outside its write paths.
- **Trust boundary (read this)**: root executes code from this checkout: `approval_bind.py` (the `+` ExecStartPost of `scalar-social-approve.service`), the Threads/Instagram token refresh services, and the `sudo python3 -I -B …` commands the owner runs (`activate.py`, `resolve_job.py`). That is safe only because of these facts. (1) Only `scalar-social-update` can write the checkout (ownership, plus `ProtectSystem=strict` without `/opt` in every other unit). (2) That user only fast-forwards to GitHub `main`'s tip after the staged checks; whoever can push to `main` decides what root runs, and (see above) any scalar-social process can ask for that tip to be applied. (3) Its deploy key is read-only and unreadable by scalar-social, so a compromised Pi cannot change GitHub. (4) Its HOME, git config and ssh config are root-owned. (5) Root runs Python with `-I -B`: systemd sets `HOME=/var/lib/scalar-social` from `User=` even for `+` steps, so without `-I` root would load a user site (`.pth`, `usercustomize`) a scalar-social process could plant there; the scripts add their own folder to `sys.path` because `-I` leaves it out. Root never writes bytecode there (`-B`, `PYTHONDONTWRITEBYTECODE=1`), and any `__pycache__`/`.pyc` in the checkout makes it dirty. Review what you push to `main`. Possible future hardening, not done: signed commits (above), and running root steps from a root-owned copy of the checked commit.
- **Logs**: `status.log` holds phase lines and short git/test output tails; the environment is never passed on or logged, URL userinfo is redacted.
- **Memory**: one git thread, small pack caches, `MemoryMax=256M`; the quick test subset runs in about 1 s on the Mac.

## Moving the checkout to another GitHub repository

The code moved (2026-10-11) from the private `scalargame-marketing-plan` to the public `StudioZero`, whose history is unrelated (old StudioZero commits, then one import commit of this tree). The updater cannot follow that: its check marks HEAD `diverged` (HEAD is not an ancestor of the new `main`) and the switch is `--ff-only`, so a re-pointed `origin` would refuse every update. `migrate-origin.sh` replaces the checkout instead, once:

1. The updater already accepts both origins (shipped through the normal flow first), so either checkout keeps updating.
2. `--commit <sha> --dry-run`: clones StudioZero partial + sparse into `/opt/scalar-social/repo.next` as `scalar-social-update` with the same root-owned ssh config, key and pinned host keys; proves `publisher/` and `contract/` are byte-identical to the running checkout (git tree hashes and `diff -r`), the bundle matches its MANIFEST, and the key cannot push; then removes the clone.
3. Without `--dry-run`, it also snapshots unit states, `PAUSED` and the config/approved-schedule hashes, stops `scalar-social-update.path`, waits for a quiet minute (at least 30 minutes from an autopilot run and the daily post time, clear of the quarter-hour ticks), takes `runner.lock`, swaps the folders with `mv --exchange` (the path never disappears), moves the previous checkout to `/opt/scalar-social/repo.pre-studiozero-<stamp>` (root-only), records `units-applied.json` at the new HEAD (the `publisher/` bytes are unchanged, so no unit apply is due), restarts the UI and runs an update check against the new origin. Any failure after the swap swaps back. It never runs `apply-units.sh`, which would re-enable timers.
4. `--rollback /opt/scalar-social/repo.pre-studiozero-<stamp>` swaps back the same way.

`/etc/scalar-social`, `/etc/scalar-social-update`, `/var/lib/scalar-social`, channels and timers are untouched. The deploy key stayed attached to the old repository until the move was verified (a public repository is readable with any key); then it moved to StudioZero as read-only, and the old repository was archived, not deleted (2026-10-12).

## Owner commands (on the Pi)

First, push the commit that contains this feature to GitHub `main`, and stage a copy of `publisher/` + `contract/` on the Pi as for earlier installs.

```bash
# 0. Log in, preferably inside tmux so a dropped connection cannot cut the bootstrap off halfway
#    (optional: sudo apt install tmux; the script installs nothing)
ssh scalar-pi
tmux new -s bootstrap

# 1. Once: user scalar-social-update, root-owned key + ssh config + pinned host keys, clone, read-only proof,
#    state folders, backups, units, update path unit
sudo bash ~/.scalar-social-staging/git-bootstrap/publisher/deploy/bootstrap-git.sh
#    It prints the public key and waits: add it at
#    https://github.com/samirhusain26/StudioZero/settings/keys  (Add deploy key, write access OFF)
#    then press Enter; it verifies `ssh -F /etc/scalar-social-update/ssh_config -T git@github.com-scalar` as
#    scalar-social-update, clones into /opt/scalar-social/repo.new-<ts> and moves it into place only after checking
#    it (clean, on main, UI bundle = MANIFEST.json, every file the units reference), and stops unless GitHub refuses
#    a `git push --dry-run` as read-only. If pi-package*.json differ from /opt/scalar-social/package*.json it asks
#    [y/N] before apply-units.sh runs npm ci. Once units changed, any failure prints the rollback commands.
#    Re-running is safe: a broken or half-finished checkout is moved aside and cloned again.

# 2. Verify
curl -fsS http://127.0.0.1:8765/api/health
systemctl status scalar-social-ui.service scalar-social-update.path

# 3. Once, to install scalar-social-apply-units.path; afterwards only when Settings says the automatic apply failed
sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh
```

**Automatic apply.** When an update completes (the new UI serves the new commit) and `deploy_changes()` reports unit or `pi-package*.json` changes since `units-applied.json`, `updater.queue_units_apply()` (the update user) writes `units-apply.json` (`phase: queued`) and the trigger `units-pending.json` in `/var/lib/scalar-social-update`. `scalar-social-apply-units.path` (PathExists, TriggerLimitBurst=20 per 60 s) starts `scalar-social-apply-units.service` (root, oneshot, 45 min), which runs `apply-units.sh --auto`. The script removes the trigger first (no loop), waits up to 10 min for `scalar-social-update.service` and a queued update request, and in the npm step up to 15 min for the publisher, then does exactly what a run by hand does (same refusals: dirty checkout, bytecode, symlinks). It reports `running`, then `ok` or `failed` with the reason and the last 20 log lines, in `units-apply.json` (written as the update user, 0644). `GET /api/system/update/status` returns it as `unitsApply`; Settings → Update shows "Applying … automatically" (and keeps polling), the failure with the command as a fallback, or "applied automatically". A queued record that never starts within 10 minutes (no path unit yet) falls back to showing the command. A run by hand also removes a pending trigger, so enabling the path unit never starts a second run. Trust: root now runs the checkout's `apply-units.sh` without the owner typing it; that is the same boundary as the root steps listed under Security (only the update user writes the checkout, which only fast-forwards to the GitHub `main` commit the owner confirmed with `UPDATE TO <sha>`).

`apply-units.sh` installs the changed units and re-enables only what was already enabled, with these exceptions: it always enables `scalar-social-apply-units.path` (the automatic apply above) and the two read-only post stats units, `scalar-social-metrics.timer` and `scalar-social-metrics.path` (a masked one is left masked, with a message). They never publish; whether the hourly reads run is the UI's switch, the flag `/var/lib/scalar-social/metrics/enabled` ([MEASUREMENT.md](MEASUREMENT.md)). On its first run of this version it carries the old state over once: if the stats timer was enabled before, it creates the flag so hourly reads stay on; then it writes the root-owned marker `/etc/scalar-social/metrics-switch-migrated`, so a later run never recreates a flag the owner has switched off. It also creates empty 0600 placeholders for missing stats credentials (never overwriting one; an empty file installs no publishing drop-in). It never touches `scalar-social.timer`, the pause state or channels. Any new or changed unit file under `publisher/deploy/` (`.service`, `.path`, `.timer`, `.conf`) sets `unitsChanged`, so the update that adds `scalar-social-metrics.path` shows "Unit files changed" until the owner runs `apply-units.sh`.

Git on the Pi by hand, always as the checkout owner with only root-owned config (never `sudo git`, never scalar-social's home):

```bash
ugit() { (cd / && sudo -u scalar-social-update env -i PATH=/usr/bin:/bin HOME=/etc/scalar-social-update GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_PAGER=cat GIT_SSH_COMMAND='ssh -F /etc/scalar-social-update/ssh_config' git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C /opt/scalar-social/repo "$@"); }
ugit log -1 --oneline
ugit status --ignored
```

Rollback of an update (code only), when the automatic one did not happen or the UI stays down. Find the previous commit in git's own record, not in `status.json` (any scalar-social process can write the inbox, and the status is display only):

```bash
ugit reflog -n5 --format='%H %gs'        # the line below "merge <sha>: Fast-forward" is the commit before the update
ugit merge-base --is-ancestor <previous full sha> HEAD && echo 'ancestor: safe to go back'
ugit reset --hard <previous full sha>
sudo systemctl reset-failed scalar-social-ui.service
sudo systemctl restart scalar-social-ui.service
```

## Checking the boundaries on the Pi (after the bootstrap)

Each line shows what must happen; anything else is a finding.

```bash
# Ownership and modes
stat -c '%U:%G %a %n' /opt/scalar-social/repo /etc/scalar-social-update /etc/scalar-social-update/* \
  /var/lib/scalar-social-update /var/lib/scalar-social-update/inbox /var/lib/scalar-social /var/lib/scalar-social/runner.lock
#   repo scalar-social-update 755; /etc/scalar-social-update root:scalar-social-update 750, deploy_key root:scalar-social-update 640;
#   /var/lib/scalar-social-update scalar-social-update 755; inbox scalar-social-update:scalar-social 1730; runner.lock 644
sudo find /opt/scalar-social/repo ! -user scalar-social-update -print -quit        # prints nothing
id scalar-social-update; id scalar-social                                         # no shared groups

# scalar-social cannot write the checkout, read the key, or write the update status
sudo -u scalar-social touch /opt/scalar-social/repo/probe                          # Permission denied
sudo -u scalar-social cat /etc/scalar-social-update/deploy_key                     # Permission denied
sudo -u scalar-social touch /var/lib/scalar-social-update/status.json              # Permission denied
sudo -u scalar-social sh -c 'echo {} > /var/lib/scalar-social-update/inbox/probe.json && rm /var/lib/scalar-social-update/inbox/probe.json && echo inbox ok'

# scalar-social cannot reach into a process of the update user (/proc/<pid>/cwd needs the same UID)
sudo systemd-run --unit=probe-update -p User=scalar-social-update -p WorkingDirectory=/opt/scalar-social/repo sleep 60
sudo -u scalar-social ls "/proc/$(systemctl show -p MainPID --value probe-update)/cwd/"   # Permission denied
sudo systemctl stop probe-update

# The update user cannot write the publisher's state
sudo -u scalar-social-update touch /var/lib/scalar-social/probe                    # Permission denied

# Root Python ignores HOME's user site even with HOME=/var/lib/scalar-social
sudo systemd-run --wait --pipe -p User=root -E HOME=/var/lib/scalar-social /usr/bin/python3 -I -B -c 'import sys; print(sys.flags.isolated, sys.flags.no_user_site, sys.flags.dont_write_bytecode)'   # 1 1 1
systemctl cat scalar-social-approve.service scalar-social-threads-refresh.service scalar-social-instagram-refresh.service | grep -n 'python3'   # every root python3 has -I -B

# The unit's sandbox as systemd applied it
systemctl show scalar-social-update.service -p User -p Group -p ReadWritePaths -p Environment -p UMask -p NoNewPrivileges
systemd-analyze security scalar-social-update.service | tail -1

# The key is read-only (expect "marked as read only")
ugit push --dry-run origin HEAD:refs/heads/readonly-probe

# The UI reads the checkout with safe.directory only (plain git as scalar-social refuses it)
(cd / && sudo -u scalar-social git -C /opt/scalar-social/repo log -1 --oneline)   # fatal: detected dubious ownership
curl -fsS http://127.0.0.1:8765/api/health
```

Rollback of the git bootstrap (back to the copied install; `bootstrap-git.sh` prints the exact backup path):

```bash
sudo systemctl disable --now scalar-social-update.path
sudo cp -a /var/backups/scalar-social/pre-git-<ts>/systemd/scalar-social* /etc/systemd/system/
sudo rm -f /etc/systemd/system/scalar-social-update.path /etc/systemd/system/scalar-social-update.service
sudo systemctl daemon-reload && sudo systemctl restart scalar-social-ui.service
```

`/opt/scalar-social/scripts` and `/opt/scalar-social/ui` stay in place after the bootstrap (copies also in the backup). Once `/opt/scalar-social/repo` exists, the old copy installers (`install.sh`, `install-ui-paused.sh`, `update-paused.sh`, `install-instagram-paused.sh`) refuse to run and point here.

## Mac checks

```bash
python3 -m unittest publisher/tests/test_updater.py
python3 publisher/tests/selfupdate_demo.py          # real ui_server + updater over file:// git, two state folders,
                                                    # planted HOME config, crash-at-start rollback; prints a transcript
```
