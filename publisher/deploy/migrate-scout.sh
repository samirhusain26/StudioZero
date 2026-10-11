#!/bin/sh
# Owner-approved migration only. No Scout data, secrets, checkout or Tailscale is removed.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the intended Pi'; exit 1; }
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# First install Scalar separately, still paused, without interrupting Scout.
sh "$SOURCE/publisher/deploy/install.sh"
runuser -u scalar-social -- python3 /opt/scalar-social/scripts/social/runner.py status \
  --config /etc/scalar-social/config.json --state /var/lib/scalar-social >/dev/null
# Preserve exact enabled/active states for recovery; no credentials enter this record.
install -d -m 700 /var/lib/scalar-social/migration
systemctl list-unit-files 'scout*' --no-legend --no-pager > /var/lib/scalar-social/migration/scout-unit-states.txt
systemctl list-units 'scout*' --all --plain --no-legend --no-pager > /var/lib/scalar-social/migration/scout-active-states.txt
# Stop timers before services so no new collection starts during handover.
for unit in $(systemctl list-unit-files 'scout*.timer' --no-legend --no-pager | awk '{print $1}'); do
  systemctl disable --now "$unit"
done
for unit in $(systemctl list-units 'scout*.service' --all --plain --no-legend --no-pager | awk '{print $1}'); do
  systemctl stop "$unit"
done
systemctl disable scout-web.service
# Leave the old private tailnet endpoint intact for possible recovery, no public exposure.
echo 'Scout stopped; files and secrets preserved. Scalar is installed, paused, and its timer is not enabled.'
echo 'Do not enable recurring publishing before account, media, monitoring and launch approvals.'
