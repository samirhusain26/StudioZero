from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'publisher/app'))
from runner import Ledger
from facebook_adapter import FacebookAdapter
from fixture_ids import IDENTITIES, PAGE, PROFILE
from buffer_adapter import PublishError

class Remote:
    def __init__(self):self.starts=0;self.finishes=0;self.uploads=0;self.published=False;self.lose_finish=False;self.lose_start=False;self.owner=PAGE
    def call(self,method,path,params,token):
        if path=='me':return {'id':self.owner,'name':'Scalargame'}
        if params.get('upload_phase')=='start':
            self.starts+=1
            if self.lose_start:raise PublishError('uncertain')
            return {'video_id':'123'}
        if params.get('upload_phase')=='finish':
            self.finishes+=1;self.published=True
            if self.lose_finish:raise PublishError('uncertain')
            return {'success':True}
        if params.get('fields')=='status':return {'status':{'uploading_phase':{'status':'complete'},'publishing_phase':{'status':'complete' if self.published else 'not_started'}}}
        return {'id':'123','from':{'id':PAGE},'description':'caption','created_time':'2026-10-06T23:00:00+0000','permalink_url':'https://www.facebook.com/reel/123/'}
    def upload(self,video,data,token):self.uploads+=1;return {'success':True}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.tmp.name)/'ledger.sqlite3');self.remote=Remote()
        self.config={'identities':IDENTITIES,'channels':{'facebook':{'accountId':PAGE,'profileUrl':PROFILE}}}
        self.job={'id':'test','account':PAGE};self.payload={'caption':'caption','media':{'url':'https://example.com/test.mp4'}}
        self.adapter=FacebookAdapter(self.ledger,self.config,self.remote.call,lambda:'test-only',self.remote.upload,lambda p:b'x')
    def tearDown(self):self.ledger.db.close();self.tmp.cleanup()
    def test_complete_and_repeated_publish_dont_duplicate(self):
        self.adapter.publish(self.job,self.payload);self.adapter.reconcile(self.job,self.payload)
        self.assertEqual(self.adapter.reconcile(self.job,self.payload)['status'],'confirmed')
        self.adapter.publish(self.job,self.payload)
        self.assertEqual((self.remote.starts,self.remote.uploads,self.remote.finishes),(1,1,1))
    def test_lost_finish_reads_receipt_without_repeating(self):
        self.remote.lose_finish=True;self.adapter.publish(self.job,self.payload)
        with self.assertRaises(PublishError):self.adapter.reconcile(self.job,self.payload)
        self.assertEqual(self.adapter.reconcile(self.job,self.payload)['status'],'confirmed');self.assertEqual(self.remote.finishes,1)
    def test_lost_start_is_held(self):
        self.remote.lose_start=True
        with self.assertRaises(PublishError):self.adapter.publish(self.job,self.payload)
        self.adapter.publish(self.job,self.payload)
        self.assertEqual(self.adapter.reconcile(self.job,self.payload)['status'],'uncertain');self.assertEqual(self.remote.starts,1)
    def test_wrong_owner_never_mutates(self):
        self.remote.owner='other'
        with self.assertRaises(PublishError):self.adapter.publish(self.job,self.payload)
        self.assertEqual(self.remote.starts,0)
    def test_pause_blocks_finish(self):
        self.adapter.publish(self.job,self.payload);self.adapter.pause_check=lambda:True
        self.assertEqual(self.adapter.reconcile(self.job,self.payload)['status'],'uncertain');self.assertEqual(self.remote.finishes,0)
    def test_quota_blocks_finish(self):
        import time
        self.adapter.publish(self.job,self.payload)
        self.ledger.db.execute('CREATE TABLE facebook_finishes(at REAL)')
        self.ledger.db.executemany('INSERT INTO facebook_finishes VALUES(?)',[(time.time(),)]*30);self.ledger.db.commit()
        with self.assertRaises(PublishError):self.adapter.reconcile(self.job,self.payload)
        self.assertEqual(self.remote.finishes,0)
    def test_relative_api_permalink_is_normalized(self):
        self.adapter.publish(self.job,self.payload);self.adapter.reconcile(self.job,self.payload)
        original=self.adapter.transport
        def relative(*args):
            data=original(*args)
            if 'permalink_url' in data:data['permalink_url']='/reel/123/'
            return data
        self.adapter.transport=relative
        self.assertEqual(self.adapter.reconcile(self.job,self.payload)['permalink'],'https://www.facebook.com/reel/123/')
