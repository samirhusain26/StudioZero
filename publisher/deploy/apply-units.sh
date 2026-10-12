#!/bin/bash
# Runs by itself after a self-update that changed unit files or pi-package*.json: the update writes
# /var/lib/scalar-social-update/units-pending.json and scalar-social-apply-units.path starts
# scalar-social-apply-units.service, which runs this script as root with --auto (it removes the trigger first, waits
# for the update and publisher runs to finish, and reports in units-apply.json, shown on Settings > Update).
# Run it by hand once to install that path unit, or whenever the UI shows that the automatic apply failed:
#   sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh
# Installs the systemd units and the credential drop-ins from the checkout, reloads systemd, restarts the UI and
# re-enables what was already enabled. Exceptions: it always enables the two read-only post stats units
# (scalar-social-metrics.timer and .path, which never publish) and the autopilot timer (scalar-social-autopilot.timer,
# which refills the schedule and follows it; pausing in the UI stops it); whether the hourly reads run is the UI's switch
# (/var/lib/scalar-social/metrics/enabled, carried over once from the timer's earlier state, see 1b). It creates empty
# placeholders for missing stats credentials but never overwrites a credential, and never changes the pause state,
# channels or whether the publishing timer is enabled. If publisher/pi-package*.json differ from
# /opt/scalar-social/package*.json it reinstalls /opt/scalar-social/node_modules (old copy kept). Reports installed
# scalar-social units that are no longer in the repo (never deletes them). Records the applied commit for the UI only
# after everything succeeded.
# Refuses while a self-update runs, and stops the update path unit while it works. Safe to re-run.
set -eu
set -o pipefail
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
AUTO=0
[ "${1:-}" != --auto ] || AUTO=1
REPO=/opt/scalar-social/repo
OPT=/opt/scalar-social
USTATE=/var/lib/scalar-social-update
UUSER=scalar-social-update
UPD=/etc/scalar-social-update
UNITS=/etc/systemd/system
DROPINS=$UNITS/scalar-social.service.d
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP=/var/backups/scalar-social/units-$STAMP
CREDS=/etc/scalar-social/credentials
SUSER=scalar-social
METRICS=/var/lib/scalar-social/metrics
# Root-owned record that the one-time switch migration (1b) has run; scalar-social cannot write /etc/scalar-social.
METRICS_MIGRATED=/etc/scalar-social/metrics-switch-migrated
STATS_CREDENTIALS=(INSTAGRAM_ACCESS_TOKEN THREADS_ACCESS_TOKEN FACEBOOK_PAGE_TOKEN YOUTUBE_API_KEY BUFFER_API_KEY)
# git as the checkout's owner with only root-owned config, offline, as updater.py does.
ugit() {
  runuser -u "$UUSER" -- env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$UPD" GIT_CONFIG_GLOBAL=/dev/null \
    GIT_CONFIG_NOSYSTEM=1 GIT_ATTR_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_PAGER=cat PAGER=cat GIT_OPTIONAL_LOCKS=0 GIT_NO_LAZY_FETCH=1 \
    sh -c 'cd / && exec "$@"' sh git -c core.hooksPath=/dev/null -c core.fsmonitor=false -c protocol.allow=never "$@"
}
as_update() { (cd / && runuser -u "$UUSER" -- "$@"); }
as_social() { (cd / && runuser -u "$SUSER" -- "$@"); }
say() { printf '==> %s\n' "$*"; }
in_list() { local want=$1 item; shift; for item in "$@"; do [ "$item" = "$want" ] && return 0; done; return 1; }
# Copy a regular file out of the scalar-social checkout without following a link: the file is opened once and the
# opened file must be the same regular file that was checked.
copy_regular() {
  local before after
  [ -f "$1" ] && [ ! -L "$1" ] || return 1
  before=$(stat -c '%d:%i:%F' -- "$1")
  exec 3< "$1"
  after=$(stat -L -c '%d:%i:%F' /dev/fd/3)
  case ${after##*:} in 'regular file'|'regular empty file') ;; *) exec 3<&-; return 1 ;; esac
  if [ "$before" != "$after" ]; then exec 3<&-; return 1; fi
  cat <&3 > "$2" || { exec 3<&-; return 1; }
  exec 3<&-
}

# units-apply.json (Settings > Update): phase, commit, error and the last log lines, written by the update user into
# its own folder (0644, root never writes or follows a link there).
PENDING=$USTATE/units-pending.json
LOG=
HEAD=
record() {
  local log='[]'
  [ -z "$LOG" ] || log=$(tail -n 20 "$LOG" | python3 -I -c 'import json, sys; print(json.dumps([l.rstrip("\n")[:300] for l in sys.stdin]))') || log='[]'
  as_update python3 -I -c '
import datetime, json, os, sys
state, phase, commit, error, log = sys.argv[1:6]
data = {"phase": phase, "commit": commit or None, "error": error or None, "log": json.loads(log),
        "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
tmp = os.path.join(state, ".units-apply.tmp")
with open(tmp, "w") as f:
    json.dump(data, f, indent=1, sort_keys=True)
    f.write("\n")
os.chmod(tmp, 0o644)
os.replace(tmp, os.path.join(state, "units-apply.json"))
' "$USTATE" "$1" "$HEAD" "${2:-}" "$log" || echo 'WARNING: could not write units-apply.json'
}
# wait_idle <seconds> <unit>...: until none of the units is running (the publisher and updater runs are short).
wait_idle() {
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
TMP=
PATH_WAS=
cleanup() {
  local code=$?
  [ -z "$TMP" ] || rm -rf "$TMP"
  [ "$PATH_WAS" != active ] || systemctl start scalar-social-update.path || echo 'WARNING: could not restart scalar-social-update.path'
  if [ "$AUTO" = 1 ]; then
    if [ "$code" = 0 ]; then
      record ok
    else
      record failed "apply-units.sh stopped (exit $code). The last lines are below; fix the cause, then run it by hand once."
    fi
    rm -f "$LOG"
  fi
}
trap cleanup EXIT
# Remove the trigger before anything can fail, so the path unit cannot loop (a new update queues a new one); a run by
# hand covers it too, so enabling the path unit below never starts a second run.
rm -f "$PENDING"
if [ "$AUTO" = 1 ]; then
  LOG=$(mktemp /run/scalar-units-log.XXXXXX)
  exec > >(tee -a "$LOG") 2>&1
  # The commit being applied, so Settings matches this run to the checkout while it works (re-read below).
  HEAD=$(ugit -C "$REPO" rev-parse --verify HEAD 2>/dev/null || true)
  record running
  # The update that queued this run finishes after writing the trigger; a queued request starts another one.
  for _ in $(seq 1 90); do
    wait_idle 600 scalar-social-update.service || break
    [ -e "$USTATE/inbox/request.json" ] || break
    sleep 10
  done
fi

[ -d "$REPO/.git" ] || { echo "Refusing: $REPO is not a git checkout (run bootstrap-git.sh first)"; exit 1; }
id "$UUSER" >/dev/null 2>&1 || { echo "Refusing: user $UUSER missing (run bootstrap-git.sh first)"; exit 1; }
[ "$(stat -c %U "$REPO")" = "$UUSER" ] || { echo "Refusing: $REPO is not owned by $UUSER (run bootstrap-git.sh)"; exit 1; }
id "$SUSER" >/dev/null 2>&1 || { echo "Refusing: user $SUSER missing (run install.sh first)"; exit 1; }
[ -d "$CREDS" ] && [ ! -L "$CREDS" ] || { echo "Refusing: $CREDS is not a directory (run install.sh first)"; exit 1; }
if [ -e "$METRICS" ] || [ -L "$METRICS" ]; then
  [ -d "$METRICS" ] && [ ! -L "$METRICS" ] || { echo "Refusing: $METRICS exists but is not a directory; nothing was installed"; exit 1; }
fi
# Read before this run changes anything (the re-enable loop and 1b below enable this timer): the one-time switch
# migration in 1b decides from this value only.
METRICS_TIMER_BEFORE=$(systemctl is-enabled scalar-social-metrics.timer 2>/dev/null || true)
# No new update may start while units change: stop the path unit now, start it again on every exit path.
PATH_WAS=$(systemctl is-active scalar-social-update.path 2>/dev/null || true)
systemctl stop scalar-social-update.path 2>/dev/null || true
case $(systemctl is-active scalar-social-update.service 2>/dev/null || true) in
  active|activating|reloading|deactivating) echo 'Refusing: scalar-social-update.service is running (a self-update is in progress). Re-run when Settings > Update shows it finished.'; exit 1 ;;
esac
[ ! -e "$USTATE/inbox/request.json" ] || { echo 'Refusing: a self-update request is queued. Re-run when Settings > Update shows it finished.'; exit 1; }
HEAD=$(ugit -C "$REPO" rev-parse --verify HEAD)
# Tracked changes, untracked files, and ignored bytecode under publisher/ or contract/ (Python would run it).
PORCELAIN=$(ugit -C "$REPO" status --porcelain --ignored) || { echo "Refusing: git status failed in $REPO"; exit 1; }
DIRTY=$(printf '%s\n' "$PORCELAIN" | awk '!/^!! / && NF {print; next} /^!! (publisher|contract)\/(.*\/)?(__pycache__\/?|[^\/]+\.py[co])$/ {print}')
[ -z "$DIRTY" ] || { echo "Refusing: $REPO has local changes or Python bytecode; nothing was installed:"; echo "$DIRTY" | head -20; exit 1; }
# The UI unit reads its tailnet origin from here (not in git); without it the UI would refuse to start.
grep -Eq '^SCALAR_UI_ORIGIN=https://[a-z0-9-]+(\.[a-z0-9-]+)+$' /etc/scalar-social/ui.env 2>/dev/null \
  || { echo 'Refusing: /etc/scalar-social/ui.env needs SCALAR_UI_ORIGIN=https://<pi>.<tailnet>.ts.net (the Tailscale Serve address); nothing was installed'; exit 1; }
say "Applying units from $REPO at $HEAD"
TMP=$(mktemp -d /run/scalar-units.XXXXXX)

# 1. Units and credential drop-ins, staged in a root-only temp folder first (nothing is installed if one is bad).
NAMES=()
for unit in "$REPO"/publisher/deploy/scalar-social*.service "$REPO"/publisher/deploy/scalar-social*.path "$REPO"/publisher/deploy/scalar-social*.timer; do
  [ -e "$unit" ] || [ -L "$unit" ] || continue
  name=${unit##*/}
  copy_regular "$unit" "$TMP/$name" || { echo "Refusing: $unit is not a regular file; nothing was installed"; exit 1; }
  NAMES+=("$name")
done
# <platform>-credential.conf -> scalar-social.service.d/<platform>.conf (the existing LoadCredential drop-in names).
CONFS=()
for conf in "$REPO"/publisher/deploy/*-credential.conf; do
  [ -e "$conf" ] || [ -L "$conf" ] || continue
  name=${conf##*/}
  name=${name%-credential.conf}.conf
  copy_regular "$conf" "$TMP/dropin-$name" || { echo "Refusing: $conf is not a regular file; nothing was installed"; exit 1; }
  CONFS+=("$name")
done
install -d -m 700 -o root -g root /var/backups/scalar-social "$BACKUP"
cp -a "$UNITS"/scalar-social* "$BACKUP"/ 2>/dev/null || true
say "Previous units and drop-ins backed up to $BACKUP"
for name in "${NAMES[@]}"; do
  if cmp -s "$TMP/$name" "$UNITS/$name"; then
    echo "  unchanged  $name"
  else
    install -m 644 -o root -g root "$TMP/$name" "$UNITS/$name"
    echo "  installed  $name"
  fi
done
for name in "${CONFS[@]}"; do
  target=$DROPINS/$name
  credential=$(sed -n 's/^LoadCredential=[^:]*:\(.*\)$/\1/p' "$TMP/dropin-$name" | head -n 1)
  if cmp -s "$TMP/dropin-$name" "$target"; then
    echo "  unchanged  scalar-social.service.d/$name"
  elif [ -e "$target" ] || [ -s "$credential" ]; then
    install -d -m 755 -o root -g root "$DROPINS"
    install -m 644 -o root -g root "$TMP/dropin-$name" "$target"
    echo "  installed  scalar-social.service.d/$name"
  else
    # A LoadCredential= for a missing file would stop scalar-social.service from starting at all; an empty file is a
    # stats placeholder (1b, enable-metrics.sh), not a channel set up for publishing.
    echo "  skipped    scalar-social.service.d/$name (${credential:-its credential} is not installed; that channel is not set up)"
  fi
done
systemctl daemon-reload
say 'systemd reloaded'
for name in "${NAMES[@]}"; do
  [ "$name" != scalar-social.timer ] || continue  # the publishing timer's state belongs to activation only
  if [ "$(systemctl is-enabled "$name" 2>/dev/null || true)" = enabled ]; then
    systemctl reenable --quiet "$name"
    echo "  re-enabled $name"
  fi
done
echo "  scalar-social.timer left as it was: enabled=$(systemctl is-enabled scalar-social.timer 2>/dev/null || true) active=$(systemctl is-active scalar-social.timer 2>/dev/null || true)"
# Installed but no longer in the repo: report with the exact command; never deleted here.
for path in "$UNITS"/scalar-social*; do
  [ -e "$path" ] || [ -L "$path" ] || continue
  name=${path##*/}
  case $name in scalar-social.service.d) continue ;; esac
  in_list "$name" "${NAMES[@]}" && continue
  if [ -d "$path" ]; then
    echo "  not in the repo (left in place): $path. Remove: sudo rm -r $path && sudo systemctl daemon-reload"
  else
    echo "  not in the repo (left in place): $name. Remove: sudo systemctl disable --now $name && sudo rm $path && sudo systemctl daemon-reload"
  fi
done
for path in "$DROPINS"/*; do
  [ -e "$path" ] || [ -L "$path" ] || continue
  in_list "${path##*/}" "${CONFS[@]}" && continue
  echo "  drop-in not in the repo (left in place): $path. Remove: sudo rm $path && sudo systemctl daemon-reload"
done

# 1b. Post stats reader (read-only, never publishes). After the drop-ins above, so a placeholder created here never
# decides whether a publishing drop-in is installed.
for credential in "${STATS_CREDENTIALS[@]}"; do
  # Never overwrite (or follow) anything already there; contents are never read or printed.
  if [ ! -e "$CREDS/$credential" ] && [ ! -L "$CREDS/$credential" ]; then
    install -m 600 -o root -g root /dev/null "$CREDS/$credential"
    echo "  created empty placeholder credentials/$credential (reads as not configured)"
  fi
done
# The state folder belongs to scalar-social: created as that user (root never writes into its folders); an existing
# folder keeps its mode and owner.
as_social sh -c 'umask 077; [ -d "$1" ] || mkdir -m 700 "$1"' sh "$METRICS"
[ -d "$METRICS" ] && [ ! -L "$METRICS" ] || { echo "Refusing: $METRICS is not a directory"; exit 1; }
# One-time migration to the UI switch: hourly reads stay on if the timer was enabled before the first run of this
# version, otherwise they start off. The root-owned marker is written before the enable below, so a re-run (when the
# timer is enabled because this script enabled it) never recreates a flag the owner has since switched off.
if [ -e "$METRICS_MIGRATED" ] || [ -L "$METRICS_MIGRATED" ]; then
  echo "  hourly stats reads left as the UI switch has them (switch migration already done: $METRICS_MIGRATED)"
else
  if [ "$METRICS_TIMER_BEFORE" = enabled ]; then
    as_social sh -c 'umask 077; [ -e "$1" ] || : > "$1"' sh "$METRICS/enabled"
    echo "  hourly stats reads stay on (scalar-social-metrics.timer was enabled before this run)"
  else
    echo "  hourly stats reads start off (turn them on in the UI, or run enable-metrics.sh)"
  fi
  printf 'timerEnabledBefore=%s migratedAt=%s commit=%s\n' "${METRICS_TIMER_BEFORE:-unknown}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$HEAD" > "$TMP/metrics-migrated"
  install -m 644 -o root -g root "$TMP/metrics-migrated" "$METRICS_MIGRATED"
fi
# The exceptions to "re-enables only what was already enabled", for these units only: the two read-only stats units
# (the hourly timer does nothing while the switch is off; the path unit is the UI's "read now" request), the
# automatic apply after an update (scalar-social-apply-units.path, which runs this script), the autopilot timer
# (it does nothing while publishing is paused in the UI) and the Studio proxy (no network until studio-worker.sh
# configures the one worker address; it never publishes). Never scalar-social.timer, the pause state or channels.
STATS_UNITS=()
for name in scalar-social-metrics.timer scalar-social-metrics.path scalar-social-apply-units.path scalar-social-autopilot.timer scalar-social-studio-proxy.service; do
  if [ "$(systemctl is-enabled "$name" 2>/dev/null || true)" = masked ]; then
    echo "  $name is masked: left as it is (unmask it to use it)"
  else
    STATS_UNITS+=("$name")
  fi
done
[ ${#STATS_UNITS[@]} = 0 ] || systemctl enable --now --quiet "${STATS_UNITS[@]}"
echo "  enabled ${STATS_UNITS[*]:-nothing}; hourly stats reads are $([ -e "$METRICS/enabled" ] && echo on || echo off)"

# 2. Node packages for wrangler (owner step only; the updater never runs npm).
if cmp -s "$REPO/publisher/pi-package.json" "$OPT/package.json" && cmp -s "$REPO/publisher/pi-package-lock.json" "$OPT/package-lock.json"; then
  say 'pi-package*.json unchanged; node_modules left as is'
else
  if [ "$AUTO" = 1 ]; then
    wait_idle 900 scalar-social.service scalar-social-approve.service || { echo 'Refusing npm step: the publisher kept running for 15 minutes'; exit 1; }
  fi
  for busy in scalar-social.service scalar-social-approve.service; do
    [ "$(systemctl is-active "$busy" 2>/dev/null || true)" != active ] || { echo "Refusing npm step: $busy is running; re-run when it has finished"; exit 1; }
  done
  [ -x /opt/node22/bin/npm ] || { echo 'Refusing npm step: /opt/node22/bin/npm missing'; exit 1; }
  for file in pi-package.json pi-package-lock.json; do
    copy_regular "$REPO/publisher/$file" "$TMP/$file" || { echo "Refusing: publisher/$file is not a regular file"; exit 1; }
  done
  OLD=$OPT/node_modules.before-$STAMP
  say "pi-package*.json changed: reinstalling $OPT/node_modules (old copy: $OLD)"
  cp -p "$OPT/package.json" "$OPT/package-lock.json" "$BACKUP"/ 2>/dev/null || true
  [ ! -d "$OPT/node_modules" ] || mv "$OPT/node_modules" "$OLD"
  install -m 644 -o root -g root "$TMP/pi-package.json" "$OPT/package.json"
  install -m 644 -o root -g root "$TMP/pi-package-lock.json" "$OPT/package-lock.json"
  if ! (cd "$OPT" && PATH=/opt/node22/bin:$PATH NODE_OPTIONS=--max-old-space-size=180 npm ci --omit=dev --ignore-scripts --no-audit --no-fund); then
    echo 'npm ci failed: restoring the previous packages (units.applied not recorded)'
    rm -rf "$OPT/node_modules"
    [ ! -d "$OLD" ] || mv "$OLD" "$OPT/node_modules"
    cp -p "$BACKUP/package.json" "$BACKUP/package-lock.json" "$OPT"/ 2>/dev/null || true
    exit 1
  fi
  echo "  node_modules reinstalled; remove $OLD once wrangler works"
fi

# 3. Restart the UI (and the path watchers) on the new units; record what was applied only if all of it worked.
systemctl try-restart scalar-social-approve.path scalar-social-metrics.path scalar-social-apply-units.path scalar-social-studio-proxy.service
if [ "$(systemctl is-enabled scalar-social-ui.service 2>/dev/null || true)" = enabled ]; then
  # Type=notify: restart itself fails when the UI crashes or never becomes ready, so it must not end the script
  # (set -e) before the rollback is printed.
  if systemctl restart scalar-social-ui.service && sleep 3 && curl -fsS http://127.0.0.1:8765/api/health; then
    echo
  else
    echo
    echo "The UI did not start on the new units; units-applied.json NOT updated (the UI keeps showing this command)."
    echo "See: journalctl -u scalar-social-ui -n 50"
    echo "Rollback of the units: sudo cp -a $BACKUP/scalar-social* $UNITS/ && sudo systemctl daemon-reload && sudo systemctl restart scalar-social-ui.service"
    exit 1
  fi
fi
# Written by the update user into its own folder (root never follows a link there); 0644 so the UI reads it.
as_update sh -c 'umask 022; printf "{\"commit\": \"%s\", \"appliedAt\": \"%s\"}\n" "$2" "$3" > "$1/.units-applied.tmp" && mv "$1/.units-applied.tmp" "$1/units-applied.json"' \
  sh "$USTATE" "$HEAD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "Recorded $HEAD in $USTATE/units-applied.json"
systemctl list-units --all --no-pager 'scalar-social*'
echo "Done. Rollback: sudo cp -a $BACKUP/scalar-social* $UNITS/ && sudo systemctl daemon-reload && sudo systemctl restart scalar-social-ui.service"
