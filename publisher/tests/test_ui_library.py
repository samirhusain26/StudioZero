import copy
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import library_contract as lc
import ui_library as ul
from contract_fixtures import JPEG, FakeProbe, document, episode, mp4_bytes, probe_json, write_batch

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)


def setUpModule():
    # Temp dirs live in /tmp, a ~200 MB tmpfs on the Pi, below the 2 GB upload reserve (which has its own test).
    global _RESERVE
    _RESERVE, ul.FREE_SPACE_RESERVE = ul.FREE_SPACE_RESERVE, 0


def tearDownModule():
    ul.FREE_SPACE_RESERVE = _RESERVE


def grabber(video, out):
    Path(out).write_bytes(JPEG + hashlib.sha256(Path(video).read_bytes()).digest())


def media_url(kind, sha):
    return f'/api/media/{kind}/{sha}?t=x'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)/'state'
        self.state.mkdir()
        self.src = Path(self.tmp.name)/'mac'
        self.index = ul.open_index(self.state)
        self.probe = FakeProbe()

    def tearDown(self):
        self.index.close()
        self.tmp.cleanup()

    def batch(self, data=None):
        folder, data, blobs = write_batch(self.src, data)
        return data, blobs, (folder/'batch.json').read_bytes()

    def put(self, batch_id, name, blob, length=None, probe=None):
        return ul.accept_batch_file(self.index, self.state, batch_id, name, io.BytesIO(blob),
                                    len(blob) if length is None else length, probe or self.probe, grabber, NOW)

    def upload_all(self, data, blobs):
        for e in data['episodes']:
            for kind in ('video', 'cover'):
                name = e[kind]['file']
                self.assertTrue(self.put(data['batchId'], name, blobs[name])['ok'])

    def status(self, eid, rev=1):
        return self.index.execute('SELECT status FROM episodes WHERE episode_id=? AND revision=?', (eid, rev)).fetchone()['status']

    def parts(self):
        return list((self.state/'library/.incoming').glob('*.part'))


class IndexTests(Base):
    def test_permissions_and_wal(self):
        self.assertEqual(stat.S_IMODE((self.state/'library/index.sqlite3').stat().st_mode), 0o600)
        for d in ('library', 'library/objects', 'library/covers', 'library/.incoming'):
            self.assertEqual(stat.S_IMODE((self.state/d).stat().st_mode), 0o700)
        self.assertEqual(self.index.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        tables = {r[0] for r in self.index.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'batches', 'episodes', 'videos', 'covers', 'approvals', 'drafts', 'manifests'} <= tables)
        ul.open_index(self.state).close()  # reopening is safe


class StreamTests(Base):
    def test_receive_hashes_and_writes_part(self):
        blob = b'x' * 200_000
        sha, part = ul.receive(io.BytesIO(blob), len(blob), self.state, cap=1_000_000, reserve=0)
        self.assertEqual(sha, hashlib.sha256(blob).hexdigest())
        self.assertEqual(part.read_bytes(), blob)
        self.assertEqual(stat.S_IMODE(part.stat().st_mode), 0o600)
        self.assertEqual(part.parent, self.state/'library/.incoming')

    def test_reads_exactly_length(self):
        stream = io.BytesIO(b'abcdefgh')
        sha, _ = ul.receive(stream, 4, self.state, cap=10, reserve=0)
        self.assertEqual(sha, hashlib.sha256(b'abcd').hexdigest())
        self.assertEqual(stream.read(), b'efgh')

    def test_cap_and_expected_bytes_refused_before_reading(self):
        stream = io.BytesIO(b'x' * 100)
        with self.assertRaisesRegex(ul.UploadError, 'too large'):
            ul.receive(stream, 100, self.state, cap=99, reserve=0)
        with self.assertRaisesRegex(ul.UploadError, 'expects'):
            ul.receive(stream, 100, self.state, cap=1000, expected_bytes=50, reserve=0)
        with self.assertRaisesRegex(ul.UploadError, 'Content-Length'):
            ul.receive(stream, None, self.state, cap=1000)
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(self.parts(), [])

    def test_free_space_refusal(self):
        stream = io.BytesIO(b'x' * 10)
        with self.assertRaisesRegex(ul.UploadError, 'storage'):
            ul.receive(stream, 10, self.state, cap=100, reserve=10**18)
        self.assertEqual(stream.tell(), 0)
        original = ul.FREE_SPACE_RESERVE
        ul.FREE_SPACE_RESERVE = 10**18
        try:
            with self.assertRaises(ul.UploadError):
                ul.receive(io.BytesIO(b'x'), 1, self.state, cap=100)
        finally:
            ul.FREE_SPACE_RESERVE = original

    def test_short_read_and_hash_mismatch_remove_part(self):
        with self.assertRaisesRegex(ul.UploadError, 'stopped'):
            ul.receive(io.BytesIO(b'x' * 10), 20, self.state, cap=100, reserve=0)
        self.assertEqual(self.parts(), [])
        with self.assertRaisesRegex(ul.UploadError, "doesn't match"):
            ul.receive(io.BytesIO(b'x' * 10), 10, self.state, cap=100, expected_sha256='0' * 64, reserve=0)
        self.assertEqual(self.parts(), [])

    def test_connection_error_removes_part(self):
        class Broken:
            def __init__(self):
                self.n = 0

            def read(self, size):
                self.n += 1
                if self.n > 1:
                    raise ConnectionResetError('peer reset')
                return b'x' * size
        with self.assertRaisesRegex(ul.UploadError, 'interrupted'):
            ul.receive(Broken(), 200_000, self.state, cap=10**6, reserve=0)
        self.assertEqual(self.parts(), [])

    def test_cleanup_incoming(self):
        incoming = self.state/'library/.incoming'
        old, new = incoming/'old.part', incoming/'new.part'
        old.write_bytes(b'1')
        new.write_bytes(b'2')
        past = time.time() - 7*3600
        os.utime(old, (past, past))
        self.assertEqual(ul.cleanup_incoming(self.state), 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertEqual(ul.cleanup_incoming(self.state, all_files=True), 1)
        self.assertEqual(self.parts(), [])


class ImportTests(Base):
    def test_import_upload_and_reviewable(self):
        data, blobs, raw = self.batch(document([episode(1), episode(2)]))
        result = ul.import_batch_json(self.index, self.state, raw, NOW)
        self.assertEqual(result['problems'], [])
        self.assertEqual(result['status'], 'imported')
        self.assertEqual(len(result['expected']), 4)
        self.assertFalse(any(x['present'] for x in result['expected']))
        self.assertEqual(self.status('scalar-clues-001'), 'awaiting_files')
        r = self.put(data['batchId'], 'videos/scalar-clues-001.mp4', blobs['videos/scalar-clues-001.mp4'])
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['status'], 'awaiting_files')
        r = self.put(data['batchId'], 'covers/scalar-clues-001.jpg', blobs['covers/scalar-clues-001.jpg'])
        self.assertEqual(r['status'], 'reviewable')
        sha = data['episodes'][0]['video']['sha256']
        self.assertTrue((self.state/f'library/objects/{sha}.mp4').is_file())
        video = self.index.execute('SELECT * FROM videos WHERE sha256=?', (sha,)).fetchone()
        self.assertEqual(video['path'], f'library/objects/{sha}.mp4')
        self.assertTrue(json.loads(video['platforms'])['instagram']['eligible'])
        self.assertEqual(self.status('scalar-clues-002'), 'awaiting_files')
        self.assertEqual(self.parts(), [])

    def test_rejects_invalid_documents(self):
        result = ul.import_batch_json(self.index, self.state, b'{', NOW)
        self.assertIn('invalid JSON', result['problems'][0])
        result = ul.import_batch_json(self.index, self.state, b' ' * (lc.MAX_BATCH_JSON_BYTES + 1), NOW)
        self.assertIn('1 MB', result['problems'][0])
        data = document()
        data['episodes'][0]['publication']['captions']['threads'] = 'It is Bolivia {link}'
        _, _, raw = self.batch(data)
        result = ul.import_batch_json(self.index, self.state, raw, NOW)
        self.assertTrue(any(p.startswith('scalar-clues-001 · publication.captions.threads') for p in result['problems']))
        self.assertIsNone(self.index.execute('SELECT 1 FROM batches').fetchone())
        _, _, raw = self.batch(document(batch_id='manual-20261007-1'))
        self.assertTrue(ul.import_batch_json(self.index, self.state, raw, NOW)['problems'])

    def test_dirty_generator_warning_recorded(self):
        data = document()
        data['generator']['dirty'] = True
        _, _, raw = self.batch(data)
        result = ul.import_batch_json(self.index, self.state, raw, NOW)
        self.assertEqual(result['problems'], [])
        self.assertTrue(result['warnings'])
        view = ul.library_view(self.index, self.state, media_url)
        self.assertEqual(view[0]['warnings'], result['warnings'])

    def test_path_rejection(self):
        data, blobs, raw = self.batch()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        blob = blobs['videos/scalar-clues-001.mp4']
        for name in ('../x', '/abs', 'videos/../covers/scalar-clues-001.jpg', 'videos\\scalar-clues-001.mp4',
                     'videos/other.mp4', 'videos/scalar-clues-002.mp4', 'covers/x.png', 'covers/scalar-clues-001.png',
                     'videos/scalar-clues-001.jpg', 'review/scalar-clues-001.mp4', '/videos/scalar-clues-001.mp4'):
            result = self.put(data['batchId'], name, blob)
            self.assertFalse(result['ok'], name)
            self.assertTrue(result['problems'], name)
        self.assertFalse(self.put('2026-10-unknown', 'videos/scalar-clues-001.mp4', blob)['ok'])
        self.assertEqual(self.parts(), [])
        self.assertIsNone(self.index.execute('SELECT 1 FROM videos').fetchone())

    def test_hash_mismatch_and_short_upload_keep_episode_waiting(self):
        data, blobs, raw = self.batch()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        wrong = blobs['covers/scalar-clues-001.jpg'][:-1] + b'!'
        result = self.put(data['batchId'], 'covers/scalar-clues-001.jpg', wrong)
        self.assertFalse(result['ok'])
        self.assertIn("doesn't match", result['problems'][0])
        blob = blobs['videos/scalar-clues-001.mp4']
        result = ul.accept_batch_file(self.index, self.state, data['batchId'], 'videos/scalar-clues-001.mp4',
                                      io.BytesIO(blob[:50]), len(blob), self.probe, grabber, NOW)
        self.assertFalse(result['ok'])
        self.assertEqual(self.status('scalar-clues-001'), 'awaiting_files')
        self.assertEqual(self.parts(), [])
        self.assertIsNone(self.index.execute('SELECT 1 FROM videos').fetchone())

    def test_media_failures_mark_invalid_and_register_nothing(self):
        data, blobs, raw = self.batch()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        sha = data['episodes'][0]['video']['sha256']
        probe = FakeProbe({sha: probe_json(duration=29.0)})
        result = self.put(data['batchId'], 'videos/scalar-clues-001.mp4', blobs['videos/scalar-clues-001.mp4'], probe=probe)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'invalid')
        self.assertTrue(any('durationSeconds' in p for p in result['problems']))
        self.assertIsNone(self.index.execute('SELECT 1 FROM videos').fetchone())
        self.assertFalse((self.state/f'library/objects/{sha}.mp4').exists())

    def test_cover_must_be_jpeg(self):
        data = document()
        folder, data, blobs = write_batch(self.src, data)
        png = b'\x89PNG' + b'0' * 20
        data['episodes'][0]['cover'].update(sha256=hashlib.sha256(png).hexdigest(), bytes=len(png))
        raw = json.dumps(data).encode()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        result = self.put(data['batchId'], 'covers/scalar-clues-001.jpg', png)
        self.assertEqual(result['status'], 'invalid')
        self.assertIn('JPEG', result['problems'][0])

    def test_dedupe_reuses_objects(self):
        data, blobs, raw = self.batch()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        self.upload_all(data, blobs)
        calls = self.probe.calls
        # A second batch (new episode id) shipping the same files.
        other = copy.deepcopy(data)
        other['batchId'] = '2026-10-second'
        e = other['episodes'][0]
        e['episodeId'], e['video']['file'], e['cover']['file'] = 'scalar-clues-002', 'videos/scalar-clues-002.mp4', 'covers/scalar-clues-002.jpg'
        result = ul.import_batch_json(self.index, self.state, json.dumps(other).encode(), NOW)
        self.assertEqual(result['problems'], [])
        self.assertTrue(all(x['present'] for x in result['expected']))
        self.assertEqual(self.status('scalar-clues-002'), 'reviewable')
        obj = self.state/f"library/objects/{e['video']['sha256']}.mp4"
        before = obj.stat().st_mtime_ns
        r = self.put('2026-10-second', 'videos/scalar-clues-002.mp4', blobs['videos/scalar-clues-001.mp4'])
        self.assertTrue(r['ok'])
        self.assertTrue(r['alreadyPresent'])
        self.assertEqual(self.probe.calls, calls)
        self.assertEqual(obj.stat().st_mtime_ns, before)
        self.assertEqual(self.index.execute('SELECT count(*) FROM videos').fetchone()[0], 1)
        self.assertEqual(len(list((self.state/'library/objects').iterdir())), 1)
        self.assertEqual(self.parts(), [])
        view = ul.library_view(self.index, self.state, media_url)
        episodes = [x for b in view for x in b['episodes']]
        self.assertTrue(all(x['videoUrl'] for x in episodes))

    def test_merge_rules(self):
        data, blobs, raw = self.batch()
        self.assertEqual(ul.import_batch_json(self.index, self.state, raw, NOW)['status'], 'imported')
        self.upload_all(data, blobs)
        ul.approve(self.index, [{'episodeId': 'scalar-clues-001', 'revision': 1}], 'owner', NOW)
        # Same batch, same hashes: no-op.
        again = ul.import_batch_json(self.index, self.state, raw, NOW)
        self.assertEqual(again['status'], 'already imported')
        self.assertEqual(again['alreadyImported'], ['scalar-clues-001'])
        self.assertTrue(all(x['present'] for x in again['expected']))
        self.assertEqual(self.status('scalar-clues-001'), 'approved')
        # Same revision, different content: rejected.
        changed = copy.deepcopy(data)
        changed['episodes'][0]['publication']['captions']['x'] = 'Changed {link}'
        result = ul.import_batch_json(self.index, self.state, json.dumps(changed).encode(), NOW)
        self.assertIn('Bump the revision', result['problems'][0])
        # Higher revision with a new hash: new row; approved revision 1 untouched.
        bumped = copy.deepcopy(data)
        bumped['episodes'][0]['revision'] = 2
        bdata, bblobs, braw = self.batch(bumped)
        result = ul.import_batch_json(self.index, self.state, braw, NOW)
        self.assertEqual(result['problems'], [])
        self.assertEqual(self.status('scalar-clues-001', 2), 'awaiting_files')
        self.assertEqual(self.status('scalar-clues-001', 1), 'approved')
        self.assertEqual(self.index.execute('SELECT count(*) FROM approvals').fetchone()[0], 1)
        self.assertEqual(self.index.execute('SELECT count(*) FROM batch_documents').fetchone()[0], 2)
        # Uploads for this batch now match revision 2.
        self.upload_all(bdata, bblobs)
        self.assertEqual(self.status('scalar-clues-001', 2), 'reviewable')
        # Lower revision with a different hash: rejected.
        lower = copy.deepcopy(data)
        lower['episodes'][0]['publication']['captions']['x'] = 'Other {link}'
        result = ul.import_batch_json(self.index, self.state, json.dumps(lower).encode(), NOW)
        self.assertIn('Bump the revision to 3', result['problems'][0])
        # A batch with one bad episode imports nothing.
        mixed = document([episode(5), copy.deepcopy(changed['episodes'][0])], batch_id='2026-10-mixed')
        result = ul.import_batch_json(self.index, self.state, json.dumps(mixed).encode(), NOW)
        self.assertTrue(result['problems'])
        self.assertIsNone(self.index.execute("SELECT 1 FROM episodes WHERE episode_id='scalar-clues-005'").fetchone())


class LegacyTests(Base):
    def setUp(self):
        super().setUp()
        bank = []
        self.clips = {}
        for n, game, answer, choices, question in (
                (1, 'scalar', 'Bolivia', ['Bolivia', 'China', 'India', 'United States'], ['Which country?', 'Americas', 'Landlocked']),
                (7, 'tectonic', 'Mongolia · Eastern Asia', ['Southern Asia', 'Eastern Asia', 'South-Eastern Asia'],
                 ['Where would you place Mongolia?'])):
            ep_id = f'ep{n:02d}'
            blob = mp4_bytes(ep_id.encode())
            rel = f'clips/{ep_id}-self-abc.mp4'
            (self.state/'site/clips').mkdir(parents=True, exist_ok=True)
            (self.state/'site'/rel).write_bytes(blob)
            self.clips[ep_id] = (rel, blob)
            bank.append({'id': ep_id, 'game': game, 'question': question, 'answer': answer, 'choices': choices,
                         'deepLink': f'/{game}', 'reveal': answer, 'provenance': {'source': 'fixture', 'ids': ['X']},
                         'verification': {'status': 'verified', 'sourceHash': 'f' * 64, 'verifiedAt': '2026-10-06T01:00:00Z'}})
        catalog = {'version': 1, 'generatedAt': '2026-10-06T01:44:20.146Z', 'rightsReviewed': True, 'episodes': bank,
                   'clips': {f'{k}:self': {'path': rel, 'sha256': hashlib.sha256(blob).hexdigest(), 'frames': 900}
                             for k, (rel, blob) in self.clips.items()}}
        (self.state/'catalog.json').write_text(json.dumps(catalog))
        self.yuvj = FakeProbe({hashlib.sha256(blob).hexdigest(): probe_json(duration=30.0, pix='yuvj420p')
                               for _, blob in self.clips.values()})

    def register(self):
        return ul.register_legacy(self.index, self.state, self.yuvj, grabber, NOW)

    def test_registers_in_place(self):
        result = self.register()
        self.assertEqual(result['registered'], ['scalar-legacy-001', 'tectonic-legacy-007'])
        self.assertEqual(result['invalid'], [])
        rows = self.index.execute('SELECT * FROM episodes ORDER BY episode_id').fetchall()
        self.assertEqual([r['question_id'] for r in rows], ['ep01', 'ep07'])
        self.assertTrue(all(r['status'] == 'reviewable' and r['batch_id'] == ul.LEGACY_BATCH for r in rows))
        video = self.index.execute('SELECT * FROM videos WHERE sha256=?', (rows[0]['video_sha256'],)).fetchone()
        self.assertEqual(video['path'], 'site/clips/ep01-self-abc.mp4')
        self.assertEqual(video['legacy'], 1)
        self.assertEqual(list((self.state/'library/objects').iterdir()), [])
        self.assertEqual(len(list((self.state/'library/covers').iterdir())), 2)
        meta = json.loads(rows[1]['metadata'])
        self.assertEqual(meta['creative']['answer'], 'Eastern Asia')
        self.assertEqual(meta['creative']['choices'][1], {'key': 'B', 'label': 'Eastern Asia'})
        self.assertIn('Mongolia', meta['publication']['youtube']['title'])
        self.assertIn('utm_source=x', meta['publication']['captions']['x'])
        self.assertEqual(json.loads(rows[0]['metadata'])['publication']['poll']['options'][0], 'Bolivia')
        batch = self.index.execute('SELECT * FROM batches').fetchone()
        self.assertEqual(batch['origin'], 'legacy')

    def test_idempotent(self):
        self.register()
        calls = self.yuvj.calls
        covers = sorted((self.state/'library/covers').iterdir())
        before = [tuple(r) for r in self.index.execute('SELECT episode_id, metadata_sha256, cover_sha256 FROM episodes ORDER BY 1')]
        result = self.register()
        self.assertEqual(result['already'], ['scalar-legacy-001', 'tectonic-legacy-007'])
        self.assertEqual(result['registered'], [])
        self.assertEqual(self.yuvj.calls, calls)
        self.assertEqual(sorted((self.state/'library/covers').iterdir()), covers)
        self.assertEqual(before, [tuple(r) for r in self.index.execute('SELECT episode_id, metadata_sha256, cover_sha256 FROM episodes ORDER BY 1')])

    def test_hash_mismatch_is_invalid_and_untouched(self):
        rel, blob = self.clips['ep07']
        (self.state/'site'/rel).write_bytes(blob + b'tampered')
        result = self.register()
        self.assertEqual(result['registered'], ['scalar-legacy-001'])
        self.assertEqual(result['invalid'][0]['episodeId'], 'tectonic-legacy-007')
        self.assertIn("doesn't match the catalogue hash", result['invalid'][0]['problems'][0])
        self.assertEqual(self.status('tectonic-legacy-007'), 'invalid')
        self.assertEqual((self.state/'site'/rel).read_bytes(), blob + b'tampered')
        # Restoring the clip lets the next registration verify it.
        (self.state/'site'/rel).write_bytes(blob)
        self.assertEqual(self.register()['registered'], ['tectonic-legacy-007'])

    def test_yuvj_tolerated_only_for_legacy(self):
        self.register()
        self.assertEqual(self.status('scalar-legacy-001'), 'reviewable')
        data, blobs, raw = self.batch()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        sha = data['episodes'][0]['video']['sha256']
        probe = FakeProbe({sha: probe_json(pix='yuvj420p')})
        result = self.put(data['batchId'], 'videos/scalar-clues-001.mp4', blobs['videos/scalar-clues-001.mp4'], probe=probe)
        self.assertEqual(result['status'], 'invalid')
        self.assertIn('Pixel format must be yuv420p', result['problems'])

    def test_missing_catalogue(self):
        (self.state/'catalog.json').unlink()
        self.assertTrue(self.register()['problems'])

    def test_real_catalogue_builds_valid_episodes(self):
        path = ROOT/'studio/out/social-site/catalog.json'
        if not path.exists():
            self.skipTest('no local legacy catalogue')
        m = lc.measure(probe_json(duration=30.0, pix='yuvj420p'))
        for ep in json.loads(path.read_text())['episodes']:
            report = lc.Report()
            lc.validate_episode(ul.legacy_episode(ep, 'a' * 64, m, 1000, 'b' * 64, 100), 'e', {}, NOW.date(), report, origin='pi')
            self.assertEqual(report.errors, [], ep['id'])


class ApprovalTests(Base):
    def setUp(self):
        super().setUp()
        data = document([episode(1), episode(2, 'continuum')])
        data['episodes'][1]['eligibility']['expiresAt'] = '2026-10-20'
        self.data, blobs, raw = self.batch(data)
        ul.import_batch_json(self.index, self.state, raw, NOW)
        self.upload_all(self.data, blobs)

    def items(self, *ids):
        return [{'episodeId': i, 'revision': 1} for i in ids]

    def test_approve_records_hashes(self):
        result = ul.approve(self.index, self.items('scalar-clues-001'), 'owner', NOW)
        self.assertEqual(result['count'], 1)
        row = self.index.execute('SELECT * FROM approvals').fetchone()
        e = self.data['episodes'][0]
        self.assertEqual((row['action'], row['reviewer'], row['at']), ('approve', 'owner', '2026-10-07T12:00:00Z'))
        self.assertEqual(row['video_sha256'], e['video']['sha256'])
        self.assertEqual(row['cover_sha256'], e['cover']['sha256'])
        self.assertEqual(row['metadata_sha256'], lc.episode_metadata_hash(e))
        self.assertEqual(row['caption_sha256'], lc.caption_hash(e))
        self.assertEqual(self.status('scalar-clues-001'), 'approved')
        again = ul.approve(self.index, self.items('scalar-clues-001'), 'owner', NOW)
        self.assertEqual(again['results'][0]['problem'], 'Already approved.')

    def test_refuses_non_reviewable_and_changed_files(self):
        data, _, raw = self.batch(document([episode(3)], batch_id='2026-10-waiting'))
        ul.import_batch_json(self.index, self.state, raw, NOW)
        result = ul.approve(self.index, self.items('scalar-clues-003', 'scalar-clues-404'), 'owner', NOW)
        self.assertEqual(result['count'], 0)
        self.assertIn('not been uploaded', result['results'][0]['problem'])
        self.assertIn('No such', result['results'][1]['problem'])
        self.assertEqual(ul.approve(self.index, self.items('scalar-clues-001'), '', NOW)['count'], 0)
        obj = self.state/f"library/objects/{self.data['episodes'][0]['video']['sha256']}.mp4"
        obj.write_bytes(b'corrupted')
        result = ul.approve(self.index, self.items('scalar-clues-001'), 'owner', NOW)
        self.assertIn('changed on disk', result['results'][0]['problem'])
        self.assertEqual(self.status('scalar-clues-001'), 'reviewable')

    def test_withdraw_and_schedulable(self):
        ul.approve(self.index, self.items('scalar-clues-001', 'continuum-clues-002'), 'owner', NOW)
        videos = ul.schedulable_videos(self.index, '2026-10-12')
        self.assertEqual([v['episodeId'] for v in videos], ['continuum-clues-002', 'scalar-clues-001'])
        record = videos[1]
        self.assertEqual(record['episode']['eligibility']['status'], 'approved')
        self.assertEqual(record['durationSeconds'], 22.0)
        self.assertEqual(record['eligibility'], {'notBefore': None, 'reviewBy': '2027-04-01', 'expiresAt': None})
        self.assertTrue(record['platforms']['x']['eligible'])
        self.assertEqual(record['metadataSha256'], lc.episode_metadata_hash(self.data['episodes'][0]))
        # Expired after expiresAt.
        self.assertEqual([v['episodeId'] for v in ul.schedulable_videos(self.index, dt.date(2026, 10, 21))], ['scalar-clues-001'])
        # Withdrawn.
        result = ul.withdraw(self.index, self.items('continuum-clues-002'), 'owner', NOW)
        self.assertEqual(result['count'], 1)
        self.assertEqual(self.status('continuum-clues-002'), 'withdrawn')
        self.assertEqual([v['episodeId'] for v in ul.schedulable_videos(self.index, '2026-10-12')], ['scalar-clues-001'])
        # Metadata changed after approval.
        meta = copy.deepcopy(self.data['episodes'][0])
        meta['publication']['captions']['x'] = 'Sneaky edit {link}'
        with self.index:
            self.index.execute('UPDATE episodes SET metadata=? WHERE episode_id=?', (json.dumps(meta), 'scalar-clues-001'))
        self.assertEqual(ul.schedulable_videos(self.index, '2026-10-12'), [])
        # Re-approval of a withdrawn revision is a fresh decision.
        self.assertEqual(ul.approve(self.index, self.items('continuum-clues-002'), 'owner', NOW)['count'], 1)

    def test_older_and_newer_revisions_independent(self):
        ul.approve(self.index, self.items('scalar-clues-001'), 'owner', NOW)
        bumped = copy.deepcopy(self.data)
        bumped['episodes'] = [bumped['episodes'][0]]
        bumped['episodes'][0]['revision'] = 2
        bdata, bblobs, braw = self.batch(bumped)
        ul.import_batch_json(self.index, self.state, braw, NOW)
        self.upload_all(bdata, bblobs)
        ul.approve(self.index, [{'episodeId': 'scalar-clues-001', 'revision': 2}], 'owner', NOW)
        ul.withdraw(self.index, self.items('scalar-clues-001'), 'owner', NOW)
        self.assertEqual(self.status('scalar-clues-001', 1), 'withdrawn')
        self.assertEqual(self.status('scalar-clues-001', 2), 'approved')
        self.assertEqual([(v['episodeId'], v['revision']) for v in ul.schedulable_videos(self.index, '2026-10-12')
                          if v['game'] == 'scalar'], [('scalar-clues-001', 2)])

    def test_delete_refused_when_in_manifest(self):
        sha = self.data['episodes'][0]['video']['sha256']
        ul.record_manifest(self.index, 'm' * 64, 'd' * 64, [sha], '2026-10-07T12:00:00Z')
        self.assertTrue(ul.in_manifest(self.index, sha))
        result = ul.delete_episode(self.index, self.state, 'scalar-clues-001', 1)
        self.assertFalse(result['ok'])
        self.assertIn('approved schedule', result['problem'])
        # Manifest files on disk count too.
        other = self.data['episodes'][1]['video']['sha256']
        (self.state/'manifests').mkdir()
        (self.state/'manifests/abc.json').write_text(json.dumps({'jobs': [{'payload': {'media': {'sha256': other}}}]}))
        self.assertFalse(ul.delete_episode(self.index, self.state, 'continuum-clues-002', 1)['ok'])
        view = ul.library_view(self.index, self.state, media_url)
        self.assertTrue(all(e['inManifest'] for e in view[0]['episodes']))

    def test_delete_removes_unshared_objects(self):
        e = self.data['episodes'][0]
        result = ul.delete_episode(self.index, self.state, 'scalar-clues-001', 1)
        self.assertTrue(result['ok'])
        self.assertFalse((self.state/f"library/objects/{e['video']['sha256']}.mp4").exists())
        self.assertFalse((self.state/f"library/covers/{e['cover']['sha256']}.jpg").exists())
        self.assertIsNone(self.index.execute('SELECT 1 FROM videos WHERE sha256=?', (e['video']['sha256'],)).fetchone())
        self.assertTrue((self.state/f"library/objects/{self.data['episodes'][1]['video']['sha256']}.mp4").exists())
        self.assertFalse(ul.delete_episode(self.index, self.state, 'scalar-clues-001', 1)['ok'])

    def test_delete_never_removes_legacy_files(self):
        clip = self.state/'site/clips/ep01-self-x.mp4'
        clip.parent.mkdir(parents=True)
        blob = mp4_bytes(b'legacy')
        clip.write_bytes(blob)
        sha = hashlib.sha256(blob).hexdigest()
        catalog = {'generatedAt': '2026-10-06T00:00:00Z', 'episodes': [{
            'id': 'ep01', 'game': 'scalar', 'question': ['Which country?'], 'answer': 'Bolivia',
            'choices': ['Bolivia', 'Chile'], 'deepLink': '/scalar', 'verification': {'status': 'verified'}}],
            'clips': {'ep01:self': {'path': 'clips/ep01-self-x.mp4', 'sha256': sha}}}
        (self.state/'catalog.json').write_text(json.dumps(catalog))
        self.assertEqual(ul.register_legacy(self.index, self.state, self.probe, grabber, NOW)['registered'], ['scalar-legacy-001'])
        self.assertTrue(ul.delete_episode(self.index, self.state, 'scalar-legacy-001', 1)['ok'])
        self.assertEqual(clip.read_bytes(), blob)

    def test_library_view(self):
        ul.approve(self.index, self.items('scalar-clues-001'), 'owner', NOW)
        view = ul.library_view(self.index, self.state, media_url, today='2026-10-21')
        self.assertEqual(view[0]['batchId'], '2026-10-fixture')
        by_id = {e['episodeId']: e for e in view[0]['episodes']}
        s = by_id['scalar-clues-001']
        self.assertEqual(s['status'], 'approved')
        self.assertEqual(s['approval']['action'], 'approve')
        self.assertEqual(s['measured']['durationSeconds'], 22.0)
        self.assertTrue(s['measured']['fastStart'])
        self.assertEqual(s['videoUrl'], media_url('videos', s['videoSha256']))
        self.assertTrue(s['captions']['x'].endswith('{link}'))
        self.assertIn('utm_content=scalar-clues-001', s['links']['x'])
        self.assertFalse(s['inManifest'])
        self.assertTrue(by_id['continuum-clues-002']['expired'])
        text = json.dumps(view)
        self.assertNotIn(str(self.state), text)


@unittest.skipUnless(Path('/usr/bin/ffmpeg').exists(), 'Pi ffmpeg path only')
class RealFrameGrabTests(unittest.TestCase):
    def test_frame_grab_writes_jpeg_to_part_name(self):
        # The cover temp file ends in .part, so ffmpeg must not infer the format from the name.
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp)/'in.mp4'
            made = ul.subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=180x320:d=2',
                                      '-pix_fmt', 'yuv420p', '-c:v', 'libx264', str(clip)], capture_output=True)
            if made.returncode:
                self.skipTest('no libx264')
            out = Path(tmp)/'cover.jpg.part'
            ul.frame_grab(clip, out)
            self.assertTrue(lc.is_jpeg(out))


if __name__ == '__main__':
    unittest.main()


class CleanupTests(Base):
    """Removing posted videos keeps episodes, records and covers; approval-relevant rules come from the ledger."""

    def setUp(self):
        super().setUp()
        import ui_approval
        self.key = ui_approval.ledger_key
        self.data, self.blobs, raw = self.batch()
        ul.import_batch_json(self.index, self.state, raw, NOW)
        self.upload_all(self.data, self.blobs)
        ul.approve(self.index, [{'episodeId': 'scalar-clues-001', 'revision': 1}], 'owner', NOW)
        self.sha = self.index.execute("SELECT video_sha256 FROM episodes WHERE episode_id='scalar-clues-001'").fetchone()[0]
        self.object = self.state/'library/objects'/f'{self.sha}.mp4'
        self.site = self.state/'site/library'/f'{self.sha}.mp4'
        self.site.parent.mkdir(parents=True)
        os.link(self.object, self.site)
        self.accounts = {'instagram': 'ig', 'threads': 'th', 'bluesky': 'bs'}

    def row(self, platform, slot, status, sha=None):
        payload = {'episode': {'id': 'scalar:Q1'}, 'media': {'sha256': sha or self.sha}}
        return {'id': self.key(platform, self.accounts[platform], slot), 'platform': platform, 'status': status,
                'payload': json.dumps(payload)}

    def manifest(self, *jobs):
        return {'jobs': [{'platform': p, 'slot': s, 'payload': {'media': {'sha256': self.sha}}} for p, s in jobs]}

    def candidates(self, rows, manifest=None):
        return ul.cleanup_candidates(self.index, self.state, rows, manifest, self.accounts)

    def test_only_fully_finished_posted_videos_are_candidates(self):
        ig, th = ('instagram', '2026-10-08T22:00:00+00:00'), ('threads', '2026-10-08T13:00:00+00:00')
        self.assertEqual(self.candidates([]), [])
        self.assertEqual(self.candidates([self.row(*ig, 'confirmed'), self.row(*th, 'ready')]), [])
        self.assertEqual(self.candidates([self.row(*ig, 'confirmed'), self.row(*th, 'uncertain')]), [])
        self.assertEqual(self.candidates([self.row(*ig, 'expired')]), [])   # never posted anywhere
        rows = [self.row(*ig, 'confirmed'), self.row(*th, 'expired')]
        [found] = self.candidates(rows, self.manifest(ig, th))
        self.assertEqual((found['videoSha256'], found['postedOn'], found['bytes']), (self.sha, ['instagram'], self.object.stat().st_size))
        self.assertEqual(found['episodes'][0]['episodeId'], 'scalar-clues-001')
        # Still scheduled for Bluesky (no ledger row yet): kept.
        self.assertEqual(self.candidates(rows, self.manifest(ig, th, ('bluesky', '2026-10-09T14:30:00+00:00'))), [])

    def test_remove_keeps_cover_and_records_and_reupload_restores(self):
        rows = [self.row('instagram', '2026-10-08T22:00:00+00:00', 'confirmed')]
        today = dt.date(2026, 10, 8)
        self.assertEqual(len(ul.schedulable_videos(self.index, today)), 1)
        result = ul.archive_videos(self.index, self.state, [self.sha, 'f'*64], rows, None, self.accounts, NOW)
        self.assertEqual((result['removed'], result['refused']), ([self.sha], ['f'*64]))
        self.assertGreater(result['bytesFreed'], 0)
        self.assertFalse(self.object.exists() or self.site.exists())
        cover = self.index.execute("SELECT c.path FROM episodes e JOIN covers c ON c.sha256=e.cover_sha256 "
                                   "WHERE e.episode_id='scalar-clues-001'").fetchone()[0]
        self.assertTrue((self.state/cover).is_file())
        view = {e['episodeId']: e for b in ul.library_view(self.index, self.state, media_url) for e in b['episodes']}
        self.assertEqual((view['scalar-clues-001']['missing'], view['scalar-clues-001']['videoRemovedAt']), ([], '2026-10-07T12:00:00Z'))
        self.assertIsNone(view['scalar-clues-001']['videoUrl'])
        self.assertIsNotNone(view['scalar-clues-001']['coverUrl'])
        self.assertEqual(ul.schedulable_videos(self.index, today), [])
        self.assertEqual(self.candidates(rows), [])   # already removed
        name = self.data['episodes'][0]['video']['file']
        self.assertTrue(self.put(self.data['batchId'], name, self.blobs[name])['ok'])
        self.assertTrue(self.object.is_file())
        self.assertIsNone(ul.archived(self.index, self.sha))
        self.assertEqual(len(ul.schedulable_videos(self.index, today)), 1)

    def test_legacy_clips_are_never_removed(self):
        with self.index:
            self.index.execute('UPDATE videos SET legacy=1 WHERE sha256=?', (self.sha,))
        self.assertEqual(self.candidates([self.row('instagram', '2026-10-08T22:00:00+00:00', 'confirmed')]), [])
