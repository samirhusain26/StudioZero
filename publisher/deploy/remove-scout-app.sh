#!/bin/bash
# Owner-run (sudo): remove the dead "scout" APP from the Pi (rebuild plan L12). The `scout` LOGIN USER,
# its home, Tailscale and everything scalar-social stay. Dry run by default: prints the exact plan.
#   sudo bash remove-scout-app.sh                          # dry run
#   sudo bash remove-scout-app.sh --apply                  # back up (root-only tarball), then remove
#   sudo bash remove-scout-app.sh --apply --shred-threads-token
#        also shreds /home/scout/.scalar-social-staging/THREADS_ACCESS_TOKEN, but only if the installed
#        credential /etc/scalar-social/credentials/THREADS_ACCESS_TOKEN exists.
#   --i-tested-sudo  required before it deletes an /etc/sudoers.d/scout that grants NOPASSWD: you confirm you ran
#        `sudo -k; sudo -v` as scout and your password worked (group sudo asks for it once the file is gone).
set -eu
APPLY=0
SHRED=0
TESTED=0
for arg in "$@"; do
  case $arg in
    --apply) APPLY=1 ;;
    --shred-threads-token) SHRED=1 ;;
    --i-tested-sudo) TESTED=1 ;;
    *) echo "Usage: sudo bash $0 [--apply] [--shred-threads-token] [--i-tested-sudo]"; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
id scout >/dev/null 2>&1 || { echo 'Refusing: user scout not found (wrong machine?)'; exit 1; }
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE=/var/backups/scout-app-$STAMP.tar.gz
SSH_CONFIG=/home/scout/.ssh/config
SUDOERS=/etc/sudoers.d/scout
STAGED_TOKEN=/home/scout/.scalar-social-staging/THREADS_ACCESS_TOKEN
INSTALLED_TOKEN=/etc/scalar-social/credentials/THREADS_ACCESS_TOKEN
UNITS=(scout-web.service scout-briefing@.service scout-job@.service
  scout-availability.timer scout-backup.timer scout-briefing-0700.timer scout-briefing-0715.timer scout-briefing-0730.timer
  scout-collect.timer scout-route.timer scout-router-devices.timer scout-router-usage.timer)
PATHS=(/home/scout/scout /etc/scout /var/lib/scout /var/log/scout /home/scout/.cache/uv
  /home/scout/.local/bin/uv /home/scout/.local/bin/uvx /home/scout/.ssh/scout_github_ed25519 /home/scout/.ssh/scout_github_ed25519.pub)
for target in "${UNITS[@]}" "${PATHS[@]}"; do
  case $target in *scalar-social*|*tailscale*) echo "Refusing: $target is out of scope"; exit 1 ;; esac
done
unit_files() {  # unit file and drop-in dir for $1, wherever systemd keeps them
  for dir in /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system; do
    [ ! -e "$dir/$1" ] || echo "$dir/$1"
    [ ! -d "$dir/$1.d" ] || echo "$dir/$1.d"
  done
}
github_block() {  # the `Host github.com` block (exactly that host) of scout's ssh config
  awk 'tolower($1)=="host"||tolower($1)=="match" {skip = (tolower($1)=="host" && NF==2 && $2=="github.com")} skip' "$SSH_CONFIG"
}
without_github_block() {
  awk 'tolower($1)=="host"||tolower($1)=="match" {skip = (tolower($1)=="host" && NF==2 && $2=="github.com")} !skip' "$SSH_CONFIG"
}

# /etc/sudoers.d/scout is handled on its own: deleting it must never leave scout (the owner's login) without sudo.
sudoers_grants() {  # any directive at all (comments and blank lines excluded; #include/#includedir are directives)
  grep -Ev '^[[:space:]]*($|#)' "$SUDOERS" >/dev/null 2>&1 || grep -Eq '^[[:space:]]*#include' "$SUDOERS" 2>/dev/null
}
SUDOERS_ACTION=absent
SUDOERS_REASON=
SUDOERS_OK=1
visudo -c >/dev/null 2>&1 || SUDOERS_OK=0
PASSWD_STATUS=$(passwd -S scout 2>/dev/null | awk '{print $2}')
if [ -L "$SUDOERS" ]; then
  if [ -e "$SUDOERS" ]; then
    SUDOERS_ACTION=keep; SUDOERS_REASON="it is a symlink to $(readlink "$SUDOERS"); inspect and remove it by hand (sudo visudo -c afterwards)"
  else
    SUDOERS_ACTION=remove; SUDOERS_REASON="a dangling symlink to $(readlink "$SUDOERS"); it grants nothing"
  fi
elif [ -e "$SUDOERS" ]; then
  if ! sudoers_grants; then
    SUDOERS_ACTION=remove; SUDOERS_REASON='it grants nothing'
  elif ! id -nG scout | tr ' ' '\n' | grep -qx sudo; then
    SUDOERS_ACTION=keep; SUDOERS_REASON='it grants scout sudo and scout is not in group sudo: deleting it would lock you out of sudo. To remove it later: sudo usermod -aG sudo scout, log in again, check sudo -v works with your password, then re-run'
  elif grep -q NOPASSWD "$SUDOERS" && [ "$PASSWD_STATUS" != P ]; then
    SUDOERS_ACTION=keep; SUDOERS_REASON="it grants passwordless sudo and scout has no usable password (passwd -S: ${PASSWD_STATUS:-unknown}), so group sudo could not be used. Set one (sudo passwd scout), test it (sudo -k; sudo -v), then re-run with --apply --i-tested-sudo"
  elif grep -q NOPASSWD "$SUDOERS" && [ "$TESTED" != 1 ]; then
    SUDOERS_ACTION=keep; SUDOERS_REASON='it grants passwordless sudo; group sudo will ask for your password instead. Log in as scout, run: sudo -k; sudo -v (type your password), then re-run with --apply --i-tested-sudo'
  else
    SUDOERS_ACTION=remove; SUDOERS_REASON='scout is in group sudo, which keeps sudo working (it may ask for your password where this file did not)'
  fi
fi

echo "== Plan ($([ "$APPLY" = 1 ] && echo APPLY || echo 'dry run: nothing changes'))"
echo '-- systemd units: stop, disable, remove unit file + drop-ins'
FILES=()
for unit in "${UNITS[@]}"; do
  found=$(unit_files "$unit")
  printf '  %-30s enabled=%s active=%s files=%s\n' "$unit" "$(systemctl is-enabled "$unit" 2>/dev/null || true)" \
    "$(systemctl is-active "$unit" 2>/dev/null || true)" "$(echo "$found" | tr '\n' ' ')"
  [ -z "$found" ] || while read -r file; do FILES+=("$file"); done <<< "$found"
done
OTHER=$(ls -d /etc/systemd/system/scout* 2>/dev/null | grep -vxF -f <(printf '%s\n' "${FILES[@]:-}") || true)
[ -z "$OTHER" ] || echo "  also present, NOT in the reviewed list, left alone: $(echo "$OTHER" | tr '\n' ' ')"
echo '-- paths: remove'
EXISTING=()
for path in "${PATHS[@]}"; do
  if [ -e "$path" ] || [ -L "$path" ]; then
    printf '  %-48s %s\n' "$path" "$(du -sh "$path" 2>/dev/null | cut -f1)"
    EXISTING+=("$path")
  else
    printf '  %-48s (absent)\n' "$path"
  fi
done
echo "-- $SUDOERS: $SUDOERS_ACTION${SUDOERS_REASON:+ ($SUDOERS_REASON)}"
if [ "$SUDOERS_ACTION" != absent ]; then
  if [ -f "$SUDOERS" ]; then sed 's/^/  | /' "$SUDOERS"; else ls -l "$SUDOERS" | sed 's/^/  | /'; fi
  echo "  groups of scout: $(id -nG scout); password status (passwd -S): ${PASSWD_STATUS:-unknown}"
fi
if [ "$SUDOERS_OK" != 1 ]; then
  echo "-- WARNING: sudoers does not validate now (sudo visudo -c). --apply will stop before changing anything."
fi
if [ -L "$SSH_CONFIG" ]; then
  echo "-- $SSH_CONFIG is a symlink (to $(readlink "$SSH_CONFIG")): left alone; remove its 'Host github.com' block by hand"
else
  echo "-- $SSH_CONFIG: remove the 'Host github.com' block (backup kept next to it)"
  if [ -f "$SSH_CONFIG" ] && [ -n "$(github_block)" ]; then github_block | sed 's/^/  | /'; else echo '  (no such block)'; fi
fi
echo "-- backup first: $ARCHIVE (root-only 0600; holds /etc/scout secrets, so keep it private)"
echo '-- untouched: the scout user and home, Tailscale, /etc/scalar-social, /opt/scalar-social, /var/lib/scalar-social'
if [ "$SHRED" = 1 ]; then
  if [ -s "$INSTALLED_TOKEN" ] && [ -f "$STAGED_TOKEN" ]; then echo "-- shred $STAGED_TOKEN (installed credential present)"
  else echo "-- will NOT shred $STAGED_TOKEN (installed credential missing or staged file absent)"; fi
fi
[ "$APPLY" = 1 ] || { echo; echo 'Dry run only. Re-run with --apply to do this.'; exit 0; }
[ "$SUDOERS_OK" = 1 ] || { echo; echo 'Refusing: sudoers does not validate before any change (sudo visudo -c). Fix that first; nothing was changed.'; exit 1; }

echo; echo "== Backing up to $ARCHIVE"
LIST=("${FILES[@]:-}" "${EXISTING[@]:-}")
[ ! -f "$SSH_CONFIG" ] || LIST+=("$SSH_CONFIG")
[ "$SUDOERS_ACTION" = absent ] || LIST+=("$SUDOERS")
REL=()
for item in "${LIST[@]}"; do [ -z "$item" ] || REL+=("${item#/}"); done
if [ "${#REL[@]}" -gt 0 ]; then
  install -d -m 755 /var/backups
  (umask 077; tar -czf "$ARCHIVE" -C / "${REL[@]}")
  chown root:root "$ARCHIVE"; chmod 600 "$ARCHIVE"
  ls -l "$ARCHIVE"
else
  echo '  nothing left to back up'
fi

echo '== Units'
for unit in "${UNITS[@]}"; do
  case $unit in
    *@.service) systemctl stop "${unit%@.service}@*.service" 2>/dev/null || true ;;
    *) systemctl stop "$unit" 2>/dev/null || true ;;
  esac
  systemctl disable "$unit" 2>/dev/null || true
done
for file in "${FILES[@]:-}"; do [ -z "$file" ] || { rm -rf -- "$file"; echo "  removed $file"; }; done
systemctl daemon-reload
systemctl reset-failed 'scout*' 2>/dev/null || true

echo '== Paths'
for path in "${EXISTING[@]:-}"; do [ -z "$path" ] || { rm -rf -- "$path"; echo "  removed $path"; }; done

echo "== $SUDOERS"
if [ "$SUDOERS_ACTION" = remove ]; then
  KEEP=$(mktemp -u /root/scout-sudoers.XXXXXX)
  cp -P -p -- "$SUDOERS" "$KEEP"
  rm -f -- "$SUDOERS"
  # Without the file scout must still have full sudo through group sudo (Debian: %sudo ALL=(ALL:ALL) ALL).
  if visudo -c >/dev/null && sudo -l -U scout 2>/dev/null | grep -Eq '^[[:space:]]+\(ALL( ?: ?ALL)?\)[[:space:]]+ALL[[:space:]]*$'; then
    rm -f -- "$KEEP"
    echo "  removed ($SUDOERS_REASON); sudo -l -U scout still shows:"
    sudo -l -U scout 2>/dev/null | grep -E '\(ALL' | sed 's/^/  | /'
  else
    mv -f -- "$KEEP" "$SUDOERS"
    echo "  RESTORED: without it sudoers did not validate (visudo -c) or sudo -l -U scout no longer showed (ALL) ALL; $SUDOERS put back unchanged"
  fi
else
  echo "  ${SUDOERS_ACTION}${SUDOERS_REASON:+: $SUDOERS_REASON}"
fi
visudo -c

if [ -f "$SSH_CONFIG" ] && [ ! -L "$SSH_CONFIG" ] && [ -n "$(github_block)" ]; then
  echo "== $SSH_CONFIG"
  runuser -u scout -- cp -p "$SSH_CONFIG" "$SSH_CONFIG.before-scout-removal-$STAMP"
  without_github_block | runuser -u scout -- sh -c 'umask 077; cat > "$1.new" && mv "$1.new" "$1"' sh "$SSH_CONFIG"
  echo "  removed the Host github.com block (backup: $SSH_CONFIG.before-scout-removal-$STAMP)"
fi

if [ "$SHRED" = 1 ]; then
  if [ -s "$INSTALLED_TOKEN" ] && [ -f "$STAGED_TOKEN" ]; then
    shred -u -- "$STAGED_TOKEN"
    echo "== Shredded $STAGED_TOKEN"
  else
    echo "== Not shredded: $INSTALLED_TOKEN missing or $STAGED_TOKEN absent"
  fi
fi
echo
systemctl list-units --all --no-pager 'scout*' || true
echo "Done. Restore: sudo tar -xzpf $ARCHIVE -C / && sudo systemctl daemon-reload"
