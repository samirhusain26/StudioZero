import io
import copy
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
    def test_http_200_graphql_coercion_rejection_is_safe_and_redacted(self):
        body = {'errors':[{'extensions':{'code':'INTERNAL_SERVER_ERROR'},
            'message':'Variable $input got invalid value {description: "PRIVATE"}; Field is not defined by type'}]}
        with patch('buffer_adapter.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(body).encode())):
            with self.assertRaises(PublishError) as caught:
                request('mutation{}',{},'test-token')
        self.assertEqual(caught.exception.category, 'rejected')
        self.assertNotIn('PRIVATE', str(caught.exception))
    def test_http_200_authorization_and_rate_limit_errors_take_priority(self):
        coercion={'message':'Variable input got invalid value SECRET'}
        for priority_error, expected in (({'extensions':{'code':'FORBIDDEN'}}, 'authorization'),
                ({'extensions':{'code':'RATE_LIMIT_EXCEEDED'}}, 'rate_limit')):
            body={'errors':[coercion, priority_error]}
            with self.subTest(expected=expected), patch('buffer_adapter.urllib.request.urlopen',
                    return_value=io.BytesIO(json.dumps(body).encode())):
                with self.assertRaises(PublishError) as caught:
                    request('mutation{}',{},'test-token')
            self.assertEqual(caught.exception.category, expected)
    def test_validation_rejection_predicate_requires_proven_pre_execution(self):
        self.assertEqual(self.failure(400, {'errors':[{'extensions':{'code':'GRAPHQL_VALIDATION_FAILED'}}]}), 'rejected')
        self.assertEqual(self.failure(400, {'data':{}, 'errors':[{'message':'Variable input got invalid value'}]}), 'uncertain')
        self.assertEqual(self.failure(400, {'errors':[{'message':'Variable input got invalid value'}, {'message':'unknown'}]}), 'uncertain')
        self.assertEqual(self.failure(400, {'errors':[{'message':'Variable input got invalid value','path':['createPost']}]}), 'uncertain')
    def test_execution_and_server_errors_remain_uncertain(self):
        self.assertEqual(self.failure(400,{'errors':[{'message':'failure','path':['createPost']}]}),'uncertain')
        self.assertEqual(self.failure(500,{}),'uncertain')
        self.assertEqual(self.failure(500,{'errors':[{'message':'Variable input got invalid value'}]}),'uncertain')
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

    def youtube_adapter(self):
        class Ledger:
            def consume_call(self, now): pass
        calls=[]
        def transport(query, variables, token):
            calls.append(variables)
            if 'channel' in query and 'mutation' not in query:
                return {'channel':{'id':'account','service':'youtube','serviceId':'provider','externalLink':'https://example.test/profile','isDisconnected':False,'isLocked':False}}
            return {'createPost':{'__typename':'PostActionSuccess','post':{'id':'post','schedulingType':'automatic','channelId':'account'}}}
        adapter=BufferAdapter(Ledger(),{'channels':{'youtube':{'providerAccountId':'provider','profileUrl':'https://example.test/profile'}}},transport,lambda:'test-token')
        return adapter, calls

    def test_youtube_description_is_removed_without_mutating_approved_payload(self):
        adapter, calls = self.youtube_adapter()
        payload={'caption':'Approved text','media':{'url':'https://example.test/video.mp4'},
            'metadata':{'youtube':{'title':'Approved title','description':'Approved text','categoryId':'24','isAiGenerated':True}}}
        original=copy.deepcopy(payload)
        with patch('buffer_adapter.verify_media'):
            adapter.publish({'platform':'youtube','account':'account'},payload)
        sent=calls[-1]['input']
        self.assertEqual(sent['text'], 'Approved text')
        self.assertEqual(sent['metadata']['youtube'], {'title':'Approved title','categoryId':'24','isAiGenerated':True})
        self.assertEqual(payload, original)

    def test_youtube_mismatched_description_rejected_before_remote_calls(self):
        adapter, calls = self.youtube_adapter()
        payload={'caption':'Approved text','media':{'url':'https://example.test/video.mp4'},
            'metadata':{'youtube':{'description':'different'}}}
        with patch('buffer_adapter.verify_media') as verify, self.assertRaises(PublishError) as error:
            adapter.publish({'platform':'youtube','account':'account'},payload)
        self.assertEqual(error.exception.category, 'rejected')
        verify.assert_not_called()
        self.assertEqual(calls, [])

    def test_youtube_without_description_keeps_existing_metadata(self):
        adapter, calls = self.youtube_adapter()
        metadata={'youtube':{'title':'Title','categoryId':'24'}}
        with patch('buffer_adapter.verify_media'):
            adapter.publish({'platform':'youtube','account':'account'},
                {'caption':'Approved text','media':{'url':'https://example.test/video.mp4'},'metadata':metadata})
        self.assertEqual(calls[-1]['input']['metadata'], metadata)

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
