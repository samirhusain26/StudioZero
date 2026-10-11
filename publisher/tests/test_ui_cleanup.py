import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import ui_library as ul
from contract_fixtures import document, episode, write_batch
from runner import Ledger
from test_ui_server import ServerTestCase
from test_ui_views import assert_shape


class CleanupEndpointTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        folder, data, blobs = write_batch(Path(self.tmp.name)/'mac', document([episode(1)], batch_id='2026-10-b05'))
        self.assertEqual(self.json('POST', '/api/library/batches', (folder/'batch.json').read_bytes())[0], 200)
        for name, blob in blobs.items():
            kind = 'video/mp4' if name.endswith('.mp4') else 'image/jpeg'
            self.assertEqual(self.json('PUT', f"/api/library/batches/{data['batchId']}/files/{name}", blob, content_type=kind)[0], 200)
        index = ul.open_index(self.state)
        try:
            self.sha = index.execute("SELECT video_sha256 FROM episodes WHERE episode_id='scalar-clues-001'").fetchone()[0]
        finally:
            index.close()

    def post(self, status):
        ledger = Ledger(self.state/'ledger.sqlite3')
        try:
            key = ledger.enqueue('instagram', 'ig-1', '2026-10-08T22:00:00+00:00',
                                 {'episode': {'id': 'scalar:Q1'}, 'kind': 'post', 'media': {'sha256': self.sha}})
            ledger.update(key, status)
        finally:
            ledger.db.close()

    def test_preview_remove_and_library_shows_removed(self):
        self.post('uncertain')
        status, body = self.json('GET', '/api/library/cleanup')
        self.assertEqual((status, body['candidates'], body['blockedReason']), (200, [], None))
        assert_shape(self, body, 'CleanupPreview')
        self.post('confirmed')
        body = self.json('GET', '/api/library/cleanup')[1]
        [candidate] = body['candidates']
        assert_shape(self, candidate, 'CleanupCandidate')
        self.assertEqual((candidate['videoSha256'], candidate['postedOn']), (self.sha, ['instagram']))
        self.assertEqual(body['totalBytes'], candidate['bytes'])
        status, result = self.json('POST', '/api/library/cleanup', {'videoSha256': [self.sha]})
        self.assertEqual(status, 200, result)
        assert_shape(self, result, 'CleanupResult')
        self.assertEqual(result['removed'], [self.sha])
        self.assertFalse((self.state/'library/objects'/f'{self.sha}.mp4').exists())
        library = self.json('GET', '/api/library')[1]
        [ep] = [e for e in library['episodes'] if e['episodeId'] == 'scalar-clues-001']
        self.assertIsNotNone(ep['videoRemovedAt'])
        self.assertIsNone(ep['videoUrl'])

    def test_post_validates_and_needs_the_usual_write_guards(self):
        for body in ({}, {'videoSha256': []}, {'videoSha256': ['nothex']}):
            self.assertEqual(self.json('POST', '/api/library/cleanup', body)[0], 422)
        payload = json.dumps({'videoSha256': [self.sha]}).encode()
        self.assertEqual(self.request('POST', '/api/library/cleanup', payload, auth=False)[0], 401)
        self.assertEqual(self.request('POST', '/api/library/cleanup', payload, mutate=False)[0], 403)
        (self.state/'approval').mkdir(exist_ok=True)
        (self.state/'approval'/'request.json').write_text('{}')
        self.assertEqual(self.json('POST', '/api/library/cleanup', {'videoSha256': [self.sha]})[0], 409)


if __name__ == '__main__':
    unittest.main()
