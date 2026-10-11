#!/bin/sh
# Install the reviewed publisher update without credentials, activation or media deployment.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
# Since the git bootstrap the Pi runs from /opt/scalar-social/repo; copying files over it would be wrong.
[ ! -e /opt/scalar-social/repo ] || { echo 'Refusing: /opt/scalar-social/repo exists, so this Pi runs from a git checkout. Update from the UI; for unit or package changes run sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh (first setup: publisher/deploy/bootstrap-git.sh). See publisher/docs/SELF_UPDATE.md.'; exit 1; }
# Units in the repo point at the git checkout; this copy install keeps the old layout.
to_copy_layout() { sed -e 's#/opt/scalar-social/repo/publisher/app/static #/opt/scalar-social/ui #' -e 's#/opt/scalar-social/repo/publisher/app/#/opt/scalar-social/scripts/social/#g' "$1"; }
install_units() { for unit in "$@"; do case $unit in *-update.*) continue ;; esac; to_copy_layout "$unit" > "/etc/systemd/system/${unit##*/}"; chmod 644 "/etc/systemd/system/${unit##*/}"; done; }
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ -f "$SOURCE/contract/library_contract.py" ] || { echo "Refusing: contract/library_contract.py is missing from the staged copy (stage publisher/ and contract/)."; exit 1; }
[ "$(systemctl is-active scalar-social.timer 2>/dev/null || true)" != active ] || { echo 'Pause the publishing timer first'; exit 1; }
python3 - <<'PY'
import json
from pathlib import Path
config = json.loads(Path('/etc/scalar-social/config.json').read_text())
assert config['paused'] and not any(c['enabled'] for c in config['channels'].values()), 'Must remain paused with all channels disabled'
assert Path('/var/lib/scalar-social/PAUSED').exists(), 'Pause sentinel required'
PY
BACKUP=/var/lib/scalar-social/backup-instagram-$(date -u +%Y%m%dT%H%M%S).sqlite3
python3 "$SOURCE/publisher/app/operations.py" backup --destination "$BACKUP"
chown scalar-social:scalar-social "$BACKUP"
install -m 644 "$SOURCE"/publisher/app/*.py "$SOURCE"/contract/library_contract.py /opt/scalar-social/scripts/social/
install_units "$SOURCE"/publisher/deploy/scalar-social-instagram-refresh.service "$SOURCE"/publisher/deploy/scalar-social-instagram-refresh.timer
systemctl daemon-reload
echo 'Publisher runtime updated while paused. Instagram credentials, route, renewal activation and live acceptance remain pending.'

