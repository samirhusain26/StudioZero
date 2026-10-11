from email.message import Message
import hashlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from verify_delivery import verify
from buffer_adapter import PublishError


class DeliveryTests(unittest.TestCase):
    def response(self, data=b'video', url='https://media.example.test/video.mp4', mime='video/mp4'):
        response = io.BytesIO(data)
        response.url = url
        response.headers = Message()
        response.headers['Content-Type'] = mime
        return response

    def test_public_bytes_must_match_hash(self):
        digest = hashlib.sha256(b'video').hexdigest()
        url = 'https://media.example.test/video.mp4'
        self.assertTrue(verify(url, digest, lambda *a, **k: self.response())['publicDeliveryVerified'])
        with self.assertRaises(PublishError):
            verify(url, digest, lambda *a, **k: self.response(b'wrong'))

    def test_auth_html_and_cross_host_redirect_rejected(self):
        url = 'https://media.example.test/video.mp4'
        digest = hashlib.sha256(b'video').hexdigest()
        for response in (self.response(mime='text/html'), self.response(url='https://login.example.test/video.mp4')):
            with self.assertRaises(PublishError):
                verify(url, digest, lambda *a, **k: response)
