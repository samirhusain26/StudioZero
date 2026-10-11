#!/bin/sh
# Owner-run: install the private management UI and approval applier while publishing stays paused.
# Never unpauses, never enables channels or the publisher timer, never touches Tailscale, the router
# or credential permissions. Run from the staged copy: sudo sh publisher/deploy/install-ui-paused.sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
# Since the git bootstrap the Pi runs from /opt/scalar-social/repo; copying files over it would be wrong.
[ ! -e /opt/scalar-social/repo ] || { echo 'Refusing: /opt/scalar-social/repo exists, so this Pi runs from a git checkout. Update from the UI; for unit or package changes run sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh (first setup: publisher/deploy/bootstrap-git.sh). See publisher/docs/SELF_UPDATE.md.'; exit 1; }
# Units in the repo point at the git checkout; this copy install keeps the old layout.
to_copy_layout() { sed -e 's#/opt/scalar-social/repo/publisher/app/static #/opt/scalar-social/ui #' -e 's#/opt/scalar-social/repo/publisher/app/#/opt/scalar-social/scripts/social/#g' "$1"; }
install_units() { for unit in "$@"; do case $unit in *-update.*) continue ;; esac; to_copy_layout "$unit" > "/etc/systemd/system/${unit##*/}"; chmod 644 "/etc/systemd/system/${unit##*/}"; done; }
[ "$(uname -m)" = aarch64 ] || { echo 'Expected the ARM64 Pi'; exit 1; }
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ -f "$SOURCE/contract/library_contract.py" ] || { echo "Refusing: contract/library_contract.py is missing from the staged copy (stage publisher/ and contract/)."; exit 1; }
STATE=/var/lib/scalar-social
CONFIG=/etc/scalar-social/config.json
STAMP=$(date -u +%Y%m%dT%H%M%S)

# 1. Refuse unless the publisher is fully paused.
[ "$(systemctl is-active scalar-social.timer 2>/dev/null || true)" != active ] || { echo 'Refusing: scalar-social.timer is active'; exit 1; }
[ "$(systemctl is-enabled scalar-social.timer 2>/dev/null || true)" = disabled ] || { echo 'Refusing: scalar-social.timer must be disabled'; exit 1; }
python3 - "$CONFIG" "$STATE" <<'PY'
import json, sys
from pathlib import Path
config = json.loads(Path(sys.argv[1]).read_text())
assert config['paused'] and not any(c['enabled'] for c in config['channels'].values()), 'Refusing: config must stay paused with all channels disabled'
assert (Path(sys.argv[2])/'PAUSED').exists(), 'Refusing: PAUSED sentinel missing'
PY
[ -f "$SOURCE/publisher/app/static/index.html" ] || { echo 'Refusing: built UI missing (publisher/app/static)'; exit 1; }
[ ! -e "$SOURCE/publisher/app/static/.env" ] || { echo 'Refusing: unexpected file in UI build'; exit 1; }
# The live publisher unit must differ from the staged one only by --catalog → --manifest
# (credential drop-ins in scalar-social.service.d/ are left as they are).
REVIEWED=$(mktemp)
trap 'rm -f "$REVIEWED"' EXIT
to_copy_layout "$SOURCE/publisher/deploy/scalar-social.service" > "$REVIEWED"
sed 's#--catalog /var/lib/scalar-social/catalog.json#--manifest /var/lib/scalar-social/manifests/approved.json#' \
  /etc/systemd/system/scalar-social.service | cmp -s - "$REVIEWED" \
  || grep -q -- '--manifest /var/lib/scalar-social/manifests/approved.json' /etc/systemd/system/scalar-social.service \
  || { echo 'Refusing: live scalar-social.service differs from the reviewed version'; exit 1; }

# 2. Consistent ledger backup before any change.
BACKUP=$STATE/backup-ui-$STAMP.sqlite3
runuser -u scalar-social -- python3 /opt/scalar-social/scripts/social/operations.py backup --state "$STATE" --destination "$BACKUP"
# Root-only rollback copy: never under $STATE, which the unprivileged service user controls.
install -d -m 700 -o root -g root /var/backups/scalar-social
cp /etc/systemd/system/scalar-social.service "/var/backups/scalar-social/scalar-social.service.before-ui-$STAMP"

# 3. Code, compiled UI and state directories.
install -m 644 "$SOURCE"/publisher/app/*.py "$SOURCE"/contract/library_contract.py /opt/scalar-social/scripts/social/
rm -rf /opt/scalar-social/ui.new
install -d -m 755 /opt/scalar-social/ui.new
cp -R "$SOURCE/publisher/app/static/." /opt/scalar-social/ui.new/
rm -f /opt/scalar-social/ui.new/MANIFEST.json /opt/scalar-social/ui.new/.DS_Store
chown -R root:root /opt/scalar-social/ui.new
find /opt/scalar-social/ui.new -type d -exec chmod 755 {} +
find /opt/scalar-social/ui.new -type f -exec chmod 644 {} +
rm -rf /opt/scalar-social/ui.old
[ ! -d /opt/scalar-social/ui ] || mv /opt/scalar-social/ui /opt/scalar-social/ui.old
mv /opt/scalar-social/ui.new /opt/scalar-social/ui
rm -rf /opt/scalar-social/ui.old
# Created by the service user itself, so root never follows a link planted under $STATE.
runuser -u scalar-social -- sh -c 'umask 077; cd /var/lib/scalar-social && mkdir -p library/objects library/covers library/.incoming manifests approval/history site/library'

# 4. Units: UI (enabled), approval path/service, publisher switched to --manifest (timer untouched).
install_units "$SOURCE/publisher/deploy/scalar-social-ui.service" "$SOURCE/publisher/deploy/scalar-social-approve.path" \
  "$SOURCE/publisher/deploy/scalar-social-approve.service" "$SOURCE/publisher/deploy/scalar-social.service"

# 5. UI passcode (owner types it; hidden input, never in argv or logs).
if [ ! -s /etc/scalar-social/credentials/UI_PASSCODE ]; then
  echo 'Choose the UI passcode (4 or more characters; a 4-digit PIN is fine):'
  python3 /opt/scalar-social/scripts/social/credential_entry.py UI_PASSCODE
fi

# 6. Report (never silently change) configuration permissions.
PERMS=$(stat -c '%a %U:%G' "$CONFIG")
if [ "$PERMS" != '640 root:scalar-social' ]; then
  echo "WARNING: $CONFIG is $PERMS; expected 640 root:scalar-social (monitor and UI fail closed). Not changed."
fi

systemctl daemon-reload
systemctl enable --now scalar-social-ui.service
systemctl enable --now scalar-social-approve.path

# 7. Post-install verification (still paused).
sleep 3
curl -fsS http://127.0.0.1:8765/api/health && echo
systemctl --no-pager --lines=0 status scalar-social-ui.service || true
systemctl list-timers --all --no-pager 'scalar-social*'
echo "scalar-social.timer: enabled=$(systemctl is-enabled scalar-social.timer 2>/dev/null || true) active=$(systemctl is-active scalar-social.timer 2>/dev/null || true)"
runuser -u scalar-social -- python3 /opt/scalar-social/scripts/social/operations.py check || true
echo "Installed. Open the Pi UI (its Tailscale Serve address) from a tailnet device. Publishing remains paused;"
echo "channels and the publisher timer are unchanged. Ledger backup: $BACKUP"
