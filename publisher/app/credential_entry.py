"""Owner-operated hidden entry on Pi. Values never enter argv, history or logs."""
import argparse
import getpass
import os
from pathlib import Path
import re
import tempfile

NAMES = ('BUFFER_API_KEY', 'CLOUDFLARE_API_TOKEN', 'HEALTHCHECKS_PING_URL', 'THREADS_ACCESS_TOKEN', 'INSTAGRAM_ACCESS_TOKEN', 'BLUESKY_APP_PASSWORD', 'FACEBOOK_PAGE_TOKEN', 'UI_PASSCODE')


def store(directory, name, value):
    if name not in NAMES or not value or '\n' in value or '\r' in value:
        raise ValueError('Invalid credential input')
    if name == 'HEALTHCHECKS_PING_URL' and not re.fullmatch(r'https://hc-ping\.com/[0-9a-f-]{36}', value):
        raise ValueError('Use the HTTPS Healthchecks ping URL')
    # Tailnet-only UI with a global lockout (ui_server.GLOBAL_FAILURE_LIMIT), so a 4-digit PIN is allowed.
    if name == 'UI_PASSCODE' and (len(value) < 4 or len(value) > 128):
        raise ValueError('Use a UI passcode of 4 to 128 characters')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError('Credential directory must be private')
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.credential-')
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(value+'\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, directory/name)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clear_superseded_failure(failure, source):
    """Remove a renewal failure marker written before the credential was replaced; that failure no longer applies."""
    try:
        if Path(failure).stat().st_mtime < Path(source).stat().st_mtime:
            Path(failure).unlink()
            return True
    except FileNotFoundError:
        pass
    return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('name', choices=NAMES)
    args = parser.parse_args()
    if os.geteuid() != 0 or not os.isatty(0):
        parser.error('Run interactively with sudo on the Pi')
    try:
        value = getpass.getpass('Paste credential (hidden): ').strip()
        store('/etc/scalar-social/credentials', args.name, value)
        print('Credential stored privately. Publishing remains paused.')
    except (OSError, ValueError):
        raise SystemExit('Credential not saved; check private directory and input format.')
