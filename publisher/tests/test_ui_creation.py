import tempfile
import unittest
from pathlib import Path

from publisher.app.ui_creation import CreationError, CreationStore


class CreationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CreationStore(Path(self.tmp.name), lambda _path: {'streams': [{'codec_type': 'video'}], 'format': {'duration': '2'}})
        self.production = self.store.create({'id': 'prod-1', 'project': 'scalargame', 'brief': 'A quiz'})

    def tearDown(self):
        self.tmp.cleanup()

    def video(self, name='cut.mp4', data=b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00'):
        return self.store.stage('prod-1', name, data, 'video/mp4')

    def manifest(self, result, revision='rev-1'):
        return {'productionId': 'prod-1', 'project': 'scalargame', 'revisionId': revision, 'batchId': 'batch-1', 'episodeId': 'episode-1', 'files': [
            {'fileId': result['fileId'], 'path': 'cut.mp4', 'size': result['size'], 'sha256': result['sha256'], 'mediaType': result['mediaType'], 'role': 'video'}]}

    def test_manifest_identity_and_hash_are_checked(self):
        file = self.video()
        bad = self.manifest(file)
        bad['productionId'] = 'elsewhere'
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': bad})
        bad = self.manifest(file)
        bad['files'][0]['sha256'] = '0' * 64
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': bad})
        self.assertIsNone(self.store.get('prod-1')['currentRevisionId'])

    def test_approval_is_revision_bound_and_new_revision_invalidates_it(self):
        first = self.video()
        record = self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': self.manifest(first)})
        record = self.store.decide('prod-1', {'expectedRevisionId': 'rev-1', 'decision': 'approve-cut'})
        self.assertEqual(record['revisions'][0]['cutApproval']['revisionId'], 'rev-1')
        with self.assertRaises(CreationError):
            self.store.decide('prod-1', {'expectedRevisionId': None, 'decision': 'approve-cut'})
        second = self.video('cut2.mp4', b'\x00\x00\x00\x18ftypisomnew!')
        record = self.store.revise('prod-1', {'expectedRevisionId': 'rev-1', 'manifest': self.manifest(second, 'rev-2')})
        self.assertIsNone(record['revisions'][1]['cutApproval'])
        self.assertEqual(record['revisions'][0]['cutApproval']['revisionId'], 'rev-1')

    def test_identical_revision_retry_is_idempotent_even_after_commit(self):
        file = self.video()
        manifest = self.manifest(file)
        first = self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})
        second = self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})
        self.assertEqual(len(second['revisions']), 1)
        self.assertEqual(first['currentRevisionId'], second['currentRevisionId'])

    def test_research_hold_and_originals_hold_are_server_gates(self):
        explainer = self.store.create({'id': 'explain-1', 'project': 'explainers', 'brief': 'Explain topic'})
        file = self.store.stage('explain-1', 'cut.mp4', b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00', 'video/mp4')
        manifest = self.manifest(file)
        manifest.update(productionId='explain-1', project='explainers')
        with self.assertRaises(CreationError):
            self.store.revise('explain-1', {'expectedRevisionId': None, 'manifest': manifest})
        self.store.research('explain-1', {'expectedVersion': 0, 'status': 'held', 'question': 'Q?', 'angle': 'A', 'sources': []})
        with self.assertRaises(CreationError):
            self.store.revise('explain-1', {'expectedRevisionId': None, 'manifest': manifest})
        self.store.research('explain-1', {'expectedVersion': 1, 'status': 'accepted', 'question': 'Q?', 'angle': 'A', 'sources': ['https://example.org/source']})
        self.assertEqual(self.store.revise('explain-1', {'expectedRevisionId': None, 'manifest': manifest, 'expectedResearchVersion': 2})['currentRevisionId'], 'rev-1')
        self.store.create({'id': 'orig-1', 'project': 'originals', 'brief': 'Recap'})
        with self.assertRaises(CreationError):
            self.store.research('orig-1', {'expectedVersion': 0, 'status': 'accepted', 'question': 'Q', 'angle': 'A', 'sources': ['https://example.org/source']})

    def test_stale_research_cannot_approve_or_replace_cut(self):
        self.store.create({'id': 'explain-1', 'project': 'explainers', 'brief': 'Topic'})
        research = {'status': 'accepted', 'question': 'Q?', 'angle': 'First angle', 'sources': ['https://example.org/source']}
        self.store.research('explain-1', dict(research, expectedVersion=0))
        file = self.store.stage('explain-1', 'cut.mp4', b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00', 'video/mp4')
        manifest = dict(self.manifest(file), productionId='explain-1', project='explainers')
        self.store.revise('explain-1', {'expectedRevisionId': None, 'manifest': manifest, 'expectedResearchVersion': 1})
        self.store.research('explain-1', dict(research, expectedVersion=1, angle='Reframed angle'))
        with self.assertRaises(CreationError) as stale:
            self.store.decide('explain-1', {'expectedRevisionId': 'rev-1', 'expectedResearchVersion': 1, 'decision': 'approve-cut'})
        self.assertEqual(stale.exception.status, 409)
        with self.assertRaises(CreationError):
            self.store.revise('explain-1', {'expectedRevisionId': 'rev-1', 'expectedResearchVersion': 1, 'manifest': dict(manifest, revisionId='rev-2')})
        record = self.store.decide('explain-1', {'expectedRevisionId': 'rev-1', 'expectedResearchVersion': 2, 'decision': 'approve-cut'})
        self.assertEqual(record['revisions'][0]['cutApproval']['researchVersion'], 2)

    def test_invalid_replacement_keeps_playable_current_revision(self):
        first = self.video()
        self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': self.manifest(first)})
        second = self.video('replacement.mp4', b'\x00\x00\x00\x18ftypisombroken')
        self.store.probe = lambda _path: (_ for _ in ()).throw(ValueError('broken'))
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': 'rev-1', 'manifest': self.manifest(second, 'rev-2')})
        record = self.store.get('prod-1')
        self.assertEqual(record['currentRevisionId'], 'rev-1')
        path = Path(self.tmp.name) / 'prod-1' / 'revisions' / 'rev-1' / 'cut.mp4'
        self.assertTrue(path.is_file())

    def test_unsafe_duplicate_paths_and_media_are_rejected(self):
        file = self.video()
        manifest = self.manifest(file)
        manifest['files'][0]['path'] = '../cut.mp4'
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})
        with self.assertRaises(CreationError):
            self.store.stage('prod-1', '../cut.mp4', b'x', 'video/mp4')

    def test_duplicate_path_and_wrong_video_role_are_rejected(self):
        file = self.video()
        manifest = self.manifest(file)
        manifest['files'].append(dict(manifest['files'][0], fileId=file['fileId'], role='caption'))
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})
        manifest = self.manifest(file)
        manifest['files'][0]['role'] = 'script'
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})

    def test_mapping_types_and_multicut_revision_scope(self):
        file = self.video()
        manifest = self.manifest(file)
        manifest['batchId'] = {'unsafe': 'object'}
        with self.assertRaises(CreationError):
            self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})
        manifest = self.manifest(file)
        manifest['files'].append(dict(manifest['files'][0], path='second.mp4'))
        record = self.store.revise('prod-1', {'expectedRevisionId': None, 'manifest': manifest})
        self.assertEqual(len(record['revisions'][0]['artifacts']), 2)

    def test_manual_delivery_needs_current_approved_marathon_cut(self):
        self.store.create({'id': 'week-1', 'project': 'marathon', 'brief': 'Real weekly story'})
        file = self.store.stage('week-1', 'cut.mp4', b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00', 'video/mp4')
        manifest = self.manifest(file)
        manifest.update(productionId='week-1', project='marathon')
        self.store.revise('week-1', {'expectedRevisionId': None, 'manifest': manifest})
        with self.assertRaises(CreationError):
            self.store.manual_delivery('week-1', {'expectedRevisionId': 'rev-1'})
        self.store.decide('week-1', {'expectedRevisionId': 'rev-1', 'decision': 'approve-cut'})
        self.store.manual_delivery('week-1', {'expectedRevisionId': 'rev-1'})
        record = self.store.manual_delivery('week-1', {'expectedRevisionId': 'rev-1'})
        self.assertEqual(len(record['manualDeliveries']), 1)


if __name__ == '__main__':
    unittest.main()
