import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from runner import Ledger, UTC
from fixture_ids import IDENTITIES, PAGE, PROFILE
from facebook_first_post import execute

class Adapter:
    def __init__(self, fail=False): self.creates=0; self.reads=0; self.fail=fail
    def publish(self, job, payload):
        self.creates+=1
        if self.fail: raise TimeoutError()
        return {'remoteId':'test'}
    def reconcile(self, job, payload):
        self.reads+=1
        return {'status':'confirmed','remoteId':'test','permalink':'https://bsky.app/profile/test/post/test','publishedAt':'2026-10-06T12:00:00+00:00'}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.ledger=Ledger(Path(self.tmp.name)/'ledger.sqlite3')
        self.now=dt.datetime(2026,10,6,12,tzinfo=UTC)
        self.config={'paused':True,'identities':IDENTITIES,'channels':{'facebook':{'enabled':False,'accountId':PAGE,'identityVerified':True,'route':'facebook','profileUrl':PROFILE}}}
        self.plan={'kind':'one-time-facebook-test','recurringPublishing':False,'account':PAGE,'slot':self.now.isoformat(),'payload':{'episode':{'id':'test','answer':'a','verification':{'status':'verified','sourceHash':'hash'},'provenance':{'ids':['source']}}}}
        self.digest=hashlib.sha256(json.dumps(self.plan,sort_keys=True).encode()).hexdigest()
    def tearDown(self): self.ledger.db.close(); self.tmp.cleanup()
    def test_normal_and_uncertain_publish_only_dispatch_once(self):
        for fail in (False,True):
            with self.subTest(fail=fail):
                self.ledger.db.execute('DELETE FROM jobs');self.ledger.db.commit()
                a=Adapter(fail)
                execute(self.ledger,self.config,self.plan,self.digest,a,self.now)
                result=execute(self.ledger,self.config,self.plan,self.digest,a,self.now)
                execute(self.ledger,self.config,self.plan,self.digest,a,self.now)
                self.assertEqual(result['status'],'confirmed');self.assertEqual(a.creates,1)
    def test_scope_or_paused_gate_never_dispatches(self):
        a=Adapter(); self.config['paused']=False
        with self.assertRaises(ValueError): execute(self.ledger,self.config,self.plan,self.digest,a,self.now)
        self.assertEqual(a.creates,0)
