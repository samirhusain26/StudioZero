#!/bin/sh
# Opt-in: run the story worker agent at login on this host (launchd on macOS, a systemd user unit on Linux).
#   sh scripts/install-agent.sh            install and start (needs scripts/agent-token.py first)
#   sh scripts/install-agent.sh --remove   stop and remove
# The agent listens on 127.0.0.1:8911 only. Expose it to the tailnet with Tailscale Serve on this host, e.g.
#   tailscale serve --bg --https=8911 http://127.0.0.1:8911
# then give the Pi its address: python3 scripts/agent-token.py --send-to-pi --url https://<this host>.<tailnet>.ts.net:8911 --addr <tailnet IP>
set -eu
cd "$(dirname "$0")/.."
ENGINE=$(pwd)
PY=$ENGINE/.venv/bin/python
LABEL=com.studiozero.story-agent
[ -x "$PY" ] || { echo "No venv at $ENGINE/.venv (python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt)"; exit 1; }
case $(uname) in
  Darwin)
    PLIST=$HOME/Library/LaunchAgents/$LABEL.plist
    if [ "${1:-}" = --remove ]; then
      launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
      rm -f "$PLIST"; echo "Removed $LABEL"; exit 0
    fi
    mkdir -p "$HOME/Library/LaunchAgents" "$ENGINE/output/agent"
    cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>-m</string><string>src.agent</string></array>
  <key>WorkingDirectory</key><string>$ENGINE</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>$ENGINE/output/agent/agent.log</string>
  <key>StandardErrorPath</key><string>$ENGINE/output/agent/agent.log</string>
</dict></plist>
PL
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Installed and started $LABEL (log: output/agent/agent.log)" ;;
  Linux)
    UNIT=$HOME/.config/systemd/user/studio-story-agent.service
    if [ "${1:-}" = --remove ]; then
      systemctl --user disable --now studio-story-agent.service 2>/dev/null || true
      rm -f "$UNIT"; systemctl --user daemon-reload; echo "Removed studio-story-agent"; exit 0
    fi
    mkdir -p "$(dirname "$UNIT")"
    printf '[Unit]\nDescription=StudioZero story worker agent\n\n[Service]\nWorkingDirectory=%s\nExecStart=%s -m src.agent\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n' "$ENGINE" "$PY" > "$UNIT"
    systemctl --user daemon-reload
    systemctl --user enable --now studio-story-agent.service
    echo "Installed and started studio-story-agent (journalctl --user -u studio-story-agent)" ;;
  *) echo "Unsupported host $(uname)"; exit 1 ;;
esac
