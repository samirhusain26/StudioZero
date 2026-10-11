import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
import metrics
from buffer_adapter import PublishError
from runner import Ledger

UTC = dt.timezone.utc
PUBLISHED = dt.datetime(2026, 10, 12, 13, tzinfo=UTC)   # 09:00 in New York
NOW = PUBLISHED+dt.timedelta(hours=2)
TOKEN = 'TOKEN-q7Zx41'
BODY = 'BODY-w3Rk88'
NY = ZoneInfo('America/New_York')


class Remote:
    """Fake transport keyed on the URL path suffix (first match wins); records URLs; `first` runs before the first call."""

    def __init__(self, routes, first=None):
        self.routes, self.urls, self.first = routes, [], first

    def __call__(self, url, headers=None):
        if not self.urls and self.first:
            self.first()
        self.urls.append(url)
        path = urllib.parse.urlsplit(url).path
        for suffix, answer in self.routes.items():
            if path.endswith(suffix):
                if isinstance(answer, BaseException):
                    raise answer
                return answer(url) if callable(answer) else answer
        raise AssertionError('unexpected '+url)


def tokens(platform):
    return TOKEN


def metric_of(url):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('metric', [''])[0]


def routes(threads=None):
    """Instagram and Threads, posts and accounts; every body carries a distinctive marker."""
    return {
        'v26.0/me/insights': lambda url: {'data': [{'name': metric_of(url), 'total_value': {'value': 4}}], 'note': BODY},
        'v26.0/me': {'followers_count': 120, 'follows_count': 3, 'media_count': 9, 'note': BODY},
        '/comments': {'data': [{'username': 'ana', 'text': BODY}]},
        'threads_insights': threads or (lambda url: {'data': [{'name': metric_of(url), 'total_value': {'value': 7}}]}),
        '/replies': {'data': []},
        '/insights': lambda url: {'data': [{'name': 'views', 'values': [{'value': 100}]}], 'note': BODY},
    }


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.folder = self.state/'metrics'
        self.ledger = Ledger(self.state/'ledger.sqlite3')
        verified = {'identityVerified': True}
        self.config = {'timezone': 'America/New_York',
                       'channels': {'instagram': {**verified, 'route': 'instagram'}, 'threads': verified}}

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def post(self, platform, remote_id, episode='ep01'):
        key = self.ledger.enqueue(platform, 'acct', PUBLISHED.isoformat()+platform+episode, {'episode': {'id': episode}})
        self.ledger.update(key, 'confirmed', remote_id=remote_id, permalink='https://example.invalid/p',
                           published_at=PUBLISHED.isoformat())
        return key

    def run_once(self, remote, now=NOW, backfill=0):
        return metrics.run(self.state, self.config, now, remote, tokens, backfill)

    def last_run(self):
        return json.loads((self.folder/'last-run.json').read_text())

    def enable(self):
        self.folder.mkdir(exist_ok=True)
        (self.folder/'enabled').write_text('')

    def request(self, body):
        self.folder.mkdir(exist_ok=True)
        (self.folder/'request.json').write_bytes(body if isinstance(body, bytes) else json.dumps(body).encode())

    def history(self, prefix='request-'):
        return sorted(p for p in (self.folder/'history').iterdir() if p.name.startswith(prefix))

    def test_flag_off_timer_run_reads_nothing(self):
        remote = Remote(routes())
        summary = self.run_once(remote)
        self.assertEqual(remote.urls, [])
        self.assertEqual((summary['trigger'], summary['outcome']), ('timer', 'stats-off'))
        run = self.last_run()
        self.assertEqual((run['trigger'], run['outcome'], run['backfill'], run['platforms']), ('timer', 'stats-off', 0, {}))
        self.assertEqual(set(run), {'startedAt', 'finishedAt', 'trigger', 'backfill', 'outcome', 'platforms'})
        self.assertEqual(run['startedAt'], '2026-10-12T15:00:00Z')
        self.assertFalse((self.state/'metrics.sqlite3').exists())
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)

    def test_flag_on_timer_run_reads_and_records_platforms(self):
        self.post('instagram', '1789')
        self.enable()
        remote = Remote(routes())
        summary = self.run_once(remote)
        self.assertEqual((summary['trigger'], summary['outcome'], summary['reads']), ('timer', 'ok', {'instagram': {'ok': 1}}))
        platforms = self.last_run()['platforms']
        self.assertEqual(platforms['instagram'], {'status': 'ok', 'postsRead': 1, 'accountsRead': 5, 'reason': None})
        self.assertEqual(platforms['threads'], {'status': 'ok', 'postsRead': 0, 'accountsRead': 5, 'reason': None})
        self.assertEqual(self.history(), [])

    def test_request_is_moved_before_any_fetch_and_forces_account_counts(self):
        self.enable()
        self.run_once(Remote(routes()))   # timer: today's counts read
        seen = []

        def first():
            seen.append((self.folder/'request.json').exists())
            seen.append([json.loads(p.read_text()) for p in self.history()])
        (self.folder/'enabled').unlink()   # a manual read works with hourly reads off
        body = {'requestedAt': '2026-10-12T15:30:00Z', 'backfill': 5}
        self.request(body)
        remote = Remote(routes(), first)
        summary = self.run_once(remote, NOW+dt.timedelta(hours=1))
        self.assertEqual(seen, [False, [body]])
        self.assertEqual((summary['trigger'], summary['outcome']), ('request', 'ok'))
        self.assertTrue(any(urllib.parse.urlsplit(u).path.endswith('v26.0/me') for u in remote.urls))   # inside 6 h
        self.assertIn('2026-10-07', {dt.datetime.fromtimestamp(int(urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)['since'][0]),
                                                               NY).date().isoformat() for u in remote.urls if 'me/insights' in u})
        run = self.last_run()
        self.assertEqual((run['trigger'], run['backfill'], run['outcome']), ('request', 5, 'ok'))
        self.assertRegex(self.history()[0].name, r'^request-20261012T160000Z-[0-9a-f]{6}\.json$')
        self.assertFalse((self.folder/'request.json').exists())
        remote = Remote(routes())
        self.assertEqual(self.run_once(remote, NOW+dt.timedelta(hours=2))['outcome'], 'stats-off')
        self.assertEqual(remote.urls, [])

    def test_larger_of_request_and_cli_backfill_wins(self):
        self.request({'requestedAt': '2026-10-12T15:30:00Z', 'backfill': 0})
        self.run_once(Remote(routes()), backfill=20)   # an owner's enable-metrics.sh --backfill is never dropped
        self.assertEqual((self.last_run()['trigger'], self.last_run()['backfill']), ('request', 20))
        self.request({'requestedAt': '2026-10-12T15:40:00Z', 'backfill': 9})
        self.run_once(Remote(routes()), NOW+dt.timedelta(minutes=30), backfill=3)
        self.assertEqual(self.last_run()['backfill'], 9)
        self.enable()
        self.run_once(Remote(routes()), NOW+dt.timedelta(hours=7), backfill=20)
        self.assertEqual((self.last_run()['trigger'], self.last_run()['backfill']), ('timer', 20))

    def test_bad_requests_are_recorded_and_moved_without_fetching(self):
        self.enable()
        bad = [{'requestedAt': 'x', 'backfill': True}, {'requestedAt': 'x', 'backfill': -1}, {'requestedAt': 'x', 'backfill': 94},
               {'requestedAt': 'x', 'backfill': '3'}, {'requestedAt': 'x', 'backfill': 3, 'force': True}, {'requestedAt': 'x'},
               {'requestedAt': 7, 'backfill': 1}, [3], b'{not json', b'{"backfill": 1, "requestedAt": "' + b'x'*5000 + b'"}']
        for index, body in enumerate(bad):
            with self.subTest(body=str(body)[:40]):
                self.request(body)
                remote = Remote(routes())
                summary = self.run_once(remote, NOW+dt.timedelta(seconds=index))
                self.assertEqual(remote.urls, [])
                self.assertEqual((summary['trigger'], summary['outcome']), ('request', 'bad-request'))
                self.assertEqual((self.last_run()['outcome'], self.last_run()['trigger']), ('bad-request', 'request'))
                self.assertFalse((self.folder/'request.json').exists())
                self.assertEqual(len(self.history()), index+1)
        self.assertEqual(self.history()[-1].read_bytes()[:30], bad[-1][:30])

    def test_last_run_never_holds_tokens_bodies_or_exception_text(self):
        self.post('instagram', '1789')
        self.post('threads', '555', episode='ep02')
        self.enable()
        threads = lambda url: (_ for _ in ()).throw(PublishError('authorization'))
        self.run_once(Remote(routes(threads)))
        text = (self.folder/'last-run.json').read_text()
        self.assertEqual(json.loads(text)['platforms']['threads']['status'], 'authorization')
        for secret in (TOKEN, BODY, 'graph.instagram.com', 'https://'):
            self.assertNotIn(secret, text)
        broken = routes()
        broken['/insights'] = RuntimeError(f'boom {TOKEN} {BODY}')
        with self.assertRaises(RuntimeError):
            self.run_once(Remote(broken), NOW+dt.timedelta(hours=30))
        text = (self.folder/'last-run.json').read_text()
        self.assertEqual(json.loads(text)['outcome'], 'error')
        for secret in (TOKEN, BODY, 'boom', 'RuntimeError'):
            self.assertNotIn(secret, text)

    def test_platforms_without_reads_carry_over_previous_status(self):
        self.enable()
        threads = lambda url: (_ for _ in ()).throw(PublishError('authorization'))
        self.run_once(Remote(routes(threads)))
        self.assertEqual(self.last_run()['platforms']['threads']['status'], 'authorization')
        remote = Remote(routes())
        self.run_once(remote, NOW+dt.timedelta(hours=1))   # nothing due within 6 h
        self.assertEqual(remote.urls, [])
        platforms = self.last_run()['platforms']
        self.assertEqual(platforms['threads'], {'status': 'authorization', 'postsRead': 0, 'accountsRead': 0, 'reason': None})
        self.assertEqual(platforms['instagram'], {'status': 'ok', 'postsRead': 0, 'accountsRead': 0, 'reason': None})
        (self.folder/'enabled').unlink()
        self.run_once(remote, NOW+dt.timedelta(hours=2))
        self.assertEqual(self.last_run()['platforms'], platforms)   # stats-off keeps them, zero reads
        self.request({'requestedAt': 'x', 'backfill': 100})
        self.run_once(remote, NOW+dt.timedelta(hours=3))
        self.assertEqual(self.last_run()['platforms'], platforms)
        (self.folder/'last-run.json').unlink()   # no previous run: the stored account statuses
        self.enable()
        self.run_once(remote, NOW+dt.timedelta(hours=4))
        self.assertEqual({p: e['status'] for p, e in self.last_run()['platforms'].items()},
                         {'instagram': 'ok', 'threads': 'authorization'})

    def test_status_is_the_worst_read_and_buffer_ids_get_a_reason(self):
        self.post('instagram', 'buffer-6702', episode='ep01')
        self.post('threads', '555', episode='ep02')
        self.post('x', 'buffer-x', episode='ep03')
        self.enable()
        remote = routes()
        remote['/insights'] = PublishError('rejected')
        self.run_once(Remote(remote))
        platforms = self.last_run()['platforms']
        self.assertEqual(platforms['instagram'], {'status': 'rejected', 'postsRead': 0, 'accountsRead': 5, 'reason': 'buffer'})
        self.assertEqual(platforms['threads'], {'status': 'rejected', 'postsRead': 0, 'accountsRead': 5, 'reason': None})
        self.assertEqual(platforms['x'], {'status': 'rejected', 'postsRead': 0, 'accountsRead': 0, 'reason': None})   # not a Buffer id
        self.assertEqual([metrics.RUN_STATUS.get(s, 'error') for s in ('not_configured', 'uncertain', 'rate_limit', 'gone')],
                         ['not-configured', 'error', 'error', 'error'])

    def test_history_keeps_the_newest_200_files(self):
        history = self.folder/'history'
        history.mkdir(parents=True)
        for minute in range(205):
            stamp = (NOW-dt.timedelta(days=1, minutes=minute)).strftime('%Y%m%dT%H%M%SZ')
            (history/f"{'switch' if minute % 2 else 'request'}-{stamp}-abcdef.json").write_text('{}')
        (history/'notes.txt').write_text('kept')
        self.request({'requestedAt': 'x', 'backfill': 0})
        self.run_once(Remote(routes()))
        names = sorted(p.name for p in history.iterdir())
        self.assertEqual(len(names), 201)
        self.assertIn('notes.txt', names)
        at = lambda minute: (NOW-dt.timedelta(days=1, minutes=minute)).strftime('%Y%m%dT%H%M%SZ')
        self.assertIn(f'request-{at(198)}-abcdef.json', names)   # oldest kept: 199 seeded + the new request = 200
        self.assertNotIn(f'switch-{at(199)}-abcdef.json', names)
        self.assertIn(f'switch-{at(197)}-abcdef.json', names)
        self.assertEqual(len([n for n in names if n.startswith('request-20261012T150000Z-')]), 1)

    def test_instagram_follows_are_split_by_follow_type(self):
        shape = {'data': [{'name': 'follows_and_unfollows', 'period': 'day',
                           'total_value': {'value': 9, 'breakdowns': [{'dimension_keys': ['follow_type'], 'results': [
                               {'dimension_values': ['FOLLOWER'], 'value': 7}, {'dimension_values': ['NON_FOLLOWER'], 'value': 2},
                               {'dimension_values': ['bad key!'], 'value': 1}, {'dimension_values': ['UNKNOWN'], 'value': 'x'}]}]}}]}
        self.assertEqual(metrics.insight_values(shape), {'follows_and_unfollows': 9, 'follows_and_unfollows.FOLLOWER': 7,
                                                         'follows_and_unfollows.NON_FOLLOWER': 2})
        remote = Remote({'v26.0/me/insights': lambda url: shape if metric_of(url) == 'follows_and_unfollows' else {'data': []}})
        values = metrics.account_day('instagram', dt.date(2026, 10, 11), NY, remote, tokens, {})
        self.assertEqual(values['follows_and_unfollows.FOLLOWER'], 7)
        breakdowns = {metric_of(u): urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).get('breakdown') for u in remote.urls}
        self.assertEqual(breakdowns.pop('follows_and_unfollows'), ['follow_type'])
        self.assertEqual(set(breakdowns.values()), {None})
        for url in remote.urls:
            parts = urllib.parse.urlsplit(url)
            self.assertRegex(parts.path, metrics.ALLOWED[parts.hostname])


class FunnelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.store = metrics.Store(self.state/'metrics.sqlite3')
        self.jobs = []

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def job(self, episode, platform, published, status='confirmed', snap=None, remote_id='1'):
        job = {'id': f'{episode}-{platform}-{len(self.jobs)}', 'episode': episode, 'platform': platform, 'status': status,
               'remote_id': remote_id, 'permalink': None, 'published_at': published.isoformat(), 'dispatched_at': None}
        self.jobs.append(job)
        for checkpoint, state, values in snap or ():
            self.store.put(job, checkpoint, published, state, values)
        return job

    def account(self, platform, day, values):
        self.store.put_account(platform, day, 'day', PUBLISHED, 'ok', values)

    def test_rows_totals_sources_and_nulls(self):
        day, before = dt.date(2026, 10, 12), dt.date(2026, 10, 11)
        self.job('ep01', 'instagram', PUBLISHED, snap=[
            ('1h', 'ok', {'impressions': 40, 'engagements': 2}),
            ('24h', 'ok', {'impressions': 100, 'engagements': 10, 'ig_reels_avg_watch_time': 8400, 'answers.A': 2, 'answers.B': 1}),
            ('72h', 'authorization', None)])
        self.job('ep01', 'facebook', PUBLISHED, snap=[('24h', 'ok', {'impressions': 50, 'engagements': 5,
                                                                     'total_video_avg_time_watched': 4000})])
        self.job('ep01', 'threads', PUBLISHED, snap=[('24h', 'authorization', None)])
        self.job('ep01', 'x', PUBLISHED, snap=[('24h', 'unsupported', None)])
        self.job('ep01', 'tiktok', PUBLISHED)
        self.job('ep02', 'tiktok', PUBLISHED-dt.timedelta(days=1), snap=[('24h', 'ok', {'impressions': 120, 'engagements': 12,
                                                                                         'avg_watch_seconds': 6.4})])
        self.job('ep01', 'bluesky', PUBLISHED+dt.timedelta(days=1))
        self.job('ep01#comment', 'instagram', PUBLISHED, snap=[('24h', 'ok', {'impressions': 999})])
        self.job('ep09', 'instagram', PUBLISHED, status='failed', snap=[('24h', 'ok', {'impressions': 999})])
        self.account('instagram', day, {'follows_and_unfollows.FOLLOWER': 3, 'follows_and_unfollows.NON_FOLLOWER': 9,
                                        'followers': 500})
        self.account('instagram', before, {'followers': 400})
        self.account('facebook', day, {'page_daily_follows_unique': 2})
        self.account('threads', day, {'followers': 50})
        self.account('threads', before, {'followers': 47})
        self.account('bluesky', day+dt.timedelta(days=1), {'followers': 15})   # no row for the day before
        self.account('x', day, {'followers': 5})
        rows = metrics.funnel(self.state, self.jobs, NY)
        self.assertEqual([r['episode'] for r in rows], ['ep01', 'ep02'])
        # TikTok through Buffer: seconds as reported, answers unknown (Buffer gives no comment text), never 0.
        self.assertEqual(rows[1]['platforms']['tiktok'], {'status': 'ok', 'views': 120, 'engaged': 12, 'answered': None,
                                                          'avgWatchSeconds': 6.4, 'followsThatDay': None, 'followsSource': None})
        row = rows[0]
        self.assertEqual(row['publishedDates'], ['2026-10-12', '2026-10-13'])
        p = row['platforms']
        self.assertEqual(list(p), ['bluesky', 'facebook', 'instagram', 'threads', 'tiktok', 'x'])
        self.assertEqual(p['instagram'], {'status': 'ok', 'views': 100, 'engaged': 10, 'answered': 3, 'avgWatchSeconds': 8.4,
                                          'followsThatDay': 3, 'followsSource': 'day-metric'})
        self.assertEqual(p['facebook'], {'status': 'ok', 'views': 50, 'engaged': 5, 'answered': 0, 'avgWatchSeconds': 4.0,
                                         'followsThatDay': 2, 'followsSource': 'day-metric'})
        self.assertEqual(p['threads'], {'status': 'authorization', 'views': None, 'engaged': None, 'answered': None,
                                        'avgWatchSeconds': None, 'followsThatDay': 3, 'followsSource': 'follower-change'})
        empty = dict.fromkeys(('views', 'engaged', 'answered', 'avgWatchSeconds', 'followsThatDay', 'followsSource'))
        self.assertEqual(p['bluesky'], {'status': None, **empty})
        self.assertEqual(p['x'], {'status': 'unsupported', **empty})
        self.assertEqual(p['tiktok'], {'status': None, **empty})
        self.assertEqual({k: row[k] for k in metrics.FUNNEL_KEYS},
                         {'views': 150, 'engaged': 15, 'answered': 3, 'avgWatchSeconds': 6.9, 'followsThatDay': 8})
        self.assertEqual(row['counted'], {'views': ['facebook', 'instagram'], 'engaged': ['facebook', 'instagram'],
                                          'answered': ['facebook', 'instagram'], 'avgWatchSeconds': ['facebook', 'instagram'],
                                          'followsThatDay': ['facebook', 'instagram', 'threads']})

    def test_fallbacks_plain_mean_newest_post_order_and_limit(self):
        later = PUBLISHED+dt.timedelta(days=2)
        self.job('ep02', 'instagram', later, snap=[('24h', 'ok', {'ig_reels_avg_watch_time': 3000})])   # no views
        self.job('ep02', 'facebook', later, snap=[('24h', 'ok', {'impressions': 10, 'post_video_avg_time_watched': 5000})])
        self.job('ep02', 'youtube', later, snap=[('24h', 'ok', {'impressions': 7})])
        self.job('ep02', 'youtube', later-dt.timedelta(hours=5), snap=[('24h', 'ok', {'impressions': 70000})])   # older duplicate
        self.account('instagram', dt.date(2026, 10, 14), {'followers': 130})   # no day metric: follower change
        self.account('instagram', dt.date(2026, 10, 13), {'followers': 120})
        self.account('youtube', dt.date(2026, 10, 14), {'followers': 40})
        self.account('youtube', dt.date(2026, 10, 13), {'followers': 42})
        self.job('ep01', 'bluesky', PUBLISHED, snap=[('24h', 'ok', {'engagements': 4})])
        self.job('ep00', 'threads', dt.datetime(2026, 10, 12, 2, tzinfo=UTC))   # 22:00 the evening before in New York
        rows = metrics.funnel(self.state, self.jobs, NY)
        self.assertEqual([r['episode'] for r in rows], ['ep02', 'ep01', 'ep00'])
        ep02 = rows[0]
        self.assertEqual(ep02['avgWatchSeconds'], 4.0)   # instagram has no views: plain mean
        self.assertEqual(ep02['platforms']['youtube']['views'], 7)
        self.assertEqual(ep02['views'], 17)
        self.assertEqual((ep02['platforms']['instagram']['followsThatDay'], ep02['platforms']['instagram']['followsSource']),
                         (10, 'follower-change'))
        self.assertEqual((ep02['platforms']['youtube']['followsThatDay'], ep02['followsThatDay']), (-2, 8))
        self.assertEqual(ep02['publishedDates'], ['2026-10-14'])
        self.assertEqual((rows[1]['answered'], rows[1]['views'], rows[1]['counted']['views']), (0, None, []))
        self.assertEqual(rows[2]['publishedDates'], ['2026-10-11'])
        self.assertEqual([r['episode'] for r in metrics.funnel(self.state, self.jobs, NY, limit=2)], ['ep02', 'ep01'])

    def test_missing_store_gives_null_rows(self):
        self.job('ep01', 'instagram', PUBLISHED)
        rows = metrics.funnel(self.state/'none', self.jobs, NY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['platforms']['instagram'],
                         {'status': None, **dict.fromkeys(('views', 'engaged', 'answered', 'avgWatchSeconds', 'followsThatDay',
                                                           'followsSource'))})
        self.assertEqual(({k: rows[0][k] for k in metrics.FUNNEL_KEYS}, rows[0]['publishedDates']),
                         (dict.fromkeys(metrics.FUNNEL_KEYS), ['2026-10-12']))
        self.assertEqual(metrics.funnel(self.state/'none', [], NY), [])


if __name__ == '__main__':
    unittest.main()
