"""Owned Bluesky video publishing with durable processing and record checkpoints."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from buffer_adapter import PublishError
from identities import IdentityMissing, pin

HANDLE = 'studiozeroflow.bsky.social'
PDS = 'https://discina.us-west.host.bsky.network'
VIDEO = 'https://video.bsky.app'
COLLECTION = 'app.bsky.feed.post'


def request(method, host, endpoint, params=None, token=None, video=None):
    if host not in ('https://bsky.social', PDS, VIDEO):
        raise PublishError('authorization')
    url = host+'/xrpc/'+endpoint
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer '+token
    body = None
    if method == 'GET' or video is not None:
        url += '?'+urllib.parse.urlencode(params or {})
    elif params is not None:
        body = json.dumps(params).encode()
        headers['Content-Type'] = 'application/json'
    if video is not None:
        body = video
        headers['Content-Type'] = 'video/mp4'
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # The video service may return an existing processed blob with an error.
        try:
            data = json.loads(error.read(65536))
        except (ValueError, OSError):
            data = {}
        if data.get('error') == 'already_exists' and (data.get('blob') or data.get('jobStatus')):
            return data
        if endpoint == 'com.atproto.repo.getRecord' and data.get('error') == 'RecordNotFound':
            return {'missing': True}
        if error.code == 429:
            raise PublishError('rate_limit') from None
        if error.code in (401, 403):
            raise PublishError('authorization') from None
        raise PublishError('uncertain') from None
    except (OSError, ValueError):
        raise PublishError('uncertain') from None


def password():
    root = os.environ.get('CREDENTIALS_DIRECTORY')
    if not root:
        raise PublishError('authorization')
    value = (Path(root)/'BLUESKY_APP_PASSWORD').read_text().strip()
    if not value:
        raise PublishError('authorization')
    return value


def link_facets(text, link):
    if not link or text.count(link) != 1 or urllib.parse.urlsplit(link).scheme != 'https':
        raise PublishError('rejected')
    start = len(text[:text.index(link)].encode())
    return [{'index': {'byteStart': start, 'byteEnd': start+len(link.encode())},
             'features': [{'$type': 'app.bsky.richtext.facet#link', 'uri': link}]}]


def record_key(job):
    timestamp = dt.datetime.fromisoformat(job['dispatched_at'])
    if timestamp.tzinfo is None:
        raise PublishError('rejected')
    delta = timestamp-dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    micros = (delta.days*86400+delta.seconds)*1000000+delta.microseconds
    if not 0 <= micros < 2**53:
        raise PublishError('rejected')
    value = (micros << 10) | (int(hashlib.sha256(job['id'].encode()).hexdigest()[:4], 16) & 1023)
    alphabet = '234567abcdefghijklmnopqrstuvwxyz'
    return ''.join(alphabet[(value >> shift) & 31] for shift in range(60, -1, -5))


class BlueskyAdapter:
    def __init__(self, ledger, config, transport=request, password_loader=password,
                 media_loader=None, pause_check=lambda: False):
        self.ledger, self.config = ledger, config
        self.transport, self.password_loader = transport, password_loader
        self.media_loader = media_loader or self.load_media
        self.pause_check = pause_check
        self.session = None
        with ledger.db:
            ledger.db.execute('CREATE TABLE IF NOT EXISTS bluesky_uploads(job TEXT PRIMARY KEY, processing TEXT, blob TEXT, record TEXT, attempted INTEGER NOT NULL DEFAULT 0, rkey TEXT)')
            columns = [r['name'] for r in ledger.db.execute('PRAGMA table_info(bluesky_uploads)')]
            if 'rkey' not in columns:
                ledger.db.execute('ALTER TABLE bluesky_uploads ADD COLUMN rkey TEXT')
            if 'cid' not in columns:
                ledger.db.execute('ALTER TABLE bluesky_uploads ADD COLUMN cid TEXT')

    @property
    def did(self):
        try:
            return pin(self.config, 'blueskyDid')
        except IdentityMissing:
            raise PublishError('authorization') from None

    def identity(self, job):
        did = self.did
        if self.session is None:
            session = self.transport('POST', 'https://bsky.social', 'com.atproto.server.createSession',
                                     {'identifier': HANDLE, 'password': self.password_loader()})
            endpoints = [s.get('serviceEndpoint') for s in session.get('didDoc', {}).get('service', [])
                         if s.get('id', '').endswith('#atproto_pds')]
            if (session.get('did') != did or session.get('handle') != HANDLE
                    or session.get('emailConfirmed') is not True or endpoints != [PDS]
                    or not session.get('accessJwt')):
                raise PublishError('authorization')
            self.session = session
        channel = self.config['channels']['bluesky']
        if job['account'] != did or channel['accountId'] != did or channel['profileUrl'] != 'https://bsky.app/profile/'+HANDLE:
            raise PublishError('authorization')

    def call(self, method, endpoint, params=None):
        return self.transport(method, PDS, endpoint, params, self.session['accessJwt'])

    def service_token(self, audience, scope):
        return self.call('GET', 'com.atproto.server.getServiceAuth',
                         {'aud': audience, 'lxm': scope, 'exp': int(time.time())+1800})['token']

    def load_media(self, payload):
        media = payload['media']
        url = urllib.parse.urlsplit(media['url'])
        base = urllib.parse.urlsplit(self.config['media']['baseUrl'])
        if (url.scheme != 'https' or url.hostname != base.hostname or url.username or url.password
                or url.query or url.fragment or not url.path.endswith('.mp4') or not media.get('rightsReviewed')):
            raise PublishError('media')
        try:
            req = urllib.request.Request(media['url'], headers={'Accept': 'video/mp4', 'User-Agent': 'ScalarMediaVerifier/1.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                if (urllib.parse.urlsplit(response.url).hostname != base.hostname
                        or response.headers.get_content_type() != 'video/mp4'):
                    raise PublishError('media')
                data = response.read(self.config['media']['maxFileBytes']+1)
        except (OSError, ValueError):
            raise PublishError('media') from None
        if (not data or len(data) > self.config['media']['maxFileBytes']
                or hashlib.sha256(data).hexdigest() != media.get('sha256')):
            raise PublishError('media')
        return data

    def save(self, job, **values):
        with self.ledger.db:
            for name, value in values.items():
                if name not in ('processing', 'blob', 'record', 'attempted', 'cid'):
                    raise ValueError('Invalid checkpoint')
                self.ledger.db.execute('UPDATE bluesky_uploads SET '+name+'=? WHERE job=?', (value, job['id']))

    def parent_ref(self, payload):
        # The parent's own checkpoint supplies uri + cid; never trust a bare remote id.
        uri = str((payload.get('parent') or {}).get('remoteId') or '')
        prefix = 'at://'+self.did+'/'+COLLECTION+'/'
        row = self.ledger.db.execute('SELECT * FROM bluesky_uploads WHERE rkey=?', (uri[len(prefix):],)).fetchone() if uri.startswith(prefix) else None
        if not row or not row['cid'] or not row['record']:
            raise PublishError('rejected')
        return {'uri': uri, 'cid': row['cid']}

    def reply(self, job, payload):
        caption = payload.get('caption') or ''
        if payload.get('kind') not in ('comment', 'answer') or not caption or len(caption) > 300 or len(caption.encode()) > 3000:
            raise PublishError('rejected')
        ref = self.parent_ref(payload)
        if self.ledger.db.execute('SELECT 1 FROM bluesky_uploads WHERE job=?', (job['id'],)).fetchone():
            raise PublishError('uncertain')
        if self.pause_check():
            raise PublishError('rate_limit', 300)
        rkey = record_key(job)
        record = {'$type': COLLECTION, 'text': caption, 'langs': ['en'], 'createdAt': job['dispatched_at'],
                  'reply': {'root': ref, 'parent': ref}}
        if payload.get('link'):
            record['facets'] = link_facets(caption, payload['link'])
        # Record checkpoint before the request; reconcile reads the deterministic key.
        with self.ledger.db:
            self.ledger.db.execute('INSERT INTO bluesky_uploads(job,rkey,record,attempted) VALUES(?,?,?,1)',
                                   (job['id'], rkey, json.dumps(record)))
        self.call('POST', 'com.atproto.repo.createRecord', {'repo': self.did, 'collection': COLLECTION, 'rkey': rkey, 'record': record})
        return {'remoteId': 'bluesky:'+job['id']}

    def publish(self, job, payload):
        self.identity(job)
        if payload.get('companion'):
            return self.reply(job, payload)
        if len(payload['caption']) > 300 or len(payload['caption'].encode()) > 3000 or payload.get('nativePoll'):
            raise PublishError('rejected')
        link_facets(payload['caption'], payload['link'])
        existing = self.ledger.db.execute('SELECT 1 FROM bluesky_uploads WHERE job=?', (job['id'],)).fetchone()
        if existing:
            return {'remoteId': 'bluesky:'+job['id']}
        video = self.media_loader(payload)
        token = self.service_token('did:web:video.bsky.app', 'app.bsky.video.getUploadLimits')
        limits = self.transport('GET', VIDEO, 'app.bsky.video.getUploadLimits', {}, token)
        if not limits.get('canUpload') or limits.get('remainingDailyVideos', 0) < 1 or limits.get('remainingDailyBytes', 0) < len(video):
            raise PublishError('rate_limit')
        if self.pause_check():
            raise PublishError('rate_limit', 300)
        # A lost upload response is held for operator recovery; never re-upload it.
        with self.ledger.db:
            self.ledger.db.execute('INSERT INTO bluesky_uploads(job,rkey) VALUES(?,?)', (job['id'], record_key(job)))
        token = self.service_token('did:web:'+urllib.parse.urlsplit(PDS).hostname, 'com.atproto.repo.uploadBlob')
        result = self.transport('POST', VIDEO, 'app.bsky.video.uploadVideo',
                                {'did': self.did, 'name': payload['media']['sha256']+'.mp4'}, token, video)
        status = result.get('jobStatus', result)
        self.save(job, processing=status.get('jobId'), blob=json.dumps(status['blob']) if status.get('blob') else None)
        return {'remoteId': 'bluesky:'+job['id']}

    def reconcile(self, job, payload):
        self.identity(job)
        row = self.ledger.db.execute('SELECT * FROM bluesky_uploads WHERE job=?', (job['id'],)).fetchone()
        if not row or not row['rkey']:
            return {'status': 'uncertain'}
        rkey = row['rkey']
        params = {'repo': self.did, 'collection': COLLECTION, 'rkey': rkey}
        found = self.call('GET', 'com.atproto.repo.getRecord', params)
        if not found.get('missing'):
            expected = json.loads(row['record']) if row['record'] else None
            uri = 'at://'+self.did+'/'+COLLECTION+'/'+rkey
            if found.get('value') != expected or found.get('uri') != uri or not found.get('cid'):
                return {'status': 'uncertain'}
            self.save(job, cid=found['cid'])
            return {'status': 'confirmed', 'remoteId': uri,
                    'permalink': 'https://bsky.app/profile/'+HANDLE+'/post/'+rkey,
                    'publishedAt': expected['createdAt']}
        if row['attempted']:
            return {'status': 'uncertain'}
        blob = json.loads(row['blob']) if row['blob'] else None
        if not blob and row['processing']:
            result = self.transport('GET', VIDEO, 'app.bsky.video.getJobStatus', {'jobId': row['processing']})
            status = result.get('jobStatus', result)
            if status.get('state') == 'JOB_STATE_FAILED':
                return {'status': 'failed'}
            blob = status.get('blob')
            if blob:
                self.save(job, blob=json.dumps(blob))
        if not blob or self.pause_check():
            return {'status': 'uncertain'}
        record = {'$type': COLLECTION, 'text': payload['caption'], 'langs': ['en'],
                  'createdAt': job['dispatched_at'], 'facets': link_facets(payload['caption'], payload['link']),
                  'embed': {'$type': 'app.bsky.embed.video', 'video': blob,
                            'alt': 'Play along with this Scalar puzzle.',
                            'aspectRatio': {'width': 9, 'height': 16}}}
        self.save(job, record=json.dumps(record), attempted=1)
        self.call('POST', 'com.atproto.repo.createRecord', {**params, 'record': record})
        return {'status': 'uncertain'}
