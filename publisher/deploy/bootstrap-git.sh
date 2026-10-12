#!/bin/bash
# Owner-run once (sudo) to move the Pi from the copied install to a git checkout that the UI can update:
#   sudo bash <staged copy>/publisher/deploy/bootstrap-git.sh
# Creates the system user scalar-social-update (owns and alone writes the checkout; runs the update unit), a
# root-owned folder /etc/scalar-social-update with a read-only deploy key (you add it on GitHub), an ssh config for
# the github.com-scalar alias and GitHub's published SSH host keys. Clones the sparse cone of publisher/deploy/sparse-paths (partial, sparse)
# to /opt/scalar-social/repo, proves the key cannot push, creates the update state folder and its inbox, backs up
# the current units and code, installs the units from the checkout, enables scalar-social-update.path and restarts
# the UI. Never touches /etc/scalar-social, credentials, other /var/lib content, the pause state or the publishing
# timer. Safe to re-run: every step checks what is already there. Design: publisher/docs/SELF_UPDATE.md.
set -eu
set -o pipefail
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Pi'; exit 1; }
REPO=/opt/scalar-social/repo
STATE=/var/lib/scalar-social              # scalar-social's state (and passwd home); runner.lock lives here
USTATE=/var/lib/scalar-social-update      # the update user's state: status.json, units-applied.json, inbox/
UUSER=scalar-social-update
# Root-owned (0750 root:scalar-social-update): HOME, ssh config, deploy key and known_hosts of every git call the
# update unit makes. Neither scalar-social nor the update user can change anything there.
UPD=/etc/scalar-social-update
KEY=$UPD/deploy_key
# The public StudioZero repository (it replaced the private, now archived scalargame-marketing-plan; the updater
# still accepts the old names so an old checkout keeps verifying).
ORIGIN=git@github.com-scalar:samirhusain26/StudioZero.git
KEYS_URL=https://github.com/samirhusain26/StudioZero/settings/keys
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP=/var/backups/scalar-social/pre-git-$STAMP
LOW_MEMORY=(-c pack.threads=1 -c pack.windowMemory=32m -c core.deltaBaseCacheLimit=16m -c core.packedGitLimit=64m -c core.packedGitWindowSize=16m)
HARDENED=(-c core.hooksPath=/dev/null -c core.fsmonitor=false -c protocol.allow=never -c protocol.ssh.allow=always -c protocol.file.allow=never)
# git and ssh as the update user with only root-owned config, exactly as updater.py runs them (umask 022: the
# checkout stays readable, never writable, for the scalar-social services). From / so git never trips over an
# unreadable working directory (e.g. /root).
as_update() {
  runuser -u "$UUSER" -- env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$UPD" GIT_CONFIG_GLOBAL=/dev/null \
    GIT_CONFIG_NOSYSTEM=1 GIT_ATTR_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_PAGER=cat PAGER=cat GIT_SSH_COMMAND="ssh -F $UPD/ssh_config" \
    sh -c 'umask 022; cd / && exec "$@"' sh "$@"
}
ugit() { as_update git "${HARDENED[@]}" "$@"; }
# Writes under $STATE are made by scalar-social itself, so root never follows a link planted there.
as_service() { (cd / && runuser -u scalar-social -- "$@"); }
say() { printf '\n==> %s\n' "$*"; }
# Tracked changes, untracked files, and ignored bytecode under publisher/ or contract/ (Python would run it).
dirty_lines() {
  local out
  out=$(ugit -C "$1" status --porcelain --ignored) || { echo '?? (git status failed)'; return; }
  printf '%s\n' "$out" | awk '!/^!! / && NF {print; next} /^!! (publisher|contract)\/(.*\/)?(__pycache__\/?|[^\/]+\.py[co])$/ {print}'
}
# The sparse cone listed in publisher/deploy/sparse-paths at <rev> (the updater applies the same list on every update);
# publisher and contract always. Plain lowercase paths only.
sparse_paths() {
  local rev=$1 line out=()
  while IFS= read -r line; do
    line=${line%%#*}; line=${line//[[:space:]]/}
    [ -z "$line" ] && continue
    [[ "$line" =~ ^[a-z0-9_-]+(/[a-z0-9_-]+){0,4}$ ]] || { echo "Refusing: invalid sparse path '$line'" >&2; return 1; }
    out+=("$line")
  done < <(ugit -C "$2" show "$rev:publisher/deploy/sparse-paths" 2>/dev/null || printf 'publisher\ncontract\n')
  printf '%s\n' publisher contract "${out[@]}" | sort -u
}
# Moves a checkout that must not be reused out of the way, root-only.
move_aside() {
  local aside=/opt/scalar-social/repo.$2-$STAMP
  mv "$1" "$aside"; chown -R -h root:root "$aside"; chmod 700 "$aside"
  echo "Moved $1 to $aside (root-only; $3). Remove it once this works."
}
# Everything the units need, checked in checkout $1 before any unit changes: origin, branch, clean, an ancestor
# of GitHub main, the UI bundle matching MANIFEST.json, and every repo file a unit references.
verify_checkout() {
  local dir=$1 url dirty unit ref
  url=$(ugit -C "$dir" remote get-url origin)
  case $url in
    git@github.com-scalar:samirhusain26/scalargame-marketing.git|git@github.com-scalar:samirhusain26/scalargame-marketing-plan.git|\
    git@github.com-scalar:samirhusain26/StudioZero.git) echo "origin $url";;
    *) echo "Refusing: $dir has origin $url"; return 1;;
  esac
  [ "$(ugit -C "$dir" symbolic-ref --short -q HEAD || true)" = main ] || { echo "Refusing: $dir is not on branch main"; return 1; }
  ugit "${LOW_MEMORY[@]}" -C "$dir" fetch --no-tags --quiet origin +refs/heads/main:refs/remotes/origin/main
  dirty=$(dirty_lines "$dir")
  [ -z "$dirty" ] || { echo "Refusing: $dir has local changes (or Python bytecode):"; echo "$dirty" | head -20; return 1; }
  ugit -C "$dir" merge-base --is-ancestor HEAD refs/remotes/origin/main || { echo "Refusing: $dir HEAD is not on GitHub main (diverged); reconcile it by hand first"; return 1; }
  ugit -C "$dir" log -1 --format='HEAD %H %s'
  for need in publisher/app/updater.py publisher/app/static/index.html publisher/deploy/apply-units.sh \
      publisher/deploy/scalar-social-update.service publisher/deploy/scalar-social-update.path contract/library_contract.py; do
    [ -f "$dir/$need" ] || { echo "Refusing: $dir/$need missing (push the self-update work to GitHub main first)"; return 1; }
  done
  grep -qx "User=$UUSER" "$dir/publisher/deploy/scalar-social-update.service" \
    || { echo "Refusing: the checkout's update unit predates the $UUSER hardening (push the current main first)"; return 1; }
  for unit in "$dir"/publisher/deploy/scalar-social*.service "$dir"/publisher/deploy/scalar-social*.path "$dir"/publisher/deploy/scalar-social*.timer; do
    [ -f "$unit" ] || continue
    for ref in $(grep -o '/opt/scalar-social/repo/[^ ]*' "$unit" | sort -u); do
      [ -e "$dir${ref#/opt/scalar-social/repo}" ] || { echo "Refusing: ${unit##*/} needs $ref, which the checkout lacks"; return 1; }
    done
  done
  as_update /usr/bin/python3 -I -B -c 'import pathlib, sys; sys.path.insert(0, sys.argv[1]); import updater; updater.check_static(pathlib.Path(sys.argv[2])); print("UI bundle matches MANIFEST.json")' \
    "$dir/publisher/app" "$dir/publisher/app/static" || { echo "Refusing: $dir/publisher/app/static does not match its MANIFEST.json"; return 1; }
}
UNITS_TOUCHED=0
print_rollback() {
  cat <<EOF

Rollback to the copied install (pre-git code):
  sudo systemctl disable --now scalar-social-update.path
  sudo systemctl stop scalar-social-update.service
  sudo cp -a $BACKUP/systemd/scalar-social* /etc/systemd/system/
  sudo rm -f /etc/systemd/system/scalar-social-update.path /etc/systemd/system/scalar-social-update.service
  sudo systemctl daemon-reload && sudo systemctl restart scalar-social-ui.service
  (/opt/scalar-social/scripts and /opt/scalar-social/ui were left in place; copies are in $BACKUP/opt)
  Caution: the copied code is older. If newer code already ran and changed state in /var/lib/scalar-social (for
  example the library index), the old code may not understand it; ask Claude before rolling back after real use.
EOF
}
on_exit() {
  local code=$?
  if [ "$code" != 0 ] && [ "$UNITS_TOUCHED" = 1 ]; then
    echo; echo "bootstrap-git.sh stopped with an error after the units were changed."
    print_rollback
  fi
}
trap on_exit EXIT

say 'Preflight'
id scalar-social >/dev/null 2>&1 || { echo 'Refusing: user scalar-social missing'; exit 1; }
[ "$(getent passwd scalar-social | cut -d: -f6)" = "$STATE" ] || { echo "Refusing: scalar-social's home is not $STATE"; exit 1; }
for tool in git ssh ssh-keygen curl python3 runuser useradd stat awk; do command -v "$tool" >/dev/null || { echo "Refusing: $tool missing"; exit 1; }; done
[ "$(systemctl is-active scalar-social.timer 2>/dev/null || true)" != active ] || { echo 'Refusing: scalar-social.timer is active (publishing must stay paused)'; exit 1; }
[ "$(systemctl is-enabled scalar-social.timer 2>/dev/null || true)" != enabled ] || { echo 'Refusing: scalar-social.timer is enabled (publishing must stay paused; it would start at the next boot)'; exit 1; }
if [ -z "${TMUX:-}" ] && [ -z "${STY:-}" ]; then
  if command -v tmux >/dev/null; then
    echo 'Tip: run this inside tmux (tmux new -s bootstrap) so a dropped SSH connection cannot cut it off halfway.'
  else
    echo 'Tip: a dropped SSH connection would stop this script; tmux helps (optional: sudo apt install tmux, then run it inside tmux).'
  fi
fi
python3 -I - <<'PY'
import json, sys
from pathlib import Path
config = json.loads(Path('/etc/scalar-social/config.json').read_text())
if not (config['paused'] and not any(c['enabled'] for c in config['channels'].values())):
    sys.exit('Refusing: config must stay paused with all channels disabled')
if not Path('/var/lib/scalar-social/PAUSED').exists():
    sys.exit('Refusing: /var/lib/scalar-social/PAUSED missing')
PY
echo 'Paused config, PAUSED present, publishing timer inactive.'

say "System user $UUSER (owns the checkout, runs the update unit; no login, no home)"
if id "$UUSER" >/dev/null 2>&1; then
  echo "Exists: $(id "$UUSER")"
else
  useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin "$UUSER"
  echo "Created: $(id "$UUSER")"
fi
id -nG "$UUSER" | tr ' ' '\n' | grep -qx scalar-social && { echo "Refusing: $UUSER must not be in group scalar-social"; exit 1; }
id -nG scalar-social | tr ' ' '\n' | grep -qx "$UUSER" && { echo "Refusing: scalar-social must not be in group $UUSER"; exit 1; }

say "Root-owned git/ssh folder $UPD"
[ ! -L "$UPD" ] || { echo "Refusing: $UPD is a symlink"; exit 1; }
install -d -m 750 -o root -g "$UUSER" "$UPD"
for file in "$KEY" "$KEY.pub" "$UPD/ssh_config" "$UPD/known_hosts"; do
  [ ! -L "$file" ] || { echo "Refusing: $file is a symlink"; exit 1; }
done
ROTATED=
if [ -f "$KEY" ] && [ "$(stat -c %G "$KEY")" != "$UUSER" ]; then
  # An earlier draft made the key readable by group scalar-social; any scalar-social process could have copied it.
  mv "$KEY" "$KEY.revoke-$STAMP"; mv "$KEY.pub" "$KEY.pub.revoke-$STAMP" 2>/dev/null || true
  ROTATED=$KEY.pub.revoke-$STAMP
  echo "The old key was readable by group $(stat -c %G "$KEY.revoke-$STAMP"): moved to $KEY.revoke-$STAMP; a new one is made."
fi
if [ -f "$KEY" ]; then
  echo "Key exists: $KEY (kept)"
else
  ssh-keygen -q -t ed25519 -N '' -C 'scalar-social-update@scout-readonly-deploy' -f "$KEY"
  echo "Created $KEY"
fi
# OpenSSH checks a private key's permissions only when the key file belongs to the user running ssh
# (sshkey_perm_ok). Root-owned 0640, group scalar-social-update: the update unit can read it but cannot change or
# replace it (the file and the folder belong to root), and scalar-social cannot read it at all.
chown "root:$UUSER" "$KEY"; chmod 640 "$KEY"
chown root:root "$KEY.pub"; chmod 644 "$KEY.pub"
# GitHub's published host keys (docs.github.com "GitHub's SSH key fingerprints", checked 2026-10-08):
#   SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU (Ed25519)
#   SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM (ECDSA)
#   SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s (RSA)
cat > "$UPD/known_hosts.new" <<'EOF'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
EOF
cat > "$UPD/ssh_config.new" <<EOF
# Read by the update unit only through GIT_SSH_COMMAND="ssh -F $UPD/ssh_config" (no ~/.ssh, no /etc/ssh).
Host github.com-scalar
  HostName github.com
  User git
  IdentityFile $KEY
  IdentitiesOnly yes
  IdentityAgent none
  HostKeyAlias github.com
  UserKnownHostsFile $UPD/known_hosts
  GlobalKnownHostsFile /dev/null
  StrictHostKeyChecking yes
  UpdateHostKeys no
  BatchMode yes
  PasswordAuthentication no
  ForwardAgent no
  ControlMaster no
  ControlPath none
  PermitLocalCommand no
  ProxyCommand none
EOF
for file in known_hosts ssh_config; do
  chown root:root "$UPD/$file.new"; chmod 644 "$UPD/$file.new"; mv -f "$UPD/$file.new" "$UPD/$file"
done
ssh-keygen -lf "$UPD/known_hosts"
ls -la "$UPD"
if as_service test -e "$STATE/.ssh/scalar_github_ed25519"; then
  echo "Note: $STATE/.ssh/scalar_github_ed25519 (an earlier draft's key) is not used; revoke it on GitHub and remove it."
fi

say 'Add this public key on GitHub as a READ-ONLY deploy key (leave "Allow write access" unticked)'
echo "  $KEYS_URL  ->  Add deploy key, title: scalar-social-update@scout"
[ -z "$ROTATED" ] || echo "  Also DELETE the old key there (its public half: $ROTATED)."
echo
cat "$KEY.pub"
echo
read -r -p 'Press Enter once the deploy key is added... ' _

say "Verifying SSH access as $UUSER (root-owned config only)"
OUT=$(as_update ssh -F "$UPD/ssh_config" -T git@github.com-scalar 2>&1 || true)
echo "$OUT"
echo "$OUT" | grep -q 'successfully authenticated' || { echo 'Refusing: GitHub did not accept the key. Check the deploy key, then re-run this script.'; exit 1; }

say "Checkout at $REPO"
for left in /opt/scalar-social/repo.new-*; do
  [ -e "$left" ] || continue
  rm -rf -- "$left"; echo "Removed $left (an interrupted earlier clone)"
done
if [ -e "$REPO" ] || [ -L "$REPO" ]; then
  [ ! -L "$REPO" ] || { echo "Refusing: $REPO is a symlink"; exit 1; }
  if [ -d "$REPO/.git" ] && [ "$(stat -c %U "$REPO")" = "$UUSER" ] && [ -z "$(find "$REPO" -xdev ! -user "$UUSER" -print -quit)" ]; then
    if ugit -C "$REPO" rev-parse --verify -q HEAD >/dev/null && [ -n "$(ugit -C "$REPO" ls-files | head -n 1)" ]; then
      echo "Existing checkout owned by $UUSER kept"
    else
      move_aside "$REPO" broken 'no HEAD or no files: an interrupted clone'
    fi
  elif [ -z "$(ls -A "$REPO")" ]; then
    rmdir "$REPO"
  else
    # A checkout from before this hardening (owned by scalar-social) may have been changed by any scalar-social
    # process; never reuse it.
    move_aside "$REPO" pre-hardening "not owned by $UUSER"
  fi
fi
if [ -d "$REPO" ]; then
  verify_checkout "$REPO"
  echo 'Existing checkout: clean, on main, an ancestor of origin/main, bundle and unit files present.'
else
  # Cloned and verified next to the final place, then moved in: an interrupted clone never looks like a checkout.
  NEW=$REPO.new-$STAMP
  install -d -m 755 -o "$UUSER" -g "$UUSER" "$NEW"
  ugit "${LOW_MEMORY[@]}" clone --quiet --filter=blob:none --no-checkout --branch main "$ORIGIN" "$NEW"
  SPARSE_LIST=$(sparse_paths origin/main "$NEW")  # command substitution: an invalid list stops the script (set -e)
  mapfile -t SPARSE <<<"$SPARSE_LIST"
  ugit -C "$NEW" sparse-checkout set --cone "${SPARSE[@]}"
  ugit "${LOW_MEMORY[@]}" -C "$NEW" checkout --quiet main
  verify_checkout "$NEW"
  mv "$NEW" "$REPO"
  echo "Cloned main (partial, sparse: ${SPARSE[*]}) and moved it to $REPO"
fi

say 'Proving the deploy key is read-only (GitHub must refuse a dry-run push as read-only)'
if OUT=$(ugit -C "$REPO" push --dry-run origin HEAD:refs/heads/readonly-probe 2>&1); then
  echo "$OUT"
  echo "Refusing: GitHub accepted a push with this key. Delete it at $KEYS_URL, add it again with \"Allow write access\" unticked, then re-run."
  exit 1
fi
echo "$OUT" | sed 's/^/  | /'
# GitHub answers a read-only deploy key with "ERROR: The key you are authenticating with has been marked as read
# only." Anything else (DNS, network, repository not found) proves nothing: stop and retry later.
if echo "$OUT" | grep -qi 'marked as read only'; then
  echo 'Push refused because the key is read-only.'
else
  echo 'Refusing: the push failed for another reason, so read-only access is not proven. Check the network and the repository name, then re-run.'
  exit 1
fi

say "Update state folder $USTATE and the publisher's runner.lock"
for dir in "$USTATE" "$USTATE/inbox"; do [ ! -L "$dir" ] || { echo "Refusing: $dir is a symlink"; exit 1; }; done
# 0755: status.json and units-applied.json are written only by the update user and read by the UI.
install -d -m 755 -o "$UUSER" -g "$UUSER" "$USTATE"
# 1730 scalar-social-update:scalar-social: the UI (group) may create and replace its own request.json/ui.json but
# not list, read or remove the update user's files; the update user (owner) consumes the requests.
install -d -m 1730 -o "$UUSER" -g scalar-social "$USTATE/inbox"
# The update user flocks runner.lock read-only: it needs to traverse $STATE (o+x, no listing) and read the empty
# lock file (0644). Files in $STATE keep their own (0600) modes.
as_service chmod o+x "$STATE"
as_service sh -c 'umask 022; [ -e "$1" ] || : > "$1"; chmod 644 "$1"' sh "$STATE/runner.lock"
ls -ld "$USTATE" "$USTATE/inbox" "$STATE" "$STATE/runner.lock"
[ ! -d "$STATE/update" ] || echo "Note: $STATE/update (an earlier draft's update folder) is no longer used; remove it when convenient."

say "Backing up current units and code to $BACKUP"
install -d -m 700 -o root -g root /var/backups/scalar-social "$BACKUP" "$BACKUP/systemd" "$BACKUP/opt"
cp -a /etc/systemd/system/scalar-social* "$BACKUP/systemd/" 2>/dev/null || true
for dir in /opt/scalar-social/scripts /opt/scalar-social/ui; do
  [ ! -d "$dir" ] || cp -a "$dir" "$BACKUP/opt/"
done
ls -la "$BACKUP/systemd" "$BACKUP/opt"

say 'Node packages (pi-package*.json)'
if cmp -s "$REPO/publisher/pi-package.json" /opt/scalar-social/package.json && cmp -s "$REPO/publisher/pi-package-lock.json" /opt/scalar-social/package-lock.json; then
  echo 'Same as /opt/scalar-social/package*.json: node_modules stays as it is.'
else
  echo 'publisher/pi-package*.json differ from /opt/scalar-social/package*.json, so apply-units.sh will reinstall'
  echo '/opt/scalar-social/node_modules with npm ci (a few minutes on this Pi; the old copy is kept next to it).'
  read -r -p 'Continue with the npm reinstall? [y/N] ' ANSWER
  case $ANSWER in y|Y|yes|YES) ;; *) echo 'Stopped before changing any unit or package; re-run when ready.'; exit 1 ;; esac
fi

say 'Installing units from the checkout (apply-units.sh)'
UNITS_TOUCHED=1
bash "$REPO/publisher/deploy/apply-units.sh"

say 'Enabling scalar-social-update.path'
systemctl enable --now scalar-social-update.path
if systemctl restart scalar-social-ui.service && sleep 3 && curl -fsS http://127.0.0.1:8765/api/health; then
  echo
else
  echo; echo 'The UI did not start on the checkout. See: journalctl -u scalar-social-ui -n 50'
  exit 1
fi
systemctl --no-pager --lines=0 status scalar-social-ui.service scalar-social-update.path || true
echo "scalar-social.timer: enabled=$(systemctl is-enabled scalar-social.timer 2>/dev/null || true) active=$(systemctl is-active scalar-social.timer 2>/dev/null || true) (unchanged)"

cat <<EOF

Done. The Pi now runs from $REPO (owned by $UUSER) and updates from Settings > Update in the UI.
Publishing is still paused; channels, credentials and the publishing timer were not touched.
Revoke the deploy key at $KEYS_URL if you abandon the checkout.
EOF
print_rollback
