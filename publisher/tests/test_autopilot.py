import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'publisher/tests'))
sys.path.insert(0, str(ROOT/'contract'))
import autopilot
import runner
import ui_approval
import ui_library
from library_contract import canonical
import test_ui_schedule as fixtures

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)  # 08:00 in New York


class Env(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.state = base/'state'
        (self.state/'manifests').mkdir(parents=True)
        self.config_path = base/'config.json'
        self.config = fixtures.config()
        self.write_config()
        self.ledger = runner.Ledger(self.state/'ledger.sqlite3')
        # Sorted like ui_library.schedulable_videos, so the draft's library hash matches what the UI recomputes.
        self.videos = sorted((fixtures.record(n, game) for n, game in enumerate(('scalar', 'continuum', 'whenabouts'), 1)),
                             key=lambda v: (v['batchId'], v['episodeId'], v['revision']))
        patcher = mock.patch.object(ui_library, 'schedulable_videos', lambda db, today: self.videos)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config, indent=2)+'\n')
        os.chmod(self.config_path, 0o640)

    def approve_manifest(self, last_slot):
        data = canonical({'version': 1, 'draftSha256': 'd'*64, 'scopeHash': 'e'*64, 'scope': ['x'],
                          'jobs': [{'platform': 'x', 'slot': '2026-10-11T13:30:00+00:00', 'key': 'x|a', 'payload': {}},
                                   {'platform': 'x', 'slot': last_slot, 'key': 'x|b', 'payload': {}}]})
        (self.state/'manifests'/'approved.json').write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def refill(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            message = autopilot.refill(self.config_path, self.state, now=NOW)
        return message, out.getvalue()

    def request(self):
        path = self.state/'approval'/'request.json'
        return json.loads(path.read_text()) if path.exists() else None

    def drafts(self):
        db = ui_library.open_index(self.state)
        try:
            return {r['sha256']: (r['status'], json.loads(r['body'])) for r in db.execute('SELECT * FROM drafts')}
        finally:
            db.close()


class RefillTests(Env):
    def test_long_runway_does_nothing(self):
        self.approve_manifest('2026-10-30T22:00:00+00:00')
        message, _ = self.refill()
        self.assertTrue(message.startswith('Runway ok: the approved schedule runs to 2026-10-30 (20 days left)'), message)
        self.assertIsNone(self.request())
        self.assertFalse((self.state/'library'/'index.sqlite3').exists())

    def test_runway_is_counted_in_the_config_timezone(self):
        # 02:00 UTC on Oct 17 is still Oct 16 in New York: 6 days left, so it refills.
        self.approve_manifest('2026-10-17T02:00:00+00:00')
        message, _ = self.refill()
        self.assertIn('Runway low (the approved schedule ends 2026-10-16)', message)
        self.assertIsNotNone(self.request())

    def test_low_runway_requests_the_recommended_draft(self):
        base = self.approve_manifest('2026-10-15T22:00:00+00:00')
        message, _ = self.refill()
        request = self.request()
        self.assertEqual(set(request), {'draftSha256', 'requestedAt'})
        sha = request['draftSha256']
        self.assertIn(f'requested approval of draft {sha[:8]}', message)
        status, draft = self.drafts()[sha]
        self.assertEqual(status, 'requested')
        self.assertEqual(draft['baseManifestSha256'], base)
        inputs = draft['inputs']
        self.assertEqual((inputs['timezone'], inputs['startDate'], inputs['endDate']),
                         ('America/New_York', '2026-10-11', '2026-10-31'))
        self.assertEqual({p for p, v in inputs['platforms'].items() if v['include']}, set(autopilot.RECOMMENDED_TIMES))
        for p, v in inputs['platforms'].items():
            self.assertEqual((v['weekdays'], v['times'], v['maxPerDay'], inputs['minGapHours'][p]),
                             (list(range(7)), [autopilot.RECOMMENDED_TIMES[p]], 1, 2))
        self.assertEqual((inputs['staggerMinutes'], inputs['companions']), (0, {'firstComment': True, 'answerReply': True}))
        self.assertGreater(draft['summary']['filled'], 0)
        # The applier accepts exactly this request (same phrase as the UI's Approve button).
        with self.assertRaises(ui_approval.Conflict):
            ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}', draft_exists=True, now=NOW)

    def test_unverified_platforms_stay_out(self):
        self.config['channels']['tiktok']['publishingVerified'] = False
        self.config['channels']['bluesky']['route'] = 'disabled'
        self.write_config()
        self.refill()
        _, draft = self.drafts()[self.request()['draftSha256']]
        included = {p for p, v in draft['inputs']['platforms'].items() if v['include']}
        self.assertEqual(included, set(autopilot.RECOMMENDED_TIMES) - {'tiktok', 'bluesky'})
        self.assertNotIn('tiktok', {j['platform'] for j in draft['jobs']})

    def test_waits_when_paused_or_an_approval_is_pending(self):
        (self.state/'PAUSED').touch()
        self.assertIn('Paused in the UI', self.refill()[0])
        self.assertIsNone(self.request())
        (self.state/'PAUSED').unlink()
        (self.state/'approval').mkdir()
        (self.state/'approval'/'request.json').write_text('{}')
        self.assertIn('already being processed', self.refill()[0])
        self.assertEqual(self.drafts() if (self.state/'library').exists() else {}, {})

    def test_used_up_library_requests_nothing(self):
        self.videos = []
        message, _ = self.refill()
        self.assertIn('no approved video is left', message)
        self.assertIsNone(self.request())

    def test_blocked_draft_requests_nothing(self):
        with mock.patch.object(autopilot, 'RUNWAY_DAYS', 30), \
                mock.patch('ui_views.blocking_problems', return_value=['Something blocks it']):
            self.approve_manifest('2026-10-15T22:00:00+00:00')
            message, out = self.refill()
        self.assertIn('blocked', message)
        self.assertIn('Something blocks it', out)
        self.assertIsNone(self.request())

    def test_cli_reports_and_exits(self):
        self.approve_manifest('2026-10-30T22:00:00+00:00')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = autopilot.main(['refill', '--config', str(self.config_path), '--state', str(self.state)])
        self.assertEqual(code, 0)
        self.assertIn('Runway ok', out.getvalue())
        (self.config_path).write_text('not json')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(autopilot.main(['refill', '--config', str(self.config_path), '--state', str(self.state)]), 1)
        self.assertIn('Nothing was requested', err.getvalue())


class VerifyChannelsTests(Env):
    def setUp(self):
        super().setUp()
        self.config['channels']['tiktok'].update(publishingVerified=False, enabled=False)
        self.config['channels']['youtube'].update(publishingVerified=False, enabled=False)
        self.write_config()

    def confirmed(self, platform, account, slot, permalink):
        key = self.ledger.enqueue(platform, account, slot, {'episode': {'id': 'q-'+slot}})
        self.ledger.update(key, 'confirmed', remote_id='r', permalink=permalink, published_at=slot)

    def verify(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            recorded = autopilot.verify_channels(self.config_path, self.state)
        return recorded, out.getvalue()

    def test_records_the_posting_test_from_a_confirmed_post(self):
        self.confirmed('tiktok', 'tt-old', '2026-10-01T23:00:00+00:00', 'https://www.tiktok.com/@old/video/1')
        self.confirmed('tiktok', 'tt-1', '2026-10-09T23:00:00+00:00', 'https://www.tiktok.com/@studiozeroflow/video/2')
        recorded, out = self.verify()
        self.assertEqual(recorded, ['tiktok'])
        config = json.loads(self.config_path.read_text())
        tiktok = config['channels']['tiktok']
        self.assertIs(tiktok['publishingVerified'], True)
        self.assertIs(tiktok['enabled'], False)
        self.assertIn('video/2', tiktok['reason'])
        self.assertIs(config['channels']['youtube']['publishingVerified'], False)
        self.assertIn('youtube: no confirmed post', out)
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o640)

    def test_skips_enabled_unverified_identity_and_non_buffer_channels(self):
        self.config['channels']['tiktok']['enabled'] = True
        self.config['channels']['youtube']['identityVerified'] = False
        self.config['channels']['threads']['publishingVerified'] = False
        self.write_config()
        for platform, account in (('tiktok', 'tt-1'), ('youtube', 'yt-1'), ('threads', 'th-1')):
            self.confirmed(platform, account, '2026-10-09T23:00:00+00:00', f'https://example.test/{platform}/1')
        before = self.config_path.read_bytes()
        self.assertEqual(self.verify()[0], [])
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_cli_needs_root_and_never_fails_the_unit(self):
        if os.geteuid() != 0:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(autopilot.main(['verify-channels', '--config', str(self.config_path),
                                                 '--state', str(self.state)]), 1)
        self.config_path.write_text('not json')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = autopilot.main(['verify-channels', '--config', str(self.config_path), '--state', str(self.state),
                                   '--allow-non-root-for-tests'])
        self.assertEqual(code, 0)
        self.assertIn('next run retries', out.getvalue())


if __name__ == '__main__':
    unittest.main()
