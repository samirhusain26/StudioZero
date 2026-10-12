"""Post stats controls (GET /api/metrics/status, PUT /api/metrics/enabled, POST /api/metrics/read), their Activity
entries and the per-video funnel in GET /api/next-batch. The UI only writes files in STATE/metrics/; nothing here
runs systemctl beyond the injected read-only `show`, and nothing depends on free disk space."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'publisher/tests'))
import metrics
import ui_activity
import ui_health
import ui_views
from runner import Ledger
from test_ui_server import ORIGIN, PASSCODE, SENTINEL, ServerTestCase
from test_ui_views import assert_shape

STATUS, ENABLED, READ = '/api/metrics/status', '/api/metrics/enabled', '/api/metrics/read'
LAST_RUN = {'startedAt': '2026-10-07T11:20:00Z', 'finishedAt': '2026-10-07T11:20:09.5+00:00', 'trigger': 'timer',
            'backfill': 0, 'outcome': 'ok',
            'platforms': {'instagram': {'status': 'rejected', 'postsRead': 2, 'accountsRead': 1, 'reason': 'buffer'},
                          'x': {'status': 'unsupported', 'postsRead': 0, 'accountsRead': 0, 'reason': None}}}


class MetricsServerCase(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.state/'metrics'

    def history(self):
        return sorted(p.name for p in (self.folder/'history').iterdir())


class AccessTests(MetricsServerCase):
    def test_auth_csrf_and_origin_on_all_three(self):
        for method, path, body in (('GET', STATUS, None), ('PUT', ENABLED, {'enabled': True}), ('POST', READ, {})):
            self.assertEqual(self.request(method, path, body, auth=False)[0], 401, path)
            self.assertEqual(self.request(method, path, body, headers={'Authorization': 'Bearer wrong'}, auth=False)[0], 401)
        for method, path, body in (('PUT', ENABLED, {'enabled': True}), ('POST', READ, {})):
            self.assertEqual(self.request(method, path, body, mutate=False)[0], 403)  # no header, no Origin
            self.assertEqual(self.request(method, path, body, headers={'Origin': 'https://evil.example'})[0], 403)
            self.assertEqual(self.request(method, path, body, headers={'X-Scalar-Request': '1'}, mutate=False)[0], 403)
            self.assertEqual(self.request(method, path, body, headers={'X-Scalar-Request': '0', 'Origin': ORIGIN},
                                          mutate=False)[0], 403)
        self.assertFalse(self.folder.exists())  # nothing written by a refused request
        self.assertEqual(self.request('POST', STATUS, {})[0], 404)
        self.assertEqual(self.request('GET', ENABLED)[0], 404)


class StatusTests(MetricsServerCase):
    def test_empty_status_shape(self):
        status, body = self.json('GET', STATUS)
        self.assertEqual(status, 200)
        assert_shape(self, body, 'MetricsStatus')
        assert_shape(self, body['timer'], 'TimerStatus')
        self.assertEqual({k: body[k] for k in ('enabled', 'pending', 'lastRun', 'pathActive')},
                         {'enabled': False, 'pending': None, 'lastRun': None, 'pathActive': False})
        self.assertEqual((body['timer']['unit'], body['timer']['role'], body['timer']['label'], body['timer']['lastResult']),
                         ('scalar-social-metrics.timer', 'metrics', 'Post stats', 'never'))
        self.assertFalse(self.folder.exists())  # reading never creates the folder

    def test_timer_facts_from_systemctl_show(self):
        seen = []

        def show(unit):
            seen.append(unit)
            facts = {'scalar-social-metrics.timer': {'enabled': 'enabled', 'active': 'active',
                                                     'nextRun': 'Wed 2026-10-07 12:20:00 UTC'},
                     'scalar-social-metrics.service': {'result': 'success', 'exitStatus': '0',
                                                       'lastExit': 'Wed 2026-10-07 11:20:09 UTC'},
                     'scalar-social-metrics.path': {'enabled': 'enabled', 'active': 'active'}}
            return {'unit': unit, 'available': True, **facts.get(unit, {})}
        self.app.show = show
        body = self.json('GET', STATUS)[1]
        self.assertEqual(body['timer'], {'unit': 'scalar-social-metrics.timer', 'role': 'metrics', 'label': 'Post stats',
                                         'enabled': True, 'active': True, 'lastRunAt': '2026-10-07T11:20:09Z',
                                         'lastResult': 'success', 'lastResultDetail': 'Finished successfully',
                                         'nextRunAt': '2026-10-07T12:20:00Z'})
        self.assertTrue(body['pathActive'])
        self.assertEqual(set(seen), {'scalar-social-metrics.timer', 'scalar-social-metrics.service', 'scalar-social-metrics.path'})
        self.app.show = lambda unit: {'unit': unit, 'available': False}
        body = self.json('GET', STATUS)[1]
        self.assertEqual((body['timer'], body['pathActive']), (None, False))

    def test_path_unit_is_read_with_the_others(self):
        self.assertIn('scalar-social-metrics.path', ui_health.UNITS)

    def test_last_run_keeps_only_typed_fields(self):
        self.folder.mkdir()
        raw = json.loads(json.dumps(LAST_RUN))
        raw.update(token=SENTINEL, responseBody={'error': SENTINEL}, extra=1)
        raw['platforms']['instagram'].update(body=SENTINEL, accessToken=SENTINEL)
        raw['platforms']['myspace'] = {'status': 'ok', 'postsRead': 1, 'accountsRead': 1, 'reason': None}
        raw['platforms']['threads'] = {'status': 'ok', 'postsRead': True, 'accountsRead': 0, 'reason': None}
        raw['platforms']['facebook'] = {'status': 'mystery', 'postsRead': 0, 'accountsRead': 0, 'reason': None}
        raw['platforms']['bluesky'] = {'status': 'ok', 'postsRead': 3, 'accountsRead': 1}  # reason absent = null
        (self.folder/'last-run.json').write_text(json.dumps(raw))
        status, headers, data = self.request('GET', STATUS)
        self.assertEqual(status, 200)
        self.assertNotIn(SENTINEL.encode(), data)
        run = json.loads(data)['lastRun']
        assert_shape(self, run, 'MetricsLastRun')
        for value in run['platforms'].values():
            assert_shape(self, value, 'MetricsPlatformRun')
        self.assertEqual(run, {'startedAt': '2026-10-07T11:20:00Z', 'finishedAt': '2026-10-07T11:20:09Z', 'trigger': 'timer',
                               'backfill': 0, 'outcome': 'ok', 'platforms': {
                                   'instagram': {'status': 'rejected', 'postsRead': 2, 'accountsRead': 1, 'reason': 'buffer'},
                                   'x': {'status': 'unsupported', 'postsRead': 0, 'accountsRead': 0, 'reason': None},
                                   'bluesky': {'status': 'ok', 'postsRead': 3, 'accountsRead': 1, 'reason': None}}})

    def test_malformed_files_read_as_null_never_500(self):
        self.folder.mkdir()
        bad_runs = ['{', '[1]', 'null', json.dumps({**LAST_RUN, 'trigger': 'cron'}), json.dumps({**LAST_RUN, 'backfill': '3'}),
                    json.dumps({**LAST_RUN, 'startedAt': '2026-10-07T11:20:00'}), json.dumps({**LAST_RUN, 'platforms': []}),
                    json.dumps({**LAST_RUN, 'outcome': None}), '[' * 50000 + ']' * 50000]
        bad_requests = ['{', '"x"', json.dumps({'requestedAt': '2026-10-07T11:00:00Z', 'backfill': 94}),
                        json.dumps({'requestedAt': '2026-10-07T11:00:00Z', 'backfill': True}), json.dumps({'backfill': 1}),
                        json.dumps({'requestedAt': 5, 'backfill': 1})]
        for run, request in zip(bad_runs, bad_requests + bad_requests[:len(bad_runs) - len(bad_requests)]):
            (self.folder/'last-run.json').write_text(run)
            (self.folder/'request.json').write_text(request)
            status, body = self.json('GET', STATUS)
            self.assertEqual(status, 200, run[:40])
            self.assertIsNone(body['lastRun'], run[:40])
            # An unreadable request.json still blocks a new read (409), so it is shown as pending with its file time.
            self.assertEqual(body['pending']['backfill'], 0, request)
            self.assertRegex(body['pending']['requestedAt'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        (self.folder/'last-run.json').write_bytes(b'\xff\xfe\x00')
        (self.folder/'last-run.json').write_text(json.dumps({**LAST_RUN, 'pad': 'x' * ui_health.METRICS_CAP}))  # over the cap
        self.assertIsNone(self.json('GET', STATUS)[1]['lastRun'])
        (self.folder/'last-run.json').unlink()
        target = Path(self.tmp.name)/'elsewhere.json'
        target.write_text(json.dumps(LAST_RUN))
        os.symlink(target, self.folder/'last-run.json')
        self.assertIsNone(self.json('GET', STATUS)[1]['lastRun'])
        # A malformed pending request still blocks a new one until the collector moves it.
        self.assertEqual(self.json('POST', READ, {})[0], 409)
        (self.folder/'request.json').unlink()
        self.assertIsNone(self.json('GET', STATUS)[1]['pending'])


class SwitchTests(MetricsServerCase):
    def test_flag_created_and_removed_with_switch_events(self):
        status, body = self.json('PUT', ENABLED, {'enabled': True})
        self.assertEqual(status, 200)
        assert_shape(self, body, 'MetricsStatus')
        self.assertTrue(body['enabled'])
        self.assertTrue((self.folder/'enabled').is_file())
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.folder/'history').stat().st_mode & 0o777, 0o700)
        [name] = self.history()
        self.assertRegex(name, r'^switch-20261007T120000Z-[0-9a-f]{6}\.json$')
        self.assertEqual(json.loads((self.folder/'history'/name).read_text()), {'at': '2026-10-07T12:00:00Z', 'enabled': True})
        self.assertEqual([p.name for p in self.folder.iterdir() if p.name.startswith('.')], [])  # no temp files left
        self.assertTrue(self.json('PUT', ENABLED, {'enabled': True})[1]['enabled'])
        self.assertEqual(len(self.history()), 1)  # no change, no event
        self.clock[0] += 60
        status, body = self.json('PUT', ENABLED, {'enabled': False})
        self.assertEqual((status, body['enabled']), (200, False))
        self.assertFalse((self.folder/'enabled').exists())
        self.assertEqual(len(self.history()), 2)
        off = json.loads((self.folder/'history'/self.history()[1]).read_text())
        self.assertEqual(off, {'at': '2026-10-07T12:01:00Z', 'enabled': False})
        self.assertFalse(self.json('PUT', ENABLED, {'enabled': False})[1]['enabled'])
        self.assertEqual(len(self.history()), 2)
        self.assertIn('post stats turned on from the UI', self.log.getvalue())

    def test_bad_enabled_bodies_are_422(self):
        for body in ({}, {'enabled': 'yes'}, {'enabled': 1}, {'enabled': None}, {'enabled': True, 'also': 1}, [True], 'on'):
            status, reply = self.json('PUT', ENABLED, body)
            self.assertEqual(status, 422, body)
            self.assertEqual(reply['problems'][0]['code'], 'invalid')
        self.assertEqual(self.json('PUT', ENABLED, {'enabled': True, 'also': 1})[1]['problems'][0]['path'], 'also')
        self.assertEqual(self.request('PUT', ENABLED, b'{', content_type='application/json')[0], 400)
        self.assertEqual(self.request('PUT', ENABLED, b'{"enabled":true}', content_type='text/plain')[0], 415)
        self.assertFalse((self.folder/'enabled').exists())

    def test_history_pruned_to_newest_200(self):
        (self.folder/'history').mkdir(parents=True)
        for n in range(205):  # interleaved kinds: pruning orders by stamp, not by name
            kind = 'request' if n % 2 else 'switch'
            day, minute = divmod(n, 60)
            (self.folder/'history'/f'{kind}-202609{day + 1:02d}T00{minute:02d}00Z-{n:06x}.json').write_text('{}')
        (self.folder/'history'/'notes.txt').write_text('kept')
        self.json('PUT', ENABLED, {'enabled': True})
        names = [n for n in self.history() if n != 'notes.txt']
        self.assertEqual(len(names), ui_health.METRICS_HISTORY_KEEP)
        self.assertEqual(ui_health.METRICS_HISTORY_KEEP, metrics.HISTORY_KEEP)  # both writers keep the same number
        stamps = sorted(n.split('-')[1] for n in names)
        self.assertEqual(stamps[0], '20260901T000600Z')  # the six oldest went
        self.assertIn('20261007T120000Z', stamps)
        self.assertTrue((self.folder/'history'/'notes.txt').exists())


class ReadRequestTests(MetricsServerCase):
    def test_request_written_then_409_while_pending(self):
        status, body = self.json('POST', READ)  # no body: backfill 0
        self.assertEqual(status, 202)
        assert_shape(self, body, 'MetricsStatus')
        assert_shape(self, body['pending'], 'MetricsPendingRequest')
        self.assertEqual(body['pending'], {'requestedAt': '2026-10-07T12:00:00Z', 'backfill': 0})
        self.assertEqual(json.loads((self.folder/'request.json').read_text()), {'backfill': 0, 'requestedAt': '2026-10-07T12:00:00Z'})
        self.assertEqual((self.folder/'request.json').stat().st_mode & 0o777, 0o600)
        status, body = self.json('POST', READ, {'backfill': 5})
        self.assertEqual((status, body['code']), (409, 'busy'))
        self.assertEqual(json.loads((self.folder/'request.json').read_text())['backfill'], 0)  # untouched
        # The collector consumes it (renames into history); a new one is accepted.
        os.replace(self.folder/'request.json', self.folder/'history'/'request-20261007T120000Z-abcdef.json')
        self.clock[0] += 5
        status, body = self.json('POST', READ, {'backfill': 93})
        self.assertEqual((status, body['pending']), (202, {'requestedAt': '2026-10-07T12:00:05Z', 'backfill': 93}))
        self.assertEqual(self.json('POST', READ, {})[0], 409)
        self.assertFalse((self.folder/'enabled').exists())  # a manual read never switches hourly reads on

    def test_bad_backfill_and_unknown_fields_are_422(self):
        for body in ({'backfill': -1}, {'backfill': 94}, {'backfill': True}, {'backfill': 3.0}, {'backfill': '3'},
                     {'backfill': None}, {'backfill': 1, 'days': 2}, {'days': 2}, [], 3):
            status, reply = self.json('POST', READ, body)
            self.assertEqual(status, 422, body)
        self.assertEqual(self.json('POST', READ, {'backfill': 94})[1]['problems'][0]['path'], 'backfill')
        self.assertEqual(self.json('POST', READ, {'days': 2})[1]['problems'][0]['path'], 'days')
        self.assertFalse((self.folder/'request.json').exists())
        self.assertEqual(self.json('POST', READ, {'backfill': 0})[0], 202)


class ActivityTests(MetricsServerCase):
    def system(self):
        body = self.json('GET', '/api/activity?kind=system&limit=500')[1]
        return [e for e in body['entries'] if e['event'].startswith('system.metrics')]

    def test_switch_and_read_entries(self):
        self.json('PUT', ENABLED, {'enabled': True})
        self.clock[0] += 60
        self.json('POST', READ, {'backfill': 30})
        pending = self.system()
        self.assertEqual([(e['event'], e['title'], e['detail']) for e in pending], [
            ('system.metrics-read-requested', 'Post stats read requested', 'Also past 30 days.'),
            ('system.metrics-on', 'Post stats turned on', 'Hourly reads of post and account stats are on.')])
        for item in pending:
            assert_shape(self, item, 'ActivityEntry')
            self.assertEqual((item['kind'], item['severity']), ('system', 'info'))
        # Consumed by the collector: same entry, same id.
        os.replace(self.folder/'request.json', self.folder/'history'/'request-20261007T120100Z-0a1b2c.json')
        self.assertEqual(self.system(), pending)
        self.clock[0] += 60
        self.json('POST', READ, {})
        self.clock[0] += 60
        self.json('PUT', ENABLED, {'enabled': False})
        entries = self.system()
        self.assertEqual([(e['event'], e['at'], e['detail']) for e in entries], [
            ('system.metrics-off', '2026-10-07T12:03:00Z', 'Hourly reads stopped; a manual read still works.'),
            ('system.metrics-read-requested', '2026-10-07T12:02:00Z', None),
            ('system.metrics-read-requested', '2026-10-07T12:01:00Z', 'Also past 30 days.'),
            ('system.metrics-on', '2026-10-07T12:00:00Z', 'Hourly reads of post and account stats are on.')])
        self.assertEqual(len({e['id'] for e in entries}), 4)
        self.assertEqual(self.json('GET', '/api/activity?kind=job')[1]['entries'], [])

    def test_malformed_history_is_skipped(self):
        history = self.folder/'history'
        history.mkdir(parents=True)
        (history/'request-20261007T110000Z-000001.json').write_text('{')  # a bad request the collector moved
        (history/'request-20261007T110100Z-000002.json').write_text(json.dumps({'requestedAt': 'x', 'backfill': 1}))
        (history/'switch-20261007T110200Z-000003.json').write_text(json.dumps({'at': '2026-10-07T11:02:00Z', 'enabled': 'on'}))
        (history/'switch-20261007T110300Z-000004.json').write_text(json.dumps({'at': '2026-10-07T11:03:00Z', 'enabled': False}))
        (history/'other-20261007T110300Z-000005.json').write_text(json.dumps({'at': '2026-10-07T11:03:00Z', 'enabled': True}))
        events = [e['event'] for e in ui_activity.metrics_entries(self.state)]
        self.assertEqual(events, ['system.metrics-off'])
        self.assertEqual(ui_activity.metrics_entries(Path(self.tmp.name)/'missing'), [])


class FunnelTests(MetricsServerCase):
    def ledger_rows(self):
        db = Ledger(self.state/'ledger.sqlite3')
        payload = {'episode': {'id': 'scalar:Q1:clues', 'episodeId': 'scalar-clues-001', 'revision': 1, 'game': 'scalar'},
                   'caption': 'Guess', 'media': {'url': 'https://m.pages.dev/a.mp4', 'sha256': 'a'*64}}
        posted = db.enqueue('instagram', '111', '2026-10-05T16:00:00+00:00', payload)
        db.update(posted, 'confirmed', permalink='https://www.instagram.com/reel/A/', published_at='2026-10-05T16:01:00+00:00',
                  remote_id='17900')
        db.enqueue('x', 'x-1', '2026-10-06T16:00:00+00:00', payload)  # ready: not confirmed
        db.db.close()
        return posted

    def test_funnel_payload_shape(self):
        posted = self.ledger_rows()
        calls = []
        row = {'episode': 'scalar:Q1:clues', 'publishedDates': ['2026-10-05'], 'views': 120, 'engaged': 9, 'answered': 3,
               'avgWatchSeconds': 7.4, 'followsThatDay': 2, 'secret': SENTINEL,
               'counted': {'views': ['instagram'], 'engaged': ['instagram'], 'answered': ['instagram'],
                           'avgWatchSeconds': ['instagram'], 'followsThatDay': ['instagram'], 'raw': SENTINEL},
               'platforms': {'instagram': {'status': 'ok', 'views': 120, 'engaged': 9, 'answered': 3, 'avgWatchSeconds': 7.4,
                                           'followsThatDay': 2, 'followsSource': 'follower-change', 'remoteId': SENTINEL}}}

        def funnel(state, jobs, zone, limit=30):
            calls.append((Path(state), [j['id'] for j in jobs], zone))
            return [row]
        with mock.patch.object(metrics, 'funnel', funnel, create=True):
            status, headers, data = self.request('GET', '/api/next-batch')
        self.assertEqual(status, 200)
        self.assertNotIn(SENTINEL.encode(), data)
        body = json.loads(data)
        assert_shape(self, body, 'NextBatchInfo')
        self.assertEqual(calls, [(self.state, [posted], ZoneInfo('America/New_York'))])
        [item] = body['funnel']
        assert_shape(self, item, 'EpisodeFunnel')
        assert_shape(self, item['counted'], 'FunnelCounted')
        assert_shape(self, item['platforms']['instagram'], 'FunnelPlatform')
        self.assertEqual(item['views'], 120)
        self.assertEqual(item['platforms']['instagram']['followsSource'], 'follower-change')

    def test_episode_funnel_defaults(self):
        self.assertEqual(ui_views.episode_funnel({'episode': 'e', 'platforms': {'x': 'bad', 'bluesky': {}}}), {
            'episode': 'e', 'publishedDates': [], 'labels': None, 'views': None, 'engaged': None, 'answered': None, 'avgWatchSeconds': None,
            'followsThatDay': None, 'counted': {k: [] for k in ui_views.FUNNEL_VALUES},
            'platforms': {'bluesky': {'status': None, 'views': None, 'engaged': None, 'answered': None, 'avgWatchSeconds': None,
                                      'followsThatDay': None, 'followsSource': None}}})

    def test_episode_funnel_labels(self):
        labels = {'e': {'project': 'originals', 'engine': 'story', 'route': 'recap', 'format': 'movie-recap', 'renderer': None,
                        'group': 'originals', 'extra': 'dropped'}}
        row = ui_views.episode_funnel({'episode': 'e'}, labels)
        self.assertEqual(row['labels'], {k: labels['e'][k] for k in ui_views.LABEL_KEYS})
        assert_shape(self, row['labels'], 'FunnelLabels')

    @unittest.skipUnless(hasattr(metrics, 'funnel'), 'metrics.funnel not written yet')
    def test_real_funnel(self):
        self.ledger_rows()
        status, body = self.json('GET', '/api/next-batch')
        self.assertEqual(status, 200)
        assert_shape(self, body, 'NextBatchInfo')
        self.assertEqual([(f['episode'], f['publishedDates'], sorted(f['platforms'])) for f in body['funnel']],
                         [('scalar:Q1:clues', ['2026-10-05'], ['instagram'])])  # the ready X job is not counted
        for item in body['funnel']:
            assert_shape(self, item, 'EpisodeFunnel')
            assert_shape(self, item['counted'], 'FunnelCounted')
            for value in item['platforms'].values():
                assert_shape(self, value, 'FunnelPlatform')


if __name__ == '__main__':
    unittest.main()
