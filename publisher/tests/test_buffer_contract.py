import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from buffer_adapter import request, PublishError, BufferAdapter

class BufferContractTests(unittest.TestCase):
    def failure(self, code, body):
        error=urllib.error.HTTPError('https://api.buffer.com',code,'failure',{},io.BytesIO(json.dumps(body).encode()))
        with patch('buffer_adapter.urllib.request.urlopen',side_effect=error):
            with self.assertRaises(PublishError) as caught: request('mutation{}',{},'test-token')
        error.close()
        return caught.exception.category
    def test_coercion_rejection_is_safe_and_redacted(self):
        self.assertEqual(self.failure(400,{'errors':[{'message':'Variable input got invalid value PRIVATE'}]}),'rejected')
    def test_execution_and_server_errors_remain_uncertain(self):
        self.assertEqual(self.failure(400,{'errors':[{'message':'failure','path':['createPost']}]}),'uncertain')
        self.assertEqual(self.failure(500,{}),'uncertain')
    def test_publish_uses_live_share_mode(self):
        class Ledger:
            def consume_call(self, now): pass
        calls=[]
        def transport(query, variables, token):
            calls.append(variables)
            if 'channel' in query and 'mutation' not in query:
                return {'channel':{'id':'account','service':'youtube','serviceId':'provider','externalLink':'https://example.test/profile','isDisconnected':False,'isLocked':False}}
            return {'createPost':{'__typename':'PostActionSuccess','post':{'id':'post','schedulingType':'automatic','channelId':'account'}}}
        adapter=BufferAdapter(Ledger(),{'channels':{'youtube':{'providerAccountId':'provider','profileUrl':'https://example.test/profile'}}},transport,lambda:'test-token')
        with patch('buffer_adapter.verify_media'):
            adapter.publish({'platform':'youtube','account':'account'},{'caption':'test','media':{'url':'https://example.test/video.mp4'}})
        self.assertEqual(calls[-1]['input']['mode'],'shareNow')
        self.assertFalse(calls[-1]['input']['saveToDraft'])

    def tiktok_adapter(self, post=None, channel=None):
        class Ledger:
            def consume_call(self, now): pass
        calls = []
        identity = {'id': 'tiktok-connection', 'service': 'tiktok', 'serviceId': 'owned-id',
            'externalLink': 'https://www.tiktok.com/@studiozeroflow', 'isDisconnected': False, 'isLocked': False}
        identity.update(channel or {})
        def transport(query, variables, token):
            calls.append(variables)
            if 'mutation' in query:
                return {'createPost': {'__typename': 'PostActionSuccess', 'post': {
                    'id': 'post', 'schedulingType': 'automatic', 'channelId': 'tiktok-connection'}}}
            if 'PostInput' in query:
                return {'post': post}
            return {'channel': identity}
        adapter = BufferAdapter(Ledger(), {'channels': {'tiktok': {
            'providerAccountId': 'owned-id', 'profileUrl': 'https://www.tiktok.com/@studiozeroflow'}}},
            transport, lambda: 'test-token')
        return adapter, calls

    def test_tiktok_uses_existing_video_and_automatic_publication_contract(self):
        adapter, calls = self.tiktok_adapter()
        with patch('buffer_adapter.verify_media'):
            receipt = adapter.publish({'platform': 'tiktok', 'account': 'tiktok-connection'},
                {'caption': 'Quiz', 'media': {'url': 'https://example.test/quiz.mp4'}})
        self.assertEqual(receipt, {'remoteId': 'post'})
        self.assertEqual(calls[-1]['input']['assets'], [{'video': {'url': 'https://example.test/quiz.mp4'}}])
        self.assertEqual(calls[-1]['input']['schedulingType'], 'automatic')

    def test_tiktok_wrong_identity_is_rejected_before_create_post(self):
        adapter, calls = self.tiktok_adapter(channel={'serviceId': 'other',
            'externalLink': 'https://www.tiktok.com/@other'})
        with patch('buffer_adapter.verify_media'), self.assertRaises(PublishError) as error:
            adapter.publish({'platform': 'tiktok', 'account': 'tiktok-connection'},
                {'caption': 'Quiz', 'media': {'url': 'https://example.test/quiz.mp4'}})
        self.assertEqual(error.exception.category, 'authorization')
        self.assertEqual(len(calls), 1)

    def test_tiktok_confirmation_requires_owned_video_permalink(self):
        post = {'id': 'post', 'status': 'sent', 'sentAt': '2026-10-07T00:00:00Z',
            'schedulingType': 'automatic', 'channelId': 'tiktok-connection', 'text': 'Quiz',
            'externalLink': 'https://www.tiktok.com/@studiozeroflow/video/1234567890'}
        for link, expected in ((post['externalLink'], 'confirmed'),
                ('https://www.tiktok.com/@other/video/1234567890', 'uncertain'),
                ('https://www.tiktok.com/@studiozeroflow', 'uncertain'),
                ('https://www.tiktok.com.evil.test/@studiozeroflow/video/1234567890', 'uncertain')):
            with self.subTest(link=link):
                adapter, _ = self.tiktok_adapter(post={**post, 'externalLink': link})
                result = adapter.reconcile({'platform': 'tiktok', 'account': 'tiktok-connection',
                    'remote_id': 'post'}, {'caption': 'Quiz'})
                self.assertEqual(result['status'], expected)
        adapter, _ = self.tiktok_adapter(post={**post, 'schedulingType': 'notification'})
        self.assertEqual(adapter.reconcile({'platform': 'tiktok', 'account': 'tiktok-connection',
            'remote_id': 'post'}, {'caption': 'Quiz'})['status'], 'uncertain')
