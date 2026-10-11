"""Activity feed: merged ledger/approval/library/system timeline, cursor paging, no secrets."""
import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import ui_activity
import ui_library
from contract_fixtures import JPEG, FakeProbe, document, episode, write_batch
from runner import Ledger
from test_ui_views import assert_shape

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)


def setUpModule():
    # Temp dirs live in /tmp, a ~200 MB tmpfs on the Pi, below the 2 GB upload reserve (which has its own test).
    global _RESERVE
    _RESERVE, ui_library.FREE_SPACE_RESERVE = ui_library.FREE_SPACE_RESERVE, 0


def tearDownModule():
    ui_library.FREE_SPACE_RESERVE = _RESERVE
SECRET = 'sentinel-secret-value-4417'
DRAFT = 'ab' * 32
MANIFEST = 'cd' * 32


def grab(video, out):
    Path(out).write_bytes(JPEG + b'frame')


def show(unit):
    units = {
        'scalar-social-threads-refresh.service': {'result': 'exit-code', 'exitStatus': '1',
                                                  'lastExit': 'Wed 2026-10-07 04:31:00 UTC'},
        'scalar-social-monitor.service': {'result': 'success', 'exitStatus': '0', 'lastExit': 'Wed 2026-10-07 10:30:00 UTC'},
        'scalar-social.service': {'result': 'success', 'exitStatus': '0', 'lastExit': None},
    }
    if unit not in units:
        return {'unit': unit, 'available': False}
    return {'unit': unit, 'available': True, 'enabled': 'enabled', 'active': 'inactive', **units[unit]}


def query(**values):
    return ui_activity.query({k: [str(v)] for k, v in values.items()})


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)/'state'
        self.state.mkdir()
        self.config = {'timezone': 'America/New_York', 'channels': {}, 'apiToken': SECRET}
        creds = self.state/'credentials'
        creds.mkdir()
        (creds/'UI_PASSCODE').write_text(SECRET)
        self.ledger_fixture()
        self.approval_fixture()
        self.library_fixture()
        (self.state/'threads-token-failure.json').write_text(json.dumps({'checkedAt': '2026-10-07T04:31:00Z', 'token': SECRET}))
        (self.state/'instagram-token-health.json').write_text(json.dumps({'expiresAt': '2026-12-01T00:00:00+00:00', 'renewed': True}))
        (self.state/'health.json').write_text(json.dumps({'checkedAt': '2026-10-07T11:55:00+00:00', 'paused': True,
                                                          'jobs': {'uncertain': 1, 'confirmed': 1}, 'contentExhausted': []}))
        (self.state/'PAUSED').touch()

    def tearDown(self):
        self.tmp.cleanup()

    def ledger_fixture(self):
        db = Ledger(self.state/'ledger.sqlite3')
        def add(platform, slot, episode, kind='post'):
            return db.enqueue(platform, '111', slot, {'episode': {'id': episode, 'episodeId': 'scalar-clues-001', 'game': 'scalar'},
                                                      'kind': kind, 'caption': f'Caption {SECRET}'})
        def event(job, kind, at, detail=''):
            db.db.execute('INSERT INTO events(job,kind,at,detail) VALUES(?,?,?,?)', (job, kind, at, detail))
        with db.db:
            posted = add('instagram', '2026-10-05T16:00:00+00:00', 'scalar:Q1:clues')
            db.db.execute("UPDATE jobs SET status='confirmed', permalink='https://www.instagram.com/reel/A/' WHERE id=?", (posted,))
            event(posted, 'dispatching', '2026-10-05T16:00:01.250000+00:00')
            event(posted, 'confirmed', '2026-10-05T16:01:00+00:00')
            unsure = add('threads', '2026-10-06T16:00:00+00:00', 'scalar:Q2:clues')
            db.db.execute("UPDATE jobs SET status='uncertain' WHERE id=?", (unsure,))
            event(unsure, 'dispatching', '2026-10-06T16:00:01+00:00')
            event(unsure, 'uncertain', '2026-10-06T16:00:02+00:00', 'uncertain_response')
            failed = add('bluesky', '2026-10-06T17:00:00+00:00', 'scalar:Q3:clues')
            event(failed, 'failed', '2026-10-06T17:00:05+00:00', f'vendor said {SECRET}')
            comment = add('instagram', '2026-10-05T16:02:00+00:00', 'scalar:Q1:clues#comment', 'comment')
            event(comment, 'expired', '2026-10-05T17:00:00+00:00', 'parent_unavailable')
            resolved = add('instagram', '2026-10-04T16:00:00+00:00', 'scalar:Q4:clues')
            event(resolved, 'owner_resolved', '2026-10-06T09:00:00+00:00',
                  json.dumps({'resolution': 'confirmed', 'permalink': 'https://www.instagram.com/reel/B/', 'evidence': SECRET}))
            prior = {'id': 'f' * 24, 'platform': 'instagram', 'account': '111', 'slot': '2026-10-09T13:00:00+00:00',
                     'episode': 'scalar:Q5:clues', 'payload': json.dumps({'episode': {'id': 'scalar:Q5:clues', 'game': 'scalar'},
                                                                          'caption': f'Cancelled caption {SECRET}'}),
                     'status': 'ready', 'dispatched_at': None}
            event('f' * 24, 'cancelled', '2026-10-06T20:00:00+00:00', json.dumps(prior))
            event(None, 'content_exhausted', '2026-10-06T08:00:00+00:00', 'x')
        db.db.close()

    def approval_fixture(self):
        folder = self.state/'approval'
        (folder/'history').mkdir(parents=True)
        (folder/'history/20261006T100000000000Z-abababab-request.json').write_text(
            json.dumps({'draftSha256': DRAFT, 'requestedAt': '2026-10-06T10:00:00Z'}))
        ready = {'status': 'manifest-ready', 'draftSha256': DRAFT, 'manifestSha256': MANIFEST, 'jobs': 3, 'at': '2026-10-06T10:01:00Z'}
        (folder/'history/20261006T100100000000Z-abababab-result.json').write_text(json.dumps(ready))
        (folder/'result.json').write_text(json.dumps({**ready, 'status': 'bound', 'boundAt': '2026-10-06T10:01:05Z'}))
        failed = {'status': 'failed', 'category': 'deployment', 'message': f'curl output {SECRET}', 'draftSha256': None,
                  'at': '2026-10-05T09:00:00Z'}
        (folder/'history/20261005T090000000000Z-unknown-result.json').write_text(json.dumps(failed))

    def library_fixture(self):
        index = ui_library.open_index(self.state)
        folder, data, blobs = write_batch(Path(self.tmp.name)/'mac', document([episode(1), episode(2, 'continuum')]))
        ui_library.import_batch_json(index, self.state, (folder/'batch.json').read_bytes(), NOW - dt.timedelta(hours=5))
        for name, blob in blobs.items():
            ui_library.accept_batch_file(index, self.state, data['batchId'], name, io.BytesIO(blob), len(blob), FakeProbe(),
                                         grab, NOW - dt.timedelta(hours=4))
        items = [{'episodeId': 'scalar-clues-001', 'revision': 1}]
        ui_library.approve(index, items, 'owner', NOW - dt.timedelta(hours=3), state=self.state)
        ui_library.withdraw(index, items, 'owner', NOW - dt.timedelta(hours=2), note='wrong cover')
        ui_library.delete_episode(index, self.state, 'continuum-clues-002', 1, NOW - dt.timedelta(hours=1))
        index.close()

    def feed(self, **values):
        return ui_activity.feed(self.state, show, self.config, query(**values), NOW)

    def test_shape_order_and_sources(self):
        body = self.feed(limit=500)
        assert_shape(self, body, 'ActivityResponse')
        entries = body['entries']
        for item in entries:
            assert_shape(self, item, 'ActivityEntry')
        ids = [e['id'] for e in entries]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([e['at'] for e in entries], sorted((e['at'] for e in entries), reverse=True))
        events = {e['event'] for e in entries}
        for name in ('job.dispatching', 'job.confirmed', 'job.uncertain', 'job.failed', 'job.expired', 'job.cancelled',
                     'job.owner_resolved', 'job.content_exhausted', 'approval.requested', 'approval.manifest-ready',
                     'approval.bound', 'approval.failed', 'library.batch-imported', 'library.video-stored',
                     'library.cover-stored', 'library.approved', 'library.withdrawn', 'library.deleted',
                     'system.service', 'system.token-renewal-failed', 'system.token-health', 'system.publisher-health',
                     'system.paused'):
            self.assertIn(name, events)
        confirmed = next(e for e in entries if e['event'] == 'job.confirmed')
        self.assertEqual((confirmed['severity'], confirmed['title'], confirmed['permalink'], confirmed['game']),
                         ('success', 'Posted on Instagram', 'https://www.instagram.com/reel/A/', 'scalar'))
        self.assertEqual(confirmed['at'], '2026-10-05T16:01:00Z')
        threads = next(e for e in entries if e['event'] == 'system.service' and e['platform'] == 'threads')
        self.assertEqual((threads['severity'], threads['title'], threads['at']),
                         ('error', 'Threads token renewal failed', '2026-10-07T04:31:00Z'))
        monitor = next(e for e in entries if e['title'] == 'Monitor finished OK')
        self.assertEqual(monitor['severity'], 'success')
        self.assertFalse(any(e['title'].startswith('Publisher finished') for e in entries))  # never ran: no entry
        expired = next(e for e in entries if e['event'] == 'job.expired')
        self.assertIn('Comment not sent', expired['detail'])
        self.assertEqual(expired['jobKind'], 'comment')
        withdrawn = next(e for e in entries if e['event'] == 'library.withdrawn')
        self.assertIn('wrong cover', withdrawn['detail'])
        uncertain = next(e for e in entries if e['event'] == 'job.uncertain')
        self.assertNotIn('post again', json.dumps(uncertain).lower().replace('never post it again', ''))

    def test_no_secret_or_stored_text_reaches_the_feed(self):
        body = self.feed(limit=500)
        text = json.dumps(body)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('Caption', text)
        cancelled = next(e for e in body['entries'] if e['event'] == 'job.cancelled')
        self.assertEqual(cancelled['detail'], 'Removed by a re-approved schedule (was due 2026-10-09T13:00:00Z).')
        self.assertEqual((cancelled['platform'], cancelled['episode'], cancelled['jobId']), ('instagram', 'scalar:Q5:clues', 'f' * 24))
        failed = next(e for e in body['entries'] if e['event'] == 'job.failed')
        self.assertEqual(failed['detail'], None)  # unknown free text is not echoed
        approval = next(e for e in body['entries'] if e['event'] == 'approval.failed')
        self.assertNotIn('curl', approval['detail'])
        self.assertNotIn(SECRET, ui_activity.feed_csv(body['entries']))

    def test_cursor_pagination_is_stable_and_complete(self):
        everything = [e['id'] for e in self.feed(limit=500)['entries']]
        for size in (1, 3, 7):
            seen, before = [], None
            while True:
                page = self.feed(limit=size, **({'before': before} if before else {}))
                seen += [e['id'] for e in page['entries']]
                before = page['nextBefore']
                if not before:
                    break
                self.assertEqual(before, page['entries'][-1]['id'])
            self.assertEqual(seen, everything, size)

    def test_filters(self):
        jobs = self.feed(limit=500, kind='job')['entries']
        self.assertTrue(jobs and all(e['kind'] == 'job' for e in jobs))
        threads = self.feed(limit=500, platform='threads')['entries']
        self.assertEqual({e['platform'] for e in threads}, {'threads'})
        self.assertIn('system.service', {e['event'] for e in threads})
        errors = self.feed(limit=500, severity='error')['entries']
        self.assertTrue(errors and all(e['severity'] == 'error' for e in errors))
        x = self.feed(limit=500, platform='x')['entries']
        self.assertEqual([e['event'] for e in x], ['job.content_exhausted'])
        for bad in ({'kind': 'mail'}, {'severity': 'fatal'}, {'limit': '501'}, {'limit': '0'}, {'before': 'nope'},
                    {'platform': 'myspace'}, {'format': 'xml'}):
            with self.assertRaises(ValueError):
                ui_activity.query({k: [v] for k, v in bad.items()})

    def test_csv_columns(self):
        text = ui_activity.feed_csv(self.feed(limit=5)['entries'])
        self.assertEqual(text.splitlines()[0].split(','), list(ui_activity.FIELDS))
        self.assertEqual(len(text.splitlines()), 6)

    def test_empty_state(self):
        empty = Path(self.tmp.name)/'empty'
        empty.mkdir()
        body = ui_activity.feed(empty, lambda unit: {'unit': unit, 'available': False}, {}, query(), NOW)
        self.assertEqual((body['entries'], body['nextBefore'], body['displayTimezone']), ([], None, 'UTC'))
        self.assertFalse((empty/'library').exists())  # read-only: nothing created


if __name__ == '__main__':
    unittest.main()
