"""Read-only performance collector for posts and accounts. Never publishes and never writes the ledger.

Posts: each confirmed post (companions excluded) is read at fixed ages after publishing: 1 h, 24 h, 72 h, 7 and
30 days. Only the newest due checkpoint is fetched, so a Pi that was off catches up with one late read. A failed
read is stored with its category; transient ones (uncertain, rate_limit) are retried on the next run in the window.

Accounts: one row per platform per local day (config timezone). Day totals (views, reach, engagements, link clicks)
are re-read every 6 hours until three days after the day ends, because platforms report them late; point-in-time
counts (followers, totals) go on today's row. `collect --backfill N` reads the last N days once where the platform
keeps history. Everything lives in its own SQLite file and is never pruned.

Values are what each platform reports: views are plays, not people. Derived on top: `impressions` (views or plays),
`engagements` (interactions) and `engagement_rate` (engagements / impressions). `answers.<letter>` counts one A–D
reply per commenter (the caption asks viewers to comment their letter).

Controls (STATE/metrics/, written by the UI, which has no network or tokens): hourly timer runs read only while the
`enabled` flag file exists; `request.json` asks for one manual read now ({"requestedAt", "backfill": 0-93}). A request
is moved to `history/` before any fetch, also re-reads each account's point-in-time counts, and works with the flag
off. Every run writes `last-run.json` (status per platform, counts of successful reads; never bodies or tokens).
"""
import argparse
import contextlib
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from buffer_adapter import PublishError
from identities import IdentityMissing, pin

UTC = dt.timezone.utc
CHECKPOINTS = (('1h', 3600), ('24h', 86400), ('72h', 259200), ('7d', 604800), ('30d', 2592000))
LAST_READ = 45*86400   # a post older than this is not read again
TRANSIENT = ('uncertain', 'rate_limit', 'pending')   # pending: Buffer has not read the network for this post yet
SUPPORTED = ('instagram', 'threads', 'facebook', 'bluesky', 'youtube', 'tiktok', 'x')
# Posted through Buffer: read from Buffer's Post.metrics (Free plan included; Buffer refreshes them once a day).
BUFFER_PLATFORMS = ('tiktok', 'x')
BUFFER_ID = re.compile(r'[0-9a-f]{24}')
BUFFER_QUERY = 'query($input:PostInput!){post(input:$input){id status sentAt metricsUpdatedAt metrics{type unit value}}}'
# Buffer metric type -> stored key (our vocabulary where one exists); engagementRate is ours to derive.
BUFFER_METRICS = {'views': 'views', 'impressions': 'post_impressions', 'reactions': 'likes', 'comments': 'comments',
                  'shares': 'shares', 'reposts': 'reposts', 'quotes': 'quotes', 'saves': 'saves', 'reach': 'reach',
                  'clicks': 'clicks', 'averageTimeWatched': 'avg_watch_seconds', 'totalTimeWatched': 'total_watch_minutes'}
# Fixed hosts and paths: ids are numeric (Meta), at:// URIs (Bluesky) or 11-character video ids (YouTube).
ALLOWED = {
    'graph.instagram.com': r'/v26\.0/([0-9]+/(insights|comments)|me(/insights)?)',
    'graph.threads.net': r'/v1\.0/([0-9]+/(insights|replies)|me/threads_insights)',
    'graph.facebook.com': r'/v26\.0/[0-9]+(/video_insights|/comments|/insights)?',
    'public.api.bsky.app': r'/xrpc/app\.bsky\.(feed\.(getPosts|getPostThread)|actor\.getProfile)',
    'www.googleapis.com': r'/youtube/v3/(videos|commentThreads|channels)',
    'api.buffer.com': r'/?',
}
INSTAGRAM_METRICS = ('views,reach,likes,comments,saved,shares,total_interactions,'
                     'ig_reels_avg_watch_time,ig_reels_video_view_total_time')
INSTAGRAM_CORE = 'views,reach,likes,comments,saved,shares'
THREADS_METRICS = 'views,likes,replies,reposts,quotes,shares'
THREADS_CORE = 'views,likes,replies,reposts,quotes'
# Day totals per account, one request per metric so a renamed or retired metric only loses itself.
ACCOUNT_DAY = {
    'instagram': ('views', 'reach', 'accounts_engaged', 'total_interactions', 'likes', 'comments', 'shares', 'saves',
                  'replies', 'profile_links_taps', 'follows_and_unfollows'),
    'threads': ('views', 'likes', 'replies', 'reposts', 'quotes', 'clicks'),
    'facebook': ('page_media_view', 'page_total_media_view_unique', 'page_post_engagements', 'page_daily_follows_unique'),
}
ACCOUNT_PLATFORMS = ('instagram', 'threads', 'facebook', 'bluesky', 'youtube')
ACCOUNT_REFRESH = 6*3600
ACCOUNT_SETTLE = 3*86400   # day totals are re-read until this long after the day ends
IMPRESSIONS = ('views', 'page_media_view', 'post_media_view', 'blue_reels_play_count', 'fb_reels_total_plays',
               'post_impressions')
TOTAL_ENGAGEMENT = ('total_interactions', 'page_post_engagements')
INTERACTIONS = ('likes', 'comments', 'replies', 'shares', 'saved', 'saves', 'reposts', 'quotes')
# Instagram follows_and_unfollows split by follow_type: .FOLLOWER = follows, .NON_FOLLOWER = unfollows (or left Instagram).
ACCOUNT_BREAKDOWN = {'follows_and_unfollows': 'follow_type'}
META = ('instagram', 'threads', 'facebook')   # platform ids are decimal; anything else is a Buffer-era id
REQUEST_CAP = 4096
HISTORY_KEEP = 200
HISTORY_NAME = re.compile(r'(request|switch)-([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{6}\.json')
RUN_STATUS = {'ok': 'ok', 'not_configured': 'not-configured', 'authorization': 'authorization', 'rejected': 'rejected',
              'unsupported': 'unsupported', 'pending': 'ok'}   # anything else (uncertain, rate_limit, gone, …) is 'error'
SEVERITY = ('ok', 'unsupported', 'not-configured', 'rejected', 'error', 'authorization')   # last = worst
YOUTUBE_ID = re.compile(r'[A-Za-z0-9_-]{11}')
# A reply that is just a letter (emoji or punctuation allowed after it), or a letter followed by ")".
ANSWER = re.compile(r'\W*([A-Da-d])(\)|[^A-Za-z0-9]*$)')


def get(url, headers=None, body=None):
    """GET, or with `body` a JSON POST (Buffer's GraphQL API); only the allowed hosts and paths."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or not re.fullmatch(ALLOWED.get(parts.hostname, r'(?!)'), parts.path):
        raise PublishError('rejected')
    if body is None:
        req = urllib.request.Request(url, headers=headers or {}, method='GET')
    else:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                     headers={**(headers or {}), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise PublishError('rate_limit') from None
        if error.code in (401, 403):
            raise PublishError('authorization') from None
        if error.code == 404:
            raise PublishError('gone') from None
        if error.code == 400:
            try:
                body = json.loads(error.read(65536))
            except (OSError, ValueError):
                body = {}
            code = (body.get('error') or {}).get('code') if isinstance(body.get('error'), dict) else None
            # Meta reports missing grants (e.g. *_insights) as OAuth codes on HTTP 400.
            raise PublishError('authorization' if code in (10, 190) or (isinstance(code, int) and 200 <= code < 300)
                               else 'rejected') from None
        raise PublishError('uncertain') from None
    except (OSError, ValueError):
        raise PublishError('uncertain') from None
    if not isinstance(data, dict) or data.get('error'):
        raise PublishError('uncertain')
    return data


def number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,15}', value):
        return int(value)
    return None


def stamp(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00').replace('+0000', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def insight_values(data, until=None):
    """Meta insights rows -> {name: number}; a breakdown dict becomes name.key entries.

    A daily series keeps the platform day whose end falls in the 12 hours after `until` (our local day's end), so
    a platform on Pacific or UTC days maps to the nearest local day instead of being counted twice."""
    out = {}
    for row in data.get('data') or []:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str):
            continue
        values, total = row.get('values'), row.get('total_value')
        if isinstance(values, list) and values and isinstance(values[0], dict):
            value = values[0].get('value')
            entries = [v for v in values if isinstance(v, dict)]
            if until is not None and any(stamp(v.get('end_time')) for v in entries):
                entries = [v for v in entries if (end := stamp(v.get('end_time')))
                           and until < end <= until+dt.timedelta(hours=12)]
                value = entries[0].get('value') if len(entries) == 1 else None
            elif len(entries) > 1 and all(number(v.get('value')) is not None for v in entries):
                value = sum(number(v.get('value')) for v in entries)
        else:
            value = total.get('value') if isinstance(total, dict) else None
            out.update(breakdown_values(row['name'], total))
        if isinstance(value, dict):
            for key, item in value.items():
                if number(item) is not None and re.fullmatch(r'[A-Za-z0-9_]{1,40}', str(key)):
                    out[f"{row['name']}.{key}"] = number(item)
        elif number(value) is not None:
            out[row['name']] = number(value)
    return out


def breakdown_values(name, total):
    """total_value.breakdowns over one dimension -> {name.<dimension value>: n}, e.g. follows_and_unfollows.FOLLOWER."""
    out = {}
    for breakdown in (total.get('breakdowns') if isinstance(total, dict) else None) or []:
        if not isinstance(breakdown, dict) or not isinstance(breakdown.get('dimension_keys'), list) \
                or len(breakdown['dimension_keys']) != 1:
            continue
        for result in breakdown.get('results') or []:
            keys = result.get('dimension_values') if isinstance(result, dict) else None
            if isinstance(keys, list) and len(keys) == 1 and re.fullmatch(r'[A-Za-z0-9_]{1,40}', str(keys[0])) \
                    and number(result.get('value')) is not None:
                out[f'{name}.{keys[0]}'] = number(result['value'])
    return out


def tally(replies):
    """[(author, text)] -> {'answers.A': n, …}, one answer per author (their first)."""
    seen, counts = set(), {}
    for author, text in replies:
        match = ANSWER.match(text) if isinstance(text, str) else None
        if not match or author in seen:
            continue
        seen.add(author)
        key = 'answers.'+match[1].upper()
        counts[key] = counts.get(key, 0)+1
    return counts


def query(base, path, params):
    return f'{base}/{path}?{urllib.parse.urlencode(params)}'


def bearer(token):
    return {'Authorization': 'Bearer '+token}


def with_answers(values, read):
    """Add answer counts; comment access is optional, so its failure never drops the main metrics."""
    try:
        values.update(tally(read()))
    except PublishError:
        pass
    return values


def derived(values):
    """impressions, engagements and engagement_rate from whatever the platform returned."""
    out = {}
    impressions = next((number(values[k]) for k in IMPRESSIONS if number(values.get(k)) is not None), None)
    engagements = next((number(values[k]) for k in TOTAL_ENGAGEMENT if number(values.get(k)) is not None), None)
    if engagements is None:
        parts = [number(values[k]) for k in INTERACTIONS if number(values.get(k)) is not None]
        social = [number(v) for k, v in values.items() if k.startswith('post_video_social_actions.') and number(v) is not None]
        # Facebook Reels give reactions only as a breakdown; social actions, where returned, already include them.
        reactions = [number(v) for k, v in values.items() if k.startswith('post_video_likes_by_reaction_type.') and number(v) is not None]
        parts += social or reactions
        engagements = sum(parts) if parts else None
    if impressions is not None:
        out['impressions'] = impressions
    if engagements is not None:
        out['engagements'] = engagements
    if impressions and engagements is not None:
        out['engagement_rate'] = round(engagements/impressions, 4)
    return out


DERIVED = ('impressions', 'engagements', 'engagement_rate')


def instagram(remote_id, transport, tokens):
    import instagram_adapter
    token, base = tokens('instagram'), 'https://graph.instagram.com/v26.0'
    try:
        data = transport(query(base, remote_id+'/insights', {'metric': INSTAGRAM_METRICS}), bearer(token))
    except PublishError as error:
        if error.category != 'rejected':
            raise
        data = transport(query(base, remote_id+'/insights', {'metric': INSTAGRAM_CORE}), bearer(token))
    comments = lambda: [(c.get('username'), c.get('text'))
                        for c in transport(query(base, remote_id+'/comments', {'fields': 'text,username', 'limit': '50'}),
                                           bearer(token)).get('data') or []
                        if (c.get('username') or '').lower() != instagram_adapter.USERNAME]
    return with_answers(insight_values(data), comments)


def threads(remote_id, transport, tokens, own=None):
    token, base = tokens('threads'), 'https://graph.threads.net/v1.0'
    try:
        data = transport(query(base, remote_id+'/insights', {'metric': THREADS_METRICS}), bearer(token))
    except PublishError as error:
        if error.category != 'rejected':
            raise
        data = transport(query(base, remote_id+'/insights', {'metric': THREADS_CORE}), bearer(token))
    replies = lambda: [(r.get('username'), r.get('text'))
                       for r in transport(query(base, remote_id+'/replies', {'fields': 'text,username'}), bearer(token)).get('data') or []
                       if (r.get('username') or '').lower() != (own or '').lower()]
    return with_answers(insight_values(data), replies)


def pinned(config, name):
    """A pinned identity (identities.py); without it this platform's stats are not configured."""
    try:
        return pin(config, name)
    except IdentityMissing:
        raise PublishError('not_configured') from None


def facebook(remote_id, transport, tokens, page):
    token, base = tokens('facebook'), 'https://graph.facebook.com/v26.0'
    data = transport(query(base, remote_id+'/video_insights', {}), bearer(token))
    comments = lambda: [((c.get('from') or {}).get('id'), c.get('message'))
                        for c in transport(query(base, remote_id+'/comments', {'fields': 'message,from', 'limit': '50'}),
                                           bearer(token)).get('data') or []
                        if (c.get('from') or {}).get('id') != page]
    return with_answers(insight_values(data), comments)


def bluesky(remote_id, transport, tokens, did):
    if not remote_id.startswith('at://'+did+'/'):
        raise PublishError('rejected')
    base = 'https://public.api.bsky.app/xrpc'
    posts = transport(query(base, 'app.bsky.feed.getPosts', {'uris': remote_id})).get('posts') or []
    if len(posts) != 1:
        raise PublishError('gone')
    values = {name: number(posts[0].get(field)) for name, field in
              (('likes', 'likeCount'), ('reposts', 'repostCount'), ('replies', 'replyCount'), ('quotes', 'quoteCount'))
              if number(posts[0].get(field)) is not None}
    replies = lambda: [((r.get('post') or {}).get('author', {}).get('did'), ((r.get('post') or {}).get('record') or {}).get('text'))
                       for r in (transport(query(base, 'app.bsky.feed.getPostThread', {'uri': remote_id, 'depth': '1'}))
                                 .get('thread') or {}).get('replies') or []
                       if isinstance(r, dict) and (r.get('post') or {}).get('author', {}).get('did') != did]
    return with_answers(values, replies)


def youtube_id(permalink):
    parts = urllib.parse.urlsplit(permalink or '')
    if parts.scheme != 'https' or parts.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        return None
    if parts.hostname == 'youtu.be':
        candidate = parts.path.strip('/')
    elif parts.path.startswith('/shorts/'):
        candidate = parts.path[len('/shorts/'):].strip('/')
    else:
        candidate = (urllib.parse.parse_qs(parts.query).get('v') or [''])[0]
    return candidate if YOUTUBE_ID.fullmatch(candidate) else None


def youtube(permalink, transport, tokens):
    video = youtube_id(permalink)
    if not video:
        raise PublishError('rejected')
    key, base = tokens('youtube'), 'https://www.googleapis.com/youtube/v3'
    items = transport(query(base, 'videos', {'part': 'statistics', 'id': video, 'key': key})).get('items') or []
    if len(items) != 1:
        raise PublishError('gone')
    stats = items[0].get('statistics') or {}
    values = {name: number(stats.get(field)) for name, field in
              (('views', 'viewCount'), ('likes', 'likeCount'), ('comments', 'commentCount')) if number(stats.get(field)) is not None}
    comments = lambda: [(((t.get('snippet') or {}).get('topLevelComment') or {}).get('snippet', {}).get('authorChannelId', {}).get('value'),
                         ((t.get('snippet') or {}).get('topLevelComment') or {}).get('snippet', {}).get('textOriginal'))
                        for t in transport(query(base, 'commentThreads', {'part': 'snippet', 'videoId': video, 'maxResults': '50',
                                                                         'textFormat': 'plainText', 'key': key})).get('items') or []]
    return with_answers(values, comments)


def buffer(remote_id, transport, tokens):
    """One Buffer post's metrics (TikTok, X): Buffer reads the network once a day, so a post it has not read since
    it was sent is 'pending' (retried next hour) rather than zeros."""
    if not BUFFER_ID.fullmatch(remote_id):
        raise PublishError('rejected')
    data = transport('https://api.buffer.com', bearer(tokens('buffer')), {'query': BUFFER_QUERY, 'variables': {'input': {'id': remote_id}}})
    if data.get('errors'):
        codes = {str((e.get('extensions') or {}).get('code')) for e in data['errors'] if isinstance(e, dict)}
        raise PublishError('authorization' if codes & {'UNAUTHENTICATED', 'FORBIDDEN', 'UNAUTHORIZED'} else 'rejected')
    post = (data.get('data') or {}).get('post')
    if not isinstance(post, dict) or post.get('id') != remote_id:
        raise PublishError('gone')
    updated, sent = stamp(post.get('metricsUpdatedAt')), stamp(post.get('sentAt'))
    if updated is None or (sent is not None and updated < sent) or not isinstance(post.get('metrics'), list):
        raise PublishError('pending')
    values = {}
    for metric in post['metrics']:
        kind = metric.get('type') if isinstance(metric, dict) else None
        value = metric.get('value') if isinstance(metric, dict) else None
        if not isinstance(kind, str) or kind == 'engagementRate' or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        key = BUFFER_METRICS.get(kind) or (f'buffer.{kind}' if re.fullmatch(r'[A-Za-z0-9_]{1,40}', kind) else None)
        if key:
            values[key] = int(value) if float(value).is_integer() and kind != 'averageTimeWatched' else value
    return values


def day_bounds(day, zone):
    start = dt.datetime.combine(day, dt.time(), zone)
    return start, dt.datetime.combine(day+dt.timedelta(days=1), dt.time(), zone)


def account_day(platform, day, zone, transport, tokens, config):
    """Day totals for one local day; one request per metric, so an unknown metric only drops itself."""
    page = pinned(config, 'facebookPageId') if platform == 'facebook' else None
    start, end = day_bounds(day, zone)
    window = {'since': str(int(start.timestamp())), 'until': str(int(end.timestamp()))}
    base, path, extra, series = {
        'instagram': ('https://graph.instagram.com/v26.0', 'me/insights', {'period': 'day', 'metric_type': 'total_value'}, False),
        'threads': ('https://graph.threads.net/v1.0', 'me/threads_insights', {}, True),
        'facebook': ('https://graph.facebook.com/v26.0', f'{page}/insights', {'period': 'day'}, True),
    }[platform]
    token, values, failures = tokens(platform), {}, []
    for metric in ACCOUNT_DAY[platform]:
        try:
            split = {'breakdown': ACCOUNT_BREAKDOWN[metric]} if platform == 'instagram' and metric in ACCOUNT_BREAKDOWN else {}
            data = transport(query(base, path, {'metric': metric, **window, **extra, **split}), bearer(token))
        except PublishError as error:
            if error.category in ('authorization', 'not_configured', 'rate_limit'):
                raise   # the whole account read stops, not one metric
            failures.append(error.category)
            continue
        values.update(insight_values(data, end if series else None))
    if not values and failures:
        raise PublishError(failures[0])
    return values


def account_now(platform, transport, tokens, config):
    """Point-in-time account counts: followers, following, posts (YouTube: channel views)."""
    if platform == 'instagram':
        data = transport(query('https://graph.instagram.com/v26.0', 'me', {'fields': 'followers_count,follows_count,media_count'}),
                         bearer(tokens('instagram')))
        fields = (('followers', 'followers_count'), ('following', 'follows_count'), ('posts', 'media_count'))
    elif platform == 'threads':
        data = insight_values(transport(query('https://graph.threads.net/v1.0', 'me/threads_insights', {'metric': 'followers_count'}),
                                        bearer(tokens('threads'))))
        fields = (('followers', 'followers_count'),)
    elif platform == 'facebook':
        data = transport(query('https://graph.facebook.com/v26.0', pinned(config, 'facebookPageId'), {'fields': 'followers_count,fan_count'}),
                         bearer(tokens('facebook')))
        fields = (('followers', 'followers_count'), ('page_likes', 'fan_count'))
    elif platform == 'bluesky':
        data = transport(query('https://public.api.bsky.app/xrpc', 'app.bsky.actor.getProfile', {'actor': pinned(config, 'blueskyDid')}))
        fields = (('followers', 'followersCount'), ('following', 'followsCount'), ('posts', 'postsCount'))
    else:
        items = transport(query('https://www.googleapis.com/youtube/v3', 'channels',
                                {'part': 'statistics', 'id': pinned(config, 'youtubeChannelId'), 'key': tokens('youtube')})).get('items') or []
        data = (items[0].get('statistics') or {}) if len(items) == 1 else {}
        fields = (('followers', 'subscriberCount'), ('channel_views', 'viewCount'), ('posts', 'videoCount'))
    out = {name: number(data.get(field)) for name, field in fields if number(data.get(field)) is not None}
    if not out:
        raise PublishError('uncertain')
    return out


def credential(platform):
    """Token or key for a platform ('buffer': the Buffer API key); an empty placeholder file means not configured."""
    if platform in ('youtube', 'buffer'):
        root = os.environ.get('CREDENTIALS_DIRECTORY')
        try:
            value = (Path(root or '/nonexistent')/('YOUTUBE_API_KEY' if platform == 'youtube' else 'BUFFER_API_KEY')).read_text().strip()
        except OSError:
            value = ''
        if not value:
            raise PublishError('not_configured')
        return value
    import facebook_adapter
    import instagram_adapter
    import threads_adapter
    loader = {'instagram': instagram_adapter.token, 'threads': threads_adapter.token, 'facebook': facebook_adapter.token}[platform]
    try:
        return loader()
    except OSError:
        raise PublishError('not_configured') from None


def threads_username(config):
    match = re.fullmatch(r'https://www\.threads\.(?:com|net)/@([A-Za-z0-9._]+)/?',
                         ((config.get('channels') or {}).get('threads') or {}).get('profileUrl') or '')
    return match[1] if match else None


def fetch(job, config, transport=get, tokens=credential):
    platform, remote = job['platform'], str(job['remote_id'] or '')
    if platform == 'instagram':
        return instagram(remote, transport, tokens) if remote.isdecimal() else _bad()
    if platform == 'threads':
        return threads(remote, transport, tokens, threads_username(config)) if remote.isdecimal() else _bad()
    if platform == 'facebook':
        return facebook(remote, transport, tokens, pinned(config, 'facebookPageId')) if remote.isdecimal() else _bad()
    if platform == 'bluesky':
        return bluesky(remote, transport, tokens, pinned(config, 'blueskyDid'))
    if platform == 'youtube':
        return youtube(job['permalink'], transport, tokens)
    if platform in BUFFER_PLATFORMS:
        return buffer(remote, transport, tokens)
    raise PublishError('unsupported')


def _bad():
    raise PublishError('rejected')


def buffer_id(job):
    """A Meta post whose remote id is not a platform id: posted through Buffer, so it cannot be read."""
    return job['platform'] in META and not str(job['remote_id'] or '').isdecimal()


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS snapshots(
            job TEXT NOT NULL, checkpoint TEXT NOT NULL, platform TEXT NOT NULL, remote_id TEXT NOT NULL,
            fetched_at TEXT NOT NULL, status TEXT NOT NULL, metrics TEXT, PRIMARY KEY(job, checkpoint))''')
        # day: local date (config timezone). metrics merges day totals and that day's point-in-time counts.
        self.db.execute('''CREATE TABLE IF NOT EXISTS accounts(
            platform TEXT NOT NULL, day TEXT NOT NULL, metrics TEXT NOT NULL DEFAULT '{}',
            day_status TEXT, day_fetched_at TEXT, now_status TEXT, now_fetched_at TEXT, PRIMARY KEY(platform, day))''')

    def get(self, job, checkpoint):
        return self.db.execute('SELECT * FROM snapshots WHERE job=? AND checkpoint=?', (job, checkpoint)).fetchone()

    def put(self, job, checkpoint, now, status, values=None):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?)',
                            (job['id'], checkpoint, job['platform'], str(job['remote_id']), now.isoformat(), status,
                             json.dumps(values, sort_keys=True) if values is not None else None))


    def account(self, platform, day):
        return self.db.execute('SELECT * FROM accounts WHERE platform=? AND day=?', (platform, day.isoformat())).fetchone()

    def put_account(self, platform, day, kind, now, status, values=None):
        """kind 'day' (day totals) or 'now' (point-in-time counts); values merge into the row."""
        row = self.account(platform, day)
        merged = json.loads(row['metrics']) if row else {}
        merged = {k: v for k, v in {**merged, **(values or {})}.items() if k not in DERIVED}
        merged.update(derived(merged))
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO accounts(platform,day) VALUES(?,?)', (platform, day.isoformat()))
            self.db.execute(f'UPDATE accounts SET metrics=?, {kind}_status=?, {kind}_fetched_at=? WHERE platform=? AND day=?',
                            (json.dumps(merged, sort_keys=True), status, now.isoformat(), platform, day.isoformat()))


def due(published, now):
    """Newest checkpoint reached by a post published at `published`, or None."""
    age = (now-published).total_seconds()
    if age > LAST_READ:
        return None
    reached = [name for name, seconds in CHECKPOINTS if age >= seconds]
    return reached[-1] if reached else None


def published_at(job):
    for value in (job['published_at'], job['dispatched_at']):
        try:
            stamp = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            continue
        if stamp.tzinfo:
            return stamp
    return None


def collect(ledger, store, config, now, transport=get, tokens=credential, reasons=None):
    """One pass over confirmed posts; returns {platform: {status: count}} for the run summary.
    `reasons` (a set) receives platforms with a read rejected because of a Buffer-era remote id."""
    summary = {}
    rows = ledger.execute("SELECT * FROM jobs WHERE status='confirmed' AND remote_id IS NOT NULL AND remote_id!='' "
                          "AND instr(episode,'#')=0 ORDER BY published_at, id").fetchall()
    for job in rows:
        stamp = published_at(job)
        checkpoint = due(stamp, now) if stamp else None
        if not checkpoint:
            continue
        previous = store.get(job['id'], checkpoint)
        # A read stored as 'unsupported' before the platform became readable (TikTok/X via Buffer) is read again.
        if previous and previous['status'] not in TRANSIENT and not (previous['status'] == 'unsupported'
                                                                     and job['platform'] in SUPPORTED):
            continue
        if job['platform'] not in SUPPORTED:
            status, values = 'unsupported', None
        else:
            try:
                values = fetch(job, config, transport, tokens)
                status, values = 'ok', {**values, **derived(values)}
            except PublishError as error:
                status, values = error.category, None
                if status == 'rejected' and reasons is not None and buffer_id(job):
                    reasons.add(job['platform'])
        store.put(job, checkpoint, now, status, values)
        counts = summary.setdefault(job['platform'], {})
        counts[status] = counts.get(status, 0)+1
    return summary


def account_platforms(config):
    channels = config.get('channels') or {}
    out = []
    for platform in ACCOUNT_PLATFORMS:
        c = channels.get(platform) or {}
        # Instagram on Buffer has no direct token; identity must have been verified on the Pi.
        if c.get('identityVerified') and (platform != 'instagram' or c.get('route') == 'instagram'):
            out.append(platform)
    return out


def needs_read(fetched_at, status, now, settled_at=None):
    fetched = stamp(fetched_at) if fetched_at else None
    if fetched is None:
        return True
    if settled_at is not None and fetched >= settled_at:
        return False   # read after the platform's late data settled: final
    return (now-fetched).total_seconds() >= ACCOUNT_REFRESH or (status in TRANSIENT and (now-fetched).total_seconds() >= 3000)


def collect_accounts(store, config, now, transport=get, tokens=credential, backfill=0, force_now=False):
    """Point-in-time counts on today's row; day totals for recent (or `backfill`) days. {platform: {status: n}}.
    `force_now` (a manual read) re-reads the point-in-time counts regardless of the 6-hour refresh."""
    zone = ZoneInfo(config.get('timezone') or 'UTC')
    today = now.astimezone(zone).date()
    summary = {}

    def read(platform, day, kind, call):
        try:
            status, values = 'ok', call()
        except PublishError as error:
            status, values = error.category, None
        store.put_account(platform, day, kind, now, status, values)
        counts = summary.setdefault(platform, {})
        counts[status] = counts.get(status, 0)+1

    for platform in account_platforms(config):
        row = store.account(platform, today)
        if force_now or needs_read(row and row['now_fetched_at'], row and row['now_status'], now):
            read(platform, today, 'now', lambda: account_now(platform, transport, tokens, config))
        if platform not in ACCOUNT_DAY:
            continue
        for back in range(1, max(4, backfill)+1):
            day = today-dt.timedelta(days=back)
            row = store.account(platform, day)
            settled = day_bounds(day, zone)[1]+dt.timedelta(seconds=ACCOUNT_SETTLE)
            if needs_read(row and row['day_fetched_at'], row and row['day_status'], now, settled):
                read(platform, day, 'day', lambda: account_day(platform, day, zone, transport, tokens, config))
    return summary


ORDER = {name: index for index, (name, _) in enumerate(CHECKPOINTS)}


def latest(state, job_ids):
    """{job id: {checkpoint, fetchedAt, status, values}}: the newest successful read, else the newest attempt."""
    path = Path(state)/'metrics.sqlite3'
    if not job_ids or not path.is_file():
        return {}
    out = {}
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        ids = list(job_ids)
        for start in range(0, len(ids), 500):
            chunk = ids[start:start+500]
            for row in db.execute(f"SELECT * FROM snapshots WHERE job IN ({','.join('?'*len(chunk))})", chunk):
                rank = (row['status'] == 'ok', ORDER.get(row['checkpoint'], -1))
                current = out.get(row['job'])
                if current and current[0] >= rank:
                    continue
                try:
                    values = json.loads(row['metrics']) if row['metrics'] else {}
                except ValueError:
                    values = {}
                out[row['job']] = (rank, {'checkpoint': row['checkpoint'], 'fetchedAt': row['fetched_at'],
                                          'status': row['status'], 'values': values})
    return {k: v[1] for k, v in out.items()}


def account_summary(state, today, days=7):
    """Per platform: newest followers and the change over `days`, and day totals summed over the last `days`
    complete local days. Reach and other unique counts are not summed."""
    path = Path(state)/'metrics.sqlite3'
    if not path.is_file():
        return []
    first = (today-dt.timedelta(days=days)).isoformat()
    out = []
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone():
            return []
        for platform in ACCOUNT_PLATFORMS:
            rows = db.execute('SELECT * FROM accounts WHERE platform=? AND day>=? ORDER BY day', (platform, first)).fetchall()
            if not rows:
                continue
            parsed = [(r, json.loads(r['metrics'] or '{}')) for r in rows]
            followers = [(r['day'], m['followers']) for r, m in parsed if number(m.get('followers')) is not None]
            complete = [m for r, m in parsed if r['day'] < today.isoformat() and r['day_status'] == 'ok']
            totals = {k: sum(m[k] for m in complete if number(m.get(k)) is not None)
                      for k in ('impressions', 'engagements', 'clicks', 'profile_links_taps')
                      if any(number(m.get(k)) is not None for m in complete)}
            if totals.get('impressions') and 'engagements' in totals:
                totals['engagement_rate'] = round(totals['engagements']/totals['impressions'], 4)
            latest = rows[-1]
            problem = next((s for s in (latest['now_status'], latest['day_status'], rows[-2]['day_status'] if len(rows) > 1 else None)
                            if s and s != 'ok'), None)
            out.append({'platform': platform, 'followers': followers[-1][1] if followers else None,
                        'followersChange': followers[-1][1]-followers[0][1] if len(followers) > 1 else None,
                        'days': len(complete), 'totals': totals, 'status': problem or 'ok'})
    return out


def export(state, kind, handle):
    """CSV of every stored read: one row per post checkpoint or per account day, one column per metric."""
    path = Path(state)/'metrics.sqlite3'
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        if kind == 'posts':
            fixed = ['job', 'platform', 'remote_id', 'checkpoint', 'fetched_at', 'status']
            rows = db.execute('SELECT * FROM snapshots ORDER BY fetched_at, job').fetchall()
        else:
            fixed = ['platform', 'day', 'day_status', 'day_fetched_at', 'now_status', 'now_fetched_at']
            rows = db.execute('SELECT * FROM accounts ORDER BY day, platform').fetchall()
        parsed = [(r, json.loads(r['metrics'] or '{}')) for r in rows]
        columns = sorted({k for _, m in parsed for k in m})
        writer = csv.writer(handle)
        writer.writerow(fixed+columns)
        for r, m in parsed:
            writer.writerow([r[k] for k in fixed]+[m.get(k, '') for k in columns])


FUNNEL_KEYS = ('views', 'engaged', 'answered', 'avgWatchSeconds', 'followsThatDay')
WATCH_MS = ('ig_reels_avg_watch_time', 'total_video_avg_time_watched', 'post_video_avg_time_watched')
FOLLOWS_DAY = {'instagram': 'follows_and_unfollows.FOLLOWER', 'facebook': 'page_daily_follows_unique'}


def day_rows(state, keys):
    """{(platform, day): metrics} for the requested account rows; read-only."""
    path = Path(state)/'metrics.sqlite3'
    if not keys or not path.is_file():
        return {}
    out = {}
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone():
            return {}
        for platform, day in sorted(keys):
            row = db.execute('SELECT metrics FROM accounts WHERE platform=? AND day=?', (platform, day)).fetchone()
            try:
                values = json.loads(row['metrics'] or '{}') if row else None
            except ValueError:
                values = None
            if isinstance(values, dict):
                out[(platform, day)] = values
    return out


def funnel_platform(platform, snap, day, before):
    """FunnelPlatform from the post's newest read and the account rows for its publish day and the day before.
    answered: the answers.* sum when any exists, else 0 for an ok read (no letter replies, or replies unreadable),
    else null."""
    out = {'status': snap['status'] if snap else None, **dict.fromkeys(FUNNEL_KEYS), 'followsSource': None}
    if platform not in SUPPORTED:
        return out
    values = (snap or {}).get('values') or {}
    out['views'], out['engaged'] = number(values.get('impressions')), number(values.get('engagements'))
    answers = [number(v) for k, v in values.items() if k.startswith('answers.') and number(v) is not None]
    # Buffer gives no comment text, so A–D answers are unknown (null) for TikTok and X, never 0.
    out['answered'] = sum(answers) if answers else (0 if out['status'] == 'ok' and platform not in BUFFER_PLATFORMS else None)
    watch = next((number(values[k]) for k in WATCH_MS if number(values.get(k)) is not None), None)
    out['avgWatchSeconds'] = round(watch/1000, 1) if watch is not None else None   # platforms report milliseconds
    if watch is None and number(values.get('avg_watch_seconds')) is not None:   # Buffer (TikTok) reports seconds
        out['avgWatchSeconds'] = round(number(values['avg_watch_seconds']), 1)
    metric = FOLLOWS_DAY.get(platform)
    if day is not None and metric and number(day.get(metric)) is not None:
        out['followsThatDay'], out['followsSource'] = number(day[metric]), 'day-metric'
    elif day is not None and before is not None and number(day.get('followers')) is not None \
            and number(before.get('followers')) is not None:
        out['followsThatDay'], out['followsSource'] = number(day['followers'])-number(before['followers']), 'follower-change'
    return out


def funnel(state, jobs, zone, limit=30):
    """[EpisodeFunnel] newest first. state: STATE path; jobs: iterable of ledger rows (mapping with id, episode, platform,
    status, remote_id, permalink, published_at, dispatched_at); zone: ZoneInfo of config timezone.
    Only confirmed jobs whose episode has no '#' (companions excluded). Read-only on metrics.sqlite3.

    Per platform the newest-published post of the episode counts. Follows are the account's on that post's local
    publish day (not attributed to the video): the platform's day follow metric, else the follower-count change from
    the day before. Totals skip nulls; avgWatchSeconds is view-weighted when every counted platform has views."""
    episodes = {}
    for job in jobs:
        if job['status'] != 'confirmed' or '#' in str(job['episode']):
            continue
        instant = published_at(job)
        episodes.setdefault(job['episode'], []).append(((instant.timestamp() if instant else float('-inf'), str(job['id'])),
                                                        instant, job))
    order = sorted(episodes, key=lambda e: (max(p[0] for p in episodes[e]), e), reverse=True)[:limit]
    chosen = {}
    for episode in order:
        for rank, instant, job in episodes[episode]:
            key = (episode, job['platform'])
            if key not in chosen or rank > chosen[key][0]:
                chosen[key] = (rank, instant, job)
    local = {key: instant.astimezone(zone).date() if instant else None for key, (_, instant, _) in chosen.items()}
    snaps = latest(state, [job['id'] for _, _, job in chosen.values()])
    rows = day_rows(state, {(platform, d.isoformat()) for (_, platform), day in local.items() if day
                            for d in (day, day-dt.timedelta(days=1))})
    out = []
    for episode in order:
        platforms = {}
        for (name, platform), (_, _, job) in sorted(chosen.items(), key=lambda item: item[0][1]):
            if name != episode:
                continue
            day = local[(name, platform)]
            platforms[platform] = funnel_platform(
                platform, snaps.get(job['id']), day and rows.get((platform, day.isoformat())),
                day and rows.get((platform, (day-dt.timedelta(days=1)).isoformat())))
        counted = {k: [p for p in platforms if platforms[p][k] is not None] for k in FUNNEL_KEYS}
        row = {'episode': episode,
               'publishedDates': sorted({i.astimezone(zone).date().isoformat() for _, i, _ in episodes[episode] if i}),
               **{k: sum(platforms[p][k] for p in counted[k]) if counted[k] else None for k in FUNNEL_KEYS}}
        watched = counted['avgWatchSeconds']
        if watched:
            views = [platforms[p]['views'] for p in watched]
            if all(v is not None for v in views) and sum(views) > 0:
                row['avgWatchSeconds'] = round(sum(platforms[p]['avgWatchSeconds']*platforms[p]['views'] for p in watched)
                                               / sum(views), 1)
            else:
                row['avgWatchSeconds'] = round(sum(platforms[p]['avgWatchSeconds'] for p in watched)/len(watched), 1)
        out.append({**row, 'counted': counted, 'platforms': platforms})
    return out


def iso_utc(moment):
    return moment.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def write_json(path, data):
    """Atomic 0600 write: temp file in the same folder, then rename."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name+'-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(data, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def prune_history(history, keep=HISTORY_KEEP):
    """Keep the newest `keep` request-/switch- files in metrics/history (ordered by their timestamp, then name)."""
    with contextlib.suppress(OSError):
        names = sorted((m[2], m[0]) for path in history.iterdir() if (m := HISTORY_NAME.fullmatch(path.name)))
        for _, name in names[:-keep]:
            with contextlib.suppress(OSError):   # one entry that cannot be removed never stops the rest
                (history/name).unlink()


def take_request(folder, now):
    """Move metrics/request.json into history/ (so the path unit cannot loop) and return its backfill.
    None when no request is waiting, 'bad-request' when it is unreadable or invalid."""
    history = folder/'history'
    history.mkdir(exist_ok=True, mode=0o700)
    target = history/f"request-{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}.json"
    try:
        os.replace(folder/'request.json', target)
    except FileNotFoundError:
        return None
    prune_history(history)
    try:
        with open(target, 'rb') as handle:
            raw = handle.read(REQUEST_CAP+1)
        request = json.loads(raw) if len(raw) <= REQUEST_CAP else None
    except (OSError, ValueError):
        request = None
    backfill = request.get('backfill') if isinstance(request, dict) else None
    if not isinstance(request, dict) or set(request)-{'requestedAt', 'backfill'} \
            or not isinstance(request.get('requestedAt', ''), str) or type(backfill) is not int or not 0 <= backfill <= 93:
        return 'bad-request'
    return backfill


def carried(folder):
    """The previous last-run.json platforms with zero reads this run."""
    try:
        previous = json.loads((folder/'last-run.json').read_text()).get('platforms')
    except (OSError, ValueError, AttributeError):
        return {}
    return {p: {'status': e['status'], 'postsRead': 0, 'accountsRead': 0, 'reason': 'buffer' if e.get('reason') == 'buffer' else None}
            for p, e in (previous.items() if isinstance(previous, dict) else ())
            if isinstance(p, str) and isinstance(e, dict) and e.get('status') in SEVERITY}


def stored_status(store, platform):
    """Worst status of the platform's newest account row, for a platform with no reads and no previous run."""
    row = store.db.execute('SELECT now_status, day_status FROM accounts WHERE platform=? ORDER BY day DESC LIMIT 1',
                           (platform,)).fetchone()
    statuses = [RUN_STATUS.get(s, 'error') for s in (row or ()) if s]
    return max(statuses, key=SEVERITY.index) if statuses else None


def run_platforms(reads, accounts, reasons, previous, configured, store):
    out = dict(previous)
    for platform in sorted(set(configured) | set(reads) | set(accounts)):
        counts = [RUN_STATUS.get(status, 'error') for summary in (reads, accounts) for status in summary.get(platform, {})]
        if counts:
            status = max(counts, key=SEVERITY.index)
            out[platform] = {'status': status, 'postsRead': reads.get(platform, {}).get('ok', 0),
                             'accountsRead': accounts.get(platform, {}).get('ok', 0),
                             'reason': 'buffer' if status == 'rejected' and platform in reasons else None}
        elif platform not in out and (status := stored_status(store, platform)):
            out[platform] = {'status': status, 'postsRead': 0, 'accountsRead': 0, 'reason': None}
    return out


def run(state, config, now, transport=get, tokens=credential, backfill=0, clock=None):
    """One collector run; writes metrics/last-run.json and returns the journal summary.

    config: the parsed config, or its path (read after a waiting request has been moved to history). A waiting
    request.json decides the trigger and backfill; otherwise a run without the `enabled` flag reads nothing."""
    state = Path(state)
    folder = state/'metrics'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    previous = carried(folder)
    record = {'startedAt': iso_utc(now), 'trigger': 'timer', 'backfill': backfill, 'outcome': 'ok', 'platforms': previous}
    reads, accounts = {}, {}

    def finish():
        write_json(folder/'last-run.json', {**record, 'finishedAt': iso_utc(clock() if clock else dt.datetime.now(UTC))})

    try:
        request = take_request(folder, now)
        if request is not None:
            record['trigger'] = 'request'
            if request == 'bad-request':
                record['outcome'] = 'bad-request'
            else:
                record['backfill'] = max(record['backfill'], request)   # an owner's CLI --backfill is never dropped
        elif not (folder/'enabled').exists():
            record['outcome'] = 'stats-off'
        if record['outcome'] == 'ok':
            if not isinstance(config, dict):
                config = json.loads(Path(config).read_text())
            store, reasons = Store(state/'metrics.sqlite3'), set()
            try:
                if (state/'ledger.sqlite3').is_file():   # account stats are read before the first post too
                    with contextlib.closing(sqlite3.connect((state/'ledger.sqlite3').resolve().as_uri()+'?mode=ro',
                                                            uri=True, timeout=10)) as ledger:
                        ledger.row_factory = sqlite3.Row
                        reads = collect(ledger, store, config, now, transport, tokens, reasons)
                accounts = collect_accounts(store, config, now, transport, tokens, record['backfill'],
                                            force_now=record['trigger'] == 'request')
                record['platforms'] = run_platforms(reads, accounts, reasons, previous, account_platforms(config), store)
            finally:
                store.db.close()
    except BaseException:
        record['outcome'] = 'error'
        with contextlib.suppress(Exception):
            finish()
        raise
    finish()
    return {'checkedAt': now.isoformat(), 'trigger': record['trigger'], 'outcome': record['outcome'],
            'reads': reads, 'accounts': accounts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('collect', 'export'))
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--backfill', type=int, default=0, help='collect: also read up to this many past days of account totals')
    parser.add_argument('--kind', choices=('posts', 'accounts'), default='posts', help='export: which table, as CSV on stdout')
    args = parser.parse_args()
    state = Path(args.state)
    if args.command == 'export':
        export(state, args.kind, sys.stdout)
        return
    if not 0 <= args.backfill <= 93:
        raise ValueError('backfill must be 0-93 days')
    print(json.dumps(run(state, Path(args.config), dt.datetime.now(UTC), backfill=args.backfill), sort_keys=True))
    # Missing permissions are expected until granted; only an unreadable ledger or store fails the unit.


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(f'Metrics collector stopped: {type(error).__name__}; check the state folder and configuration.', file=sys.stderr)
        sys.exit(1)
