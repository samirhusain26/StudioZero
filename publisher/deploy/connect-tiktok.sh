#!/bin/sh
# Owner-run with sudo after connecting TikTok @studiozeroflow (personal account) in Buffer, so the three Free slots are
# X, YouTube and TikTok (Instagram posts through its direct route). Reads Buffer identities, then applies
# them with every channel disabled, publishing paused and the schedule approval cleared. X and YouTube keep
# their posting tests when their connection is unchanged. Never posts. Guide: publisher/docs/TIKTOK.md
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.'; exit 1; }
APP=/opt/scalar-social/repo/publisher/app
[ -f "$APP/configure_paused.py" ] || { echo 'Needs the git checkout: run publisher/deploy/bootstrap-git.sh first, then update to this commit.'; exit 1; }
REPORT=/home/scout/scalar-buffer-identities.json
umask 077
systemd-run --quiet --wait --pipe --collect --uid=scalar-social --gid=scalar-social \
  -p WorkingDirectory=/opt/scalar-social \
  -p LoadCredential=BUFFER_API_KEY:/etc/scalar-social/credentials/BUFFER_API_KEY \
  /usr/bin/python3 "$APP/inspect_buffer.py" /etc/scalar-social/config.json /var/lib/scalar-social > "$REPORT"
chown scout:scout "$REPORT"
python3 -I -B "$APP/configure_paused.py" --report "$REPORT" --config /etc/scalar-social/config.json --apply
echo 'Next: the one-time TikTok test post (publisher/docs/TIKTOK.md, step 3). Publishing stays paused; approve a new schedule afterwards.'
