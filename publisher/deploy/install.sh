#!/bin/sh
# Prepared installer. Run only on the intended Pi after deployment approval.
# OS imaging, account agreements, OAuth and secret entry are user-operated.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the intended Pi'; exit 1; }
# Since the git bootstrap the Pi runs from /opt/scalar-social/repo; copying files over it would be wrong.
[ ! -e /opt/scalar-social/repo ] || { echo 'Refusing: /opt/scalar-social/repo exists, so this Pi runs from a git checkout. Update from the UI; for unit or package changes run sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh (first setup: publisher/deploy/bootstrap-git.sh). See publisher/docs/SELF_UPDATE.md.'; exit 1; }
# Units in the repo point at the git checkout; this copy install keeps the old layout.
to_copy_layout() { sed -e 's#/opt/scalar-social/repo/publisher/app/static #/opt/scalar-social/ui #' -e 's#/opt/scalar-social/repo/publisher/app/#/opt/scalar-social/scripts/social/#g' "$1"; }
install_units() { for unit in "$@"; do case $unit in *-update.*) continue ;; esac; to_copy_layout "$unit" > "/etc/systemd/system/${unit##*/}"; chmod 644 "/etc/systemd/system/${unit##*/}"; done; }
[ "$(uname -m)" = aarch64 ] || { echo 'Use Raspberry Pi OS Lite 64-bit'; exit 1; }
[ "$(systemctl is-active scalar-social.timer 2>/dev/null || true)" != active ] || { echo "Pause the existing Scalar timer before installation"; exit 1; }
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ -f "$SOURCE/contract/library_contract.py" ] || { echo "Refusing: contract/library_contract.py is missing from the staged copy (stage publisher/ and contract/)."; exit 1; }
apt-get update -qq
apt-get install -y -qq python3 ffmpeg ca-certificates curl xz-utils
NODE_TMP=$(mktemp -d)
trap 'rm -rf "$NODE_TMP"' EXIT
curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt -o "$NODE_TMP/SHASUMS256.txt"
NODE_FILE=$(awk '/node-v22\.[0-9]+\.[0-9]+-linux-arm64.tar.xz$/ {print $2}' "$NODE_TMP/SHASUMS256.txt")
[ -n "$NODE_FILE" ] || { echo 'Official Node 22 ARM64 distribution unavailable'; exit 1; }
curl -fsSL "https://nodejs.org/dist/latest-v22.x/$NODE_FILE" -o "$NODE_TMP/$NODE_FILE"
(cd "$NODE_TMP" && awk -v file="$NODE_FILE" '$2==file' SHASUMS256.txt | sha256sum -c - >/dev/null)
install -d /opt/node22
tar -xJf "$NODE_TMP/$NODE_FILE" -C /opt/node22 --strip-components=1
PATH=/opt/node22/bin:$PATH
export PATH
NODE_OPTIONS=--max-old-space-size=180
export NODE_OPTIONS
id scalar-social >/dev/null 2>&1 || useradd --system --home /var/lib/scalar-social --shell /usr/sbin/nologin scalar-social
install -d -m 755 /opt/scalar-social/scripts/social /opt/scalar-social/deploy/pi
install -d -m 750 -o root -g scalar-social /etc/scalar-social
install -d -m 700 -o root -g root /etc/scalar-social/credentials
for credential in BUFFER_API_KEY CLOUDFLARE_API_TOKEN HEALTHCHECKS_PING_URL THREADS_ACCESS_TOKEN; do
  [ -f "/etc/scalar-social/credentials/$credential" ] || install -m 600 /dev/null "/etc/scalar-social/credentials/$credential"
done
install -d -m 700 -o scalar-social -g scalar-social /var/lib/scalar-social
install -m 644 "$SOURCE"/publisher/app/*.py "$SOURCE"/contract/library_contract.py /opt/scalar-social/scripts/social/
install_units "$SOURCE"/publisher/deploy/scalar-social*.service "$SOURCE"/publisher/deploy/scalar-social*.timer
install -m 644 "$SOURCE"/publisher/pi-package.json /opt/scalar-social/package.json
install -m 644 "$SOURCE"/publisher/pi-package-lock.json /opt/scalar-social/package-lock.json
cd /opt/scalar-social
npm ci --omit=dev --ignore-scripts --no-audit --no-fund >/dev/null
[ -f /etc/scalar-social/config.json ] || install -m 640 -o root -g scalar-social "$SOURCE"/publisher/config.example.json /etc/scalar-social/config.json
# Require owner-reviewed local config and credentials before enabling; never unpause here.
systemctl daemon-reload
echo 'Installed but timer is disabled and configuration remains paused.'
echo 'Next: review config, load credentials through secure local input, verify dry run, then approve activation.'
