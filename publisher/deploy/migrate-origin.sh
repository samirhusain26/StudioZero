#!/bin/bash
# Run with sudo on the Pi, once: move the checkout from the private scalargame-marketing-plan repository to the public
# StudioZero repository. Their histories are unrelated, so the updater refuses an in-place re-point as diverged
# (SELF_UPDATE.md, "Moving the checkout to another GitHub repository"). This clones StudioZero next to the checkout
# as the update user (same root-owned ssh config, deploy key and pinned host keys), proves its publisher/ and
# contract/ are byte-identical to the running checkout, then swaps the two folders atomically (mv --exchange) while
# holding the publisher's runner.lock, rewrites units-applied.json and restarts the UI. It never touches
# /etc/scalar-social, /etc/scalar-social-update, /var/lib/scalar-social, PAUSED, channels or timers, and never runs
# apply-units.sh (which would re-enable timers). Any failure after the swap swaps back.
#   sudo bash migrate-origin.sh --commit <sha on StudioZero main> --dry-run   # clone + verify only, then remove the clone
#   sudo bash migrate-origin.sh --commit <sha on StudioZero main>             # the move (waits for a quiet minute)
#   sudo bash migrate-origin.sh --rollback /opt/scalar-social/repo.pre-studiozero-<stamp>
# Re-running after a completed move only re-verifies.
set -eu
set -o pipefail
REPO=/opt/scalar-social/repo
NEXT=/opt/scalar-social/repo.next
STATE=/var/lib/scalar-social
USTATE=/var/lib/scalar-social-update
UUSER=scalar-social-update
UPD=/etc/scalar-social-update
NEW_ORIGIN=git@github.com-scalar:samirhusain26/StudioZero.git
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ASIDE=/opt/scalar-social/repo.pre-studiozero-$STAMP
BACKUP=/var/backups/scalar-social/origin-move-$STAMP
LOW_MEMORY=(-c pack.threads=1 -c pack.windowMemory=32m -c core.deltaBaseCacheLimit=16m -c core.packedGitLimit=64m -c core.packedGitWindowSize=16m)
HARDENED=(-c core.hooksPath=/dev/null -c core.fsmonitor=false -c protocol.allow=never -c protocol.ssh.allow=always -c protocol.file.allow=never)
# git and ssh exactly as updater.py and bootstrap-git.sh run them.
as_update() {
  runuser -u "$UUSER" -- env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$UPD" GIT_CONFIG_GLOBAL=/dev/null \
    GIT_CONFIG_NOSYSTEM=1 GIT_ATTR_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_PAGER=cat PAGER=cat GIT_SSH_COMMAND="ssh -F $UPD/ssh_config" \
    sh -c 'umask 022; cd / && exec "$@"' sh "$@"
}
ugit() { as_update git "${HARDENED[@]}" "$@"; }
as_service() { (cd / && runuser -u scalar-social -- "$@"); }
say() { printf '\n==> %s\n' "$*"; }
dirty_lines() {
  local out
  out=$(ugit -C "$1" status --porcelain --ignored) || { echo '?? (git status failed)'; return; }
  printf '%s\n' "$out" | awk '!/^!! / && NF {print; next} /^!! (publisher|contract)\/(.*\/)?(__pycache__\/?|[^\/]+\.py[co])$/ {print}'
}
wait_idle() {  # <seconds> <unit>...
  local left=$1 unit busy; shift
  while :; do
    busy=
    for unit in "$@"; do
      case $(systemctl is-active "$unit" 2>/dev/null || true) in active|activating|reloading|deactivating) busy=$unit ;; esac
    done
    [ -z "$busy" ] && return 0
    [ "$left" -gt 0 ] || return 1
    echo "  waiting for $busy to finish"
    sleep 10
    left=$((left-10))
  done
}

COMMIT= DRY=0 ROLLBACK=
while [ $# -gt 0 ]; do
  case $1 in
    --commit) COMMIT=${2:-}; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --rollback) ROLLBACK=${2:-}; shift 2 ;;
    *) echo "Usage: sudo bash $0 --commit <40-hex sha> [--dry-run] | --rollback <dir>"; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
if [ -n "$ROLLBACK" ]; then
  case $ROLLBACK in /opt/scalar-social/repo.pre-studiozero-[0-9]*Z) ;; *) echo "Refusing: --rollback takes a $REPO.pre-studiozero-<stamp> folder"; exit 2 ;; esac
else
  [[ $COMMIT =~ ^[0-9a-f]{40}$ ]] || { echo 'Refusing: --commit needs the full 40-character sha on StudioZero main'; exit 2; }
fi

say 'Preflight'
for tool in git ssh python3 runuser flock curl diff systemctl; do command -v "$tool" >/dev/null || { echo "Refusing: $tool missing"; exit 1; }; done
mv --help | grep -q -- '--exchange' || { echo 'Refusing: this mv has no --exchange (coreutils 9.5+ needed for an atomic swap)'; exit 1; }
[ -d "$REPO/.git" ] && [ ! -L "$REPO" ] || { echo "Refusing: $REPO is not a checkout"; exit 1; }
[ "$(stat -c %U "$REPO")" = "$UUSER" ] && [ -z "$(find "$REPO" -xdev ! -user "$UUSER" -print -quit)" ] \
  || { echo "Refusing: $REPO has files not owned by $UUSER"; exit 1; }
HEAD=$(ugit -C "$REPO" rev-parse --verify HEAD)
URL=$(ugit -C "$REPO" remote get-url origin)
DIRTY=$(dirty_lines "$REPO")
[ -z "$DIRTY" ] || { echo "Refusing: $REPO has local changes or Python bytecode:"; echo "$DIRTY" | head -20; exit 1; }
[ "$(ugit -C "$REPO" symbolic-ref --short -q HEAD || true)" = main ] || { echo "Refusing: $REPO is not on branch main"; exit 1; }
grep -q "'StudioZero'" "$REPO/publisher/app/updater.py" || { echo 'Refusing: the running updater does not accept StudioZero yet (ship that first)'; exit 1; }
case $(systemctl is-active scalar-social-update.service 2>/dev/null || true) in
  active|activating|reloading|deactivating) echo 'Refusing: a self-update is running'; exit 1 ;;
esac
for busy in "$USTATE/inbox/request.json" "$USTATE/inbox/request.taken.json" "$USTATE/units-pending.json"; do
  [ ! -e "$busy" ] || { echo "Refusing: $busy exists (an update or unit apply is pending; let it finish)"; exit 1; }
done
python3 -I -B - "$USTATE" "$HEAD" <<'PY' || exit 1
import json, sys
from pathlib import Path
state, head = Path(sys.argv[1]), sys.argv[2]
def read(name):
    try: return json.loads((state/name).read_text())
    except (OSError, ValueError): return {}
if read('units-apply.json').get('phase') in ('queued', 'running'):
    sys.exit('Refusing: a unit apply is queued or running')
if read('units-applied.json').get('commit') != head:
    sys.exit('Refusing: units-applied.json is not at HEAD (a unit apply is pending); let it finish first')
if read('status.json').get('phase') not in (None, 'idle', 'checked', 'complete', 'failed'):
    sys.exit(f"Refusing: update status phase is {read('status.json').get('phase')}")
PY
AVAIL=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[ "${AVAIL:-0}" -ge 120000 ] || { echo "Refusing: only $((AVAIL/1024)) MB available (120 MB needed for the clone)"; exit 1; }
echo "Checkout $REPO at $HEAD, origin $URL, clean."

# units-applied.json at the checkout's new HEAD: valid because publisher/ (incl. deploy/ and pi-package*.json) is
# byte-identical on both sides of the swap. Written by the update user in its own folder, as apply-units.sh does.
mark_units_applied() {
  as_update sh -c 'umask 022; printf "{\"commit\": \"%s\", \"appliedAt\": \"%s\"}\n" "$2" "$3" > "$1/.units-applied.tmp" && mv "$1/.units-applied.tmp" "$1/units-applied.json"' \
    sh "$USTATE" "$(ugit -C "$REPO" rev-parse --verify HEAD)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
restart_ui() {
  systemctl restart scalar-social-ui.service && sleep 3 && curl -fsS http://127.0.0.1:8765/api/health >/dev/null
}
# Stops the update path unit (no update may start mid-swap), then waits for a quiet minute: away from the autopilot
# runs and the daily post time, between the quarter-hour publisher/monitor ticks and the :20 stats read. Takes the
# publisher's runner.lock on fd 9 as the updater does.
PATH_WAS=
restore_path() { [ "$PATH_WAS" != active ] || systemctl start scalar-social-update.path || true; }
quiesce() {
  PATH_WAS=$(systemctl is-active scalar-social-update.path 2>/dev/null || true)
  systemctl stop scalar-social-update.path 2>/dev/null || true
  case $(systemctl is-active scalar-social-update.service 2>/dev/null || true) in
    active|activating|reloading|deactivating) echo 'Refusing: a self-update started meanwhile'; return 1 ;;
  esac
  python3 -I -B - <<'PY' || return 1
import datetime as dt, json, subprocess, sys
from zoneinfo import ZoneInfo
def stamp(prop):
    raw = subprocess.run(['systemctl', 'show', 'scalar-social-autopilot.timer', '-p', prop, '--value'], capture_output=True, text=True).stdout.strip()
    if not raw or raw == 'n/a':
        return None
    out = subprocess.run(['date', '-d', raw, '+%s'], capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else None
now = dt.datetime.now(dt.timezone.utc).timestamp()
nxt, last = stamp('NextElapseUSecRealtime'), stamp('LastTriggerUSec')
if nxt and nxt - now < 30*60:
    sys.exit('Refusing: the autopilot runs within 30 minutes; run again later (safe: 09:00-15:00 or 19:00-03:30)')
if last and now - last < 25*60:
    sys.exit('Refusing: the autopilot ran less than 25 minutes ago; run again later')
config = json.load(open('/etc/scalar-social/config.json'))
zone = ZoneInfo(config.get('timezone') or 'UTC')
local = dt.datetime.now(zone)
hour, minute = map(int, config['schedule']['time'].split(':'))
for day in (-1, 0, 1):
    slot = local.replace(hour=hour, minute=minute, second=0, microsecond=0) + dt.timedelta(days=day)
    if abs((slot - local).total_seconds()) < 30*60:
        sys.exit('Refusing: within 30 minutes of the daily post time; run again later')
print('Clear of the autopilot runs and the daily post time.')
PY
  wait_idle 600 scalar-social.service scalar-social-approve.service scalar-social-autopilot.service scalar-social-metrics.service \
    scalar-social-monitor.service || { echo 'Refusing: the publisher kept running for 10 minutes'; return 1; }
  local tries=0 minute
  while :; do
    minute=$((10#$(date +%M) % 30))
    [ "$minute" -ge 3 ] && [ "$minute" -le 12 ] && break
    [ "$tries" -lt 90 ] || { echo 'Refusing: no quiet minute within 30 minutes'; return 1; }
    [ "$tries" -gt 0 ] || echo '  waiting for a quiet minute (:03-:12 or :33-:42)'
    tries=$((tries+1)); sleep 20
  done
  [ -f "$STATE/runner.lock" ] && [ ! -L "$STATE/runner.lock" ] || { echo "Refusing: $STATE/runner.lock missing or a link"; return 1; }
  exec 9<"$STATE/runner.lock"
  flock -w 120 9 || { echo 'Refusing: the publisher held runner.lock for 2 minutes'; return 1; }
}
# The read-only state the move must not change: hashes only, never the contents.
snapshot() {  # <file>
  {
    echo "head $(ugit -C "$REPO" rev-parse HEAD) origin $(ugit -C "$REPO" remote get-url origin)"
    echo "trees $(ugit -C "$REPO" rev-parse HEAD:publisher HEAD:contract | tr '\n' ' ')"
    systemctl list-unit-files 'scalar-social*' --no-legend --no-pager | awk '{print "enabled", $1, $2}'
    systemctl list-units 'scalar-social*' --all --plain --no-legend --no-pager | grep -v '\.service ' | awk '{print "active", $1, $3, $4}'
    if [ -e "$STATE/PAUSED" ]; then echo 'PAUSED present'; else echo 'PAUSED absent'; fi
    sha256sum /etc/scalar-social/config.json "$STATE/manifests/approved.json" 2>/dev/null | awk '{print "sha256", $2, $1}'
  } > "$1"
}
post_check() {  # the updater's own check against the new origin, run as scalar-social like sync-pi.sh
  as_service python3 -I -B - "$REPO" "$1" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1] + '/publisher/app')
import updater
STATE, REPO, origin = updater.UPDATE_STATE, sys.argv[1], sys.argv[2]
end = time.time() + 20*60
while updater.busy(STATE) and time.time() < end:
    time.sleep(5)
asked = updater.utc()
updater.queue_request(STATE, 'check')
while time.time() < end:
    status = updater.current_status(STATE)
    if (status['check'] or {}).get('checkedAt', '') >= asked and not updater.busy(STATE):
        break
    time.sleep(5)
else:
    sys.exit('Timed out waiting for the update check')
check = status['check']
problems = [k for k, ok in (('fetchOk', check.get('fetchOk')), ('originOk', check.get('originOk')), ('branchOk', check.get('branchOk')),
                            ('clean', not check.get('dirty')), ('not diverged', not check.get('diverged')),
                            ('origin url', check.get('originUrl') == origin),
                            ('head', check.get('head') == updater.running_commit(REPO))) if not ok]
info = updater.info(STATE, REPO, updater.running_commit(REPO))
for key in ('restartNeeded', 'unitsChanged', 'piPackageChanged'):
    if info.get(key):
        problems.append(key)
print(f"Update check: behind {check.get('behind')}, ahead {check.get('ahead')}; {'OK' if not problems else 'FAILED: ' + ', '.join(problems)}")
sys.exit(1 if problems else 0)
PY
}

if [ -n "$ROLLBACK" ]; then
  say "Rolling back to $ROLLBACK"
  [ -d "$ROLLBACK/.git" ] && [ ! -L "$ROLLBACK" ] && [ "$(stat -c %U "$ROLLBACK")" = "$UUSER" ] || { echo "Refusing: $ROLLBACK is not a checkout owned by $UUSER"; exit 1; }
  trap restore_path EXIT
  quiesce
  chmod 755 "$ROLLBACK"
  mv --exchange -T "$ROLLBACK" "$REPO"
  mv -T "$ROLLBACK" "/opt/scalar-social/repo.studiozero-rolledback-$STAMP"
  chmod 700 "/opt/scalar-social/repo.studiozero-rolledback-$STAMP"
  exec 9<&-
  mark_units_applied
  restart_ui || { echo 'The UI did not come back; see journalctl -u scalar-social-ui -n 50'; exit 1; }
  restore_path; trap - EXIT
  echo "Back on $(ugit -C "$REPO" remote get-url origin) at $(ugit -C "$REPO" rev-parse HEAD); the StudioZero checkout is in /opt/scalar-social/repo.studiozero-rolledback-$STAMP."
  exit 0
fi

if [ "$URL" = "$NEW_ORIGIN" ]; then
  say 'Already on StudioZero: verifying only'
  if [ -d "$NEXT/.git" ] && [ ! -L "$NEXT" ]; then
    # Interrupted right after the swap: the old checkout is still at $NEXT.
    mv -T "$NEXT" "$ASIDE"; chmod 700 "$ASIDE"; echo "Moved the previous checkout to $ASIDE"
  fi
  post_check "$NEW_ORIGIN"
  exit $?
fi
case $URL in
  git@github.com-scalar:samirhusain26/scalargame-marketing.git|git@github.com-scalar:samirhusain26/scalargame-marketing-plan.git) ;;
  *) echo "Refusing: unexpected origin $URL"; exit 1 ;;
esac

say "Fresh partial + sparse clone of StudioZero into $NEXT (as $UUSER)"
if [ -e "$NEXT" ] || [ -L "$NEXT" ]; then
  [ -d "$NEXT" ] && [ ! -L "$NEXT" ] && [ "$(stat -c %U "$NEXT")" = "$UUSER" ] || { echo "Refusing: $NEXT exists and is not a leftover clone"; exit 1; }
  rm -rf -- "$NEXT"; echo "Removed a leftover $NEXT"
fi
install -d -m 755 -o "$UUSER" -g "$UUSER" "$NEXT"
ugit "${LOW_MEMORY[@]}" clone --quiet --filter=blob:none --no-checkout --branch main "$NEW_ORIGIN" "$NEXT"
ugit -C "$NEXT" merge-base --is-ancestor "$COMMIT" refs/remotes/origin/main || { echo "Refusing: $COMMIT is not on StudioZero main"; rm -rf -- "$NEXT"; exit 1; }
ugit -C "$NEXT" sparse-checkout set --cone publisher contract
ugit "${LOW_MEMORY[@]}" -C "$NEXT" checkout --quiet -B main "$COMMIT"
ugit -C "$NEXT" branch --quiet --set-upstream-to=origin/main main

say 'Verifying the clone'
fail() { echo "Refusing: $*"; rm -rf -- "$NEXT"; exit 1; }
[ "$(ugit -C "$NEXT" remote get-url origin)" = "$NEW_ORIGIN" ] || fail 'the clone has an unexpected origin'
[ "$(ugit -C "$NEXT" symbolic-ref --short -q HEAD || true)" = main ] || fail 'the clone is not on main'
[ -z "$(dirty_lines "$NEXT")" ] || fail 'the clone is not clean'
[ -z "$(find "$NEXT" -xdev ! -user "$UUSER" -print -quit)" ] || fail "the clone has files not owned by $UUSER"
OLD_TREES=$(ugit -C "$REPO" rev-parse HEAD:publisher HEAD:contract | tr '\n' ' ')
NEW_TREES=$(ugit -C "$NEXT" rev-parse HEAD:publisher HEAD:contract | tr '\n' ' ')
[ "$OLD_TREES" = "$NEW_TREES" ] || fail "publisher/ + contract/ differ (running $OLD_TREES, StudioZero $NEW_TREES)"
diff -r --no-dereference "$REPO/publisher" "$NEXT/publisher" >/dev/null && diff -r --no-dereference "$REPO/contract" "$NEXT/contract" >/dev/null \
  || fail 'the files on disk differ'
echo "publisher/ + contract/ identical: trees $NEW_TREES"
for need in publisher/app/updater.py publisher/app/static/index.html publisher/deploy/apply-units.sh \
    publisher/deploy/scalar-social-update.service publisher/deploy/scalar-social-update.path contract/library_contract.py; do
  [ -f "$NEXT/$need" ] || fail "$need missing"
done
grep -qx "User=$UUSER" "$NEXT/publisher/deploy/scalar-social-update.service" || fail 'the update unit is not hardened'
as_update /usr/bin/python3 -I -B -c 'import pathlib, sys; sys.path.insert(0, sys.argv[1]); import updater; updater.check_static(pathlib.Path(sys.argv[2]))' \
  "$NEXT/publisher/app" "$NEXT/publisher/app/static" || fail 'the UI bundle does not match MANIFEST.json'
echo "Root files that differ (checked out at the root in cone mode; informational):"
diff <(cd "$REPO" && find . -maxdepth 1 -type f | sort) <(cd "$NEXT" && find . -maxdepth 1 -type f | sort) | sed 's/^/  /' || true
if OUT=$(ugit -C "$NEXT" push --dry-run origin HEAD:refs/heads/readonly-probe 2>&1); then
  fail 'GitHub accepted a push with the deploy key; it must be read-only'
fi
# "marked as read only": the key is attached to StudioZero read-only. "denied to deploy key"/"Permission ... denied":
# it is still attached to the old repository (StudioZero is public, so reading works). Anything else proves nothing.
echo "$OUT" | grep -Eqi 'marked as read only|denied to deploy key|permission to .* denied' || fail "the read-only proof was inconclusive: $OUT"
echo 'Push refused: the key cannot write to StudioZero.'
echo "Old HEAD $HEAD ($URL); new HEAD $COMMIT ($NEW_ORIGIN)."
if [ "$DRY" = 1 ]; then
  rm -rf -- "$NEXT"
  echo 'Dry run: nothing live changed; the clone was removed.'
  exit 0
fi

say "Snapshot of the state the move must not change ($BACKUP)"
install -d -m 700 -o root -g root /var/backups/scalar-social "$BACKUP"
cp -a "$USTATE/status.json" "$USTATE/units-applied.json" "$USTATE/units-apply.json" "$BACKUP/" 2>/dev/null || true
snapshot "$BACKUP/before.txt"

say 'Waiting for a quiet moment'
SWAPPED=0
on_exit() {
  local code=$?
  if [ "$code" != 0 ] && [ "$SWAPPED" = 1 ]; then
    echo; echo 'Failed after the swap: swapping the previous checkout back.'
    if [ -d "$ASIDE/.git" ]; then chmod 755 "$ASIDE"; mv --exchange -T "$ASIDE" "$REPO" && mv -T "$ASIDE" "$NEXT"
    elif [ -d "$NEXT/.git" ]; then mv --exchange -T "$NEXT" "$REPO"; fi
    cp -a "$BACKUP/units-applied.json" "$USTATE/units-applied.json" 2>/dev/null || true
    restart_ui || echo 'The UI did not come back; see journalctl -u scalar-social-ui -n 50'
    echo "Now at $(ugit -C "$REPO" remote get-url origin) $(ugit -C "$REPO" rev-parse HEAD); the StudioZero clone is at $NEXT."
  fi
  restore_path
}
trap on_exit EXIT
quiesce

say 'Swapping the checkouts'
mv --exchange -T "$NEXT" "$REPO"
SWAPPED=1
mv -T "$NEXT" "$ASIDE"
chmod 700 "$ASIDE"
exec 9<&-
echo "$REPO is the StudioZero checkout; the previous one is $ASIDE (kept for rollback)."
mark_units_applied
restart_ui || { echo 'The UI did not come back on the new checkout'; exit 1; }
restore_path

say 'Verifying'
post_check "$NEW_ORIGIN"
snapshot "$BACKUP/after.txt"
if diff <(grep -v '^head \|^trees ' "$BACKUP/before.txt") <(grep -v '^head \|^trees ' "$BACKUP/after.txt"); then
  echo 'Units, PAUSED, config and approved schedule: unchanged.'
else
  echo 'Something above changed between before and after (check it; nothing was rolled back for it).'
fi
grep '^trees ' "$BACKUP/before.txt" "$BACKUP/after.txt"
SWAPPED=0
trap restore_path EXIT
cat <<EOF

Done: the Pi updates from $NEW_ORIGIN (Settings > Update; sync-pi.sh from the StudioZero checkout on the Mac).
Rollback while $ASIDE exists: sudo bash $REPO/publisher/deploy/migrate-origin.sh --rollback $ASIDE
Keep it until StudioZero has delivered one normal update, then: sudo rm -rf $ASIDE
EOF
