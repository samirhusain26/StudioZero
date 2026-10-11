# Pi git-origin cutover: scalargame-marketing-plan → StudioZero

Research date 2026-10-11. Repo read: `~/Personal/code_projects/scalargame/marketing` at `4d1cdff` (= origin/main).
Pi inspected read-only over `ssh scalar-pi`. Host referred to as `scalar-pi` throughout; no tailnet names or IPs below.
All paths in `file:line` refs are relative to the marketing repo root.

---

## (a) How the update system works today

### Moving parts
| Piece | Runs as | What |
|---|---|---|
| `scalar-social-ui.service` (`ui_server.py`) | scalar-social, no network (`IPAddressDeny=any`), `/opt` read-only | Queues `inbox/request.json` (`check` / `apply`), reports restarts in `inbox/ui.json`, reads `status.json`. Never runs network git. |
| `scalar-social-update.path` | systemd | `PathExists=/var/lib/scalar-social-update/inbox/request.json` → starts the service (`publisher/deploy/scalar-social-update.path`). |
| `scalar-social-update.service` | `scalar-social-update`, oneshot, `MemoryMax=256M`, `TimeoutStartSec=60min` | `python3 -I -B …/updater.py run-request`; `ReadWritePaths=/var/lib/scalar-social-update /opt/scalar-social/repo` (a bind mount taken at unit start). |
| `scalar-social-apply-units.path/.service` | root | After a completed update with unit/package changes, runs `apply-units.sh --auto`. |
| `/etc/scalar-social-update/` | root:scalar-social-update 0750 | `deploy_key` (root:scalar-social-update 0640), `deploy_key.pub`, `ssh_config`, `known_hosts` (root:root 0644). The update unit's `HOME`. |

### Git hardening (every git call)
- `updater.git_env()` (`publisher/app/updater.py:157-160`): `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_ATTR_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_SSH_COMMAND="ssh -F /etc/scalar-social-update/ssh_config"`.
- `updater.hardened()` (`updater.py:163-169`): `core.hooksPath=/dev/null`, `core.fsmonitor=false`, `protocol.allow=never`, `protocol.ssh.allow=always`, `protocol.file.allow=never` (only `user` when a test lists a file:// origin in `SCALAR_UPDATE_ORIGINS`). **HTTPS is blocked by design**.
- `updater.run()` (`updater.py:142-154`) passes only `PATH, LANG, HOME=/etc/scalar-social-update, PYTHONDONTWRITEBYTECODE` (+`TMPDIR`) to children.
- The ssh config pins `Host github.com-scalar` → `github.com`, `IdentityFile /etc/scalar-social-update/deploy_key`, `IdentitiesOnly yes`, `UserKnownHostsFile …/known_hosts`, `GlobalKnownHostsFile /dev/null`, `StrictHostKeyChecking yes`, `UpdateHostKeys no`, `BatchMode yes`, `ProxyCommand none` (written by `bootstrap-git.sh:175-198`).

### How `originOk` is computed and where the names live
- Allowed names: `updater.py:33-34`
  ```python
  ORIGINS = tuple(f'git@github.com-scalar:samirhusain26/{name}{suffix}'
                  for name in ('scalargame-marketing', 'scalargame-marketing-plan') for suffix in ('.git', ''))
  ```
  plus `SCALAR_UPDATE_ORIGINS` (comma list; tests/Mac demo only, never set on the Pi) via `accepted_origins()` (`updater.py:463-464`).
- Computed in `inspect()` (`updater.py:471-500`): `url = git remote get-url origin`; `'originOk': url in accepted_origins()` (`updater.py:496`). **Exact string match**: only the ssh form with the `github.com-scalar` alias; https, other owners, other aliases → false.
- Enforced twice: UI-side `check_start()` (`updater.py:451-452`, Refused 409 `origin`) and unit-side `do_apply()` after the re-fetch (`updater.py:694-701`).
- A second, independent copy of the allowed names is in `bootstrap-git.sh:59-62` (`verify_checkout` case statement) plus the clone constants `ORIGIN`/`KEYS_URL` at `bootstrap-git.sh:24-25`.
- UI: `originOk`/`originUrl` are just displayed (`publisher/ui/src/lib/update.ts:115-118`, type in `publisher/ui/src/api/types.ts:1256`). No name list in the UI. Guide text naming the repo: `publisher/ui/content/guide/{overview.md:48,update.md:29,owner-only.md:8-9}` (changing these needs `npm run build:static`).

### Non-fast-forward / unrelated history
- `fetch()` (`updater.py:467-468`) uses a **forced** refspec `+refs/heads/main:refs/remotes/origin/main`, so a fetch of rewritten/unrelated history succeeds.
- `inspect()` then sets `diverged = ahead > 0 or not merge-base --is-ancestor HEAD origin/main` (`updater.py:486-488`). For an unrelated history `HEAD..origin` counts all new commits (`behind` > 0), `origin..HEAD` counts all old ones (`ahead` > 0) and HEAD is not an ancestor → `diverged: true`.
- `check_start()` refuses `diverged` (`updater.py:446-450`), `do_apply()` refuses it again (`updater.py:698`), and the switch itself is `git merge --ff-only <sha>` (`updater.py:649-660`) which would fail anyway, with `reset --hard <old>` rollback.
- **Conclusion: yes, the updater requires the new commit to descend from the current HEAD** (explicit ancestry check plus ff-only). Pointing the existing checkout at StudioZero would make every check "diverged" and every apply refused. The checkout must be replaced, not re-pointed. Same for `bootstrap-git.sh:67` (`merge-base --is-ancestor HEAD origin/main`).

### Apply sequence (for context)
check → owner confirms `UPDATE TO <sha>` → `check_start` re-validates (≤15 min old, HEAD unchanged, clean, not diverged, branch, origin, behind>0, sha == check.origin) → unit: re-fetch, `origin changed after confirmation` guard (`updater.py:692`), worktree stage under `.git/scalar-update-stage`, staged checks (compileall, import every module, contract tests, `QUICK_TESTS` incl. `test_updater`, static MANIFEST) (`updater.py:586-604`), flock `/var/lib/scalar-social/runner.lock` (`updater.py:520-564`), ff-only merge, UI exits 86 and restarts, `verify_restart` rolls back if the new UI never serves within 120 s (`updater.py:746-796`). After `complete`, `queue_units_apply()` (`updater.py:394-401`) triggers `apply-units.sh --auto` if `deploy_changes()` (`updater.py:376-391`) sees unit/pi-package diffs between `units-applied.json.commit` and HEAD.

Two details that matter for a cutover:
1. `deploy_changes()` runs `git diff <units-applied.commit> <HEAD>`; if that old SHA does not exist in the repo (it won't in a fresh StudioZero clone) the diff fails and it returns `(True, True)` → the UI shows "Unit files changed, run apply-units.sh" and the next completed update queues an automatic apply. So the cutover must rewrite `units-applied.json` to the new HEAD.
2. The UI reads its running commit once at import (`running_commit`, `updater.py:214-238`); the watcher only restarts it for `switched`/`failed` phases (`updater.py:868-888`). After a swap HEAD changes, the UI keeps the old SHA and `info()` reports `restartNeeded` (`updater.py:424-425`). So the cutover must restart `scalar-social-ui.service`.

### sync-pi.sh (Mac side)
`publisher/deploy/sync-pi.sh`:
- `:11-16` requires local branch `main`, no uncommitted changes under `publisher/ contract/`, local HEAD == `origin/main` after `git fetch origin main` (so it follows whatever the local repo's `origin` is; no repo name hard-coded).
- `:19-68` SSHes to `scalar-pi` and runs Python **as scalar-social** (`sudo -u scalar-social python3 -I -B -`) importing the Pi's `updater.py`: if `running_commit == target` exit (`:41-43`); wait idle; `queue_request('check')` and wait (`:45-48`); require fetch ok and `check.origin == target` (`:50-53`); `updater.start(... 'UPDATE TO <sha>')` (`:55-58`); wait for `complete`/`failed` (`:60-63`); report the unit apply (`:64-66`).
- `:70-72` final comparison with plain `git -c safe.directory=… rev-parse HEAD` as the login user.
- After the cutover it works unchanged as long as the Mac's local repo is StudioZero with `origin` = StudioZero.

### apply-units.sh (relevant bits)
- Stops `scalar-social-update.path` while it works and restarts it if it was active (`apply-units.sh:99-114,143-149`); refuses dirty/bytecode (`:150-154`).
- **Always** `enable --now` `scalar-social-metrics.timer`, `scalar-social-metrics.path`, `scalar-social-apply-units.path`, `scalar-social-autopilot.timer` unless masked (`:257-270`). This is why the cutover script should NOT call it (it would re-enable an autopilot timer the owner had disabled).
- Restarts the UI with a health check (`:303-316`) and records `units-applied.json` as the update user (`:318-320`).

### Timer schedule (from the unit files; `docs/AUTOPILOT_PLAN.md:42`)
All times Pi local = America/New_York.
| Timer | OnCalendar | Jitter | Runtime cap |
|---|---|---|---|
| `scalar-social-autopilot.timer` | 05:15, 17:15 | +≤120 s | 300 s; its activation can trigger `scalar-social-approve.service` (≤600 s) |
| `scalar-social.timer` (publisher) | every :00/:15/:30/:45 | +≤20 s | 600 s; takes `runner.lock` with `LOCK_NB` (`runner.py:161-169`) |
| `scalar-social-monitor.timer` | every :00/:15/:30/:45 | +≤20 s | short |
| `scalar-social-metrics.timer` | hh:20 | +≤120 s | short |
| threads / instagram refresh | 04:30 / 04:45 | +≤300 s | short |

---

## (b) Pi facts (read-only, 2026-10-11 ~17:07 EDT)

**Checkout `/opt/scalar-social/repo`**
- HEAD `3630621d12915b670ba7a87e8e84222395e1d905` on `main` ("Run publishing on autopilot…", 2026-10-09). Local/GitHub main is `4d1cdff` (one studio-only commit ahead). **`publisher/` and `contract/` trees are identical** in both: `HEAD:publisher` = `7c90efe15bfd3b19c9503dae0772cdd72c1da145`, `HEAD:contract` = `091f564a064bbaf2c4b3f427d128163f10901e92`.
- Origin: `git@github.com-scalar:samirhusain26/scalargame-marketing-plan.git` (**ssh form via the alias**), `remote.origin.promisor=true`, `remote.origin.partialclonefilter=blob:none`, fetch refspec `+refs/heads/*:refs/remotes/origin/*` (the updater passes its own main-only refspec). `branch.main.remote/merge` set. `extensions.worktreeconfig=true` (sparse settings live in `config.worktree`).
- Sparse checkout (cone): `contract`, `publisher`. Root files present: `AGENTS.md CLAUDE.md OWNER_GUIDE.md README.md .gitignore` (cone mode always checks out root-level files).
- Clean (`status --porcelain --ignored` empty), one worktree, no stage leftovers, 25 commits, 2.7 MiB packed. No `repo.*` sibling dirs.
- Owner/mode `scalar-social-update:scalar-social-update 0755`.
- No repo-local `core.sshCommand`; nothing ssh-related in git config. The wiring is **purely** `GIT_SSH_COMMAND="ssh -F /etc/scalar-social-update/ssh_config"` set by `updater.git_env()` / the scripts' `as_update`, plus `HOME=/etc/scalar-social-update`.
- git 2.47.3, OpenSSH 10.0p2, Python 3.13.5, GNU coreutils 9.7 (`mv --exchange` available → atomic `renameat2(RENAME_EXCHANGE)`), no `jq`.

**`/etc/scalar-social-update`** (root:scalar-social-update 0750)
| File | Owner | Mode |
|---|---|---|
| `deploy_key` | root:scalar-social-update | 0640 |
| `deploy_key.pub` | root:root | 0644 (ed25519) |
| `known_hosts` | root:root | 0644 — GitHub ED25519/ECDSA/RSA, fingerprints match those in `bootstrap-git.sh:166-169` |
| `ssh_config` | root:root | 0644 — identical to the `bootstrap-git.sh` template |

**Update state `/var/lib/scalar-social-update`** (scalar-social-update 0755; `inbox/` scalar-social-update:scalar-social 1730)
- `status.json`: `phase: complete`, `fromCommit ec870aca…`, `toCommit 3630621d…`, updated 2026-10-09T18:12:01Z; last check 2026-10-09T18:11:53Z: `fetchOk true, originOk true, branchOk true, dirty false, diverged false, behind 0, ahead 0, head = origin = 3630621d…`.
- `units-applied.json`: `commit 3630621d…`, applied 2026-10-09T18:12:30Z (= HEAD, so no pending unit changes).
- `units-apply.json`: `phase ok`, `commit 3630621d…`, no error.
- `inbox/ui.json`: `phase serving`, `running 3630621d…`. No `request.json`, no `units-pending.json`.

**Publisher state**
- `/var/lib/scalar-social` scalar-social 0711; `runner.lock` 0644 regular file.
- `/var/lib/scalar-social/PAUSED`: **absent** (publishing live). `scalar-social.timer` enabled + active.

**Units** (`systemctl list-units 'scalar-social*'`)
- Active/waiting: `-apply-units.path`, `-approve.path`, `-metrics.path`, `-update.path`, `-autopilot.timer`, `-instagram-refresh.timer`, `-metrics.timer`, `-monitor.timer`, `-threads-refresh.timer`, `scalar-social.timer`; `-ui.service` active (running). All enabled.
- **Pre-existing failures** (unrelated to updates, but they will muddy a before/after comparison): `scalar-social.service` failed (exit 2, last run 17:00:22), `scalar-social-monitor.service` failed (exit 2, 17:00:11), `scalar-social-threads-refresh.service` failed (exit 1, 04:30:57).

**Next timer runs (as listed)**: autopilot Sun 2026-10-11 17:15:38 EDT, then Mon 05:15 (+jitter); publisher/monitor every quarter hour; metrics hh:20; refresh Mon 04:33 / 04:46.

**Resources**: 415 MB RAM (≈225 MB available, swap 414 MB, 33 MB used); root fs 115 GB, 105 GB free; TZ `America/New_York`, NTP synchronized.

**Old copied install still present**: `/opt/scalar-social/scripts` (root, Oct 5) and `/opt/scalar-social/ui` (root, Oct 7); also `/opt/scalar-social/deploy/pi`, `node_modules`, `package*.json`. Backups under `/var/backups/scalar-social/units-*` (8, last 20261009T181201Z).

**Deploy-key reach test** (read-only `git ls-remote`, no checkout touched): the existing key (attached to the private old repo) **can already read the public StudioZero** over the pinned ssh alias: `git ls-remote git@github.com-scalar:samirhusain26/StudioZero.git refs/heads/main` → `dc127806…` (old StudioZero main; the import has not landed yet). GitHub lets any authenticated key read a public repo.

---

## Deploy key: per-repo, and ssh vs anonymous https

- A GitHub deploy key is attached to exactly one repository; adding the same public key to a second repo fails ("Key is already in use"). The current key is attached to `scalargame-marketing-plan`.
- Because StudioZero is public, the ssh fetch already works with the old key (verified above). The cutover itself therefore needs **no GitHub change and no change in `/etc/scalar-social-update`**. But relying on that long-term is fragile: deleting the old repo deletes its deploy keys (archiving keeps them), and the read-only proof against StudioZero would read "permission denied to deploy key" rather than GitHub's "marked as read only". If StudioZero ever goes private, access stops.
- Options:
  1. **Recommended: keep pinned ssh + the same key, move its attachment after the cutover is verified.** Owner deletes the key from `scalargame-marketing-plan` → Deploy keys, then adds the same public key (`/etc/scalar-social-update/deploy_key.pub`) to StudioZero with "Allow write access" **unticked** (or `gh repo deploy-key add <pub> -R samirhusain26/StudioZero --title <same title as before>` without `--allow-write`, then `gh repo deploy-key delete <id> -R samirhusain26/scalargame-marketing-plan`, only with owner OK). Re-prove read-only: `ugit push --dry-run origin HEAD:refs/heads/readonly-probe` must answer "marked as read only". No Pi file changes; every SELF_UPDATE.md property holds unchanged. Downside: after the move, a rollback to the old origin still runs locally but cannot fetch from the old repo until the key is re-attached there.
  2. New dedicated key for StudioZero: same properties, but needs a root step to add a second key and switch `IdentityFile` in `ssh_config` atomically at cutover (two keys under one alias don't work: GitHub accepts the first registered key and then denies the repo). More moving parts for little gain; only if the owner wants the old key retired.
  3. Anonymous https (no key): nothing secret on the Pi at all ("a compromised Pi cannot change GitHub" holds trivially). Against it: loses ssh host-key pinning (trust moves to the whole system CA store); needs `hardened()` changed to allow `protocol.https` and an https form in `ORIGINS`, which opens the libcurl/`http.*` config surface (env is stripped and global/system config is off, so it is manageable, but it is new attack surface needing a fresh security review); breaks silently if the repo is ever made private; diverges from the reviewed design. **Not recommended.**
- Public repo, unchanged trust rule: whoever can push to StudioZero `main` decides what root runs on the Pi. Before the cutover: branch protection on `main` (no force-push/deletion), no extra collaborators with write access, and treat merged PRs from outsiders as root code.

---

## (c) Cutover plan

### Step 0: preconditions (Mac / GitHub, no Pi change)
1. Step 1 below is shipped and the Pi runs it (`sync-pi.sh` green, `originOk` still true).
2. **Freeze `publisher/` and `contract/`** from the Step 1 commit until the cutover ends. The StudioZero import must carry the exact trees the Pi runs. On the Mac:
   `git -C <StudioZero> rev-parse <cutover-commit>:publisher <cutover-commit>:contract` must equal the Pi's `HEAD:publisher` / `HEAD:contract` (values change once Step 1 ships; today `7c90efe1…` / `091f564a…`).
3. StudioZero `main` contains the cutover commit (it may be followed by later commits; see `--commit` below). Branch protection on.
4. Root-level files of StudioZero at the cutover commit are small and harmless (cone mode checks out every root file on the Pi; `StudioZero.app/`, `assets/` etc. are directories and are not checked out).
5. Investigate the three failed units separately (the cutover does not touch them), so the before/after comparison is meaningful.

### Step 1: updater accepts StudioZero (normal flow, still on the old repo)
Code changes (one commit on the old repo `main`, push, `publisher/deploy/sync-pi.sh`):

1. `publisher/app/updater.py:33-34`
   ```python
   # Accepted GitHub repositories (exact ssh URLs via the root-owned github.com-scalar alias). StudioZero (public)
   # replaces scalargame-marketing-plan; the old names stay accepted so a rollback of the move keeps working.
   REPOS = ('scalargame-marketing', 'scalargame-marketing-plan', 'StudioZero')
   ORIGINS = tuple(f'git@github.com-scalar:samirhusain26/{name}{suffix}' for name in REPOS for suffix in ('.git', ''))
   ```
2. `publisher/deploy/bootstrap-git.sh:59-62`: add `git@github.com-scalar:samirhusain26/StudioZero.git` to the accepted `case` (so a later re-run of bootstrap on the new checkout does not refuse). Leave `ORIGIN`/`KEYS_URL` (`:24-25`) for the post-cutover commit.
3. New `publisher/deploy/migrate-origin.sh` (Step 2). Shipping it now means it already sits in the Pi checkout and, being under `publisher/`, is byte-identical in the StudioZero import. `.sh` files do not match `UNIT_FILE` (`updater.py:75`), so no `unitsChanged`.
4. `publisher/docs/SELF_UPDATE.md`: line 31 `originOk` text (add StudioZero), Files table (add `migrate-origin.sh`), new short section "Moving the checkout to another GitHub repository" (why a re-point is impossible: ancestry check; what the script does; rollback).
5. No UI code change needed (no name list in the UI). Guide text (`overview.md`, `update.md`, `owner-only.md`) and `bootstrap-git.sh` `ORIGIN`/`KEYS_URL` change **after** the cutover in StudioZero (needs `npm run build:static` + `check:static`).

Tests (`publisher/tests/test_updater.py`; `test_updater` is in `QUICK_TESTS`, so these also run in the Pi's staged checks on Linux / git 2.47):
- Extend `test_origin_and_branch_mismatch` (`:182-190`): assert both `…/StudioZero.git` and `…/StudioZero` are in `updater.ORIGINS`, and the old names still are.
- New `test_studiozero_origin_is_accepted`: modelled on `test_ssh_uses_only_the_root_owned_config` (`:503-515`): `remote set-url origin git@github.com-scalar:samirhusain26/StudioZero.git`, patched `SSH_CONFIG` whose ProxyCommand fails, run a check → `fetchOk False`, `originOk True`.
- New `test_lookalike_origins_are_refused` (with `ORIGINS_ENV` emptied): `…/StudioZero.git.evil`, `…/StudioZero-fork.git`, `git@github.com-scalar:other/StudioZero.git`, `git@github.com:samirhusain26/StudioZero.git` (no alias, i.e. not the pinned config), `https://github.com/samirhusain26/StudioZero.git` → `originOk False`.
- New `test_unrelated_history_is_diverged_and_refused`: build a second bare origin with an unrelated root commit whose `publisher/`+`contract/` content equals the current tree, `remote set-url` the Pi to it (listed in `ORIGINS_ENV`), check → `behind>0, ahead>0, diverged True`; `check_start` raises `Refused(code='diverged')`; HEAD unchanged. Documents why Step 2 exists.
- Run: `python3 -m unittest discover -s publisher/tests -p 'test_*.py'`, `python3 -m unittest discover -s contract/tests -p 'test_*.py'`, `python3 publisher/tests/selfupdate_demo.py`, `bash -n publisher/deploy/migrate-origin.sh` (+ `shellcheck` if installed; do not install without asking).
- Ship: commit → `git push origin main` → `publisher/deploy/sync-pi.sh` → confirm Settings → Update check green (`originOk` true on the old origin).

### Step 2: `publisher/deploy/migrate-origin.sh` (root, idempotent, `--dry-run`)
Usage (on the Pi):
```
sudo /opt/scalar-social/repo/publisher/deploy/migrate-origin.sh --commit <full sha on StudioZero main> --dry-run
sudo /opt/scalar-social/repo/publisher/deploy/migrate-origin.sh --commit <same sha>
sudo /opt/scalar-social/repo/publisher/deploy/migrate-origin.sh --rollback /opt/scalar-social/repo.pre-studiozero-<ts>
```
Design (reuses `bootstrap-git.sh`'s `as_update`/`ugit`/`dirty_lines`/`LOW_MEMORY`/`HARDENED` verbatim, so git runs exactly as the updater runs it):

**Constants**: `REPO=/opt/scalar-social/repo`, `NEXT=/opt/scalar-social/repo.next` (not `repo.new-*`, which `bootstrap-git.sh:219-222` deletes), `ASIDE=/opt/scalar-social/repo.pre-studiozero-$STAMP`, `NEW_ORIGIN=git@github.com-scalar:samirhusain26/StudioZero.git`, `BACKUP=/var/backups/scalar-social/origin-move-$STAMP` (root 0700). Never touches `/etc/scalar-social`, `/etc/scalar-social-update`, `/var/lib/scalar-social` (only flocks `runner.lock` read-only and reads `config.json` for the post time without printing it), `scalar-social.timer`, `PAUSED`, channels.

**0. Idempotency / resume**
- `REPO` origin == `NEW_ORIGIN` and clean on main → "already moved"; if `NEXT` exists with an old origin (interrupted right after the exchange) finish by renaming it to `ASIDE`; run the post-verification (step 7) only; exit 0.
- `NEXT` left by an interrupted run (real dir, not a symlink, owned by the update user) → `rm -rf` and re-clone.

**1. Preflight (dry-run and real)**
- root; `git ssh runuser flock curl python3`; `mv --help | grep -q -- --exchange`.
- `REPO` real dir owned by `scalar-social-update`, `find REPO -xdev ! -user scalar-social-update` empty; clean (`dirty_lines`); on `main`; origin ∈ old origins.
- The running updater accepts `NEW_ORIGIN` (`grep -q "'StudioZero'" $REPO/publisher/app/updater.py`), i.e. Step 1 is live.
- No update activity: `scalar-social-update.service` inactive; no `inbox/request.json`/`request.taken.json`; `status.json` phase not busy; no `units-pending.json`; `units-apply.json` phase not `queued`/`running`; `units-applied.json.commit == HEAD` (no pending unit apply; required for rewriting it later).
- Memory: `MemAvailable` ≥ 120 MB.

**2. Fresh partial + sparse clone into `NEXT`** (as the update user, root-owned config, exactly like `bootstrap-git.sh:244-248`)
```
install -d -m 755 -o scalar-social-update -g scalar-social-update "$NEXT"
ugit "${LOW_MEMORY[@]}" clone --quiet --filter=blob:none --no-checkout --branch main "$NEW_ORIGIN" "$NEXT"
ugit -C "$NEXT" merge-base --is-ancestor "$COMMIT" refs/remotes/origin/main   # --commit must be on StudioZero main
ugit -C "$NEXT" sparse-checkout set --cone publisher contract
ugit "${LOW_MEMORY[@]}" -C "$NEXT" checkout --quiet -B main "$COMMIT"
ugit -C "$NEXT" branch --quiet --set-upstream-to=origin/main main
```
(`--commit` lets the cutover land on the import commit even if StudioZero main has moved on; the updater then shows `behind N` and the normal flow brings it forward with staged checks.)

**3. Verify `NEXT`**
- `remote get-url origin` == `NEW_ORIGIN` exactly; `symbolic-ref` == `main`; `dirty_lines` empty; `find NEXT ! -user scalar-social-update` empty.
- **Byte identity with the running checkout**: `ugit -C REPO rev-parse HEAD:publisher HEAD:contract` == `ugit -C NEXT rev-parse HEAD:publisher HEAD:contract` (git tree hashes are content addresses: equal hashes ⇒ identical names, bytes and exec bits, regardless of history), plus `diff -r --no-dereference REPO/publisher NEXT/publisher` and the same for `contract` (catches anything on disk the tree hash can't). Print root-file differences (informational).
- Same files `bootstrap-git.sh:69-80` requires, `User=scalar-social-update` in the update unit, and `updater.check_static()` on `NEXT/publisher/app/static` as the update user with `python3 -I -B` (`bootstrap-git.sh:81-82`).
- Read-only proof: `ugit -C NEXT push --dry-run origin HEAD:refs/heads/readonly-probe` must **fail**; accept "marked as read only" (key attached to StudioZero) or "denied to deploy key"/"Permission to … denied" (key still on the old repo), refuse otherwise; refuse hard if it succeeds.
- `--dry-run` stops here: prints old/new HEAD, both tree hashes, the window it would wait for, then `rm -rf NEXT`. Nothing live changed.

**4. Before-snapshot** to `BACKUP` (0700): old HEAD and origin; copies of `status.json`, `units-applied.json`, `units-apply.json`; `systemctl is-enabled`/`is-active` for every `scalar-social*` unit; `PAUSED` present/absent; `sha256sum` of `/etc/scalar-social/config.json` and `/var/lib/scalar-social/manifests/approved.json` (hashes only, never contents); `systemctl list-timers 'scalar-social*'`.

**5. Quiesce and wait for a safe moment** (nothing disabled, nothing paused)
- `PATH_WAS=$(systemctl is-active scalar-social-update.path)`; `systemctl stop scalar-social-update.path` (restarted on every exit path by a trap); re-check `scalar-social-update.service` inactive (its `ReadWritePaths` bind would otherwise pin the old directory).
- Refuse if the autopilot timer's `NextElapseUSecRealtime` is < 30 min away or it ran < 25 min ago; refuse within ±30 min of the configured daily post time (read from `config.json`, not printed).
- `wait_idle 600 scalar-social.service scalar-social-approve.service scalar-social-autopilot.service scalar-social-metrics.service` (as `apply-units.sh:85-98`).
- Wait until the minute is in :03–:12, :33–:42 (clear of the quarter-hour publisher/monitor ticks and the :20 metrics read; :48–:57 also clear but keep it simple).
- Take the publisher lock as the updater does: `[ -f runner.lock ] && [ ! -L runner.lock ]`, `exec 9<"$STATE/runner.lock"`, `flock -w 120 9`.

**6. Atomic swap** (lock held for about a second)
```
mv --exchange -T "$NEXT" "$REPO"      # renameat2(RENAME_EXCHANGE): /opt/scalar-social/repo never missing
mv -T "$NEXT" "$ASIDE"                # NEXT now holds the old checkout
chmod 700 "$ASIDE"                    # owner unchanged (rollback); nothing can run from it
exec 9<&-                             # release runner.lock
```
Then, instead of `apply-units.sh` (which always `enable --now`s the autopilot/metrics timers):
- Rewrite `units-applied.json` as the update user with the new HEAD (valid because `publisher/` incl. `deploy/` and `pi-package*.json` is byte-identical to the previously applied commit), same command as `apply-units.sh:318-319`.
- `systemctl restart scalar-social-ui.service` (Type=notify; waits until ready), then `curl -fsS http://127.0.0.1:8765/api/health`.
- `systemctl start scalar-social-update.path` if `PATH_WAS=active`.
- Any failure from the swap on → automatic rollback (step 5 of the plan) and exit non-zero.

**7. Post-verification** (also what an idempotent re-run does)
- As scalar-social, exactly like `sync-pi.sh:37-53`: wait idle, `updater.queue_request(STATE, 'check')`, wait for the new `checkedAt`; require `fetchOk`, `originOk`, `branchOk`, `!dirty`, `!diverged`, `head` == new HEAD, `originUrl` == `NEW_ORIGIN` (`behind` may be > 0 if `--commit` was older than the tip; print it).
- `updater.py info` (as scalar-social): `runningCommit == repoHead`, `restartNeeded false`, `unitsChanged false`, `piPackageChanged false`.
- Compare with the before-snapshot: unit enabled/active states, `PAUSED`, the two hashes. Print the rollback command and the `ASIDE` path.

Security properties preserved: same dedicated user owns and alone writes the new checkout (cloned via `runuser`, umask 022, ownership verified); the same read-only key, pinned `known_hosts` and root-owned `ssh_config` in the untouched `/etc/scalar-social-update`; every git call through the root-owned HOME/`-F` config with hooks/fsmonitor off; root runs the script from the checkout (same trust boundary as `apply-units.sh`); root never writes into scalar-social's folders (only a read-only flock).

**Services**: only `scalar-social-update.path` is stopped (minutes), the UI is restarted once. Publisher, autopilot, approve, metrics, monitor and refresh timers keep running; the exchange is atomic and both directories carry identical `publisher/`+`contract/` bytes, so a unit that starts at any moment runs the same code. Running Python processes that lazily import later resolve to identical files.

### Step 3: scheduling
- Busy periods (ET): autopilot 05:15–~05:35 and 17:15–~17:35 (timer + jitter + possible approve run), refresh 04:30–04:55, publisher/monitor ticks at each quarter hour (+20 s), metrics hh:20–hh:23, plus the daily post slot from config.
- **Safe window: 09:00–15:00 or 19:00–03:30 ET, away from the post slot; start at hh:05 (e.g. 10:05 ET) when the owner is reachable.** The script enforces the minute window and the autopilot/post-slot distances itself, so starting it a bit early just waits.
- Expected duration: clone 1–3 min on the Pi Zero 2 W, verification ~1 min, swap ~1 s, UI restart ~10 s, check ~1 min.
- Run the `--dry-run` first (same day, any safe time), then the real run in the next safe slot. Never between 17:00 and 17:40 or 05:00 and 05:40.

### Step 4: verification checklist (read-only after the run)
```bash
ssh scalar-pi
ugit() { (cd / && sudo -u scalar-social-update env -i PATH=/usr/bin:/bin HOME=/etc/scalar-social-update GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_PAGER=cat GIT_SSH_COMMAND='ssh -F /etc/scalar-social-update/ssh_config' git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C /opt/scalar-social/repo "$@"); }
ugit remote get-url origin                         # git@github.com-scalar:samirhusain26/StudioZero.git
ugit rev-parse HEAD HEAD:publisher HEAD:contract   # trees == before
ugit sparse-checkout list; ugit config --get remote.origin.partialclonefilter   # contract publisher; blob:none
ugit status --porcelain --ignored                  # empty
sudo find /opt/scalar-social/repo ! -user scalar-social-update -print -quit     # nothing
stat -c '%U:%G %a %n' /opt/scalar-social/repo /etc/scalar-social-update /etc/scalar-social-update/*   # unchanged modes
systemctl list-units --all 'scalar-social*'        # same active set as before; ui running
systemctl list-timers --all | grep scalar          # autopilot next run present (05:15 or 17:15)
curl -fsS http://127.0.0.1:8765/api/health
sudo grep -E '"(phase|originOk|fetchOk|diverged|dirty|behind|head)"' /var/lib/scalar-social-update/status.json
sudo cat /var/lib/scalar-social-update/units-applied.json   # commit == new HEAD
sudo test -e /var/lib/scalar-social/PAUSED && echo PAUSED || echo not-paused   # same as before (today: not paused)
systemctl is-enabled scalar-social.timer; systemctl is-active scalar-social.timer   # same as before
sudo sha256sum /etc/scalar-social/config.json /var/lib/scalar-social/manifests/approved.json   # == before-snapshot
```
Plus: UI Settings → Update shows a green check on StudioZero; the next autopilot run completes normally (check `systemctl status scalar-social-autopilot.service` after it); on the Mac (StudioZero checkout) `publisher/deploy/sync-pi.sh` reports "In sync" (or brings the Pi from `--commit` to the tip). Finally prove read-only once the key is attached to StudioZero: `ugit push --dry-run origin HEAD:refs/heads/readonly-probe` → "marked as read only".

### Step 5: rollback
- Automatic inside the script if anything fails after the swap.
- By hand / `--rollback <ASIDE>` (same quiesce: stop update.path, wait idle, safe minute, runner.lock):
  ```
  chmod 755 "$ASIDE"
  mv --exchange -T "$ASIDE" /opt/scalar-social/repo
  mv -T "$ASIDE" /opt/scalar-social/repo.studiozero-rolledback-$STAMP && chmod 700 that dir
  restore units-applied.json from $BACKUP as the update user
  systemctl restart scalar-social-ui.service && curl -fsS http://127.0.0.1:8765/api/health
  systemctl start scalar-social-update.path
  queue a check (works only while the key is still attached to the old repo)
  ```
- Both checkouts carry the Step 1 updater, so either accepts either origin. Keep `ASIDE` (root can read; 0700) until StudioZero has delivered at least one normal update through Settings → Update; then `sudo rm -rf /opt/scalar-social/repo.pre-studiozero-*`.
- Do not move the deploy key off the old repo until the rollback window is closed.

### After the cutover (normal flow, in StudioZero)
- `bootstrap-git.sh:24-25` `ORIGIN`/`KEYS_URL` → StudioZero; guide pages (`overview.md:48`, `update.md:29`, `owner-only.md:8-9`) → StudioZero + rebuild static; `SELF_UPDATE.md` repo references; CLAUDE.md/AGENTS.md. Ship via `sync-pi.sh` (first real update through the new origin = end-to-end proof).
- Optionally, later, drop the old names from `ORIGINS` (keeping them costs nothing).

---

## (d) Risks and open questions for the owner

1. **GitHub key (owner action)**: approve moving the existing read-only deploy key from `scalargame-marketing-plan` to StudioZero after verification (Settings → Deploy keys, or `gh repo deploy-key` with explicit OK). Until then the Pi reads the public repo with a key attached elsewhere (works today, verified). **Do not delete the old repo**: that deletes its deploy keys; archive it only after the cutover is verified and the key has moved.
2. **Public repo = public update source**: whoever can push/merge to StudioZero `main` controls root on the Pi. Turn on branch protection (no force-push/deletion), keep write access to the owner. Signed-commit verification remains the documented future hardening.
3. **Tree freeze**: between shipping Step 1 and the cutover, no `publisher/`/`contract/` change may land on either repo unless the import is redone; the script refuses if the trees differ (safe failure, but a wasted window).
4. **Root files in the public repo** land on the Pi (cone mode). Keep them small; no secrets (public-safety audit covers this).
5. **Pre-existing failing units** (`scalar-social.service` exit 2, `scalar-social-monitor.service` exit 2, `scalar-social-threads-refresh.service` exit 1): diagnose before the cutover so "nothing changed" is checkable; the cutover does not touch them.
6. **Publishing is live** (no `PAUSED`, publisher timer enabled). The plan never pauses; the swap holds `runner.lock` ~1 s inside a window chosen to miss ticks. If the owner prefers a pause for the cutover, only the owner pauses/resumes.
7. **Post slot**: the script reads the daily post time from config (not printed) and refuses within ±30 min; owner may prefer a wider margin.
8. **Script testing**: the script needs Linux users, `runuser`, systemd and `mv --exchange`, so it cannot run on the Mac. Proposed proof: `bash -n` (+ shellcheck if already installed), then `--dry-run` on the Pi (writes only `/opt/scalar-social/repo.next`, which it deletes; needs OK because it is a write under `/opt`). Optional: a Debian VM/container rehearsal if the owner wants more.
9. **`--commit` choice**: cut over to the import commit (trees identical) and let the normal updater bring the Pi to StudioZero's tip, rather than requiring the tip to be identical.
10. **Mac side**: `sync-pi.sh` follows the local repo's `origin`; after the folder swap the Mac's StudioZero checkout must have `origin` = `samirhusain26/StudioZero` and be on the same commit as GitHub main.
11. **Old copied install** (`/opt/scalar-social/scripts`, `/opt/scalar-social/ui`, `/opt/scalar-social/deploy/pi`) is still present and unused; unrelated to the cutover, can be removed later with owner OK.
12. Decide whether to drop the old origin names from `ORIGINS` after the rollback window (recommendation: keep them for a few weeks, then remove in a normal update).
