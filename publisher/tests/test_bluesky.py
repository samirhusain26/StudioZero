import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from runner import Ledger
from bluesky_adapter import BlueskyAdapter, HANDLE, PDS, link_facets, record_key
from fixture_ids import DID, IDENTITIES
from buffer_adapter import PublishError


class Transport:
    def __init__(self):
        self.creates = 0
        self.uploads = 0
        self.record = None
        self.lose_create = False
        self.lose_upload = False
        self.confirmed = True
    def __call__(self, method, host, endpoint, params=None, token=None, video=None):
        if endpoint.endswith('createSession'):
            return {'did': DID, 'handle': HANDLE, 'emailConfirmed': self.confirmed,
                    'accessJwt': 'test-only', 'didDoc': {'service': [{'id': '#atproto_pds', 'serviceEndpoint': PDS}]}}
        if endpoint.endswith('getServiceAuth'): return {'token': 'test-only'}
        if endpoint.endswith('getUploadLimits'): return {'canUpload': True, 'remainingDailyVideos': 2, 'remainingDailyBytes': 100}
        if endpoint.endswith('uploadVideo'):
            self.uploads += 1
            if self.lose_upload: raise PublishError('uncertain')
            return {'jobId': 'job', 'blob': {'$type': 'blob', 'ref': {'$link': 'test-cid'}, 'mimeType': 'video/mp4', 'size': 1}}
        if endpoint.endswith('getRecord'):
            if not self.record: return {'missing': True}
            return {'value': self.record, 'cid': 'test-cid', 'uri': 'at://'+DID+'/app.bsky.feed.post/'+params['rkey']}
        if endpoint.endswith('createRecord'):
            import re
            assert re.fullmatch('[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}', params['rkey'])
            self.creates += 1
            self.record = params['record']
            if self.lose_create: raise PublishError('uncertain')
            return {'uri': 'test'}
        raise AssertionError(endpoint)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name)/'ledger.sqlite3')
        self.config = {'identities': IDENTITIES, 'channels': {'bluesky': {'accountId': DID, 'profileUrl': 'https://bsky.app/profile/'+HANDLE}}}
        self.job = {'id': 'test', 'account': DID, 'dispatched_at': '2026-10-06T23:00:00+00:00'}
        self.payload = {'caption': 'Guess! https://www.scalargame.com/', 'link': 'https://www.scalargame.com/', 'media': {'sha256': 'hash'}}
        self.transport = Transport()
        self.adapter = BlueskyAdapter(self.ledger, self.config, self.transport, lambda: 'test-only', lambda _: b'x')
    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()
    def test_publish_reconcile_and_repeat_do_not_duplicate(self):
        self.adapter.publish(self.job, self.payload)
        self.adapter.reconcile(self.job, self.payload)
        result = self.adapter.reconcile(self.job, self.payload)
        self.adapter.publish(self.job, self.payload)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual((self.transport.uploads, self.transport.creates), (1, 1))
    def test_lost_create_response_reconciles_exact_record(self):
        self.transport.lose_create = True
        self.adapter.publish(self.job, self.payload)
        with self.assertRaises(PublishError): self.adapter.reconcile(self.job, self.payload)
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'confirmed')
        self.assertEqual(self.transport.creates, 1)
        self.transport.record['text'] = 'Changed'
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'uncertain')
    def test_lost_upload_response_is_held(self):
        self.transport.lose_upload = True
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)
        self.adapter.publish(self.job, self.payload)
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'uncertain')
        self.assertEqual(self.transport.uploads, 1)
        self.assertEqual(self.transport.creates, 0)
    def test_identity_and_email_gate_before_upload(self):
        self.transport.confirmed = False
        with self.assertRaises(PublishError): self.adapter.publish(self.job, self.payload)
        self.assertEqual(self.transport.uploads, 0)
    def test_unicode_link_uses_byte_offsets(self):
        text = '🌎 https://example.com'
        self.assertEqual(link_facets(text, 'https://example.com')[0]['index']['byteStart'], 5)
    def test_record_key_is_stable_and_timestamp_based(self):
        key = record_key(self.job)
        self.assertEqual(key, record_key(dict(self.job)))
        self.assertRegex(key, '^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$')
        self.assertNotEqual(key, record_key({**self.job, 'dispatched_at': '2026-10-06T23:00:01+00:00'}))
    def test_pause_before_creation(self):
        self.adapter.publish(self.job, self.payload)
        self.adapter.pause_check = lambda: True
        self.assertEqual(self.adapter.reconcile(self.job, self.payload)['status'], 'uncertain')
        self.assertEqual(self.transport.creates, 0)
