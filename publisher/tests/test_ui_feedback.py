"""Episode feedback, batch notes, episode detail, next-batch info and dashboard standing
(REBUILD_CONTRACTS.md §2): ui_library storage, ui_views shapes and the ui_server endpoints."""
import copy
import datetime as dt
import hashlib
import inspect
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import ui_library as ul
import ui_views as v
from contract_fixtures import JPEG, FakeProbe, document, episode, write_batch
from runner import Ledger
from test_ui_server import ServerTestCase
from test_ui_views import assert_shape, fields

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)


def setUpModule():
    # Temp dirs live in /tmp, a ~200 MB tmpfs on the Pi, below the 2 GB upload reserve (which has its own test).
    global _RESERVE
    _RESERVE, ul.FREE_SPACE_RESERVE = ul.FREE_SPACE_RESERVE, 0


def tearDownModule():
    ul.FREE_SPACE_RESERVE = _RESERVE
INSTAGRAM = 'a00000000000000000000002'  # publisher/config.example.json
# The index schema before feedback/batch notes existed (abridged to the tables these tests touch).
OLD_SCHEMA = """
CREATE TABLE batches(batch_id TEXT PRIMARY KEY, origin TEXT NOT NULL,
  batch_json TEXT NOT NULL, batch_json_sha256 TEXT NOT NULL, created_at TEXT, imported_at TEXT NOT NULL,
  warnings TEXT NOT NULL DEFAULT '[]');
CREATE TABLE batch_documents(sha256 TEXT PRIMARY KEY, batch_id TEXT NOT NULL, origin TEXT NOT NULL,
  raw TEXT NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE episodes(episode_id TEXT NOT NULL, revision INTEGER NOT NULL, batch_id TEXT NOT NULL,
  question_id TEXT NOT NULL, game TEXT NOT NULL, format TEXT, difficulty TEXT,
  metadata TEXT NOT NULL, metadata_sha256 TEXT NOT NULL, video_sha256 TEXT NOT NULL, cover_sha256 TEXT,
  status TEXT NOT NULL, problems TEXT NOT NULL DEFAULT '[]', imported_at TEXT NOT NULL,
  PRIMARY KEY(episode_id, revision));
"""


def grabber(video, out):
    Path(out).write_bytes(JPEG + hashlib.sha256(Path(video).read_bytes()).digest())


class LibraryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)/'state'
        self.state.mkdir()
        self.index = ul.open_index(self.state)
        self.probe = FakeProbe()

    def tearDown(self):
        self.index.close()
        self.tmp.cleanup()

    def load(self, data, now=NOW, upload=True):
        folder, data, blobs = write_batch(Path(self.tmp.name)/'mac'/now.strftime('%H%M%S%f'), data)
        result = ul.import_batch_json(self.index, self.state, (folder/'batch.json').read_bytes(), now)
        self.assertEqual(result['problems'], [])
        for name, blob in blobs.items() if upload else ():
            self.assertTrue(ul.accept_batch_file(self.index, self.state, data['batchId'], name, io.BytesIO(blob), len(blob),
                                                 self.probe, grabber, now)['ok'])
        return data


class MigrationTests(unittest.TestCase):
    def test_old_index_gains_feedback_and_note_tables_and_keeps_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp)/'library'
            library.mkdir()
            old = sqlite3.connect(library/'index.sqlite3')
            old.executescript(OLD_SCHEMA)
            old.execute("INSERT INTO batches VALUES('2026-10-b01','mac','{}','x',NULL,'2026-10-06T00:00:00Z','[]')")
            old.commit()
            old.close()
            db = ul.open_index(tmp)
            try:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue({'feedback', 'batch_notes', 'approvals', 'drafts', 'deletions'} <= tables)
                self.assertEqual(db.execute('SELECT batch_id FROM batches').fetchall()[0][0], '2026-10-b01')
                columns = [r[1] for r in db.execute('PRAGMA table_info(feedback)')]
                self.assertEqual(columns, ['episode_id', 'revision', 'tags', 'note', 'status', 'updated_at'])
                columns = [r[1] for r in db.execute('PRAGMA table_info(batch_notes)')]
                self.assertEqual(columns, ['batch_id', 'kind', 'text', 'sha256', 'bytes', 'uploaded_at'])
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO feedback VALUES('e',1,'[]','','closed','x')")
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO batch_notes VALUES('b','summary','', 'x', 0, 'x')")
            finally:
                db.close()
            ul.open_index(tmp).close()  # reopening is a no-op


class NextBatchIdTests(LibraryBase):
    def record(self, batch_id, table='batches'):
        if table == 'batches':
            self.index.execute("INSERT INTO batches VALUES(?, 'mac', '{}', 'x', NULL, '2026-10-01T00:00:00Z', '[]')", (batch_id,))
        else:
            self.index.execute("INSERT INTO batch_documents VALUES(?, ?, 'mac', '{}', '2026-10-01T00:00:00Z')",
                               (hashlib.sha256(batch_id.encode()).hexdigest(), batch_id))

    def test_rule(self):
        self.assertEqual(ul.next_batch_id(self.index, NOW), '2026-10-b01')
        for batch_id in ('2026-10-pilots', 'legacy-2026-10-05', 'manual-20261007-3', '2026-10-b01', '2026-10-b01x'):
            self.record(batch_id)
        self.assertEqual(ul.next_batch_id(self.index, NOW), '2026-10-b02')
        # The highest bNN of any month counts, including batches deleted since (kept in batch_documents).
        self.record('2026-08-b07', 'documents')
        self.assertEqual(ul.next_batch_id(self.index, NOW), '2026-10-b08')
        self.assertEqual(ul.next_batch_id(self.index, dt.datetime(2026, 11, 30, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-5)))),
                         '2026-12-b08')  # UTC month
        self.record('2027-01-b99')
        self.assertEqual(ul.next_batch_id(self.index, NOW), '2026-10-b100')


class StoredEpisodeTests(LibraryBase):
    def test_detail_reads_the_imported_document_per_revision(self):
        first = self.load(document([episode(1)], batch_id='2026-10-b01'))
        second = copy.deepcopy(first)
        second['episodes'][0]['revision'] = 2
        second['episodes'][0]['creative']['hook'] = 'A different hook.'
        self.load(second, now=NOW + dt.timedelta(hours=1))
        latest = json.loads(self.index.execute("SELECT batch_json FROM batches WHERE batch_id='2026-10-b01'").fetchone()[0])
        self.assertEqual(latest['episodes'][0]['revision'], 2)
        one = ul.stored_episode(self.index, '2026-10-b01', 'scalar-clues-001', 1)
        two = ul.stored_episode(self.index, '2026-10-b01', 'scalar-clues-001', 2)
        self.assertEqual(one, first['episodes'][0])
        self.assertEqual(two['creative']['hook'], 'A different hook.')
        self.assertEqual(list(one), list(first['episodes'][0]))  # as imported, not re-sorted metadata
        self.assertIsNone(ul.stored_episode(self.index, '2026-10-b01', 'scalar-clues-001', 3))


class FeedbackStoreTests(LibraryBase):
    def test_upsert_mark_used_reopen_and_deleted_revisions(self):
        self.load(document([episode(1), episode(2, game='continuum')], batch_id='2026-10-b01'))
        saved = ul.set_feedback(self.index, 'scalar-clues-001', 1, ['drop', 'hook-weak'], 'Answer is Bolivia', NOW)
        self.assertEqual((saved['status'], saved['updatedAt'], saved['tags']), ('open', '2026-10-07T12:00:00Z', ['drop', 'hook-weak']))
        ul.set_feedback(self.index, 'continuum-clues-002', 1, ['keep'], '', NOW)
        self.assertEqual(ul.mark_feedback_used(self.index, [('scalar-clues-001', 1), ('scalar-clues-001', 1), ('nope-001', 1)]), 1)
        self.assertEqual(ul.mark_feedback_used(self.index, [('scalar-clues-001', 1)]), 0)
        self.assertEqual([f['episodeId'] for f in ul.open_feedback(self.index)], ['continuum-clues-002'])
        again = ul.set_feedback(self.index, 'scalar-clues-001', 1, ['tweak'], 'note', NOW + dt.timedelta(minutes=5))
        self.assertEqual((again['status'], again['tags']), ('open', ['tweak']))
        # Deleting the revision keeps its feedback usable for the next batch (metadata from the stored batch.json).
        self.assertTrue(ul.delete_episode(self.index, self.state, 'scalar-clues-001', 1, NOW)['ok'])
        items = {f['episodeId']: f for f in ul.open_feedback(self.index)}
        self.assertEqual({k: items['scalar-clues-001'][k] for k in ('batchId', 'questionId', 'game', 'format', 'styleId')},
                         {'batchId': '2026-10-b01', 'questionId': 'scalar:Q1:clues', 'game': 'scalar',
                          'format': 'progressive-clues', 'styleId': 'scalar-paper-1'})
        self.assertEqual(ul.clear_feedback(self.index, 'scalar-clues-001', 1), 1)
        self.assertEqual(ul.clear_feedback(self.index, 'scalar-clues-001', 1), 0)

    def test_standing_excludes_pi_batches_and_counts_reviewable(self):
        self.assertEqual(ul.standing(self.index, NOW.date()), {'lastBatch': None, 'awaitingReview': 0, 'openFeedback': 0})
        expired = episode(3)
        expired['eligibility']['expiresAt'] = '2026-10-08'
        self.load(document([episode(1), episode(2), expired], batch_id='2026-10-b01'))
        self.load(document([episode(4)], batch_id='2026-10-b02'), now=NOW + dt.timedelta(hours=1), upload=False)
        for batch_id in ('manual-20261008-1', 'legacy-2026-10-05'):
            self.index.execute("INSERT INTO batches VALUES(?, 'manual', '{}', 'x', NULL, '2026-10-09T00:00:00Z', '[]')", (batch_id,))
        ul.approve(self.index, [{'episodeId': 'scalar-clues-002', 'revision': 1}], 'owner', NOW, state=self.state)
        ul.set_feedback(self.index, 'scalar-clues-001', 1, ['keep'], '', NOW)
        self.assertEqual(ul.standing(self.index, dt.date(2026, 10, 9)), {
            'lastBatch': {'batchId': '2026-10-b02', 'importedAt': '2026-10-07T13:00:00Z', 'episodeCount': 1, 'awaitingFiles': 1},
            'awaitingReview': 1, 'openFeedback': 1})  # 002 approved, 003 expired, 004 still awaiting files

    def test_notes_and_last_note(self):
        self.load(document([episode(1)], batch_id='2026-10-b01'))
        self.load(document([episode(2)], batch_id='2026-10-b02'), now=NOW + dt.timedelta(hours=1))
        text = 'Brief — answers: Bolivia ✓'
        note = ul.set_batch_note(self.index, '2026-10-b01', 'brief', text, NOW)
        self.assertEqual((note['bytes'], note['sha256']), (len(text.encode()), hashlib.sha256(text.encode()).hexdigest()))
        ul.set_batch_note(self.index, '2026-10-b01', 'retro', 'Old retro', NOW)
        ul.set_batch_note(self.index, '2026-10-b02', 'retro', '', NOW)  # empty: does not count as having one
        self.assertEqual(ul.last_note(self.index, 'retro')['text'], 'Old retro')
        ul.set_batch_note(self.index, '2026-10-b02', 'retro', 'New retro', NOW + dt.timedelta(hours=2))
        self.assertEqual(ul.last_note(self.index, 'retro')['batchId'], '2026-10-b02')
        self.assertEqual(ul.last_note(self.index, 'brief')['batchId'], '2026-10-b01')
        self.assertEqual(ul.batch_notes(self.index, '2026-10-b02')['brief'], None)
        self.assertTrue(ul.batch_known(self.index, '2026-10-b01'))
        self.assertFalse(ul.batch_known(self.index, '2026-10-b09'))


class ViewTests(unittest.TestCase):
    def test_feedback_input_validation(self):
        self.assertEqual(v.feedback_input({'tags': ['music', 'keep'], 'note': 'x'}), (['keep', 'music'], 'x'))
        self.assertEqual(v.feedback_input({'tags': []}), ([], ''))
        for body, path in (([], 'body'), ({'tags': 'keep'}, 'tags'), ({'tags': ['nice']}, 'tags'),
                           ({'tags': ['keep', 'keep']}, 'tags'), ({'tags': [], 'note': 5}, 'note'),
                           ({'tags': [], 'note': 'x' * 2001}, 'note')):
            with self.assertRaises(ValueError) as caught:
                v.feedback_input(body)
            self.assertEqual(caught.exception.args[0], path, body)
        self.assertEqual(v.feedback_input({'tags': [], 'note': 'é' * 2000})[1], 'é' * 2000)

    def test_note_and_mark_used_validation(self):
        self.assertEqual(v.note_input({'text': 'é' * 32768}), 'é' * 32768)  # 65,536 bytes
        for body in ({'text': 'é' * 32768 + 'x'}, {'text': None}, {}, [], {'text': '\ud800'}):
            with self.assertRaises(ValueError):
                v.note_input(body)
        self.assertEqual(v.mark_used_input({'items': [{'episodeId': 'a', 'revision': 2}]}), [('a', 2)])
        for body in ({'items': []}, {'items': [{'episodeId': 'a', 'revision': '2'}]}, {'items': [{'episodeId': 'a', 'revision': True}]},
                     {'items': [{'revision': 1}]}, {'items': [{'episodeId': 'a', 'revision': 1}] * 1001}, None):
            with self.assertRaises(ValueError):
                v.mark_used_input(body)

    def test_tags_match_types_ts(self):
        text = (ROOT/'publisher/ui/src/api/types.ts').read_text()
        listed = next(line for line in text.splitlines() if line.startswith('export const FEEDBACK_TAGS'))
        self.assertEqual(tuple(eval(listed.split('=', 1)[1].replace('as const', ''))), v.FEEDBACK_TAGS)

    def test_next_posts_and_ledger_posts(self):
        def job(platform, slot, kind='post', episode_id='scalar-clues-001'):
            return {'platform': platform, 'slot': slot,
                    'payload': {'kind': kind, 'episode': {'id': 'scalar:Q1:clues', 'episodeId': episode_id, 'revision': 1}}}
        jobs = [job('x', '2026-10-09T16:00:00+00:00'), job('instagram', '2026-10-08T16:00:00+00:00'),
                job('instagram', '2026-10-08T16:05:00+00:00', 'comment'), job('threads', '2026-10-07T11:00:00+00:00'),
                job('bluesky', '2026-10-08T15:00:00+00:00'), job('youtube', '2026-10-08T16:00:00+00:00'),
                job('facebook', '2026-10-10T16:00:00+00:00')]
        keys = [f'k{i}' for i in range(len(jobs))]
        rows = {'k4': {'status': 'dispatching', 'dispatched_at': '2026-10-07T11:59:00+00:00'}, 'k1': {'status': 'ready', 'dispatched_at': None}}
        self.assertEqual(v.next_posts(jobs, rows, keys, NOW), [
            {'at': '2026-10-08T16:00:00Z', 'platform': 'instagram', 'episodeId': 'scalar-clues-001'},
            {'at': '2026-10-08T16:00:00Z', 'platform': 'youtube', 'episodeId': 'scalar-clues-001'},
            {'at': '2026-10-09T16:00:00Z', 'platform': 'x', 'episodeId': 'scalar-clues-001'}])

        def row(platform, episode, payload_episode, **values):
            return {'platform': platform, 'episode': episode, 'payload': json.dumps({'episode': payload_episode}),
                    'status': values.get('status', 'confirmed'), 'slot': '2026-10-05T16:00:00+00:00',
                    'published_at': values.get('published_at'), 'dispatched_at': values.get('dispatched_at'),
                    'permalink': values.get('permalink')}
        ledger = [row('instagram', 'scalar:Q1:clues', {'id': 'scalar:Q1:clues', 'episodeId': 'scalar-clues-001', 'revision': 1},
                      published_at='2026-10-05T16:01:00+00:00', permalink='https://www.instagram.com/reel/A/'),
                  row('instagram', 'scalar:Q1:clues#comment', {'id': 'scalar:Q1:clues#comment', 'episodeId': 'scalar-clues-001', 'revision': 1}),
                  row('x', 'scalar:Q1:clues', {'id': 'scalar:Q1:clues', 'episodeId': 'scalar-clues-001', 'revision': 2}),
                  row('bluesky', 'scalar:Q1:clues', {'id': 'scalar:Q1:clues'}, status='ready')]
        self.assertEqual(v.ledger_posts(ledger, 'scalar-clues-001', 1), [
            {'platform': 'instagram', 'status': 'confirmed', 'at': '2026-10-05T16:01:00Z', 'permalink': 'https://www.instagram.com/reel/A/', 'metrics': None},
            {'platform': 'bluesky', 'status': 'ready', 'at': '2026-10-05T16:00:00Z', 'permalink': None, 'metrics': None}])
        self.assertEqual(len(v.ledger_posts(ledger)), 3)
        ledger[0]['id'] = 'job-ig'
        read = {'checkpoint': '24h', 'fetchedAt': '2026-10-06T16:20:00+00:00', 'status': 'ok', 'values': {'views': 120}}
        self.assertEqual(v.ledger_posts(ledger, metrics={'job-ig': read})[0]['metrics'], read)


class NotPublishedTests(unittest.TestCase):
    def test_nothing_that_schedules_approves_or_publishes_reads_notes_or_feedback(self):
        # updater.py only names the test module test_ui_feedback in QUICK_TESTS (staged checks before a self-update).
        allowed = {'ui_library.py', 'ui_server.py', 'ui_views.py', 'updater.py'}
        for path in sorted((ROOT/'publisher/app').glob('*.py')):
            if path.name in allowed:
                continue
            text = path.read_text().lower()
            for word in ('batch_notes', 'feedback', 'last_note'):
                self.assertNotIn(word, text, f'{path.name} mentions {word}')
        for function in (ul.schedulable_videos, ul.approve, ul.withdraw, ul.library_view, ul.import_batch_json):
            source = inspect.getsource(function)
            self.assertNotIn('batch_notes', source)
            self.assertNotIn('feedback', source)


class EndpointTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.data = self.upload(document([episode(1), episode(2, game='continuum')], batch_id='2026-10-b03'))

    def upload(self, data):
        folder, data, blobs = write_batch(Path(self.tmp.name)/'mac', data)
        status, body = self.json('POST', '/api/library/batches', (folder/'batch.json').read_bytes())
        self.assertEqual(status, 200, body)
        for name, blob in blobs.items():
            kind = 'video/mp4' if name.endswith('.mp4') else 'image/jpeg'
            self.assertEqual(self.json('PUT', f"/api/library/batches/{data['batchId']}/files/{name}", blob, content_type=kind)[0], 200)
        return data

    def ledger_job(self, platform, account, slot, episode, payload_episode, status='confirmed', **values):
        ledger = Ledger(self.state/'ledger.sqlite3')
        try:
            key = ledger.enqueue(platform, account, slot, {'episode': {'id': episode, **payload_episode}, 'kind': 'post'})
            with ledger.db:
                ledger.db.execute('UPDATE jobs SET status=?, permalink=?, published_at=?, dispatched_at=? WHERE id=?',
                                  (status, values.get('permalink'), values.get('published_at'), values.get('dispatched_at'), key))
        finally:
            ledger.db.close()
        return key

    def write_auth_checks(self, method, path, body):
        self.assertEqual(self.request(method, path, body, auth=False)[0], 401)
        self.assertEqual(self.request(method, path, body, mutate=False)[0], 403)
        self.assertEqual(self.request(method, path, body, headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request(method, path, body, headers={'X-Scalar-Request': '1'}, mutate=False)[0], 403)

    def test_episode_detail(self):
        status, body = self.json('GET', '/api/library/episodes/scalar-clues-001/1')
        self.assertEqual(status, 200, body)
        assert_shape(self, body, 'EpisodeDetail')
        self.assertEqual(body['batchId'], '2026-10-b03')
        self.assertEqual(body['episode'], self.data['episodes'][0])
        self.assertEqual(body['approval'], {'status': 'reviewable', 'at': None})
        self.assertEqual(body['notes'], {'batchId': '2026-10-b03', 'brief': None, 'retro': None})
        self.assertEqual((body['feedback'], body['posts']), (None, []))
        self.json('POST', '/api/library/approve', {'items': [{'episodeId': 'scalar-clues-001', 'revision': 1}], 'reviewer': 'owner'})
        self.assertEqual(self.json('GET', '/api/library/episodes/scalar-clues-001/1')[1]['approval'],
                         {'status': 'approved', 'at': '2026-10-07T12:00:00Z'})
        for path in ('/api/library/episodes/scalar-clues-001/2', '/api/library/episodes/scalar-clues-009/1',
                     '/api/library/episodes/scalar-clues-001/0'):
            status, body = self.json('GET', path)
            self.assertEqual(status, 404)
            self.assertEqual(set(body), {'error', 'nextAction'})
        self.assertEqual(self.request('GET', '/api/library/episodes/scalar-clues-001/x')[0], 404)
        self.assertEqual(self.request('GET', '/api/library/episodes/scalar-clues-001/1', auth=False)[0], 401)

    def test_episode_posts_come_only_from_the_ledger(self):
        self.ledger_job('instagram', INSTAGRAM, '2026-10-05T16:00:00+00:00', 'scalar:Q1:clues',
                        {'episodeId': 'scalar-clues-001', 'revision': 1}, published_at='2026-10-05T16:01:00+00:00',
                        dispatched_at='2026-10-05T16:00:01+00:00', permalink='https://www.instagram.com/reel/A/')
        self.ledger_job('instagram', INSTAGRAM, '2026-10-05T16:05:00+00:00', 'scalar:Q1:clues#comment',
                        {'episodeId': 'scalar-clues-001', 'revision': 1}, permalink='https://www.instagram.com/reel/A/c/')
        self.ledger_job('x', 'x-1', '2026-10-06T16:00:00+00:00', 'scalar:Q1:clues', {'episodeId': 'scalar-clues-001', 'revision': 2})
        self.ledger_job('threads', 't-1', '2026-10-06T17:00:00+00:00', 'scalar:Q1:clues', {}, status='uncertain',
                        dispatched_at='2026-10-06T17:00:02+00:00')
        self.ledger_job('bluesky', 'b-1', '2026-10-06T18:00:00+00:00', 'continuum:Q2:clues',
                        {'episodeId': 'continuum-clues-002', 'revision': 1}, permalink='https://bsky.app/x')
        body = self.json('GET', '/api/library/episodes/scalar-clues-001/1')[1]
        for post in body['posts']:
            assert_shape(self, post, 'EpisodePost')
        self.assertEqual(body['posts'], [
            {'platform': 'instagram', 'status': 'confirmed', 'at': '2026-10-05T16:01:00Z', 'permalink': 'https://www.instagram.com/reel/A/', 'metrics': None},
            {'platform': 'threads', 'status': 'uncertain', 'at': '2026-10-06T17:00:02Z', 'permalink': None, 'metrics': None}])

    def test_feedback_put_delete_and_validation(self):
        path = '/api/library/episodes/scalar-clues-001/1/feedback'
        status, body = self.json('PUT', path, {'tags': ['too-easy', 'keep'], 'note': 'Answer: Bolivia'})
        self.assertEqual(status, 200, body)
        assert_shape(self, body, 'EpisodeFeedback')
        self.assertEqual(body, {'episodeId': 'scalar-clues-001', 'revision': 1, 'tags': ['keep', 'too-easy'],
                                'note': 'Answer: Bolivia', 'status': 'open', 'updatedAt': '2026-10-07T12:00:00Z'})
        self.assertEqual(self.json('GET', '/api/library/episodes/scalar-clues-001/1')[1]['feedback'], body)
        for bad, field in (({'tags': ['nice']}, 'tags'), ({'tags': ['keep', 'keep']}, 'tags'), ({'tags': 'keep'}, 'tags'),
                           ({'tags': [], 'note': 'x' * 2001}, 'note'), ({'tags': [], 'note': 3}, 'note'), ([], 'body')):
            status, body = self.json('PUT', path, bad)
            self.assertEqual(status, 422, bad)
            self.assertEqual(body['problems'][0]['path'], field)
        self.assertEqual(self.request('PUT', path, b'{', content_type='application/json')[0], 400)
        self.assertEqual(self.request('PUT', path, b'{}', content_type='text/plain')[0], 415)
        # A lone surrogate (valid JSON escape, not storable text) is refused, not a 500.
        status, body = self.json('PUT', path, b'{"tags": [], "note": "x\\ud800y"}')
        self.assertEqual(status, 422, body)
        self.assertIn('surrogate', body['error'])
        status, _, _ = self.request('PUT', path, b'{}', headers={'Content-Length': '12abc'})
        self.assertEqual(status, 400)
        self.assertEqual(self.json('PUT', '/api/library/episodes/scalar-clues-009/1/feedback', {'tags': []})[0], 404)
        self.assertEqual(self.json('PUT', '/api/library/episodes/scalar-clues-001/2/feedback', {'tags': []})[0], 404)
        self.write_auth_checks('PUT', path, {'tags': []})
        self.write_auth_checks('DELETE', path, None)
        status, headers, data = self.request('DELETE', path)
        self.assertEqual((status, data), (204, b''))
        self.assertNotIn('Content-Length', headers)
        self.assertIsNone(self.json('GET', '/api/library/episodes/scalar-clues-001/1')[1]['feedback'])
        self.assertEqual(self.request('DELETE', path)[0], 204)  # idempotent
        self.assertEqual(self.request('DELETE', '/api/library/episodes/scalar-clues-009/1/feedback')[0], 404)
        self.assertEqual(self.request('GET', path)[0], 404)

    def test_mark_used(self):
        for eid in ('scalar-clues-001', 'continuum-clues-002'):
            self.json('PUT', f'/api/library/episodes/{eid}/1/feedback', {'tags': ['tweak']})
        items = [{'episodeId': 'scalar-clues-001', 'revision': 1}, {'episodeId': 'unknown-001', 'revision': 1}]
        self.write_auth_checks('POST', '/api/feedback/mark-used', {'items': items})
        self.assertEqual(self.json('POST', '/api/feedback/mark-used', {'items': items}), (200, {'updated': 1}))
        self.assertEqual(self.json('POST', '/api/feedback/mark-used', {'items': items}), (200, {'updated': 0}))
        self.assertEqual(self.json('GET', '/api/library/episodes/scalar-clues-001/1')[1]['feedback']['status'], 'used')
        for bad in ({'items': []}, {'items': [{'episodeId': 'scalar-clues-001', 'revision': '1'}]}, {},
                    {'items': [{'episodeId': 'scalar-clues-001', 'revision': 2**31}]},
                    {'items': [{'episodeId': 'scalar-clues-001', 'revision': 10**30}]}):
            status, body = self.json('POST', '/api/feedback/mark-used', bad)
            self.assertEqual(status, 422, bad)
            self.assertTrue(body['problems'][0]['path'].startswith('items'))
        # Saving again reopens it.
        self.json('PUT', '/api/library/episodes/scalar-clues-001/1/feedback', {'tags': ['keep']})
        self.assertEqual(self.json('GET', '/api/library/episodes/scalar-clues-001/1')[1]['feedback']['status'], 'open')

    def test_batch_notes(self):
        self.assertEqual(self.json('GET', '/api/library/batches/2026-10-b09/notes')[0], 404)
        self.assertEqual(self.json('PUT', '/api/library/batches/2026-10-b09/notes/brief', {'text': 'x'})[0], 404)
        self.assertEqual(self.json('PUT', '/api/library/batches/2026-10-b03/notes/summary', {'text': 'x'})[0], 404)
        self.write_auth_checks('PUT', '/api/library/batches/2026-10-b03/notes/brief', {'text': 'x'})
        text = '# Brief\n\nAnswers: Bolivia, “Paraguay” ✓\n'
        status, body = self.json('PUT', '/api/library/batches/2026-10-b03/notes/brief', {'text': text})
        self.assertEqual(status, 200, body)
        assert_shape(self, body, 'BatchNote')
        self.assertEqual(body, {'batchId': '2026-10-b03', 'kind': 'brief', 'text': text,
                                'sha256': hashlib.sha256(text.encode()).hexdigest(), 'bytes': len(text.encode()),
                                'uploadedAt': '2026-10-07T12:00:00Z'})
        largest = 'é' * 32768
        self.assertEqual(self.json('PUT', '/api/library/batches/2026-10-b03/notes/retro', {'text': largest})[1]['bytes'], 65536)
        status, body = self.json('PUT', '/api/library/batches/2026-10-b03/notes/retro', {'text': largest + 'x'})
        self.assertEqual((status, body['problems'][0]['path']), (422, 'text'))
        self.assertEqual(self.json('PUT', '/api/library/batches/2026-10-b03/notes/retro', {'note': 'x'})[0], 422)
        status, notes = self.json('GET', '/api/library/batches/2026-10-b03/notes')
        assert_shape(self, notes, 'BatchNotes')
        self.assertEqual((notes['brief']['text'], notes['retro']['bytes']), (text, 65536))
        self.assertEqual(self.json('GET', '/api/library/episodes/continuum-clues-002/1')[1]['notes'], notes)
        # Notes never reach captions, the library view or a schedule.
        library = self.request('GET', '/api/library')[2].decode()
        self.assertNotIn('Answers: Bolivia', library)

    def test_next_batch(self):
        status, body = self.json('GET', '/api/next-batch')
        self.assertEqual(status, 200)
        assert_shape(self, body, 'NextBatchInfo')
        self.assertEqual(body, {'nextBatchId': '2026-10-b04', 'openFeedback': [], 'lastBrief': None, 'lastRetro': None,
                                'performance': [], 'accounts': [], 'funnel': [], 'tags': list(v.FEEDBACK_TAGS)})
        self.json('PUT', '/api/library/episodes/continuum-clues-002/1/feedback', {'tags': ['hook-weak'], 'note': 'slow start'})
        self.json('PUT', '/api/library/episodes/scalar-clues-001/1/feedback', {'tags': ['keep']})
        self.json('POST', '/api/feedback/mark-used', {'items': [{'episodeId': 'scalar-clues-001', 'revision': 1}]})
        self.json('PUT', '/api/library/batches/2026-10-b03/notes/brief', {'text': 'brief b03'})
        self.json('PUT', '/api/library/batches/2026-10-b03/notes/retro', {'text': 'retro b03'})
        self.ledger_job('instagram', INSTAGRAM, '2026-10-05T16:00:00+00:00', 'scalar:Q1:clues',
                        {'episodeId': 'scalar-clues-001', 'revision': 1}, published_at='2026-10-05T16:01:00+00:00',
                        permalink='https://www.instagram.com/reel/A/')
        self.ledger_job('x', 'x-1', '2026-10-06T16:00:00+00:00', 'scalar:Q1:clues', {}, status='ready')
        body = self.json('GET', '/api/next-batch')[1]
        item = body['openFeedback'][0]
        self.assertEqual(len(body['openFeedback']), 1)
        self.assertEqual(set(item), fields('FeedbackItem')[1] | fields('EpisodeFeedback')[1])
        self.assertEqual({k: item[k] for k in ('episodeId', 'batchId', 'questionId', 'game', 'format', 'styleId', 'tags', 'note')},
                         {'episodeId': 'continuum-clues-002', 'batchId': '2026-10-b03', 'questionId': 'continuum:Q2:clues',
                          'game': 'continuum', 'format': 'progressive-clues', 'styleId': 'continuum-paper-1',
                          'tags': ['hook-weak'], 'note': 'slow start'})
        self.assertEqual((body['lastBrief']['text'], body['lastRetro']['text']), ('brief b03', 'retro b03'))
        self.assertEqual(body['performance'], [{'platform': 'instagram', 'status': 'confirmed', 'at': '2026-10-05T16:01:00Z',
                                                'permalink': 'https://www.instagram.com/reel/A/', 'metrics': None}])

    def test_dashboard_standing(self):
        standing = self.json('GET', '/api/dashboard')[1]['standing']
        assert_shape(self, standing, 'Standing')
        self.assertEqual(standing, {'lastBatch': {'batchId': '2026-10-b03', 'importedAt': '2026-10-07T12:00:00Z', 'episodeCount': 2,
                                                  'awaitingFiles': 0},
                                    'awaitingReview': 2, 'nextPosts': [], 'openFeedback': 0, 'nextBatchId': '2026-10-b04',
                                    'postedLast7Days': 0, 'lastBriefAt': None, 'lastRetroAt': None})
        self.json('POST', '/api/library/approve', {'items': [{'episodeId': 'scalar-clues-001', 'revision': 1}], 'reviewer': 'owner'})
        self.json('PUT', '/api/library/episodes/scalar-clues-001/1/feedback', {'tags': ['keep']})

        def job(platform, slot, kind='post'):
            return {'key': f'{platform}-{slot}-{kind}', 'platform': platform, 'slot': slot,
                    'payload': {'kind': kind, 'episode': {'id': 'scalar:Q1:clues', 'episodeId': 'scalar-clues-001', 'revision': 1}}}
        manifest = {'approvedAt': '2026-10-07T10:00:00Z', 'scope': ['instagram', 'x'], 'jobs': [
            job('instagram', '2026-10-08T16:00:00+00:00'), job('instagram', '2026-10-08T16:05:00+00:00', 'comment'),
            job('x', '2026-10-07T13:00:00+00:00'), job('x', '2026-10-09T16:00:00+00:00'),
            job('instagram', '2026-10-07T11:00:00+00:00'), job('youtube', '2026-10-10T16:00:00+00:00'),
            job('x', '2026-10-11T16:00:00+00:00')]}
        (self.state/'manifests').mkdir()
        (self.state/'manifests/approved.json').write_text(json.dumps(manifest))
        # Already handed to the platform: not a "next" post.
        self.ledger_job('x', self.config['channels']['x']['accountId'], '2026-10-07T13:00:00+00:00', 'scalar:Q1:clues', {},
                        status='dispatching', dispatched_at='2026-10-07T11:59:00+00:00')
        standing = self.json('GET', '/api/dashboard')[1]['standing']
        self.assertEqual(standing['nextPosts'], [
            {'at': '2026-10-08T16:00:00Z', 'platform': 'instagram', 'episodeId': 'scalar-clues-001'},
            {'at': '2026-10-09T16:00:00Z', 'platform': 'x', 'episodeId': 'scalar-clues-001'},
            {'at': '2026-10-10T16:00:00Z', 'platform': 'youtube', 'episodeId': 'scalar-clues-001'}])
        self.assertEqual((standing['awaitingReview'], standing['openFeedback']), (1, 1))

    def test_dashboard_standing_journey_facts(self):
        account = self.config['channels']['instagram']['accountId']
        self.ledger_job('instagram', account, '2026-10-06T16:00:00+00:00', 'scalar:Q1:clues', {}, published_at='2026-10-06T16:01:00+00:00')
        self.ledger_job('instagram', account, '2026-10-06T16:02:00+00:00', 'scalar:Q1:clues#comment', {},
                        published_at='2026-10-06T16:03:00+00:00')  # companion: not counted
        self.ledger_job('instagram', account, '2026-09-20T16:00:00+00:00', 'scalar:Q2:clues', {},
                        published_at='2026-09-20T16:01:00+00:00')  # older than 7 days
        self.ledger_job('x', self.config['channels']['x']['accountId'], '2026-10-06T13:00:00+00:00', 'scalar:Q3:clues', {},
                        status='failed')
        self.json('PUT', '/api/library/batches/2026-10-b03/notes/brief', {'text': 'brief b03'})
        self.json('PUT', '/api/library/batches/2026-10-b03/notes/retro', {'text': 'retro b03'})
        standing = self.json('GET', '/api/dashboard')[1]['standing']
        self.assertEqual((standing['postedLast7Days'], standing['nextBatchId']), (1, '2026-10-b04'))
        self.assertEqual((standing['lastBriefAt'], standing['lastRetroAt']), ('2026-10-07T12:00:00Z', '2026-10-07T12:00:00Z'))


if __name__ == '__main__':
    unittest.main()
