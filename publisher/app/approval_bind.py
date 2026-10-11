"""Root ExecStartPost step: bind the approved manifest hash into config.approval. Nothing else.

Everything under STATE is written by the unprivileged service user and treated as hostile: each
directory and file is opened relative to a verified directory descriptor without following symlinks,
only regular files are read, sizes are capped and every hash is rechecked. Only
approval.manifestSha256 and approval.approvedAt change; paused, channels, credentials and timers never do.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))  # root runs this with python3 -I, which omits the script folder

from configure_paused import save

SHA = re.compile(r'[0-9a-f]{64}')
RESULT_CAP = 64*1024
MANIFEST_CAP = 8*1024*1024


class Refused(Exception):
    pass


def _open_dir(name, dir_fd=None):
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError:
        raise Refused(f'{name} is not a plain directory.') from None


def _read(name, dir_fd, cap):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError:
        raise Refused(f'{name} is a symlink or unreadable.') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Refused(f'{name} is not a regular file.')
        if info.st_size > cap:
            raise Refused(f'{name} is larger than allowed.')
        chunks, total = [], 0
        while chunk := os.read(fd, 65536):
            total += len(chunk)
            if total > cap:
                raise Refused(f'{name} is larger than allowed.')
            chunks.append(chunk)
        return b''.join(chunks), info
    finally:
        os.close(fd)


def _write_as(name, dir_fd, data, owner):
    temp = f'.{name}.{os.getpid()}.tmp'
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        try:
            os.fchown(fd, owner.st_uid, owner.st_gid)
            os.fchmod(fd, 0o600)
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            os.unlink(temp, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        raise


def bind(state, config_path, now=None):
    """Returns a plain message. Raises Refused on any untrusted-input problem."""
    now = now or dt.datetime.now(dt.timezone.utc)
    state_fd = _open_dir(str(state))
    fds = [state_fd]
    try:
        try:
            approval_fd = _open_dir('approval', state_fd)
            fds.append(approval_fd)
            raw, owner = _read('result.json', approval_fd, RESULT_CAP)
        except FileNotFoundError:
            return 'Nothing to bind: no approval result.'
        try:
            result = json.loads(raw)
        except ValueError:
            raise Refused('The approval result is not valid JSON.') from None
        if not isinstance(result, dict) or result.get('status') != 'manifest-ready':
            status = result.get('status') if isinstance(result, dict) and isinstance(result.get('status'), str) else 'unknown'
            return f'Nothing to bind: approval result is {status[:40]!r}.'
        sha = result.get('manifestSha256')
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise Refused('The approval result has no valid manifest hash.')
        try:
            manifests_fd = _open_dir('manifests', state_fd)
            fds.append(manifests_fd)
            approved, _ = _read('approved.json', manifests_fd, MANIFEST_CAP)
            named, _ = _read(f'{sha}.json', manifests_fd, MANIFEST_CAP)
        except FileNotFoundError:
            raise Refused('The approved manifest file is missing.') from None
        if hashlib.sha256(approved).hexdigest() != sha or hashlib.sha256(named).hexdigest() != sha:
            raise Refused('The approved manifest does not match the approval result.')
        try:
            manifest = json.loads(approved)
        except ValueError:
            raise Refused('The approved manifest is not valid JSON.') from None
        if (not isinstance(manifest, dict) or not isinstance(manifest.get('jobs'), list)
                or not isinstance(manifest.get('scopeHash'), str) or not SHA.fullmatch(manifest['scopeHash'])):
            raise Refused('The approved manifest is malformed.')
        config = json.loads(Path(config_path).read_text())
        approval = config.get('approval')
        if approval is None:
            approval = {}
        if not isinstance(approval, dict):
            raise Refused('config.approval is not an object; fix it by hand.')
        at = now.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        approval['manifestSha256'] = sha
        approval['approvedAt'] = at
        config['approval'] = approval
        save(config_path, config)
        message = f'Bound approved manifest {sha[:12]} into the configuration. Channels, pause and timers unchanged.'
        result.update(status='bound', boundAt=at)
        try:
            # Owned like the approval directory (opened without following links), not like the old file.
            _write_as('result.json', approval_fd, json.dumps(result, sort_keys=True, separators=(',', ':')).encode(),
                      os.fstat(approval_fd))
        except OSError:
            return message+' The approval result file could not be marked bound.'
        return message
    finally:
        for fd in fds:
            os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Bind the approved manifest hash (root). Never publishes.')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--allow-non-root-for-tests', action='store_true')
    args = parser.parse_args(argv)
    if os.geteuid() != 0 and not args.allow_non_root_for_tests:
        print('approval_bind must run as root (systemd ExecStartPost=+).', file=sys.stderr)
        return 1
    try:
        print(bind(args.state, args.config))
        return 0
    except Refused as error:
        print(f'Approval not bound: {error} The configuration was not changed.', file=sys.stderr)
    except (OSError, ValueError, KeyError):
        print('Approval not bound: configuration or approval files unavailable. The configuration was not changed.',
              file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
