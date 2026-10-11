"""Page Reels only. Checkpoint every mutation; never repeat uncertain finishing."""
import json
import hashlib
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from buffer_adapter import PublishError, verify_media
from identities import IdentityMissing, pin

VERSION = 'v26.0'


def token():
    root = os.environ.get('CREDENTIALS_DIRECTORY')
    if not root: raise PublishError('authorization')
    value = (Path(root)/'FACEBOOK_PAGE_TOKEN').read_text().strip()
    if not value: raise PublishError('authorization')
    return value


def request(method, path, params, access_token):
    if not re.fullmatch(r'(me|[0-9]+)(/video_reels)?', path): raise PublishError('rejected')
    url = 'https://graph.facebook.com/'+VERSION+'/'+path
    body = urllib.parse.urlencode(params).encode()
    if method == 'GET': url += '?'+body.decode(); body = None
    req = urllib.request.Request(url, data=body, method=method,
        headers={'Authorization': 'Bearer '+access_token, 'Content-Type': 'application/x-www-form-urlencoded'})
    return response(req)


def response(req):
    try:
        with urllib.request.urlopen(req, timeout=60) as remote: data = json.load(remote)
    except urllib.error.HTTPError as error:
        if error.code == 429: raise PublishError('rate_limit') from None
        if error.code in (401, 403): raise PublishError('authorization') from None
        raise PublishError('uncertain') from None
    except (OSError, ValueError): raise PublishError('uncertain') from None
    if data.get('error'): raise PublishError('uncertain')
    return data


def upload(video_id, video, access_token):
    if not video_id.isdecimal(): raise PublishError('rejected')
    return response(urllib.request.Request('https://rupload.facebook.com/video-upload/'+VERSION+'/'+video_id,
        data=video, method='POST', headers={'Authorization': 'OAuth '+access_token,
        'Content-Type': 'application/octet-stream', 'offset': '0', 'file_size': str(len(video))}))


class FacebookAdapter:
    def __init__(self, ledger, config, transport=request, token_loader=token,
                 uploader=upload, media_loader=None, pause_check=lambda: False):
        self.ledger, self.config = ledger, config
        self.transport, self.token_loader = transport, token_loader
        self.uploader, self.media_loader, self.pause_check = uploader, media_loader or self.load_media, pause_check
        with ledger.db:
            ledger.db.execute('CREATE TABLE IF NOT EXISTS facebook_reels(job TEXT PRIMARY KEY, video TEXT, upload_attempted INTEGER NOT NULL DEFAULT 0, finish_attempted INTEGER NOT NULL DEFAULT 0)')

    def call(self, method, path, params):
        return self.transport(method, path, params, self.token_loader())

    def identity(self, job):
        """The pinned Page id once the token's Page, the job and the channel all match the pins."""
        try:
            page_id, profile = pin(self.config, 'facebookPageId'), pin(self.config, 'facebookProfileUrl')
        except IdentityMissing:
            raise PublishError('authorization') from None
        page = self.call('GET', 'me', {'fields': 'id,name'})
        channel = self.config['channels']['facebook']
        if page.get('id') != page_id or page.get('name') != 'Scalargame' or job['account'] != page_id or channel['accountId'] != page_id or channel['profileUrl'] != profile:
            raise PublishError('authorization')
        return page_id

    def load_media(self, payload):
        verify_media(payload, self.config)
        req = urllib.request.Request(payload['media']['url'], headers={'Accept':'video/mp4','User-Agent':'ScalarMediaVerifier/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=30) as remote:
                if urllib.parse.urlsplit(remote.url).hostname != urllib.parse.urlsplit(self.config['media']['baseUrl']).hostname:
                    raise PublishError('media')
                video = remote.read(self.config['media']['maxFileBytes']+1)
        except (OSError, ValueError): raise PublishError('media') from None
        if not video or len(video)>self.config['media']['maxFileBytes'] or hashlib.sha256(video).hexdigest()!=payload['media']['sha256']:
            raise PublishError('media')
        return video

    def publish(self, job, payload):
        # Page comments need pages_manage_engagement, which is not granted: no companion route.
        if payload.get('companion'): raise PublishError('rejected')
        page_id = self.identity(job)
        if payload.get('nativePoll') or not payload.get('caption'): raise PublishError('rejected')
        row = self.ledger.db.execute('SELECT * FROM facebook_reels WHERE job=?', (job['id'],)).fetchone()
        if row: return {'remoteId': 'facebook:'+job['id']}
        video_bytes = self.media_loader(payload)
        if self.pause_check(): raise PublishError('rate_limit', 300)
        with self.ledger.db:
            self.ledger.db.execute('INSERT INTO facebook_reels(job) VALUES(?)', (job['id'],))
        result = self.call('POST', page_id+'/video_reels', {'upload_phase': 'start'})
        video = str(result.get('video_id', ''))
        if not video.isdecimal(): raise PublishError('uncertain')
        with self.ledger.db:
            self.ledger.db.execute('UPDATE facebook_reels SET video=?,upload_attempted=1 WHERE job=?', (video, job['id']))
        result = self.uploader(video, video_bytes, self.token_loader())
        if result.get('success') is not True: raise PublishError('uncertain')
        return {'remoteId': video}

    def reconcile(self, job, payload):
        page_id = self.identity(job)
        row = self.ledger.db.execute('SELECT * FROM facebook_reels WHERE job=?', (job['id'],)).fetchone()
        if not row or not row['video']: return {'status': 'uncertain'}
        video = self.call('GET', row['video'], {'fields': 'status'})
        status = video.get('status', {})
        phases = [status.get(k, {}) for k in ('uploading_phase', 'processing_phase', 'publishing_phase')]
        if any(p.get('status') == 'error' or p.get('error') for p in phases): return {'status': 'failed'}
        if status.get('publishing_phase', {}).get('status') == 'complete':
            post = self.call('GET', row['video'], {'fields': 'id,from,description,created_time,permalink_url'})
            permalink = post.get('permalink_url', '')
            if permalink.startswith('/') and not permalink.startswith('//'):
                permalink = 'https://www.facebook.com'+permalink
            url = urllib.parse.urlsplit(permalink)
            if (post.get('id') != row['video'] or post.get('from', {}).get('id') != page_id
                    or post.get('description') != payload['caption'] or not post.get('created_time')
                    or url.scheme != 'https' or url.hostname not in ('facebook.com', 'www.facebook.com')):
                return {'status': 'uncertain'}
            return {'status': 'confirmed', 'remoteId': row['video'], 'permalink': permalink, 'publishedAt': post['created_time']}
        if row['finish_attempted'] or status.get('uploading_phase', {}).get('status') != 'complete' or self.pause_check():
            return {'status': 'uncertain'}
        # Conservative rolling limit: our own finishes are counted before sending.
        with self.ledger.db:
            self.ledger.db.execute('CREATE TABLE IF NOT EXISTS facebook_finishes(at REAL)')
            now = time.time()
            if self.ledger.db.execute('SELECT count(*) FROM facebook_finishes WHERE at>?', (now-86400,)).fetchone()[0] >= 30:
                raise PublishError('rate_limit')
            self.ledger.db.execute('INSERT INTO facebook_finishes VALUES(?)', (now,))
            self.ledger.db.execute('UPDATE facebook_reels SET finish_attempted=1 WHERE job=?', (job['id'],))
        result = self.call('POST', page_id+'/video_reels', {'upload_phase': 'finish', 'video_id': row['video'],
                           'video_state': 'PUBLISHED', 'description': payload['caption']})
        if result.get('success') is not True: raise PublishError('uncertain')
        return {'status': 'uncertain'}
