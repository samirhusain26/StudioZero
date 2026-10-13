import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
import metrics
from buffer_adapter import PublishError
from runner import Ledger
from fixture_ids import IDENTITIES

UTC = dt.timezone.utc
PUBLISHED = dt.datetime(2026, 10, 12, 13, tzinfo=UTC)
BLUESKY_URI = 'at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/app.bsky.feed.post/3abc'


class Remote:
    """Fake transport keyed on the URL path suffix; records every URL."""

    def __init__(self, routes):
        self.routes, self.urls = routes, []

    def __call__(self, url, headers=None, body=None):
        self.urls.append(url)
        if body is not None:   # Buffer GraphQL POST: answered by the 'graphql' route
            self.bodies = getattr(self, 'bodies', []) + [(headers, body)]
            answer = self.routes['graphql']
            if isinstance(answer, Exception):
                raise answer
            return answer(body) if callable(answer) else answer
        path = urllib.parse.urlsplit(url).path
        for suffix, answer in self.routes.items():
            if path.endswith(suffix):
                if isinstance(answer, Exception):
                    raise answer
                return answer(url) if callable(answer) else answer
        raise AssertionError('unexpected '+url)


def tokens(platform):
    return 'token-'+platform


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name)/'ledger.sqlite3')
        self.store = metrics.Store(Path(self.tmp.name)/'metrics.sqlite3')
        self.config = {'identities': IDENTITIES, 'channels': {'threads': {'profileUrl': 'https://www.threads.com/@studiozeroflow'}}}

    def tearDown(self):
        self.ledger.db.close()
        self.store.db.close()
        self.tmp.cleanup()

    def post(self, platform, remote_id, permalink='https://example.invalid/p', episode='ep01', slot=None):
        key = self.ledger.enqueue(platform, 'acct', slot or PUBLISHED.isoformat()+platform+episode, {'episode': {'id': episode}})
        self.ledger.update(key, 'confirmed', remote_id=remote_id, permalink=permalink, published_at=PUBLISHED.isoformat())
        return key

    def collect(self, remote, hours):
        return metrics.collect(self.ledger.db, self.store, self.config, PUBLISHED+dt.timedelta(hours=hours), remote, tokens)

    def test_checkpoints_fetch_newest_due_once(self):
        self.assertIsNone(metrics.due(PUBLISHED, PUBLISHED+dt.timedelta(minutes=59)))
        self.assertEqual(metrics.due(PUBLISHED, PUBLISHED+dt.timedelta(hours=30)), '24h')
        self.assertEqual(metrics.due(PUBLISHED, PUBLISHED+dt.timedelta(days=8)), '7d')
        self.assertEqual(metrics.due(PUBLISHED, PUBLISHED+dt.timedelta(days=31)), '30d')
        self.assertIsNone(metrics.due(PUBLISHED, PUBLISHED+dt.timedelta(days=46)))
        key = self.post('instagram', '1789')
        remote = Remote({'/insights': {'data': [{'name': 'views', 'values': [{'value': 120}]}]}, '/comments': {'data': []}})
        self.assertEqual(self.collect(remote, 0.5), {})
        self.assertEqual(self.collect(remote, 2), {'instagram': {'ok': 1}})
        self.assertEqual(self.collect(remote, 3), {})
        self.assertEqual(self.collect(remote, 25), {'instagram': {'ok': 1}})
        self.assertEqual(len([u for u in remote.urls if '/insights' in u]), 2)
        snap = metrics.latest(self.tmp.name, [key])[key]
        self.assertEqual((snap['checkpoint'], snap['status'], snap['values']), ('24h', 'ok', {'views': 120, 'impressions': 120}))

    def test_instagram_insights_answers_and_fallback(self):
        key = self.post('instagram', '1789')
        insights = {'data': [{'name': 'views', 'values': [{'value': 300}]}, {'name': 'reach', 'values': [{'value': 210}]},
                             {'name': 'ig_reels_avg_watch_time', 'values': [{'value': 8400}]}]}
        calls = []

        def answer(url):
            calls.append(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['metric'][0])
            if len(calls) == 1:
                raise PublishError('rejected')
            return insights
        comments = {'data': [{'username': 'ana', 'text': 'B'}, {'username': 'ana', 'text': 'C'}, {'username': 'bo', 'text': 'b) Canada!'},
                             {'username': 'cy', 'text': 'A great puzzle'}, {'username': 'di', 'text': 'C 🎉'},
                             {'username': 'studiozeroflow', 'text': 'A'}]}
        self.collect(Remote({'/insights': answer, '/comments': comments}), 2)
        self.assertEqual(calls, [metrics.INSTAGRAM_METRICS, metrics.INSTAGRAM_CORE])
        values = metrics.latest(self.tmp.name, [key])[key]['values']
        self.assertEqual(values, {'views': 300, 'reach': 210, 'ig_reels_avg_watch_time': 8400, 'answers.B': 2, 'answers.C': 1,
                                  'impressions': 300})

    def test_missing_permission_is_stored_and_not_retried_but_network_is(self):
        threads = self.post('threads', '555')
        self.collect(Remote({'/insights': PublishError('authorization')}), 2)
        self.assertEqual(metrics.latest(self.tmp.name, [threads])[threads]['status'], 'authorization')
        remote = Remote({'/insights': PublishError('authorization')})
        self.collect(remote, 3)
        self.assertEqual(remote.urls, [])
        facebook = self.post('facebook', '777', episode='ep02')
        self.collect(Remote({'/video_insights': PublishError('uncertain')}), 2)
        remote = Remote({'/video_insights': {'data': [{'name': 'blue_reels_play_count', 'values': [{'value': 40}]},
                                                      {'name': 'post_video_social_actions', 'values': [{'value': {'like': 3, 'comment': 1}}]}]},
                         '/comments': PublishError('authorization')})
        self.collect(remote, 3)
        self.assertEqual(metrics.latest(self.tmp.name, [facebook])[facebook]['values'],
                         {'blue_reels_play_count': 40, 'post_video_social_actions.comment': 1, 'post_video_social_actions.like': 3,
                          'impressions': 40, 'engagements': 4, 'engagement_rate': 0.1})

    def test_facebook_reel_reactions_count_as_engagements(self):
        facebook = self.post('facebook', '777', episode='ep02')
        self.collect(Remote({'/video_insights': {'data': [
            {'name': 'blue_reels_play_count', 'values': [{'value': 188}]},
            {'name': 'post_video_likes_by_reaction_type', 'values': [{'value': {'REACTION_LIKE': 1, 'REACTION_LOVE': 1}}]}]},
            '/comments': {'data': []}}), 2)
        values = metrics.latest(self.tmp.name, [facebook])[facebook]['values']
        self.assertEqual((values['engagements'], values['engagement_rate']), (2, 0.0106))

    def test_threads_skips_own_reply(self):
        key = self.post('threads', '555')
        self.collect(Remote({'/insights': {'data': [{'name': 'views', 'values': [{'value': 9}]}]},
                             '/replies': {'data': [{'username': 'studiozeroflow', 'text': 'A) Spain'}, {'username': 'x1', 'text': 'a'}]}}), 2)
        self.assertEqual(metrics.latest(self.tmp.name, [key])[key]['values'], {'views': 9, 'answers.A': 1, 'impressions': 9})

    def test_bluesky_public_counts_and_replies(self):
        key = self.post('bluesky', BLUESKY_URI)
        own = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
        thread = {'thread': {'replies': [{'post': {'author': {'did': own}, 'record': {'text': 'A'}}},
                                         {'post': {'author': {'did': 'did:plc:other'}, 'record': {'text': 'D!'}}}]}}
        remote = Remote({'getPosts': {'posts': [{'likeCount': 4, 'repostCount': 1, 'replyCount': 2, 'quoteCount': 0}]},
                         'getPostThread': thread})
        self.collect(remote, 2)
        self.assertTrue(all(u.startswith('https://public.api.bsky.app/xrpc/') for u in remote.urls))
        self.assertEqual(metrics.latest(self.tmp.name, [key])[key]['values'],
                         {'likes': 4, 'reposts': 1, 'replies': 2, 'quotes': 0, 'answers.D': 1, 'engagements': 7})

    def test_youtube_statistics_from_permalink(self):
        self.assertEqual(metrics.youtube_id('https://youtube.com/shorts/abcDEF12345'), 'abcDEF12345')
        self.assertEqual(metrics.youtube_id('https://www.youtube.com/watch?v=abcDEF12345'), 'abcDEF12345')
        self.assertIsNone(metrics.youtube_id('https://evil.example/shorts/abcDEF12345'))
        key = self.post('youtube', 'buffer-post-1', permalink='https://youtube.com/shorts/abcDEF12345')
        remote = Remote({'/videos': {'items': [{'statistics': {'viewCount': '1500', 'likeCount': '30', 'commentCount': '2'}}]},
                         '/commentThreads': {'items': [{'snippet': {'topLevelComment': {'snippet': {'authorChannelId': {'value': 'U1'},
                                                                                                    'textOriginal': 'B'}}}}]}})
        self.collect(remote, 2)
        self.assertIn('key=token-youtube', remote.urls[0])
        self.assertEqual(metrics.latest(self.tmp.name, [key])[key]['values'], {'views': 1500, 'likes': 30, 'comments': 2, 'answers.B': 1,
                                                                                 'impressions': 1500, 'engagements': 32, 'engagement_rate': 0.0213})

    def test_bad_buffer_id_and_companions(self):
        x = self.post('x', 'buffer-x')
        self.post('instagram', '999', episode='ep01#comment')
        self.assertEqual(self.collect(Remote({}), 2), {'x': {'rejected': 1}})   # no request for an id Buffer never issued
        self.assertEqual(metrics.latest(self.tmp.name, [x])[x]['status'], 'rejected')

    def test_tiktok_and_x_metrics_from_buffer(self):
        tiktok, x = self.post('tiktok', 'a'*24, episode='ep01'), self.post('x', 'b'*24, episode='ep02')
        sent = PUBLISHED.isoformat().replace('+00:00', 'Z')
        answers = {'a'*24: [{'type': 'views', 'unit': 'count', 'value': 120}, {'type': 'reactions', 'unit': 'count', 'value': 9},
                            {'type': 'comments', 'unit': 'count', 'value': 2}, {'type': 'shares', 'unit': 'count', 'value': 1},
                            {'type': 'engagementRate', 'unit': 'percentage', 'value': 10}, {'type': 'reach', 'unit': 'count', 'value': 100},
                            {'type': 'averageTimeWatched', 'unit': 'count', 'value': 6.25}, {'type': 'totalTimeWatched', 'unit': 'count', 'value': 12},
                            {'type': 'newThing', 'unit': 'count', 'value': 4}, {'type': 'bad key!', 'unit': 'count', 'value': 4}],
                   'b'*24: [{'type': 'impressions', 'unit': 'count', 'value': 40}, {'type': 'reposts', 'unit': 'count', 'value': 1},
                            {'type': 'clicks', 'unit': 'count', 'value': 3}]}
        remote = Remote({'graphql': lambda body: {'data': {'post': {
            'id': body['variables']['input']['id'], 'status': 'sent', 'sentAt': sent,
            'metricsUpdatedAt': (PUBLISHED+dt.timedelta(hours=1)).isoformat(), 'metrics': answers[body['variables']['input']['id']]}}}})
        self.assertEqual(self.collect(remote, 2), {'tiktok': {'ok': 1}, 'x': {'ok': 1}})
        self.assertEqual(remote.urls, ['https://api.buffer.com']*2)
        self.assertEqual(remote.bodies[0][0], {'Authorization': 'Bearer token-buffer'})
        self.assertEqual(metrics.latest(self.tmp.name, [tiktok])[tiktok]['values'],
                         {'views': 120, 'likes': 9, 'comments': 2, 'shares': 1, 'reach': 100, 'avg_watch_seconds': 6.25,
                          'total_watch_minutes': 12, 'buffer.newThing': 4, 'impressions': 120, 'engagements': 12, 'engagement_rate': 0.1})
        self.assertEqual(metrics.latest(self.tmp.name, [x])[x]['values'],
                         {'post_impressions': 40, 'reposts': 1, 'clicks': 3, 'impressions': 40, 'engagements': 1, 'engagement_rate': 0.025})

    def test_a_read_stored_as_unsupported_is_read_again_once_supported(self):
        key = self.post('tiktok', 'e'*24)
        self.store.put(dict(id=key, platform='tiktok', remote_id='e'*24), '1h', PUBLISHED+dt.timedelta(hours=1), 'unsupported')
        remote = Remote({'graphql': {'data': {'post': {'id': 'e'*24, 'status': 'sent', 'sentAt': PUBLISHED.isoformat(),
                                                       'metricsUpdatedAt': (PUBLISHED+dt.timedelta(hours=1)).isoformat(),
                                                       'metrics': [{'type': 'views', 'unit': 'count', 'value': 7}]}}}})
        self.assertEqual(self.collect(remote, 2), {'tiktok': {'ok': 1}})
        self.assertEqual(metrics.latest(self.tmp.name, [key])[key]['values']['views'], 7)

    def test_buffer_post_not_read_yet_is_pending_and_retried(self):
        key = self.post('tiktok', 'c'*24)
        state = {'updated': (PUBLISHED-dt.timedelta(minutes=1)).isoformat()}   # Buffer's daily read ran before the post
        remote = Remote({'graphql': lambda body: {'data': {'post': {
            'id': 'c'*24, 'status': 'sent', 'sentAt': PUBLISHED.isoformat(), 'metricsUpdatedAt': state['updated'],
            'metrics': [{'type': 'views', 'unit': 'count', 'value': 0}]}}}})
        self.assertEqual(self.collect(remote, 2), {'tiktok': {'pending': 1}})
        self.assertEqual(metrics.RUN_STATUS['pending'], 'ok')
        state['updated'] = (PUBLISHED+dt.timedelta(hours=2)).isoformat()
        self.assertEqual(self.collect(remote, 3), {'tiktok': {'ok': 1}})   # same 1h checkpoint, read again
        self.assertEqual(metrics.latest(self.tmp.name, [key])[key]['values']['views'], 0)

    def test_buffer_errors(self):
        self.post('tiktok', 'd'*24)
        unauth = Remote({'graphql': {'errors': [{'message': 'secret text', 'extensions': {'code': 'UNAUTHENTICATED'}}]}})
        self.assertEqual(self.collect(unauth, 2), {'tiktok': {'authorization': 1}})
        missing = Remote({'graphql': {'data': {'post': None}}})
        self.assertEqual(self.collect(missing, 30), {'tiktok': {'gone': 1}})
        with patch.dict('os.environ', {'CREDENTIALS_DIRECTORY': self.tmp.name}):
            with self.assertRaises(PublishError) as raised:
                metrics.credential('buffer')
            self.assertEqual(raised.exception.category, 'not_configured')
            Path(self.tmp.name, 'BUFFER_API_KEY').write_text('b\n')
            self.assertEqual(metrics.credential('buffer'), 'b')

    def test_missing_youtube_key_is_not_configured(self):
        with patch.dict('os.environ', {'CREDENTIALS_DIRECTORY': self.tmp.name}):
            with self.assertRaises(PublishError) as raised:
                metrics.credential('youtube')
            self.assertEqual(raised.exception.category, 'not_configured')
            Path(self.tmp.name, 'YOUTUBE_API_KEY').write_text('k\n')
            self.assertEqual(metrics.credential('youtube'), 'k')

    def test_transport_allowlist_and_error_categories(self):
        for url in ('http://graph.instagram.com/v26.0/1/insights', 'https://graph.instagram.com/v26.0/me/media',
                    'https://evil.example/v26.0/1/insights', 'https://graph.facebook.com/v26.0/1/feed'):
            with self.assertRaises(PublishError) as raised:
                metrics.get(url)
            self.assertEqual(raised.exception.category, 'rejected')
        cases = ((429, b'{}', 'rate_limit'), (403, b'{}', 'authorization'), (404, b'{}', 'gone'),
                 (400, b'{"error":{"code":10}}', 'authorization'), (400, b'{"error":{"code":100}}', 'rejected'),
                 (500, b'{}', 'uncertain'))
        for code, body, category in cases:
            error = urllib.error.HTTPError('u', code, 'x', {}, io.BytesIO(body))
            with patch('metrics.urllib.request.urlopen', side_effect=error), self.assertRaises(PublishError) as raised:
                metrics.get('https://graph.threads.net/v1.0/5/insights?metric=views')
            self.assertEqual(raised.exception.category, category)

    def config_accounts(self):
        verified = {'identityVerified': True}
        return {'timezone': 'America/New_York', 'identities': IDENTITIES,
                'channels': {'instagram': {**verified, 'route': 'instagram'}, 'threads': verified, 'facebook': verified,
                             'bluesky': verified, 'youtube': verified, 'x': verified}}

    def account_remote(self):
        def instagram_day(url):
            metric = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['metric'][0]
            if metric == 'profile_links_taps':
                raise PublishError('rejected')   # a retired metric only loses itself
            return {'data': [{'name': metric, 'total_value': {'value': {'views': 900, 'reach': 400, 'total_interactions': 45}.get(metric, 1)}}]}

        def threads(url):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            if query['metric'][0] == 'followers_count':
                return {'data': [{'name': 'followers_count', 'total_value': {'value': 88}}]}
            until = dt.datetime.fromtimestamp(int(query['until'][0]), UTC)
            # Pacific-day series: the day before ends inside our day, ours ends 3 h after it.
            series = [{'value': 5, 'end_time': (until-dt.timedelta(hours=21)).strftime('%Y-%m-%dT%H:%M:%S+0000')},
                      {'value': 7, 'end_time': (until+dt.timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S+0000')}]
            return {'data': [{'name': query['metric'][0], 'values': series}]}
        return Remote({'v26.0/me/insights': instagram_day, 'v26.0/me': {'followers_count': 120, 'follows_count': 3, 'media_count': 9},
                       'threads_insights': threads, '/insights': PublishError('authorization'),
                       'v26.0/1000000000000002': PublishError('authorization'),
                       'getProfile': {'followersCount': 15, 'followsCount': 2, 'postsCount': 30},
                       '/channels': {'items': [{'statistics': {'subscriberCount': '40', 'viewCount': '5000', 'videoCount': '12'}}]}})

    def test_account_log_daily_totals_and_point_in_time_counts(self):
        config, remote = self.config_accounts(), self.account_remote()
        now = dt.datetime(2026, 10, 20, 14, tzinfo=UTC)   # 10:00 in New York
        summary = metrics.collect_accounts(self.store, config, now, remote, tokens)
        self.assertNotIn('x', summary)
        self.assertEqual(summary['facebook'], {'authorization': 5})
        ig = json.loads(self.store.account('instagram', dt.date(2026, 10, 19))['metrics'])
        self.assertEqual((ig['views'], ig['reach'], ig['impressions'], ig['engagements']), (900, 400, 900, 45))
        self.assertNotIn('profile_links_taps', ig)
        self.assertEqual(json.loads(self.store.account('instagram', dt.date(2026, 10, 20))['metrics'])['followers'], 120)
        threads = json.loads(self.store.account('threads', dt.date(2026, 10, 19))['metrics'])
        self.assertEqual((threads['views'], threads['likes'], threads['engagements']), (7, 7, 28))
        self.assertEqual(json.loads(self.store.account('youtube', dt.date(2026, 10, 20))['metrics']),
                         {'followers': 40, 'channel_views': 5000, 'posts': 12})
        self.assertEqual(json.loads(self.store.account('bluesky', dt.date(2026, 10, 20))['metrics'])['followers'], 15)
        calls = len(remote.urls)
        metrics.collect_accounts(self.store, config, now+dt.timedelta(hours=1), remote, tokens)
        self.assertEqual(len(remote.urls), calls)   # nothing re-read within 6 hours
        metrics.collect_accounts(self.store, config, now+dt.timedelta(hours=7), remote, tokens)
        self.assertGreater(len(remote.urls), calls)

    def test_settled_days_are_final_and_backfill_reads_older_days(self):
        config, remote = self.config_accounts(), self.account_remote()
        now = dt.datetime(2026, 10, 20, 14, tzinfo=UTC)
        metrics.collect_accounts(self.store, config, now, remote, tokens, backfill=10)
        self.assertIsNotNone(self.store.account('instagram', dt.date(2026, 10, 10)))
        later = now+dt.timedelta(days=5)
        before = len(remote.urls)
        metrics.collect_accounts(self.store, config, later, remote, tokens, backfill=10)
        days = {urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).get('since', [''])[0] for u in remote.urls[before:] if 'me/insights' in u}
        start = lambda d: str(int(dt.datetime.combine(d, dt.time(), metrics.ZoneInfo('America/New_York')).timestamp()))
        self.assertNotIn(start(dt.date(2026, 10, 10)), days)   # read after it settled: final
        self.assertIn(start(dt.date(2026, 10, 24)), days)

    def test_account_summary_and_export(self):
        config, remote = self.config_accounts(), self.account_remote()
        for day in range(14, 21):
            metrics.collect_accounts(self.store, config, dt.datetime(2026, 10, day, 14, tzinfo=UTC), remote, tokens)
        self.store.put_account('instagram', dt.date(2026, 10, 13), 'now', dt.datetime(2026, 10, 13, 14, tzinfo=UTC), 'ok', {'followers': 100})
        summary = {a['platform']: a for a in metrics.account_summary(self.tmp.name, dt.date(2026, 10, 20))}
        ig = summary['instagram']
        self.assertEqual((ig['followers'], ig['followersChange'], ig['days'], ig['status']), (120, 20, 7, 'ok'))
        self.assertEqual(ig['totals'], {'impressions': 6300, 'engagements': 315, 'engagement_rate': 0.05})
        self.assertEqual(summary['facebook']['status'], 'authorization')
        out = io.StringIO()
        metrics.export(self.tmp.name, 'accounts', out)
        header = out.getvalue().splitlines()[0].split(',')
        self.assertEqual(header[:6], ['platform', 'day', 'day_status', 'day_fetched_at', 'now_status', 'now_fetched_at'])
        self.assertIn('followers', header)

    def test_latest_without_store_is_empty(self):
        self.assertEqual(metrics.latest(Path(self.tmp.name)/'none', ['a']), {})


if __name__ == '__main__':
    unittest.main()
