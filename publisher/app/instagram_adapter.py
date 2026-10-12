"""Direct Instagram Login Reels publishing with durable, no-duplicate recovery."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from buffer_adapter import PublishError, credential_permissions_ok, verify_media

VERSION = 'v26.0'
USERNAME = 'studiozeroflow'
PROFILE = 'https://www.instagram.com/studiozeroflow/'


def token():
    root = os.environ.get('CREDENTIALS_DIRECTORY')
    if not root:
        raise PublishError('authorization')
    path = Path(root) / 'INSTAGRAM_ACCESS_TOKEN'
    try:
        metadata = path.stat()
        if path.is_symlink() or not path.is_file() or not credential_permissions_ok(path, metadata):
            raise PublishError('authorization')
        value = path.read_text().strip()
    except OSError:
        raise PublishError('authorization') from None
    if not value:
        raise PublishError('authorization')
    return value


def profile_record(data):
    # Instagram Login identifies the professional account as `user_id`.
    # Refuse ambiguous wrapped profiles rather than selecting one arbitrarily.
    if isinstance(data.get('data'), list):
        if len(data['data']) != 1 or not isinstance(data['data'][0], dict):
            raise PublishError('authorization')
        return data['data'][0]
    return data


def request(method, path, params, access_token):
    # Fixed graph host and strictly numeric/allowlisted paths prevent URL injection.
    if not re.fullmatch(r'(me|[0-9]+)(/media|/media_publish|/content_publishing_limit)?|[0-9]+/comments', path):
        raise PublishError('rejected')
    body = urllib.parse.urlencode(params).encode()
    url = f'https://graph.instagram.com/{VERSION}/{path}'
    if method == 'GET':
        url += '?' + body.decode()
        body = None
    req = urllib.request.Request(url, data=body, method=method,
        headers={'Authorization': 'Bearer ' + access_token, 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise PublishError('rate_limit', 3600) from None
        if error.code in (401, 403):
            raise PublishError('authorization') from None
        if error.code == 400:
            raise PublishError('rejected') from None
        raise PublishError('uncertain') from None
    except (OSError, ValueError):
        raise PublishError('uncertain') from None
    if data.get('error'):
        # OAuth/scope failures are categorized without exposing vendor text.
        code = data['error'].get('code') if isinstance(data['error'], dict) else None
        raise PublishError('authorization' if code in (190, 10, 200) else 'uncertain')
    return data


class InstagramAdapter:
    def __init__(self, ledger, config, transport=request, token_loader=token,
                 pause_check=lambda: False):
        self.ledger, self.config, self.transport, self.token_loader = ledger, config, transport, token_loader
        self.pause_check = pause_check
        with ledger.db:
            ledger.db.execute('''CREATE TABLE IF NOT EXISTS instagram_reels(
                job TEXT PRIMARY KEY, container TEXT, create_attempted INTEGER NOT NULL DEFAULT 0,
                publish_attempted INTEGER NOT NULL DEFAULT 0, media_id TEXT)''')
            ledger.db.execute('CREATE TABLE IF NOT EXISTS instagram_finishes(at REAL)')
            ledger.db.execute('CREATE TABLE IF NOT EXISTS instagram_comments(job TEXT PRIMARY KEY, media TEXT NOT NULL, comment TEXT)')

    def call(self, method, path, params):
        with self.ledger.db:
            now = time.time()
            self.ledger.db.execute('DELETE FROM instagram_finishes WHERE at<?', (now-86400,))
        return self.transport(method, path, params, self.token_loader())

    def identity(self, job):
        c = self.config['channels']['instagram']
        profile = profile_record(self.call('GET', 'me', {'fields': 'id,user_id,username'}))
        account_id = str(c.get('accountId') or '')
        owner_id = str(c.get('ownerId') or '')
        if (not account_id.isdecimal() or str(job.get('account')) != account_id or c.get('profileUrl') != PROFILE
                or not c.get('identityVerified') or not c.get('ownerIdVerified') or not owner_id.isdecimal()
                or str(profile.get('user_id')) != account_id or str(profile.get('id')) != owner_id
                or (profile.get('username') or '').lower() != USERNAME):
            raise PublishError('authorization')

    def quota(self):
        account_id = str(self.config['channels']['instagram']['accountId'])
        data = self.call('GET', account_id + '/content_publishing_limit', {'fields': 'quota_usage,config'})
        try:
            limit = data['data'][0]
            used, total = limit['quota_usage'], limit['config']['quota_total']
            if not isinstance(used, int) or not isinstance(total, int) or used < 0 or total < 1:
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError):
            raise PublishError('rejected') from None
        if used >= total:
            raise PublishError('rate_limit', 3600)

    def publish(self, job, payload):
        self.identity(job)
        if payload.get('companion'):
            return self._comment(job, payload)
        if not payload.get('caption') or payload.get('nativePoll'):
            raise PublishError('rejected')
        existing = self.ledger.db.execute('SELECT * FROM instagram_reels WHERE job=?', (job['id'],)).fetchone()
        if existing:
            # Any previous create attempt could have succeeded remotely.
            raise PublishError('uncertain')
        verify_media(payload, self.config)
        self.quota()
        if self.pause_check():
            raise PublishError('rate_limit', 300)
        # Durable intent first: a lost create response is never blindly repeated.
        with self.ledger.db:
            self.ledger.db.execute('INSERT INTO instagram_reels(job,create_attempted) VALUES(?,1)', (job['id'],))
        account_id = str(self.config['channels']['instagram']['accountId'])
        result = self.call('POST', account_id + '/media', {
            'media_type': 'REELS', 'video_url': payload['media']['url'],
            'caption': payload['caption'], 'share_to_feed': 'true'})
        container = str(result.get('id', ''))
        if not container.isdecimal():
            raise PublishError('uncertain')
        with self.ledger.db:
            self.ledger.db.execute('UPDATE instagram_reels SET container=? WHERE job=?', (container, job['id']))
        return {'remoteId': 'container:' + container}

    def _comment(self, job, payload):
        media = str((payload.get('parent') or {}).get('remoteId') or '')
        if payload.get('kind') not in ('comment', 'answer') or not payload.get('caption') or not media.isdecimal():
            raise PublishError('rejected')
        if self.ledger.db.execute('SELECT 1 FROM instagram_comments WHERE job=?', (job['id'],)).fetchone():
            raise PublishError('uncertain')
        if self.pause_check():
            raise PublishError('rate_limit', 300)
        with self.ledger.db:
            self.ledger.db.execute('INSERT INTO instagram_comments(job,media) VALUES(?,?)', (job['id'], media))
        result = self.call('POST', media + '/comments', {'message': payload['caption']})
        comment = str(result.get('id', ''))
        if not comment.isdecimal():
            raise PublishError('uncertain')
        with self.ledger.db:
            self.ledger.db.execute('UPDATE instagram_comments SET comment=? WHERE job=?', (comment, job['id']))
        return {'remoteId': comment}

    def _reconcile_comment(self, job, payload):
        row = self.ledger.db.execute('SELECT * FROM instagram_comments WHERE job=?', (job['id'],)).fetchone()
        parent = payload.get('parent') or {}
        if not row or row['media'] != str(parent.get('remoteId') or ''):
            return {'status': 'uncertain'}
        if row['comment']:
            return self._confirm_known_comment(job, row, parent)
        data = self.call('GET', row['media'] + '/comments', {'fields': 'id,text,username,timestamp', 'limit': '50'})
        dispatched = dt.datetime.fromisoformat(job['dispatched_at']) if job.get('dispatched_at') else None
        matches = []
        for item in data.get('data', [])[:50]:
            try:
                stamp = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            # Exact text by our own account under the parent; a known id must also match.
            if (str(item.get('id', '')).isdecimal() and item.get('text') == payload['caption']
                    and (item.get('username') or '').lower() == USERNAME and stamp.tzinfo
                    and (str(item['id']) == row['comment'] if row['comment']
                         else dispatched and stamp >= dispatched-dt.timedelta(minutes=2))):
                matches.append(item)
        if len(matches) != 1:
            return {'status': 'uncertain'}
        with self.ledger.db:
            self.ledger.db.execute('UPDATE instagram_comments SET comment=? WHERE job=?', (str(matches[0]['id']), job['id']))
        return {'status': 'confirmed', 'remoteId': str(matches[0]['id']), 'permalink': parent.get('permalink'),
                'publishedAt': matches[0]['timestamp']}

    def _confirm_known_comment(self, job, row, parent):
        # Instagram Login never lists the account's own comments under its media, and GET /{comment-id} answers
        # 200 with no fields. The id came from this job's own create response, so the receipt is: that object
        # still exists (an unknown or deleted id answers 400) and the parent counts at least one comment.
        try:
            self.call('GET', row['comment'], {'fields': 'id'})
        except PublishError as error:
            if error.category == 'rejected':
                return {'status': 'uncertain'}
            raise
        media = self.call('GET', row['media'], {'fields': 'id,comments_count'})
        count = media.get('comments_count')
        if (str(media.get('id', '')) != row['media'] or not isinstance(count, int) or isinstance(count, bool)
                or count < 1 or not job.get('dispatched_at')):
            return {'status': 'uncertain'}
        # The comment's own timestamp is not readable; the create call was made at dispatch.
        return {'status': 'confirmed', 'remoteId': row['comment'], 'permalink': parent.get('permalink'),
                'publishedAt': job['dispatched_at']}

    def _recent_match(self, job, payload):
        account_id = str(self.config['channels']['instagram']['accountId'])
        data = self.call('GET', account_id + '/media', {
            'fields': 'id,caption,media_type,media_product_type,owner,timestamp,permalink,username', 'limit': '25'})
        dispatched = dt.datetime.fromisoformat(job['dispatched_at']) if job.get('dispatched_at') else None
        matches = []
        for item in data.get('data', [])[:25]:
            try:
                stamp = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
            except (KeyError, ValueError, TypeError):
                continue
            if (dispatched and stamp >= dispatched-dt.timedelta(minutes=2)
                    and item.get('caption') == payload['caption']
                    and item.get('media_type') == 'VIDEO'
                    and item.get('media_product_type') == 'REELS'
                    and item.get('username', '').lower() == USERNAME
                    and str(item.get('owner', {}).get('id', '')) == str(self.config['channels']['instagram'].get('ownerId') or '')):
                matches.append(item)
        return matches

    def reconcile(self, job, payload):
        self.identity(job)
        if payload.get('companion'):
            return self._reconcile_comment(job, payload)
        row = self.ledger.db.execute('SELECT * FROM instagram_reels WHERE job=?', (job['id'],)).fetchone()
        if not row or not row['container']:
            # This includes an ambiguous container-create response: never create again.
            return {'status': 'uncertain'}
        if row['publish_attempted']:
            if row['media_id']:
                post = self.call('GET', row['media_id'], {
                    'fields': 'id,caption,media_type,media_product_type,owner,timestamp,permalink,username'})
            else:
                matches = self._recent_match(job, payload)
                if len(matches) != 1:
                    return {'status': 'uncertain'}
                post = matches[0]
                with self.ledger.db:
                    self.ledger.db.execute('UPDATE instagram_reels SET media_id=? WHERE job=?', (str(post['id']), job['id']))
            return self._receipt(post, payload, row['media_id'] or str(post.get('id', '')))
        status = self.call('GET', row['container'], {'fields': 'id,status_code'})
        if status.get('status_code') in ('ERROR', 'EXPIRED'):
            return {'status': 'failed'}
        if status.get('status_code') != 'FINISHED':
            return {'status': 'uncertain'}
        self.quota()
        if self.pause_check():
            return {'status': 'uncertain'}
        with self.ledger.db:
            if self.ledger.db.execute('SELECT count(*) FROM instagram_finishes WHERE at>?', (time.time()-86400,)).fetchone()[0] >= 25:
                raise PublishError('rate_limit', 3600)
            self.ledger.db.execute('INSERT INTO instagram_finishes VALUES(?)', (time.time(),))
            self.ledger.db.execute('UPDATE instagram_reels SET publish_attempted=1 WHERE job=?', (job['id'],))
        account_id = str(self.config['channels']['instagram']['accountId'])
        result = self.call('POST', account_id + '/media_publish', {'creation_id': row['container']})
        media_id = str(result.get('id', ''))
        if not media_id.isdecimal():
            raise PublishError('uncertain')
        with self.ledger.db:
            self.ledger.db.execute('UPDATE instagram_reels SET media_id=? WHERE job=?', (media_id, job['id']))
        return {'status': 'uncertain'}

    def _receipt(self, post, payload, expected_id):
        permalink = post.get('permalink') or ''
        link = urllib.parse.urlsplit(permalink)
        owner = post.get('owner') or {}
        media_id = str(post.get('id', ''))
        timestamp = post.get('timestamp')
        try:
            stamp = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            valid_timestamp = stamp.tzinfo is not None
        except (AttributeError, ValueError):
            valid_timestamp = False
        if (not expected_id or media_id != str(expected_id) or not media_id.isdecimal()
                or post.get('caption') != payload['caption'] or post.get('media_type') != 'VIDEO'
                or post.get('media_product_type') != 'REELS'
                or str(owner.get('id', '')) != str(self.config['channels']['instagram'].get('ownerId') or '')
                or post.get('username', '').lower() != USERNAME
                or link.scheme != 'https' or link.hostname not in ('instagram.com', 'www.instagram.com')
                or link.port is not None or link.username or link.password or link.query or link.fragment
                or not re.fullmatch(r'/reel/[A-Za-z0-9_-]+/?', link.path) or not valid_timestamp):
            return {'status': 'uncertain'}
        return {'status': 'confirmed', 'remoteId': str(post['id']), 'permalink': permalink,
                'publishedAt': timestamp}
