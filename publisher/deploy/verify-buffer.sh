#!/bin/sh
# Owner invokes with sudo; captures only public identities and sanitized error categories.
set -eu
[ "$(id -u)" = 0 ] || exit 1
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
install -m 644 "$SOURCE/publisher/app/inspect_buffer.py" /opt/scalar-social/scripts/social/inspect_buffer.py
install -m 644 "$SOURCE/publisher/app/buffer_adapter.py" /opt/scalar-social/scripts/social/buffer_adapter.py
REPORT=/home/scout/scalar-buffer-identities.json
ERROR=/home/scout/scalar-buffer-error.txt
umask 077
CODE=0
systemd-run --wait --pipe --collect --uid=scalar-social --gid=scalar-social \
  -p WorkingDirectory=/opt/scalar-social \
  -p LoadCredential=BUFFER_API_KEY:/etc/scalar-social/credentials/BUFFER_API_KEY \
  /usr/bin/python3 /opt/scalar-social/scripts/social/inspect_buffer.py /etc/scalar-social/config.json /var/lib/scalar-social \
  > "$REPORT" 2> "$ERROR" || CODE=$?
chown scout:scout "$REPORT" "$ERROR"
chmod 600 "$REPORT" "$ERROR"
if [ "$CODE" != 0 ]; then
  cat "$ERROR"
  exit "$CODE"
fi
echo 'Buffer identity report saved privately for read-only verification. No post created.'
