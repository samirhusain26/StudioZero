#!/bin/sh
# Owner-run, read-only snapshot of live Scalar state for the UI staging demo (plan L10).
# WAL-safe ledger copy through the existing SQLite backup API, run as scalar-social.
# Copies no credentials. Live config, ledger, timers, channels and pause state stay unchanged;
# the only live-side effect is a temporary backup file that is removed again.
# Files under /var/lib/scalar-social are read as scalar-social (never as root), so a link planted
# there cannot make root copy anything that user could not already read.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
STATE=/var/lib/scalar-social
DEMO=/home/scout/.scalar-social-staging/ui-demo
DEST=$DEMO/snapshot
[ ! -e "$DEST" ] || { echo "$DEST already exists; move it aside first"; exit 1; }
install -d -m 700 -o scout -g scout "$DEMO" "$DEST" "$DEST/site" "$DEST/site/clips"
as_service() { runuser -u scalar-social -- "$@"; }
copy_out() {  # $1 = path under $STATE, $2 = destination; read as scalar-social, written by scout
  as_service cat -- "$STATE/$1" | runuser -u scout -- sh -c 'umask 077; cat > "$1"' sh "$2"
}
NAME=.ui-demo-ledger-$(date -u +%Y%m%dT%H%M%S).sqlite3
as_service python3 /opt/scalar-social/scripts/social/operations.py backup --state "$STATE" --destination "$STATE/$NAME"
copy_out "$NAME" "$DEST/ledger.sqlite3"
as_service rm -f -- "$STATE/$NAME"
# config.json holds account identifiers and routes, never credential values.
install -m 600 -o scout -g scout /etc/scalar-social/config.json "$DEST/config.json"
for name in catalog.json health.json threads-token-health.json instagram-token-health.json instagram-token-failure.json; do
  if as_service test -f "$STATE/$name"; then copy_out "$name" "$DEST/$name"; fi
done
for clip in $(as_service sh -c 'cd /var/lib/scalar-social && ls site/clips/*.mp4 2>/dev/null' || true); do
  copy_out "$clip" "$DEST/$clip"
done
stat -c '%a %U:%G %n' /etc/scalar-social/config.json
echo "Snapshot ready in $DEST (no credentials copied). Live state unchanged."
