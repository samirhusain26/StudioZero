import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
from instagram_first_post import execute
from runner import Ledger, UTC


class Adapter:
    def __init__(self): self.calls = 0
    def publish(self, job, payload): self.calls += 1; return {'remoteId':'container:123'}
    def reconcile(self, job, payload): return {'status':'uncertain'}


class InstagramFirstPostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.ledger = Ledger(Path(self.tmp.name)/'ledger.sqlite')
        self.now = dt.datetime(2026, 10, 6, 12, tzinfo=UTC)
        self.config = {'paused':True, 'channels': {'instagram': {'enabled':False,
            'accountId':'17841400000000001', 'identityVerified':True, 'publishingVerified':False,
            'profileUrl':'https://www.instagram.com/studiozeroflow/', 'route':'instagram'}}}
        self.plan = {'kind':'one-time-instagram-test', 'recurringPublishing':False,
            'account':'17841400000000001', 'slot':self.now.isoformat(),
            'payload':{'episode':{'id':'ep','answer':'A','verification':{'status':'verified','sourceHash':'h'},
                'provenance':{'ids':['source']}}, 'caption':'caption', 'media':{'url':'https://media.test/a.mp4',
                'sha256':'a'*64, 'rightsReviewed':True}}}
        self.digest = hashlib.sha256(json.dumps(self.plan, sort_keys=True).encode()).hexdigest()
    def tearDown(self): self.ledger.db.close(); self.tmp.cleanup()
    def test_one_time_test_can_establish_publishing_verification(self):
        adapter = Adapter()
        result = execute(self.ledger, self.config, self.plan, self.digest, adapter, self.now)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(adapter.calls, 1)
    def test_scope_hash_and_pause_still_gate_test(self):
        with self.assertRaises(ValueError): execute(self.ledger, self.config, self.plan, 'wrong', Adapter(), self.now)
        self.config['paused'] = False
        with self.assertRaises(ValueError): execute(self.ledger, self.config, self.plan, self.digest, Adapter(), self.now)
    def test_previous_buffer_episode_cannot_be_posted_again(self):
        self.config['channels']['instagram']['previousAccountIds'] = ['old-buffer-connection']
        self.ledger.enqueue('instagram', 'old-buffer-connection', self.now.isoformat(), self.plan['payload'])
        adapter = Adapter()
        with self.assertRaises(ValueError):
            execute(self.ledger, self.config, self.plan, self.digest, adapter, self.now)
        self.assertEqual(adapter.calls, 0)

if __name__ == '__main__': unittest.main()
