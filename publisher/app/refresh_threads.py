"""Renew an already authorized long-lived Threads token; disabled until configured.

No app secret is needed for refresh. Values stay in private credential files and
Authorization headers. This never publishes or widens OAuth permissions.
"""
import datetime as dt
import json
from pathlib import Path
import os
import time
import urllib.request
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))  # root runs this with python3 -I, which omits the script folder

from credential_entry import clear_superseded_failure, store
from threads_adapter import request, token


def refresh(config, current, opener=urllib.request.urlopen, profile_request=request):
    channel = config['channels']['threads']
    if not channel.get('identityVerified') or not channel.get('accountId'):
        raise ValueError('Threads identity not configured')
    req = urllib.request.Request('https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token',
                                 headers={'Authorization': 'Bearer '+current})
    with opener(req, timeout=30) as response:
        result = json.load(response)
    value = result.get('access_token')
    seconds = result.get('expires_in')
    if not isinstance(value, str) or not value or not isinstance(seconds, int) or not 86400 <= seconds <= 60*86400:
        raise ValueError('Unexpected token refresh response')
    profile = profile_request('GET', 'me', {'fields': 'id,username'}, value)
    if str(profile['id']) != str(channel['accountId']) or profile['username'].lower() != channel['profileUrl'].rstrip('/').split('@')[-1].lower():
        raise ValueError('Refreshed identity mismatch')
    return value, seconds


if __name__ == '__main__':
    failure = Path('/var/lib/scalar-social/threads-token-failure.json')
    try:
        if os.geteuid() != 0:
            raise ValueError('Requires private credential write access')
        config = json.loads(Path('/etc/scalar-social/config.json').read_text())
        source = Path('/etc/scalar-social/credentials/THREADS_ACCESS_TOKEN')
        # Threads only refreshes long-lived tokens that are at least 24 hours old.
        if time.time() - source.stat().st_mtime < 86400:
            print('Threads renewal not due: token is under 24 hours old; no credential changed.')
            if clear_superseded_failure(failure, source):
                print('Cleared the earlier renewal failure: the token was replaced after it.')
            raise SystemExit(0)
        value, seconds = refresh(config, token())
        store('/etc/scalar-social/credentials', 'THREADS_ACCESS_TOKEN', value)
        expires = dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=seconds)
        path=Path('/var/lib/scalar-social/threads-token-health.json')
        path.write_text(json.dumps({'expiresAt': expires.isoformat(), 'renewed': True})+'\n')
        owner=path.parent.stat()
        os.chown(path,owner.st_uid,owner.st_gid)
        failure.unlink(missing_ok=True)
        print('Threads credential refreshed for the same verified account; no publication.')
    except SystemExit:
        raise
    except Exception:
        try:
            # Marker the monitor and the UI read; contains only a timestamp.
            failure.write_text(json.dumps({'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat()})+'\n')
            owner = failure.parent.stat()
            os.chown(failure, owner.st_uid, owner.st_gid)
        except OSError:
            pass
        raise SystemExit('Threads refresh failed; credential preserved unless secure replacement completed. Inspect eligibility, token age/expiry and configuration. No response body logged.')
