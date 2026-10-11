import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
from operations import backup, inspect, posting_schedule
from runner import Ledger, fingerprint


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.config = self.state/'config.json'
        self.config.write_text(json.dumps({'paused': True}))
        self.ledger = Ledger(self.state/'ledger.sqlite3')

    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()

    def test_backup_contains_wal_and_does_not_replace_existing(self):
        self.ledger.enqueue('x', 'a', 's', {'episode': {'id': 'e'}})
        destination = self.state/'backup.sqlite3'
        backup(self.state/'ledger.sqlite3', destination)
        restored = Ledger(destination)
        self.assertEqual(restored.db.execute('SELECT episode FROM jobs').fetchone()[0], 'e')
        restored.db.close()
        with self.assertRaises(ValueError):
            backup(self.state/'ledger.sqlite3', destination)

    def test_paused_monitor_does_not_require_publisher_tick(self):
        self.assertTrue(inspect(self.config, self.state)['healthy'])

    def test_unpaused_monitor_detects_missing_and_stale_tick(self):
        self.config.write_text(json.dumps({'paused': False}))
        self.assertIn('publisher_health_missing', inspect(self.config, self.state)['issues'])
        now = dt.datetime.now(dt.timezone.utc)
        (self.state/'health.json').write_text(json.dumps({'checkedAt': (now-dt.timedelta(hours=1)).isoformat()}))
        self.assertIn('publisher_health_stale', inspect(self.config, self.state, now)['issues'])

    def test_uncertain_post_alerts_even_while_paused(self):
        key = self.ledger.enqueue('x', 'a', 's', {'episode': {'id': 'e'}})
        self.ledger.update(key, 'uncertain')
        self.assertIn('publication_needs_review', inspect(self.config, self.state)['issues'])

    def test_missed_slot_alerts_for_a_day_and_names_the_platform(self):
        key = self.ledger.enqueue('bluesky', 'a', 's', {'episode': {'id': 'e'}})
        self.ledger.update(key, 'expired', error='missed_slot')
        report = inspect(self.config, self.state)
        self.assertIn('publication_missed', report['issues'])
        self.assertEqual(report['missedLast24h'], 1)
        later = dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=25)
        self.assertTrue(inspect(self.config, self.state, later)['healthy'])
        other = self.ledger.enqueue('threads', 'a', 't', {'episode': {'id': 'f'}})
        self.ledger.update(other, 'failed', error='retry_limit')
        self.assertEqual(inspect(self.config, self.state, later)['attention'], {'threads': ['failed']})

    def test_configured_threads_renewal_failure_alerts_while_paused(self):
        self.config.write_text(json.dumps({'paused': True, 'channels': {'threads': {'identityVerified': True}}}))
        self.assertIn('threads_token_health_missing', inspect(self.config, self.state)['issues'])
        now = dt.datetime.now(dt.timezone.utc)
        (self.state/'threads-token-health.json').write_text(json.dumps({'expiresAt': (now+dt.timedelta(hours=1)).isoformat()}))
        self.assertIn('threads_token_expiring', inspect(self.config, self.state, now)['issues'])

    def test_threads_renewal_failure_is_unhealthy_before_expiry(self):
        self.config.write_text(json.dumps({'paused': True, 'channels': {'threads': {'identityVerified': True}}}))
        now = dt.datetime.now(dt.timezone.utc)
        (self.state/'threads-token-health.json').write_text(json.dumps({'expiresAt': (now+dt.timedelta(days=50)).isoformat()}))
        self.assertTrue(inspect(self.config, self.state, now)['healthy'])
        (self.state/'threads-token-failure.json').write_text('{}')
        report = inspect(self.config, self.state, now)
        self.assertFalse(report['healthy'])
        self.assertIn('threads_token_renewal_failed', report['issues'])

    def schedule_config(self):
        config = json.loads((ROOT/'publisher/config.example.json').read_text())
        config['approval'] = {'scopeHash': fingerprint(config), 'approvedAt': '2026-10-06'}
        # Credentials must not be copied from configuration into exports.
        config['privateTestField'] = 'do-not-export'
        self.config.write_text(json.dumps(config))
        return config

    def test_instagram_renewal_health_only_required_for_direct_route(self):
        config = {'paused': True, 'channels': {'instagram': {'identityVerified': True, 'route': 'buffer'}}}
        self.config.write_text(json.dumps(config))
        self.assertTrue(inspect(self.config, self.state)['healthy'])
        config['channels']['instagram']['route'] = 'instagram'
        self.config.write_text(json.dumps(config))
        self.assertIn('instagram_token_health_missing', inspect(self.config, self.state)['issues'])
        now = dt.datetime.now(dt.timezone.utc)
        (self.state/'instagram-token-health.json').write_text(json.dumps({'expiresAt': (now+dt.timedelta(hours=1)).isoformat()}))
        self.assertIn('instagram_token_expiring', inspect(self.config, self.state, now)['issues'])

    def test_instagram_renewal_failure_is_unhealthy_before_expiry(self):
        self.config.write_text(json.dumps({'paused': True, 'channels': {
            'instagram': {'identityVerified': True, 'route': 'instagram'}}}))
        now = dt.datetime.now(dt.timezone.utc)
        (self.state/'instagram-token-health.json').write_text(json.dumps({
            'expiresAt': (now+dt.timedelta(days=59)).isoformat()}))
        (self.state/'instagram-token-failure.json').write_text('{}')
        report = inspect(self.config, self.state, now)
        self.assertFalse(report['healthy'])
        self.assertIn('instagram_token_renewal_failed', report['issues'])

    def test_schedule_reads_files_and_results_without_reserving_or_modifying_jobs(self):
        self.schedule_config()
        key = self.ledger.enqueue('instagram', 'owned-account', '2026-10-06T12:00:00+00:00',
            {'episode': {'id': 'ep01', 'game': 'scalar'}, 'format': 'self-contained',
             'media': {'url': 'https://scalar-social-media.pages.dev/published/video.mp4', 'sha256': 'b'*64}})
        self.ledger.update(key, 'confirmed', permalink='https://www.instagram.com/reel/test/',
            published_at='2026-10-06T12:01:00+00:00')
        catalog = self.state/'catalog.json'
        catalog.write_text(json.dumps({'clips': {'ep01:self': {'path': 'clips/ep01-self.mp4', 'sha256': 'a'*64}}}))
        before = [tuple(row) for row in self.ledger.db.execute('SELECT * FROM jobs')]
        report = posting_schedule(self.config, self.state, catalog,
            dt.datetime(2026, 10, 6, 11, tzinfo=dt.timezone.utc))
        job = report['jobs'][0]
        self.assertEqual(job['slotLocal'], '2026-10-06T08:00:00-04:00')
        self.assertEqual(job['files'][0]['path'], 'clips/ep01-self.mp4')
        self.assertEqual(job['mediaSha256'], 'b'*64)
        self.assertEqual(job['status'], 'confirmed')
        self.assertTrue(report['paused'])
        self.assertTrue(report['scheduleApproved'])
        self.assertFalse(report['publicationEnabled'])
        self.assertEqual(report['enabledChannels'], [])
        self.assertNotIn('do-not-export', json.dumps(report))
        self.assertEqual(before, [tuple(row) for row in self.ledger.db.execute('SELECT * FROM jobs')])

    def test_schedule_does_not_guess_an_unpublished_chain_predecessor(self):
        self.schedule_config()
        self.ledger.enqueue('x', 'a', '2026-11-01T13:00:00+00:00',
            {'episode': {'id': 'ep02'}, 'format': 'chained'})
        report = posting_schedule(self.config, self.state,
            now=dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc))
        self.assertTrue(report['jobs'][0]['predecessorPending'])
        self.assertEqual(report['jobs'][0]['slotLocal'], '2026-11-01T08:00:00-05:00')

    def test_schedule_missing_ledger_is_reported_without_creating_it(self):
        self.schedule_config()
        absent = self.state/'absent'
        report = posting_schedule(self.config, absent,
            now=dt.datetime(2026, 10, 6, 11, tzinfo=dt.timezone.utc))
        self.assertTrue(report['ledgerMissing'])
        self.assertEqual(report['jobs'], [])
        self.assertFalse(absent.exists())
