import datetime as dt
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
import ui_health
from runner import Ledger

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)
SENTINEL = 'sentinel-credential-value-7731'


def fake_show(states):
    def show(unit):
        return {'unit': unit, 'available': True, 'enabled': 'disabled', 'active': 'inactive', 'result': 'success',
                **states.get(unit, {})}
    return show


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.config = json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config['channels']['threads'].update(route='threads', accountId='t-1', identityVerified=True, publishingVerified=True)
        self.config['channels']['instagram'].update(route='instagram', accountId='111', previousAccountIds=['buffer-ig'],
                                                    identityVerified=True, publishingVerified=True)
        self.config_path = self.state/'config.json'
        self.config_path.write_text(json.dumps(self.config))
        (self.state/'PAUSED').touch()
        self.ledger = Ledger(self.state/'ledger.sqlite3')
        payload = {'episode': {'id': 'ep03', 'episodeId': 'scalar-legacy-003', 'game': 'scalar'}, 'caption': 'Guess along',
                   'media': {'url': 'https://m.pages.dev/a.mp4', 'sha256': 'a'*64}}
        self.confirmed = self.ledger.enqueue('instagram', 'buffer-ig', '2026-10-05T16:00:00+00:00', payload)
        self.ledger.update(self.confirmed, 'confirmed', permalink='https://www.instagram.com/reel/A/', published_at='2026-10-05T16:01:00+00:00')
        self.uncertain = self.ledger.enqueue('threads', 't-1', '2026-10-06T16:00:00+00:00', {**payload, 'episode': {'id': 'ep04', 'game': 'continuum'}})
        self.ledger.update(self.uncertain, 'uncertain', retry_at=NOW.timestamp()+3600, error='uncertain_response',
                           dispatched_at='2026-10-06T16:00:00+00:00')
        (self.state/'threads-token-health.json').write_text(json.dumps({'expiresAt': (NOW+dt.timedelta(days=1)).isoformat()}))
        (self.state/'instagram-token-health.json').write_text(json.dumps({'expiresAt': (NOW+dt.timedelta(days=50)).isoformat(), 'renewed': True}))

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def test_three_statuses_stay_separate(self):
        view = ui_health.dashboard(self.state, self.config_path, NOW, fake_show({}))
        self.assertTrue(view['postingTestPassed']['instagram']['passed'])  # via previousAccountIds
        self.assertFalse(view['postingTestPassed']['threads']['passed'])
        self.assertEqual(view['currentlyAuthenticated']['threads']['state'], 'expiring')
        self.assertEqual(view['currentlyAuthenticated']['instagram']['state'], 'ok')
        self.assertEqual(view['currentlyAuthenticated']['tiktok']['state'], 'not-connected')
        recurring = view['recurringPublishing']
        self.assertFalse(recurring['enabled'])
        self.assertTrue(recurring['pausedSentinel'])
        self.assertFalse(recurring['timerEnabled'])
        self.assertNotIn('healthy', view)

    def test_recurring_requires_every_switch(self):
        self.config.update(paused=False)
        self.config['channels']['threads']['enabled'] = True
        self.config_path.write_text(json.dumps(self.config))
        (self.state/'PAUSED').unlink()
        on = fake_show({'scalar-social.timer': {'enabled': 'enabled', 'active': 'active'}})
        self.assertTrue(ui_health.dashboard(self.state, self.config_path, NOW, on)['recurringPublishing']['enabled'])
        (self.state/'PAUSED').touch()
        self.assertFalse(ui_health.dashboard(self.state, self.config_path, NOW, on)['recurringPublishing']['enabled'])

    def test_uncertain_jobs_have_owner_actions_not_retry(self):
        view = ui_health.dashboard(self.state, self.config_path, NOW, fake_show({}))
        job = view['uncertainJobs'][0]
        self.assertEqual(job['id'], self.uncertain)
        self.assertEqual(job['error']['category'], 'uncertain_response')
        text = json.dumps(job).lower()
        self.assertNotIn('post again', text.replace('never post it again', ''))
        self.assertTrue(job['nextCheck'])
        self.assertIn('publication_needs_review', [i['code'] for i in view['issues']])

    def test_history_filters_and_csv(self):
        rows = ui_health.history(self.state, self.config)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['id'] for r in ui_health.history(self.state, self.config, {'platform': 'threads'})], [self.uncertain])
        self.assertEqual(len(ui_health.history(self.state, self.config, {'game': 'continuum'})), 1)
        self.assertEqual(len(ui_health.history(self.state, self.config, {'q': 'EP03'})), 1)
        self.assertEqual(len(ui_health.history(self.state, self.config, {'from': '2026-10-06', 'to': '2026-10-06'})), 1)
        row = rows[-1]
        self.assertEqual(row['slot']['zone'], 'EDT')
        self.assertEqual(row['slot']['utc'], '2026-10-05T16:00:00Z')
        text = ui_health.history_csv(rows)
        self.assertTrue(text.startswith('id,platform,account,slotLocal,zone,slotUtc'))
        self.assertIn('https://www.instagram.com/reel/A/', text)

    def test_job_detail_events_and_plain_error(self):
        detail = ui_health.job_detail(self.state, self.config, self.uncertain)
        self.assertEqual(detail['error']['title'], 'Result unknown, checking')
        self.assertTrue(detail['reconciliation']['ownerActions'])
        self.assertEqual(detail['events'][-1]['kind'], 'uncertain')
        self.assertIsNone(ui_health.job_detail(self.state, self.config, '0'*24))

    def test_backup_contains_state_but_no_credentials_or_media(self):
        creds = self.state/'credentials'
        creds.mkdir()
        (creds/'UI_PASSCODE').write_text(SENTINEL)
        (self.state/'manifests').mkdir()
        (self.state/'manifests/approved.json').write_text('{"jobs":[]}')
        (self.state/'site/clips').mkdir(parents=True)
        (self.state/'site/clips/a.mp4').write_bytes(b'video')
        config = {**self.config, 'apiToken': SENTINEL}
        body, name = ui_health.backup_archive(self.state, config, now=NOW)
        self.assertEqual(name, 'scalar-social-backup-20261007T120000Z.tar.gz')
        with tarfile.open(fileobj=io.BytesIO(body)) as tar:
            names = [m.name.split('/', 1)[1] for m in tar.getmembers()]
            self.assertIn('ledger.sqlite3', names)
            self.assertIn('manifests/approved.json', names)
            self.assertFalse([n for n in names if n.endswith('.mp4') or 'credential' in n.lower()])
            for member in tar.getmembers():
                self.assertNotIn(SENTINEL.encode(), tar.extractfile(member).read())

    def test_errors_cover_runner_categories(self):
        for category in ('authorization', 'rejected', 'budget', 'media', 'rate_limit', 'uncertain_response',
                         'missed_slot', 'retry_limit', 'remote_rejected', 'remote_confirmation_pending', 'parent_unavailable'):
            self.assertIn(category, ui_health.ERRORS)
            self.assertTrue(ui_health.explain(category)['nextAction'])


if __name__ == '__main__':
    unittest.main()
