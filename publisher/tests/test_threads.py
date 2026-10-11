import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'publisher/app'))
from threads_adapter import ThreadsAdapter
from runner import Ledger
from buffer_adapter import PublishError

class ThreadsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.tmp.name)/'ledger.sqlite')
        self.config={'channels':{'threads':{'profileUrl':'https://www.threads.com/@studiozeroflow'}}}
        self.job={'account':'42','remote_id':'99','dispatched_at':'2026-10-05T12:00:00+00:00'}
        self.payload={'caption':'Which country?','nativePoll':['Bolivia','Chile']}
        self.calls=[]
        def transport(method,path,params,token):
            self.calls.append((method,path,params))
            if path=='me':return {'id':'42','username':'studiozeroflow'}
            if path=='me/threads_publishing_limit':return {'data':[{'quota_usage':0,'config':{'quota_total':250}}]}
            if method=='POST':return {'id':'99'}
            return {'id':'99','text':'Which country?','permalink':'https://www.threads.com/@studiozeroflow/post/99','timestamp':'2026-10-05T12:01:00+00:00','username':'studiozeroflow'}
        self.adapter=ThreadsAdapter(self.ledger,self.config,transport,lambda:'fixture')
    def tearDown(self):self.ledger.db.close();self.tmp.cleanup()
    def test_exact_documented_poll_route(self):
        self.assertEqual(self.adapter.publish(self.job,self.payload),{'remoteId':'99'})
        method,path,params=self.calls[-1]
        self.assertEqual((method,path),('POST','me/threads'))
        self.assertEqual(params['media_type'],'TEXT');self.assertEqual(params['auto_publish_text'],'true')
        self.assertEqual(json.loads(params['poll_attachment']),{'option_a':'Bolivia','option_b':'Chile'})
        self.assertNotIn('video_url',params);self.assertNotIn('link_attachment',params)
    def test_confirmed_only_after_remote_fields(self):
        self.assertEqual(self.adapter.reconcile(self.job,self.payload)['status'],'confirmed')
    def test_wrong_identity_blocks(self):
        self.job['account']='other'
        with self.assertRaises(PublishError):self.adapter.publish(self.job,self.payload)
    def test_non_poll_video_disabled(self):
        with self.assertRaises(PublishError):self.adapter.publish(self.job,{'caption':'video','media':{'url':'https://example.test/a.mp4'}})
    def test_oversize_poll_options_rejected(self):
        with self.assertRaises(PublishError):self.adapter.publish(self.job,{'caption':'quiz','nativePoll':['x'*26,'Chile']})

    def test_video_checkpoint_and_uncertain_publish_never_repeated(self):
        self.config['channels']['threads']['threadsFormat']='video'
        self.job['id']='video-job'
        payload={'caption':'Which country?','media':{'url':'https://media.example.test/a.mp4'}}
        posts=[]
        def transport(method,path,params,token):
            if path=='me':return {'id':'42','username':'studiozeroflow'}
            if path=='me/threads_publishing_limit':return {'data':[{'quota_usage':0,'config':{'quota_total':250}}]}
            if method=='POST':
                posts.append(path)
                if path=='me/threads_publish':raise TimeoutError()
                return {'id':'123'}
            if path=='123':return {'id':'123','status':'FINISHED'}
            return {'data':[]}
        adapter=ThreadsAdapter(self.ledger,self.config,transport,lambda:'fixture')
        with patch('threads_adapter.verify_media'):
            receipt=adapter.publish(self.job,payload)
        self.assertEqual(receipt['remoteId'],'container:123')
        with self.assertRaises(TimeoutError):adapter.reconcile(self.job,payload)
        self.assertEqual(adapter.reconcile(self.job,payload)['status'],'uncertain')
        self.assertEqual(posts,['me/threads','me/threads_publish'])

    def test_processing_container_waits_without_publishing(self):
        self.job['id']='waiting'
        with self.ledger.db:self.ledger.db.execute('INSERT INTO threads_containers(job,container) VALUES(?,?)',('waiting','123'))
        adapter=ThreadsAdapter(self.ledger,self.config,lambda method,path,params,token: {'id':'42','username':'studiozeroflow'} if path=='me' else {'id':'123','status':'IN_PROGRESS'},lambda:'fixture')
        self.assertEqual(adapter.reconcile(self.job,self.payload)['status'],'uncertain')

    def test_exhausted_quota_prevents_native_poll_post(self):
        def transport(method,path,params,token):
            self.assertEqual(method,'GET')
            if path=='me':return {'id':'42','username':'studiozeroflow'}
            return {'data':[{'quota_usage':250,'config':{'quota_total':250}}]}
        adapter=ThreadsAdapter(self.ledger,self.config,transport,lambda:'fixture')
        with self.assertRaises(PublishError) as error:adapter.publish(self.job,self.payload)
        self.assertEqual(error.exception.category,'rate_limit')
if __name__=='__main__':unittest.main()
