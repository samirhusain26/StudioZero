#!/bin/bash
# Owner-run (sudo). Turns the hourly post stats reads on, optionally storing the YouTube key or reading past days:
#   sudo /opt/scalar-social/repo/publisher/deploy/enable-metrics.sh                 # turn hourly stats reads on
#   sudo /opt/scalar-social/repo/publisher/deploy/enable-metrics.sh --youtube-key   # also store a YouTube Data API key
#   sudo /opt/scalar-social/repo/publisher/deploy/enable-metrics.sh --backfill 28   # also read 28 past days of account stats
# Whether the hourly reads run is the flag /var/lib/scalar-social/metrics/enabled: the UI's Post stats switch turns it
# on and off (a timer run without it reads nothing), and the UI can ask for a one-off read. apply-units.sh now installs
# scalar-social-metrics.{service,timer,path}, creates the empty credential placeholders and the stats folder, and
# enables the timer and path unit, so this script is needed only for the YouTube key or a backfill. It still works on
# its own: it creates any missing placeholder (an empty file reads as "not configured") and the stats folder, sets the
# flag (so running it turns hourly reads on; the UI switch can turn them off again) and enables the timer and path
# unit. Never overwrites a token other than the YouTube key you type, and never touches publishing, the pause state or
# the publishing timer. Safe to re-run.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
CREDS=/etc/scalar-social/credentials
METRICS=/var/lib/scalar-social/metrics
YOUTUBE=0
BACKFILL=0
while [ $# -gt 0 ]; do
  case $1 in
    --youtube-key) YOUTUBE=1 ;;
    --backfill) shift; BACKFILL=${1:-}; [[ "$BACKFILL" =~ ^[0-9]{1,2}$ ]] && [ "$BACKFILL" -le 93 ] || { echo '--backfill takes 0-93 days'; exit 1; } ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
  shift
done
for unit in service timer path; do
  [ -f "/etc/systemd/system/scalar-social-metrics.$unit" ] || {
    echo 'Refusing: run apply-units.sh first (Settings > Update shows "Unit files changed").'; exit 1; }
done
if [ -e "$METRICS" ] || [ -L "$METRICS" ]; then
  [ -d "$METRICS" ] && [ ! -L "$METRICS" ] || { echo "Refusing: $METRICS exists but is not a directory"; exit 1; }
fi
for credential in INSTAGRAM_ACCESS_TOKEN THREADS_ACCESS_TOKEN FACEBOOK_PAGE_TOKEN YOUTUBE_API_KEY; do
  if [ ! -f "$CREDS/$credential" ]; then
    install -m 600 -o root -g root /dev/null "$CREDS/$credential"
    echo "  created empty placeholder $credential"
  fi
done
if [ "$YOUTUBE" = 1 ]; then
  read -rsp 'YouTube Data API key (input hidden): ' KEY; echo
  [[ "$KEY" =~ ^[A-Za-z0-9_-]{20,80}$ ]] || { echo 'That does not look like an API key; nothing changed.'; exit 1; }
  TMP=$(mktemp "$CREDS/.youtube.XXXXXX")
  printf '%s\n' "$KEY" > "$TMP"
  chmod 600 "$TMP"
  mv -f "$TMP" "$CREDS/YOUTUBE_API_KEY"
  unset KEY
  echo '  stored YOUTUBE_API_KEY'
fi
# The stats folder and flag belong to scalar-social: created as that user (root never writes into its folders); an
# existing folder keeps its mode and owner.
(cd / && runuser -u scalar-social -- sh -c 'umask 077; [ -d "$1" ] || mkdir -m 700 "$1"; [ -e "$1/enabled" ] || : > "$1/enabled"' sh "$METRICS")
[ -d "$METRICS" ] && [ ! -L "$METRICS" ] && [ -e "$METRICS/enabled" ] || { echo "Could not turn hourly stats reads on in $METRICS"; exit 1; }
echo '  hourly stats reads on (the UI Post stats switch can turn them off)'
systemctl daemon-reload
systemctl enable --now scalar-social-metrics.timer scalar-social-metrics.path
for unit in scalar-social-metrics.timer scalar-social-metrics.path; do
  echo "$unit: enabled=$(systemctl is-enabled "$unit") active=$(systemctl is-active "$unit")"
done
if [ "$BACKFILL" -gt 0 ]; then
  # One-off run with the unit's user and credentials, plus --backfill; the timer keeps its normal reads.
  systemd-run --quiet --wait --pipe --collect -p User=scalar-social -p Group=scalar-social -p UMask=0077 \
    -p ReadWritePaths=/var/lib/scalar-social -p ProtectSystem=strict -p ProtectHome=true -p NoNewPrivileges=true \
    -p LoadCredential=INSTAGRAM_ACCESS_TOKEN:$CREDS/INSTAGRAM_ACCESS_TOKEN -p LoadCredential=THREADS_ACCESS_TOKEN:$CREDS/THREADS_ACCESS_TOKEN \
    -p LoadCredential=FACEBOOK_PAGE_TOKEN:$CREDS/FACEBOOK_PAGE_TOKEN -p LoadCredential=YOUTUBE_API_KEY:$CREDS/YOUTUBE_API_KEY \
    /usr/bin/python3 /opt/scalar-social/repo/publisher/app/metrics.py collect --config /etc/scalar-social/config.json \
    --state /var/lib/scalar-social --backfill "$BACKFILL"
fi
echo 'First read: sudo systemctl start scalar-social-metrics.service && journalctl -u scalar-social-metrics.service -n 5'
