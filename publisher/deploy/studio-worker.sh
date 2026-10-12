#!/bin/bash
# Pi-local setup of the Studio proxy's worker (never in git): the story worker's Tailscale Serve address, its tailnet
# IP (the only address the proxy may reach) and the agent token, read from stdin and never printed.
#   ssh scalar-pi 'sudo /opt/scalar-social/repo/publisher/deploy/studio-worker.sh --url https://<laptop>.<tailnet>.ts.net --addr 100.x.y.z' < token
#   (engines/story/scripts/agent-token.py --send-to-pi does exactly this)
#   sudo …/studio-worker.sh --remove      back to "Worker offline"
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
UNIT=scalar-social-studio-proxy.service
DROPIN=/etc/systemd/system/$UNIT.d/worker.conf
CRED=/etc/scalar-social/credentials/STUDIO_AGENT_TOKEN
if [ "${1:-}" = --remove ]; then
  rm -f "$DROPIN" "$CRED"
  systemctl daemon-reload
  systemctl try-restart "$UNIT"
  echo "Worker removed; the Studio shows Worker offline."
  exit 0
fi
URL= ADDR=
while [ $# -gt 0 ]; do
  case $1 in
    --url) URL=$2; shift 2 ;;
    --addr) ADDR=$2; shift 2 ;;
    *) echo "Unknown option $1"; exit 2 ;;
  esac
done
[[ "$URL" =~ ^https://[a-z0-9-]+(\.[a-z0-9-]+)+(:[0-9]{1,5})?/?$ ]] || { echo 'Refusing: --url must be https://<laptop>.<tailnet>.ts.net'; exit 1; }
python3 -I -c 'import ipaddress, sys; ip = ipaddress.ip_address(sys.argv[1]); sys.exit(0 if ip in ipaddress.ip_network("100.64.0.0/10") or ip in ipaddress.ip_network("fd7a:115c:a1e0::/48") else 1)' "$ADDR" 2>/dev/null \
  || { echo 'Refusing: --addr must be the laptop'"'"'s tailnet IP (100.64.0.0/10 or fd7a:115c:a1e0::/48)'; exit 1; }
TOKEN=$(head -c 512 | tr -d '\r\n')
[[ "$TOKEN" =~ ^[A-Za-z0-9_-]{32,256}$ ]] || { echo 'Refusing: no token on stdin (32+ url-safe characters)'; exit 1; }
install -d -m 700 -o root -g root /etc/scalar-social/credentials
( umask 077; printf '%s' "$TOKEN" > "$CRED.tmp" && mv "$CRED.tmp" "$CRED" )
unset TOKEN
install -d -m 755 -o root -g root "$(dirname "$DROPIN")"
cat > "$DROPIN.tmp" <<CONF
# Pi-local (studio-worker.sh); never in git.
[Service]
Environment=STUDIO_WORKER_URL=$URL
Environment=STUDIO_WORKER_ADDR=$ADDR
LoadCredential=STUDIO_AGENT_TOKEN:$CRED
IPAddressAllow=$ADDR
CONF
chmod 644 "$DROPIN.tmp" && mv "$DROPIN.tmp" "$DROPIN"
systemctl daemon-reload
systemctl enable --now --quiet "$UNIT"
systemctl restart "$UNIT"
sleep 1
systemctl is-active --quiet "$UNIT" && echo "Studio proxy configured for the worker at $URL (token stored root-only)." \
  || { echo "The proxy did not start: journalctl -u $UNIT -n 30"; exit 1; }
