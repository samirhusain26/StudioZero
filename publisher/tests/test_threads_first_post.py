import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'publisher/app'))
from runner import Ledger,UTC
from threads_first_post import execute
from fixture_ids import IDENTITIES
class Adapter:
    def __init__(self,fail=False):self.creates=0;self.reads=0;self.fail=fail
    def publish(self,j,p):
        self.creates+=1
        if self.fail:raise TimeoutError()
        return {'remoteId':'container:123'}
    def reconcile(self,j,p):self.reads+=1;return {'status':'confirmed','remoteId':'123','permalink':'https://www.threads.com/@studiozeroflow/post/test','publishedAt':'2026-10-06T12:00:00+00:00'}
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'ledger.sqlite3');self.now=dt.datetime(2026,10,6,12,tzinfo=UTC)
        self.config={'paused':True,'identities':IDENTITIES,'channels':{'threads':{'enabled':False,'accountId':'1000000000000003','identityVerified':True,'threadsFormat':'video'}}}
        self.plan={'kind':'one-time-threads-test','recurringPublishing':False,'account':'1000000000000003','slot':self.now.isoformat(),'payload':{'episode':{'id':'test','answer':'a','verification':{'status':'verified','sourceHash':'hash'},'provenance':{'ids':['source']}}}}
        self.digest=hashlib.sha256(json.dumps(self.plan,sort_keys=True).encode()).hexdigest()
    def tearDown(self):self.ledger.db.close();self.temp.cleanup()
    def test_accepted_reconciles_without_duplicate(self):
        a=Adapter();execute(self.ledger,self.config,self.plan,self.digest,a,self.now);r=execute(self.ledger,self.config,self.plan,self.digest,a,self.now);execute(self.ledger,self.config,self.plan,self.digest,a,self.now)
        self.assertEqual(r['status'],'confirmed');self.assertEqual(a.creates,1);self.assertTrue(self.config['paused'])
    def test_lost_response_only_reconciles(self):
        a=Adapter(True);execute(self.ledger,self.config,self.plan,self.digest,a,self.now);execute(self.ledger,self.config,self.plan,self.digest,a,self.now);self.assertEqual((a.creates,a.reads),(1,1))
    def test_tampering_never_calls_api(self):
        a=Adapter();self.plan['account']='other'
        with self.assertRaises(ValueError):execute(self.ledger,self.config,self.plan,self.digest,a,self.now)
        self.assertEqual(a.creates,0)

class TopicCaptionTests(unittest.TestCase):
    def test_only_verified_first_topic_conversion_matches(self):
        from threads_adapter import caption_matches
        expected='Question? #geography #puzzles'
        self.assertTrue(caption_matches({'text':'Question? geography #puzzles','topic_tag':'geography'},expected))
        self.assertFalse(caption_matches({'text':'Question? geography #puzzles'},expected))
        self.assertFalse(caption_matches({'text':'Changed? geography #puzzles','topic_tag':'geography'},expected))
        self.assertFalse(caption_matches({'text':'Question? geography puzzles','topic_tag':'geography'},expected))
