import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
import buffer_adapter
import runner
from runner import Ledger, UTC, run_jobs
from buffer_adapter import BufferAdapter, PublishError
from instagram_adapter import InstagramAdapter
from threads_adapter import ThreadsAdapter, Router
from bluesky_adapter import BlueskyAdapter, HANDLE, PDS
from facebook_adapter import FacebookAdapter
from fixture_ids import DID, IDENTITIES, PAGE, PROFILE

SENTINEL = 'SENTINEL-credential-7f3a'
T = dt.datetime(2026, 10, 12, 13, tzinfo=UTC)
IG = '17841400000000001'
OWNER = '27000000000000007'


def companion(kind='comment', delay=2, caption='A) Bolivia B) Chile — comment your letter'):
    return {'episode': {'id': 'scalar:BOL:clues#'+kind}, 'kind': kind, 'caption': caption, 'media': None,
            'companion': {'parentEpisode': 'scalar:BOL:clues', 'delayMinutes': delay}}


class Fake:
    def __init__(self):
        self.calls = []
        self.errors = {}
        self.published = {}

    def publish(self, job, payload):
        self.calls.append(('publish', job['episode'], payload))
        if job['episode'] in self.errors:
            raise self.errors[job['episode']]
        return {'remoteId': 'r-'+job['episode']}

    def reconcile(self, job, payload):
        self.calls.append(('reconcile', job['episode'], payload))
        at = self.published.get(job['episode'])
        if not at:
            return {'status': 'uncertain'}
        return {'status': 'confirmed', 'remoteId': '900', 'permalink': 'https://x.com/a/status/900', 'publishedAt': at}


class RunnerCompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name)/'ledger.sqlite3')
        self.config = {'paused': False, 'schedule': {'maxLatenessMinutes': 120},
                       'channels': {'x': {'enabled': True, 'accountId': 'x-1'}}}
        self.parent = self.ledger.enqueue('x', 'x-1', T.isoformat(), {'episode': {'id': 'scalar:BOL:clues'}, 'caption': 'post'})
        self.child = self.ledger.enqueue('x', 'x-1', (T+dt.timedelta(minutes=2)).isoformat(), companion())
        self.fake = Fake()

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def row(self, key):
        return self.ledger.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()

    def events(self, key):
        return self.ledger.db.execute('SELECT count(*) FROM events WHERE job=?', (key,)).fetchone()[0]

    def run_at(self, minutes):
        run_jobs(self.ledger, self.config, self.fake, T+dt.timedelta(minutes=minutes))

    def test_held_until_parent_confirmed_then_effective_due(self):
        self.run_at(0)
        self.run_at(3)
        self.assertEqual(self.row(self.parent)['status'], 'accepted')
        self.assertEqual((self.row(self.child)['status'], self.events(self.child)), ('ready', 0))
        # Parent confirms three hours late; companion waits parent publication + delay, not its slot.
        self.fake.published['scalar:BOL:clues'] = (T+dt.timedelta(minutes=180)).isoformat()
        self.run_at(181)
        self.assertEqual(self.row(self.parent)['status'], 'confirmed')
        self.assertEqual((self.row(self.child)['status'], self.events(self.child)), ('ready', 0))
        self.run_at(183)
        self.assertEqual(self.row(self.child)['status'], 'accepted')
        sent = [c for c in self.fake.calls if c[1].endswith('#comment')]
        self.assertEqual(sent[0][0], 'publish')
        self.assertEqual(sent[0][2]['parent'], {'remoteId': '900', 'permalink': 'https://x.com/a/status/900'})
        self.assertNotIn('parent', json.loads(self.row(self.child)['payload']))
        self.run_at(190)
        self.assertEqual(self.fake.calls[-1][0], 'reconcile')
        self.assertEqual(self.fake.calls[-1][2]['parent']['remoteId'], '900')
        self.assertNotIn('parent', json.loads(self.row(self.child)['payload']))

    def test_lateness_uses_effective_due(self):
        self.fake.published['scalar:BOL:clues'] = (T+dt.timedelta(minutes=60)).isoformat()
        self.run_at(0)
        self.run_at(60)
        self.run_at(62+121)
        self.assertEqual(dict(self.row(self.child))['error'], 'missed_slot')
        self.assertEqual(self.row(self.child)['status'], 'expired')

    def test_failed_parent_expires_companion_without_touching_parent(self):
        self.fake.errors['scalar:BOL:clues'] = PublishError('rejected')
        self.run_at(0)
        before = dict(self.row(self.parent))
        self.run_at(3)
        child = self.row(self.child)
        # Final rather than "needs review": a blocked parent is already the item the owner reviews.
        self.assertEqual((child['status'], child['error']), ('expired', 'parent_unavailable'))
        self.assertEqual(dict(self.row(self.parent)), before)
        self.assertFalse([c for c in self.fake.calls if c[1].endswith('#comment')])

    def test_confirmed_parent_without_remote_id_expires_companion(self):
        with self.ledger.db:
            self.ledger.db.execute("UPDATE jobs SET status='confirmed', permalink='https://x.com/a/status/1', "
                                   "published_at=? WHERE id=?", (T.isoformat(), self.parent))
        self.run_at(5)
        self.assertEqual(tuple(self.row(self.child)[k] for k in ('status', 'error')), ('expired', 'parent_unavailable'))
        self.assertEqual(self.fake.calls, [])

    def test_absent_parent_expires_after_seven_days(self):
        with self.ledger.db:
            self.ledger.db.execute('DELETE FROM jobs WHERE id=?', (self.parent,))
        self.run_at(60*24*6)
        self.assertEqual(self.row(self.child)['status'], 'ready')
        self.run_at(60*24*7+5)
        self.assertEqual(self.row(self.child)['error'], 'parent_unavailable')
        self.assertEqual(self.fake.calls, [])

    def confirm_parent(self):
        self.ledger.update(self.parent, 'confirmed', remote_id='900', permalink='https://x.com/a/status/900',
                           published_at=T.isoformat(), dispatched_at=T.isoformat())

    def test_failed_companion_never_touches_parent(self):
        self.confirm_parent()
        self.fake.errors['scalar:BOL:clues#comment'] = PublishError('authorization')
        before = dict(self.row(self.parent))
        self.run_at(3)
        self.assertEqual(self.row(self.child)['status'], 'blocked')
        self.run_at(10)
        self.assertEqual(dict(self.row(self.parent)), before)
        self.assertEqual([c[1] for c in self.fake.calls], ['scalar:BOL:clues#comment'])

    def test_uncertain_companion_does_not_hold_later_posts(self):
        self.confirm_parent()
        self.fake.errors['scalar:BOL:clues#comment'] = TimeoutError()
        later = self.ledger.enqueue('x', 'x-1', (T+dt.timedelta(minutes=30)).isoformat(), {'episode': {'id': 'ep02'}, 'caption': 'next'})
        self.run_at(3)
        self.assertEqual(self.row(self.child)['status'], 'uncertain')
        self.run_at(31)
        self.assertEqual(self.row(later)['status'], 'accepted')

    def test_uncertain_parent_still_holds_companion_and_later_posts(self):
        self.fake.errors['scalar:BOL:clues'] = TimeoutError()
        later = self.ledger.enqueue('x', 'x-1', (T+dt.timedelta(minutes=30)).isoformat(), {'episode': {'id': 'ep02'}, 'caption': 'next'})
        self.run_at(0)
        self.run_at(31)
        self.assertEqual((self.row(self.child)['status'], self.row(later)['status']), ('ready', 'ready'))

    def test_malformed_companion_is_blocked(self):
        key = self.ledger.enqueue('x', 'x-1', (T+dt.timedelta(minutes=4)).isoformat(),
                                  {**companion('answer'), 'companion': {'parentEpisode': 'scalar:BOL:clues', 'delayMinutes': -1}})
        self.run_at(5)
        self.assertEqual((self.row(key)['status'], self.row(key)['error']), ('blocked', 'rejected'))


class ManifestApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        config = json.loads((ROOT/'publisher/config.example.json').read_text())
        config.update(paused=False, approval=None)
        self.config, self.state, self.manifest = base/'config.json', base/'state', base/'approved.json'
        self.config.write_text(json.dumps(config))
        self.manifest.write_text(json.dumps({'version': 1, 'jobs': []}))
        self.argv = ['runner.py', 'tick', '--config', str(self.config), '--state', str(self.state), '--manifest', str(self.manifest)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_null_approval_fails_closed_without_type_error(self):
        out = io.StringIO()
        with patch.object(sys, 'argv', self.argv), contextlib.redirect_stdout(out), self.assertRaises(ValueError):
            runner.main()
        self.assertNotIn(SENTINEL, out.getvalue())
        done = subprocess.run([sys.executable, str(ROOT/'publisher/app/runner.py'), *self.argv[1:]],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertIn('Runner stopped', done.stderr)
        self.assertNotIn('Traceback', done.stderr)

    def test_missing_manifest_fails_closed(self):
        self.manifest.unlink()
        done = subprocess.run([sys.executable, str(ROOT/'publisher/app/runner.py'), *self.argv[1:]],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertNotIn('Traceback', done.stderr)


class AdapterBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name)/'ledger.sqlite3')
        self.out = io.StringIO()
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(contextlib.redirect_stdout(self.out))
        self.stack.enter_context(contextlib.redirect_stderr(self.out))

    def tearDown(self):
        self.stack.close()
        dump = '\n'.join(self.ledger.db.iterdump())
        self.ledger.db.close()
        self.tmp.cleanup()
        self.assertNotIn(SENTINEL, self.out.getvalue())
        self.assertNotIn(SENTINEL, dump)

    def raises(self, category, fn, *args):
        with self.assertRaises(PublishError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.category, category)
        self.assertNotIn(SENTINEL, str(caught.exception))


class InstagramCommentTests(AdapterBase):
    def setUp(self):
        super().setUp()
        self.calls, self.comments, self.lose = [], [], True
        self.config = {'paused': False, 'schedule': {'maxLatenessMinutes': 120}, 'media': {'baseUrl': 'https://m.example.test', 'maxFileBytes': 10},
            'channels': {'instagram': {'enabled': True, 'route': 'instagram', 'accountId': IG, 'ownerId': OWNER, 'ownerIdVerified': True,
                'identityVerified': True, 'profileUrl': 'https://www.instagram.com/studiozeroflow/'}}}
        self.adapter = InstagramAdapter(self.ledger, self.config, self.transport, lambda: SENTINEL)
        self.payload = {**companion(), 'parent': {'remoteId': '900', 'permalink': 'https://www.instagram.com/reel/900/'}}
        self.job = {'id': 'c1', 'platform': 'instagram', 'account': IG, 'dispatched_at': '2026-10-12T13:02:00+00:00'}

    def transport(self, method, path, params, token):
        self.assertEqual(token, SENTINEL)
        self.calls.append((method, path, params))
        if path == 'me':
            return {'id': OWNER, 'user_id': IG, 'username': 'studiozeroflow'}
        if method == 'POST' and path == '900/comments':
            if self.lose:
                raise PublishError('uncertain')
            return {'id': '777'}
        if path == '900/comments':
            return {'data': self.comments}
        raise AssertionError(path)

    def comment(self, **change):
        return {'id': '777', 'text': self.payload['caption'], 'username': 'studiozeroflow',
                'timestamp': '2026-10-12T13:02:05+0000', **change}

    def test_ambiguous_comment_reconciles_by_exact_text_without_resend(self):
        self.raises('uncertain', self.adapter.publish, self.job, self.payload)
        self.raises('uncertain', self.adapter.publish, self.job, self.payload)
        posts = [c for c in self.calls if c[0] == 'POST']
        self.assertEqual(posts, [('POST', '900/comments', {'message': self.payload['caption']})])
        self.comments = [self.comment(username='someone'), self.comment(id='778', text='A) other')]
        self.assertEqual(self.adapter.reconcile(self.job, self.payload), {'status': 'uncertain'})
        self.comments.append(self.comment())
        receipt = self.adapter.reconcile(self.job, self.payload)
        self.assertEqual(receipt, {'status': 'confirmed', 'remoteId': '777', 'permalink': 'https://www.instagram.com/reel/900/',
                                   'publishedAt': '2026-10-12T13:02:05+0000'})
        self.assertEqual(sum(c[0] == 'POST' for c in self.calls), 1)

    def test_runner_marks_uncertain_then_confirms(self):
        parent = self.ledger.enqueue('instagram', IG, T.isoformat(), {'episode': {'id': 'scalar:BOL:clues'}, 'caption': 'x'})
        self.ledger.update(parent, 'confirmed', remote_id='900', permalink='https://www.instagram.com/reel/900/',
                           published_at=T.isoformat(), dispatched_at=T.isoformat())
        key = self.ledger.enqueue('instagram', IG, (T+dt.timedelta(minutes=2)).isoformat(), companion())
        router = Router(BufferAdapter(self.ledger, self.config, lambda *a: self.fail('buffer'), lambda: SENTINEL), None, instagram=self.adapter)
        run_jobs(self.ledger, self.config, router, T+dt.timedelta(minutes=2))
        self.assertEqual(self.ledger.db.execute('SELECT status FROM jobs WHERE id=?', (key,)).fetchone()[0], 'uncertain')
        self.comments = [self.comment(timestamp='2026-10-12T13:02:01+00:00')]
        run_jobs(self.ledger, self.config, router, T+dt.timedelta(hours=2))
        row = self.ledger.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
        self.assertEqual((row['status'], row['remote_id'], row['permalink']), ('confirmed', '777', 'https://www.instagram.com/reel/900/'))
        self.assertNotIn('parent', json.loads(row['payload']))
        self.assertEqual(sum(c[0] == 'POST' for c in self.calls), 1)

    def test_success_and_bad_parent(self):
        self.lose = False
        self.assertEqual(self.adapter.publish(self.job, self.payload), {'remoteId': '777'})
        self.raises('rejected', self.adapter.publish, {**self.job, 'id': 'c2'}, {**self.payload, 'parent': {'remoteId': '../me'}})
        self.raises('rejected', self.adapter.publish, {**self.job, 'id': 'c3'}, {**companion('poll'), 'parent': self.payload['parent']})

    def test_path_allowlist(self):
        from instagram_adapter import request
        for path in ('me/comments', '900/comments/1', 'https://evil.test/900/comments'):
            self.raises('rejected', request, 'POST', path, {}, SENTINEL)

        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass
        with patch('instagram_adapter.urllib.request.urlopen', return_value=Response(b'{"id":"777"}')) as opened:
            self.assertEqual(request('POST', '900/comments', {'message': 'hi'}, SENTINEL), {'id': '777'})
        self.assertEqual(opened.call_args[0][0].full_url, 'https://graph.instagram.com/v26.0/900/comments')


class ThreadsReplyTests(AdapterBase):
    def setUp(self):
        super().setUp()
        self.calls, self.replies = [], []
        self.config = {'paused': False, 'schedule': {'maxLatenessMinutes': 120},
                       'channels': {'threads': {'enabled': True, 'route': 'threads', 'accountId': '42', 'threadsFormat': 'video',
                                                'profileUrl': 'https://www.threads.com/@studiozeroflow'}}}
        self.adapter = ThreadsAdapter(self.ledger, self.config, self.transport, lambda: SENTINEL)
        self.payload = {**companion('poll'), 'parent': {'remoteId': '500', 'permalink': 'https://www.threads.com/@studiozeroflow/post/500'}}
        self.job = {'id': 't1', 'platform': 'threads', 'account': '42', 'dispatched_at': '2026-10-12T13:02:00+00:00'}
        self.post = {'id': '601', 'text': self.payload['caption'], 'permalink': 'https://www.threads.com/@studiozeroflow/post/601',
                     'timestamp': '2026-10-12T13:02:09+00:00', 'username': 'studiozeroflow', 'replied_to': {'id': '500'}}

    def transport(self, method, path, params, token):
        self.calls.append((method, path, params))
        if path == 'me':
            return {'id': '42', 'username': 'studiozeroflow'}
        if path == 'me/threads_publishing_limit':
            return {'data': [{'quota_usage': 0, 'config': {'quota_total': 250}}]}
        if method == 'POST' and path == 'me/threads':
            return {'id': '321'}
        if path == '321':
            return {'id': '321', 'status': 'FINISHED'}
        if path == 'me/threads_publish':
            raise PublishError('uncertain')
        if path == 'me/replies':
            return {'data': self.replies}
        raise AssertionError(path)

    def test_text_reply_publish_and_reconcile_by_exact_text_under_parent(self):
        self.assertEqual(self.adapter.publish(self.job, self.payload), {'remoteId': 'container:321'})
        method, path, params = [c for c in self.calls if c[0] == 'POST'][0]
        self.assertEqual(params, {'media_type': 'TEXT', 'text': self.payload['caption'], 'reply_to_id': '500'})
        self.assertNotIn('poll_attachment', params)
        self.raises('uncertain', self.adapter.reconcile, self.job, self.payload)
        self.replies = [{**self.post, 'replied_to': {'id': '499'}}]
        self.assertEqual(self.adapter.reconcile(self.job, self.payload), {'status': 'uncertain'})
        self.replies.append(self.post)
        receipt = self.adapter.reconcile(self.job, self.payload)
        self.assertEqual((receipt['status'], receipt['remoteId']), ('confirmed', '601'))
        self.assertEqual(sum(c[1] == 'me/threads_publish' for c in self.calls), 1)
        self.assertEqual(sum(c[0] == 'POST' and c[1] == 'me/threads' for c in self.calls), 1)

    def test_ambiguous_container_create_is_never_resent(self):
        def lost(method, path, params, token):
            if method == 'POST':
                self.calls.append(path)
                raise PublishError('uncertain')
            return self.transport(method, path, params, token)
        self.adapter.transport = lost
        self.raises('uncertain', self.adapter.publish, self.job, self.payload)
        self.raises('uncertain', self.adapter.publish, self.job, self.payload)
        self.assertEqual(self.adapter.reconcile(self.job, self.payload), {'status': 'uncertain'})
        self.assertEqual(self.calls.count('me/threads'), 1)

    def test_missing_reply_grant_is_authorization_and_blocks(self):
        from threads_adapter import request
        body = json.dumps({'error': {'message': SENTINEL, 'type': 'OAuthException', 'code': 10}}).encode()
        error = urllib.error.HTTPError('https://graph.threads.net', 400, 'x', {}, io.BytesIO(body))
        with patch('threads_adapter.urllib.request.urlopen', side_effect=error):
            self.raises('authorization', request, 'POST', 'me/threads', {'reply_to_id': '500'}, SENTINEL)
        error.close()
        self.raises('rejected', request, 'GET', 'me/replies/x', {}, SENTINEL)

        def denied(method, path, params, token):
            if method == 'POST':
                self.calls.append(path)
                raise PublishError('authorization')
            return self.transport(method, path, params, token)
        self.adapter.transport = denied
        parent = self.ledger.enqueue('threads', '42', T.isoformat(), {'episode': {'id': 'scalar:BOL:clues'}, 'caption': 'x'})
        self.ledger.update(parent, 'confirmed', remote_id='500', published_at=T.isoformat())
        key = self.ledger.enqueue('threads', '42', (T+dt.timedelta(minutes=2)).isoformat(), companion('poll'))
        router = Router(BufferAdapter(self.ledger, self.config, lambda *a: self.fail('buffer'), lambda: SENTINEL), self.adapter)
        for minutes in (2, 70, 200):
            run_jobs(self.ledger, self.config, router, T+dt.timedelta(minutes=minutes))
        row = self.ledger.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
        self.assertEqual((row['status'], row['error'], row['attempts']), ('blocked', 'authorization', 1))
        self.assertEqual(self.calls.count('me/threads'), 1)
        self.assertEqual(self.ledger.db.execute('SELECT status FROM jobs WHERE id=?', (parent,)).fetchone()[0], 'confirmed')


class BlueskyReplyTests(AdapterBase):
    def setUp(self):
        super().setUp()
        self.records, self.creates = {}, []
        self.config = {'identities': IDENTITIES, 'channels': {'bluesky': {'accountId': DID, 'profileUrl': 'https://bsky.app/profile/'+HANDLE}}}
        self.adapter = BlueskyAdapter(self.ledger, self.config, self.transport, lambda: SENTINEL, lambda _: b'x')
        self.parent_job = {'id': 'p1', 'account': DID, 'dispatched_at': '2026-10-12T13:00:00+00:00'}
        self.job = {'id': 'c1', 'account': DID, 'dispatched_at': '2026-10-12T13:02:00+00:00'}

    def transport(self, method, host, endpoint, params=None, token=None, video=None):
        if endpoint.endswith('createSession'):
            self.assertEqual(params['password'], SENTINEL)
            return {'did': DID, 'handle': HANDLE, 'emailConfirmed': True, 'accessJwt': 'jwt',
                    'didDoc': {'service': [{'id': '#atproto_pds', 'serviceEndpoint': PDS}]}}
        if endpoint.endswith('getServiceAuth'): return {'token': 'svc'}
        if endpoint.endswith('getUploadLimits'): return {'canUpload': True, 'remainingDailyVideos': 2, 'remainingDailyBytes': 100}
        if endpoint.endswith('uploadVideo'): return {'jobId': 'j', 'blob': {'$type': 'blob', 'ref': {'$link': 'b'}, 'mimeType': 'video/mp4', 'size': 1}}
        if endpoint.endswith('getRecord'):
            if params['rkey'] not in self.records: return {'missing': True}
            return {'value': self.records[params['rkey']], 'cid': 'cid-'+params['rkey'], 'uri': 'at://'+DID+'/app.bsky.feed.post/'+params['rkey']}
        if endpoint.endswith('createRecord'):
            self.creates.append(params)
            self.records[params['rkey']] = params['record']
            return {'uri': 'x'}
        raise AssertionError(endpoint)

    def confirm_parent(self):
        payload = {'caption': 'Guess! https://www.scalargame.com/', 'link': 'https://www.scalargame.com/', 'media': {'sha256': 'h'}}
        self.adapter.publish(self.parent_job, payload)
        self.adapter.reconcile(self.parent_job, payload)
        return self.adapter.reconcile(self.parent_job, payload)

    def test_reply_uses_parent_strong_refs_and_reconciles(self):
        parent = self.confirm_parent()
        self.assertEqual(parent['status'], 'confirmed')
        rkey = parent['remoteId'].rsplit('/', 1)[1]
        payload = {**companion(), 'parent': {'remoteId': parent['remoteId'], 'permalink': parent['permalink']}}
        self.adapter.publish(self.job, payload)
        record = self.creates[-1]['record']
        ref = {'uri': parent['remoteId'], 'cid': 'cid-'+rkey}
        self.assertEqual(record['reply'], {'root': ref, 'parent': ref})
        self.assertEqual(record['text'], payload['caption'])
        self.assertNotIn('embed', record)
        self.raises('uncertain', self.adapter.publish, self.job, payload)
        receipt = self.adapter.reconcile(self.job, payload)
        self.assertEqual(receipt['status'], 'confirmed')
        self.assertEqual(len(self.creates), 2)

    def test_lost_reply_response_reconciles_without_resend(self):
        parent = self.confirm_parent()
        payload = {**companion(), 'parent': {'remoteId': parent['remoteId']}}
        original = self.transport
        def lose(method, host, endpoint, params=None, token=None, video=None):
            result = original(method, host, endpoint, params, token, video)
            if endpoint.endswith('createRecord'): raise PublishError('uncertain')
            return result
        self.adapter.transport = lose
        self.raises('uncertain', self.adapter.publish, self.job, payload)
        self.adapter.transport = original
        self.assertEqual(self.adapter.reconcile(self.job, payload)['status'], 'confirmed')
        self.assertEqual(len(self.creates), 2)

    def test_parent_without_checkpoint_cid_is_rejected(self):
        self.raises('rejected', self.adapter.publish, self.job, {**companion(), 'parent': {'remoteId': 'at://'+DID+'/app.bsky.feed.post/unknown'}})
        with self.ledger.db:
            self.ledger.db.execute("INSERT INTO bluesky_uploads(job,rkey,record) VALUES('old','oldkey','{}')")
        self.raises('rejected', self.adapter.publish, self.job, {**companion(), 'parent': {'remoteId': 'at://'+DID+'/app.bsky.feed.post/oldkey'}})
        self.raises('rejected', self.adapter.publish, self.job, {**companion(), 'parent': {'remoteId': 'at://did:plc:other/app.bsky.feed.post/oldkey'}})
        self.assertEqual(self.creates, [])


class BufferThreadTests(AdapterBase):
    def setUp(self):
        super().setUp()
        self.calls = []
        class Budget:
            def consume_call(self, now): pass
        def transport(query, variables, token):
            self.calls.append(variables)
            if 'mutation' not in query:
                return {'channel': {'id': 'x-1', 'service': 'twitter', 'serviceId': 'p', 'externalLink': 'https://x.com/s', 'isDisconnected': False, 'isLocked': False}}
            return {'createPost': {'__typename': 'PostActionSuccess', 'post': {'id': 'post', 'schedulingType': 'automatic', 'channelId': 'x-1'}}}
        self.adapter = BufferAdapter(Budget(), {'channels': {'x': {'providerAccountId': 'p', 'profileUrl': 'https://x.com/s'},
                                                             'youtube': {'providerAccountId': 'p', 'profileUrl': 'https://x.com/s'}}}, transport, lambda: SENTINEL)
        self.job = {'platform': 'x', 'account': 'x-1'}
        self.payload = {'caption': 'Which country? A) B) C)', 'media': {'url': 'https://m.example.test/a.mp4'}, 'metadata': {}, 'thread': ['A) Bolivia B) Chile C) Peru — reply with your letter']}

    def test_thread_refused_until_verified(self):
        self.assertFalse(buffer_adapter.X_THREAD_VERIFIED)
        with patch('buffer_adapter.verify_media') as verify:
            self.raises('rejected', self.adapter.publish, self.job, self.payload)
        verify.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_documented_thread_shape_when_verified(self):
        with patch('buffer_adapter.verify_media'), patch('buffer_adapter.X_THREAD_VERIFIED', True):
            self.assertEqual(self.adapter.publish(self.job, self.payload), {'remoteId': 'post'})
            post = self.calls[-1]['input']
            self.assertEqual(post['text'], self.payload['caption'])
            self.assertEqual(post['metadata'], {'twitter': {'thread': [
                {'text': self.payload['caption'], 'assets': [{'video': {'url': 'https://m.example.test/a.mp4'}}]},
                {'text': self.payload['thread'][0]}]}})
            self.raises('rejected', self.adapter.publish, {'platform': 'youtube', 'account': 'x-1'}, self.payload)
            self.raises('rejected', self.adapter.publish, self.job, {**self.payload, 'thread': ['']})
        self.assertEqual(len(self.calls), 2)

    def test_plain_post_unchanged_and_companions_rejected(self):
        with patch('buffer_adapter.verify_media'):
            self.adapter.publish(self.job, {**self.payload, 'thread': None})
            self.assertEqual(self.calls[-1]['input']['metadata'], {})
            for platform in ('x', 'youtube', 'tiktok', 'instagram'):
                self.raises('rejected', self.adapter.publish, {'platform': platform, 'account': 'x-1'}, companion())
        self.assertEqual(len(self.calls), 2)


class NoRouteTests(AdapterBase):
    def test_facebook_companion_rejected_without_calls(self):
        calls = []
        adapter = FacebookAdapter(self.ledger, {'identities': IDENTITIES, 'channels': {'facebook': {'accountId': PAGE, 'profileUrl': PROFILE}}},
                                  lambda *a: calls.append(a), lambda: SENTINEL, lambda *a: calls.append(a), lambda p: b'x')
        self.raises('rejected', adapter.publish, {'id': 'f', 'account': PAGE}, {**companion(), 'parent': {'remoteId': '1'}})
        self.assertEqual(calls, [])

    def test_router_sends_companions_to_platform_adapter(self):
        from types import SimpleNamespace
        config = {'channels': {'instagram': {'route': 'instagram', 'accountId': IG}, 'youtube': {'route': 'buffer'}}}
        buffer, threads, bluesky, facebook, instagram = SimpleNamespace(config=config), object(), object(), object(), object()
        router = Router(buffer, threads, bluesky, facebook, instagram)
        expected = {'instagram': instagram, 'threads': threads, 'bluesky': bluesky, 'facebook': facebook, 'youtube': buffer, 'x': buffer}
        for platform, target in expected.items():
            self.assertIs(router.route({'platform': platform, 'account': IG}), target)


if __name__ == '__main__':
    unittest.main()
