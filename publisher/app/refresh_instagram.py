"""Refresh an existing long-lived Instagram Login token; never publishes."""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))  # root runs this with python3 -I, which omits the script folder

from credential_entry import clear_superseded_failure, store
from instagram_adapter import profile_record, request, token


def refresh(config, current, issued_at, opener=urllib.request.urlopen, profile_request=request, now=None):
    channel = config['channels']['instagram']
    account_id = str(channel.get('accountId') or '')
    if (not account_id.isdecimal() or not channel.get('identityVerified')
            or channel.get('profileUrl') != 'https://www.instagram.com/studiozeroflow/'):
        raise ValueError('Instagram Login identity not configured')
    now = time.time() if now is None else now
    if not isinstance(issued_at, (int, float)) or now - issued_at < 86400:
        raise ValueError('Instagram token must be at least 24 hours old before refresh')
    query = urllib.parse.urlencode({'grant_type': 'ig_refresh_token', 'access_token': current})
    req = urllib.request.Request('https://graph.instagram.com/refresh_access_token?' + query)
    try:
        with opener(req, timeout=30) as response:
            result = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        raise ValueError('Instagram token refresh failed') from None
    value, seconds = result.get('access_token'), result.get('expires_in')
    if not isinstance(value, str) or not value or not isinstance(seconds, int) or not 86400 <= seconds <= 60*86400:
        raise ValueError('Unexpected Instagram token refresh response')
    profile = profile_record(profile_request('GET', 'me', {'fields': 'user_id,username'}, value))
    if str(profile.get('user_id')) != account_id or (profile.get('username') or '').lower() != 'studiozeroflow':
        raise ValueError('Refreshed Instagram identity mismatch')
    return value, seconds


if __name__ == '__main__':
    try:
        if os.geteuid() != 0:
            raise ValueError('Requires private credential write access')
        config = json.loads(Path('/etc/scalar-social/config.json').read_text())
        source = Path('/etc/scalar-social/credentials/INSTAGRAM_ACCESS_TOKEN')
        if time.time() - source.stat().st_mtime < 86400:
            print('Instagram renewal not due: token is under 24 hours old; no credential changed.')
            if clear_superseded_failure('/var/lib/scalar-social/instagram-token-failure.json', source):
                print('Cleared the earlier renewal failure: the token was replaced after it.')
            raise SystemExit(0)
        value, seconds = refresh(config, token(), source.stat().st_mtime)
        store('/etc/scalar-social/credentials', 'INSTAGRAM_ACCESS_TOKEN', value)
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
        path = Path('/var/lib/scalar-social/instagram-token-health.json')
        path.write_text(json.dumps({'expiresAt': expires.isoformat(), 'renewed': True}) + '\n')
        owner = path.parent.stat()
        os.chown(path, owner.st_uid, owner.st_gid)
        Path('/var/lib/scalar-social/instagram-token-failure.json').unlink(missing_ok=True)
        print('Instagram credential refreshed for the same verified account; no publication.')
    except Exception:
        try:
            failure = Path('/var/lib/scalar-social/instagram-token-failure.json')
            failure.write_text(json.dumps({'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat()})+'\n')
            owner = failure.parent.stat()
            os.chown(failure, owner.st_uid, owner.st_gid)
        except OSError:
            pass
        raise SystemExit('Instagram refresh failed; no response body logged. Check token age, permissions and configured identity.')
