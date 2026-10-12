from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import os

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
from buffer_adapter import PublishError
from instagram_adapter import InstagramAdapter
from runner import Ledger

ACCOUNT = '17841400000000001'
OWNER = '27000000000000007'
class Remote:
    def __init__(self):
        self.status = 'FINISHED'; self.used = 0; self.total = 25; self.publish_lost = False
        self.calls = []; self.items = []; self.owner = OWNER; self.profile_id = OWNER; self.caption = 'Exact caption'
    def call(self, method, path, params, token):
        self.calls.append((method, path, params))
        if path == 'me': return {'id': self.profile_id, 'user_id': ACCOUNT, 'username': 'studiozeroflow'}
        if path.endswith('/content_publishing_limit'):
            return {'data': [{'quota_usage': self.used, 'config': {'quota_total': self.total}}]}
        if method == 'POST' and path.endswith('/media'):
            return {'id': '123456789'}
        if path == '123456789': return {'id': '123456789', 'status_code': self.status}
        if method == 'POST' and path.endswith('/media_publish'):
            if self.publish_lost: raise PublishError('uncertain')
            return {'id': '900'}
        if path.endswith('/media'): return {'data': self.items}
        return self.post()
    def post(self):
        return {'id': '900', 'caption': self.caption, 'media_type': 'VIDEO', 'media_product_type':'REELS',
                'owner': {'id': self.owner}, 'username': 'studiozeroflow',
                'timestamp': '2026-10-06T12:00:00+00:00',
                'permalink': 'https://www.instagram.com/reel/900/'}

class InstagramTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.ledger = Ledger(Path(self.tmp.name)/'db.sqlite')
        self.remote = Remote()
        self.config = {'media': {'baseUrl': 'https://media.example.test', 'maxFileBytes': 1000},
            'channels': {'instagram': {'accountId': ACCOUNT, 'profileUrl': 'https://www.instagram.com/studiozeroflow/',
                'identityVerified': True, 'publishingVerified': True, 'ownerId': OWNER,
                'ownerIdVerified': True, 'route': 'instagram'}}}
        self.job = {'id': 'j1', 'platform': 'instagram', 'account': ACCOUNT, 'dispatched_at': '2026-10-06T11:00:00+00:00'}
        self.payload = {'caption': 'Exact caption', 'media': {'url': 'https://media.example.test/a.mp4',
            'sha256': 'a'*64, 'rightsReviewed': True}}
        self.adapter = InstagramAdapter(self.ledger, self.config, self.remote.call, lambda: 'fixture')
        self.adapter.quota = lambda: None
        self.adapter.verify_media = lambda p, c: None
        import instagram_adapter
        self.verify_patch = patch.object(instagram_adapter, 'verify_media')
        self.verify_patch.start()
    def tearDown(self):
        self.verify_patch.stop(); self.ledger.db.close(); self.tmp.cleanup()
    def create_container(self): self.adapter.publish(self.job, self.payload)

    def test_direct_identity_does_not_reuse_buffer_channel_id(self):
        self.job['account'] = 'a00000000000000000000002'
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)
        self.assertFalse(any(m == 'POST' for m, _, _ in self.remote.calls))
    def test_quota_and_pause_prevent_mutations(self):
        self.remote.used = self.remote.total
        self.adapter.quota = lambda: (_ for _ in ()).throw(PublishError('rate_limit'))
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)
        self.assertFalse(any(m == 'POST' for m, _, _ in self.remote.calls))
        self.adapter.quota = lambda: None; self.adapter.pause_check = lambda: True
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)
        self.assertFalse(any(m == 'POST' for m, _, _ in self.remote.calls))
    def test_pending_and_error_processing_never_publish(self):
        self.create_container(); self.remote.status = 'IN_PROGRESS'
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'uncertain')
        self.remote.status = 'ERROR'
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'failed')
        self.assertFalse(any(path.endswith('/media_publish') for _, path, _ in self.remote.calls))
    def test_lost_publish_response_reconciles_without_duplicate(self):
        self.create_container(); self.remote.publish_lost = True
        with self.assertRaises(PublishError): self.adapter.reconcile(self.job, self.payload)
        self.remote.items = [self.remote.post()]
        result = self.adapter.reconcile(self.job, self.payload)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['remoteId'], '900')
        self.assertEqual(sum(path.endswith('/media_publish') for _, path, _ in self.remote.calls), 1)
    def test_processing_poll_then_publish_checkpoints(self):
        self.create_container(); self.remote.status = 'IN_PROGRESS'
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'uncertain')
        self.remote.status = 'FINISHED'
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'uncertain')
        self.assertTrue(self.ledger.db.execute('SELECT publish_attempted FROM instagram_reels').fetchone()[0])
        self.remote.items = [self.remote.post()]
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'confirmed')
    def test_wrong_caption_owner_and_hostile_permalink_do_not_confirm(self):
        for change in ({'caption':'other'}, {'owner':{'id':'other'}},
                       {'permalink':'https://instagram.com.attacker.invalid/reel/900/'}):
            post = self.remote.post(); post.update(change)
            self.assertEqual(self.adapter._receipt(post, self.payload, '900')['status'], 'uncertain')
        post = self.remote.post()
        self.assertEqual(self.adapter._receipt(post, self.payload, '901')['status'], 'uncertain')
    def test_request_restricts_paths_and_refresh_permission_identity(self):
        from instagram_adapter import request
        with self.assertRaises(PublishError): request('GET', 'https://attacker.invalid', {}, 'token')
        self.config['channels']['instagram']['identityVerified'] = False
        with self.assertRaises(PublishError): self.adapter.identity(self.job)

    def test_identity_uses_instagram_login_user_id_field(self):
        self.adapter.identity(self.job)
        call = self.remote.calls[-1]
        self.assertEqual(call[2]['fields'], 'id,user_id,username')
        self.assertEqual(self.config['channels']['instagram']['accountId'], ACCOUNT)
        self.assertEqual(self.config['channels']['instagram']['ownerId'], OWNER)

    def test_missing_or_unverified_owner_id_fails_closed(self):
        channel = self.config['channels']['instagram']
        channel['ownerIdVerified'] = False
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)
        channel['ownerIdVerified'] = True
        channel.pop('ownerId')
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)

    def test_profile_id_must_match_separately_verified_owner_id(self):
        self.remote.profile_id = 'wrong-profile-id'
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)

    def test_private_token_permissions_are_required(self):
        from instagram_adapter import token
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory)/'INSTAGRAM_ACCESS_TOKEN'
            secret.write_text('fixture-token')
            secret.chmod(0o644)
            with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': directory}):
                with self.assertRaises(PublishError): token()
                secret.chmod(0o600)
                self.assertEqual(token(), 'fixture-token')
                alias = Path(directory)/'alias'
                alias.symlink_to(secret)
                (Path(directory)/'INSTAGRAM_ACCESS_TOKEN').unlink()
                (Path(directory)/'INSTAGRAM_ACCESS_TOKEN').symlink_to(alias)
                with self.assertRaises(PublishError): token()
    def comment_setup(self, comment='18000000000000555', count=1, exists=True, listed=()):
        # Instagram Login: GET /{comment-id} answers {} (or 400 when unknown), the comments list omits own comments.
        calls = []
        def call(method, path, params, token):
            calls.append((method, path, params))
            if path == 'me': return {'id': OWNER, 'user_id': ACCOUNT, 'username': 'studiozeroflow'}
            if method == 'POST': raise AssertionError('reconcile must never post')
            if path == comment:
                if not exists: raise PublishError('rejected')
                return {}
            if path == '900': return {'id': '900', 'comments_count': count}
            if path == '900/comments': return {'data': list(listed)}
            raise AssertionError(path)
        self.adapter.transport = call
        with self.ledger.db:
            self.ledger.db.execute('INSERT INTO instagram_comments(job,media,comment) VALUES(?,?,?)', ('j1', '900', comment))
        payload = {'caption': 'A) Spain  B) Japan — comment your letter', 'companion': {'parentEpisode': 'e1'}, 'kind': 'comment',
                   'parent': {'remoteId': '900', 'permalink': 'https://www.instagram.com/reel/900/'}}
        return calls, payload

    def test_known_comment_confirms_from_object_and_parent_count(self):
        calls, payload = self.comment_setup()
        result = self.adapter.reconcile(self.job, payload)
        self.assertEqual(result, {'status': 'confirmed', 'remoteId': '18000000000000555',
                                  'permalink': 'https://www.instagram.com/reel/900/', 'publishedAt': self.job['dispatched_at']})
        self.assertFalse(any(m == 'POST' for m, _, _ in calls))

    def test_known_comment_missing_or_uncounted_stays_uncertain(self):
        for options in ({'exists': False}, {'count': 0}, {'count': None}, {'count': True}):
            with self.subTest(**options):
                self.ledger.db.execute('DELETE FROM instagram_comments')
                calls, payload = self.comment_setup(**options)
                self.assertEqual(self.adapter.reconcile(self.job, payload), {'status': 'uncertain'})
                self.assertFalse(any(m == 'POST' for m, _, _ in calls))

    def test_known_comment_other_errors_propagate_and_unknown_id_uses_the_list(self):
        calls, payload = self.comment_setup()
        def broken(method, path, params, token):
            if path == 'me': return {'id': OWNER, 'user_id': ACCOUNT, 'username': 'studiozeroflow'}
            raise PublishError('uncertain')
        self.adapter.transport = broken
        with self.assertRaises(PublishError): self.adapter.reconcile(self.job, payload)
        # A lost create response leaves no id: only an exact own-account match in the list may confirm.
        self.ledger.db.execute('DELETE FROM instagram_comments')
        calls, payload = self.comment_setup(comment=None)
        self.assertEqual(self.adapter.reconcile(self.job, payload), {'status': 'uncertain'})
        self.assertIn(('GET', '900/comments', {'fields': 'id,text,username,timestamp', 'limit': '50'}), calls)
        with self.assertRaises(PublishError): self.adapter.publish(self.job, payload)
        self.assertFalse(any(m == 'POST' for m, _, _ in calls))

    def test_router_preserves_buffer_until_configured_and_holds_wrong_account(self):
        from types import SimpleNamespace
        from threads_adapter import Router
        direct = object(); buffer = SimpleNamespace(config=self.config)
        router = Router(buffer, object(), instagram=direct)
        self.config['channels']['instagram']['route'] = 'buffer'
        self.assertIs(router.route(self.job), buffer)
        self.config['channels']['instagram']['route'] = 'instagram'
        self.assertIs(router.route(self.job), direct)
        with self.assertRaises(PublishError): router.route({**self.job, 'account':'different'})

if __name__ == '__main__': unittest.main()
