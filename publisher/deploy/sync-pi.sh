#!/usr/bin/env bash
# Mac-side. Bring the Pi checkout to the commit that is local HEAD and GitHub main, through the Pi's own updater
# (the same check -> "UPDATE TO <sha>" -> apply path as Settings -> Update), then confirm all three match.
# Usage: publisher/deploy/sync-pi.sh            (commit and push to main first)
#        SCALAR_PI=<user>@<pi>.local publisher/deploy/sync-pi.sh
set -euo pipefail

PI=${SCALAR_PI:-scalar-pi}
cd "$(git rev-parse --show-toplevel)"

[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "Not on main." >&2; exit 1; }
[ -z "$(git status --porcelain -- publisher contract)" ] || { echo "Uncommitted changes under publisher/ or contract/: commit and push first." >&2; exit 1; }
git fetch -q origin main
head=$(git rev-parse HEAD)
origin=$(git rev-parse origin/main)
[ "$head" = "$origin" ] || { echo "Local HEAD ${head:0:12} is not origin/main ${origin:0:12}: push (or pull) first." >&2; exit 1; }

echo "Target ${head:0:12}; updating $PI"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI" "cd / && sudo -u scalar-social python3 -I -B - $head" <<'PY'
import sys, time
sys.path.insert(0, '/opt/scalar-social/repo/publisher/app')
import updater

STATE, REPO, target = updater.UPDATE_STATE, '/opt/scalar-social/repo', sys.argv[1]


def wait(done, limit, what):
    end = time.time() + limit
    while time.time() < end:
        status = updater.current_status(STATE)
        if done(status):
            return status
        time.sleep(5)
    sys.exit(f'Timed out waiting for {what}; phase {updater.current_status(STATE)["phase"]}.')


def idle():
    return wait(lambda s: not updater.busy(STATE), 20*60, 'the updater to go idle')


if updater.running_commit(REPO) == target:
    print(f'Pi already on {target[:12]}.')
    sys.exit(0)

idle()
asked = updater.utc()
updater.queue_request(STATE, 'check')
status = wait(lambda s: (s['check'] or {}).get('checkedAt', '') >= asked and not updater.busy(STATE), 10*60, 'the check')
check = status['check']
if check.get('error') or not check.get('fetchOk'):
    sys.exit(f"Check failed: {check.get('error')}")
if check.get('origin') != target:
    sys.exit(f"The Pi sees GitHub main at {str(check.get('origin'))[:12]}, not {target[:12]}.")

try:
    updater.start(STATE, REPO, updater.running_commit(REPO), f'UPDATE TO {target}')
except updater.Refused as error:
    sys.exit(f'Refused: {error}')
print('Applying (the updater runs the quick tests, then restarts the UI)...')
status = wait(lambda s: s['phase'] in ('complete', 'failed'), 30*60, 'the update')
print('\n'.join(status['log'][-12:]))
if status['phase'] != 'complete' or updater.running_commit(REPO) != target:
    sys.exit(f"Update did not complete: {status['error']}")
units = updater.read_json(updater.folder(STATE)/updater.UNITS_APPLY, updater.SMALL_JSON_MAX)
if isinstance(units, dict) and units.get('commit') == target:
    print(f"Unit/package apply for this commit: {units.get('phase')} (Settings -> Update shows the result).")
print(f'Pi on {target[:12]}.')
PY

pi=$(ssh -o BatchMode=yes "$PI" 'git -c safe.directory=/opt/scalar-social/repo -C /opt/scalar-social/repo rev-parse HEAD')
[ "$pi" = "$head" ] || { echo "Pi is on ${pi:0:12}, expected ${head:0:12}." >&2; exit 1; }
echo "In sync: local = origin/main = Pi = ${head:0:12}"
