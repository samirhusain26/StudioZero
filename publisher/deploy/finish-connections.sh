#!/bin/sh
# Owner-run connection acceptance. All social platforms remain disabled.
set -eu
[ "$(id -u)" = 0 ] || exit 1
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
sh "$SOURCE/publisher/deploy/update-paused.sh"
python3 /opt/scalar-social/scripts/social/configure_paused.py --report /home/scout/scalar-buffer-identities.json --apply
MEDIA=/home/scout/scalar-media-probe.json
umask 077
systemd-run --quiet --wait --pipe --collect --uid=scalar-social --gid=scalar-social \
  -p WorkingDirectory=/opt/scalar-social \
  -p 'Environment=PATH=/opt/node22/bin:/usr/local/bin:/usr/bin:/bin NODE_OPTIONS=--max-old-space-size=180 WRANGLER_SEND_METRICS=false' \
  -p MemoryMax=300M -p TimeoutStartSec=300 \
  -p LoadCredential=CLOUDFLARE_API_TOKEN:/etc/scalar-social/credentials/CLOUDFLARE_API_TOKEN \
  /usr/bin/python3 /opt/scalar-social/scripts/social/media_probe.py > "$MEDIA"
chown scout:scout "$MEDIA"
chmod 600 "$MEDIA"
# Monitoring is independent of publishing. This service cannot dispatch social posts.
systemctl enable --now scalar-social-monitor.timer
systemctl start scalar-social-monitor.service
systemd-run --quiet --wait --pipe --collect --uid=scalar-social --gid=scalar-social \
  -p LoadCredential=HEALTHCHECKS_PING_URL:/etc/scalar-social/credentials/HEALTHCHECKS_PING_URL \
  /usr/bin/python3 /opt/scalar-social/scripts/social/operations.py alert-test
echo 'Media upload/delivery and heartbeat tested. Verify the deliberate failure email, then recover with: sudo systemctl start scalar-social-monitor.service'
echo 'Publishing timer is still disabled; no first public social post or recurring publishing was authorized.'
