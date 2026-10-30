#!/usr/bin/env python3
"""Explainers trend feeds (stdlib): fetch today's trend signals once and write one JSON digest for the trend scout.

Usage: python3 projects/explainers/tools/scout_feeds.py --out library/<batchId>/review/scout.json [--geo US] [--queries "a,b"]

Sources (projects/explainers/RESEARCH.md §5; each one fails on its own without stopping the others):
- Google Trends "Trending now" RSS (no key; fetched once, cached)
- Hacker News top and best stories (Firebase API, no key)
- Wikimedia top pageviews for yesterday (CC0; User-Agent required)
- GDELT DOC API article lists for a few queries (free with a citation; one request per 5 s)
Not used: Google News RSS (its feed is licensed for personal, non-commercial readers only), Reddit, TikTok, Product Hunt.
Only titles, links, counts and dates are kept; no article text.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = 'StudioZero-explainers-scout/1 (+https://github.com/samirhusain26/StudioZero)'
TIMEOUT = 20
HN = 'https://hacker-news.firebaseio.com/v0'
GDELT = 'https://api.gdeltproject.org/api/v2/doc/doc'
GDELT_GAP = 6.0
DEFAULT_QUERIES = ['patent', 'patent lawsuit', 'product launch', 'product recall', 'new invention']
WIKI_SKIP = ('Main_Page', 'Special:', 'Wikipedia:', 'File:', 'Portal:', 'Help:', 'Talk:', 'Category:', 'Template:', 'User:', '-')


SYSTEM_CA = '/etc/ssl/cert.pem'


def tls_context():
    """Verifying TLS context; a python.org build on macOS ships no CA store, so fall back to the system bundle."""
    context = ssl.create_default_context()
    if not context.cert_store_stats().get('x509_ca') and os.path.exists(SYSTEM_CA):
        context.load_verify_locations(SYSTEM_CA)
    return context


TLS = tls_context()


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=TLS) as response:
        return response.read().decode('utf-8', errors='replace')


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _child_text(element, name):
    for child in element:
        if _local(child.tag) == name:
            return (child.text or '').strip()
    return ''


def parse_trends_rss(text):
    """Google Trends RSS → [{title, traffic, published, news: [{title, url, source}]}]."""
    items = []
    for item in ET.fromstring(text).iter('item'):
        news = []
        for child in item:
            if _local(child.tag) == 'news_item':
                news.append({'title': _child_text(child, 'news_item_title'), 'url': _child_text(child, 'news_item_url'),
                             'source': _child_text(child, 'news_item_source')})
        items.append({'title': _child_text(item, 'title'), 'traffic': _child_text(item, 'approx_traffic'),
                      'published': _child_text(item, 'pubDate'), 'news': news})
    return items


def parse_hn_item(item):
    if not isinstance(item, dict) or item.get('type') != 'story' or item.get('dead') or item.get('deleted'):
        return None
    return {'id': item.get('id'), 'title': item.get('title', ''), 'url': item.get('url') or f"https://news.ycombinator.com/item?id={item.get('id')}",
            'score': item.get('score', 0), 'comments': item.get('descendants', 0),
            'discussion': f"https://news.ycombinator.com/item?id={item.get('id')}"}


def parse_wiki_top(data, limit=40):
    articles = (((data or {}).get('items') or [{}])[0]).get('articles') or []
    out = []
    for a in articles:
        name = a.get('article', '')
        if name.startswith(WIKI_SKIP) or name == '-':
            continue
        out.append({'title': name.replace('_', ' '), 'views': a.get('views', 0),
                    'url': 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(name)})
        if len(out) >= limit:
            break
    return out


def parse_gdelt(data, limit=15):
    out = []
    for a in (data or {}).get('articles') or []:
        out.append({'title': a.get('title', ''), 'url': a.get('url', ''), 'source': a.get('domain', ''), 'seen': a.get('seendate', '')})
        if len(out) >= limit:
            break
    return out


def google_trends(geo):
    url = f'https://trends.google.com/trending/rss?geo={urllib.parse.quote(geo)}'
    return url, parse_trends_rss(fetch(url))


def hacker_news(top=30, best=20):
    ids = json.loads(fetch(f'{HN}/topstories.json'))[:top]
    for i in json.loads(fetch(f'{HN}/beststories.json'))[:best]:
        if i not in ids:
            ids.append(i)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(lambda i: parse_hn_item(json.loads(fetch(f'{HN}/item/{i}.json'))), ids))
    return f'{HN}/topstories.json + beststories.json', [i for i in items if i]


def wikimedia(day):
    url = f'https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{day:%Y/%m/%d}'
    return url, parse_wiki_top(json.loads(fetch(url)))


def gdelt_get(url, sleep=time.sleep, tries=3):
    """GDELT answers a too-fast request with HTTP 429 or a plain-text notice; back off and retry."""
    for attempt in range(tries):
        try:
            return json.loads(fetch(url))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == tries - 1:
                raise
        except ValueError:
            if attempt == tries - 1:
                raise
        sleep(GDELT_GAP * (attempt + 1))


def gdelt(queries, sleep=time.sleep):
    results = []
    for n, q in enumerate(queries):
        if n:
            sleep(GDELT_GAP)
        params = urllib.parse.urlencode({'query': f'"{q}" sourcelang:english' if ' ' in q else f'{q} sourcelang:english',
                                         'mode': 'artlist', 'format': 'json', 'maxrecords': '25', 'timespan': '2d', 'sort': 'hybridrel'})
        results.append({'query': q, 'items': parse_gdelt(gdelt_get(f'{GDELT}?{params}', sleep))})
    return GDELT, results


def run(geo='US', queries=None, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    jobs = {
        'googleTrends': lambda: google_trends(geo),
        'hackerNews': hacker_news,
        'wikimediaTop': lambda: wikimedia(today - dt.timedelta(days=1)),
        'gdelt': lambda: gdelt(queries or DEFAULT_QUERIES),
    }
    sources = {}
    for name, job in jobs.items():
        try:
            url, items = job()
            sources[name] = {'ok': True, 'url': url, 'items': items}
        except Exception as exc:  # one failing source never stops the digest
            sources[name] = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    return {'fetchedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'geo': geo, 'userAgent': USER_AGENT,
            'citation': 'News article lists from the GDELT Project (https://www.gdeltproject.org/).', 'sources': sources}


def main(argv):
    parser = argparse.ArgumentParser(description='Fetch trend feeds for the explainers trend scout.')
    parser.add_argument('--out', help='write the digest here (default: stdout)')
    parser.add_argument('--geo', default='US')
    parser.add_argument('--queries', help='comma-separated GDELT queries')
    args = parser.parse_args(argv)
    queries = [q.strip() for q in args.queries.split(',') if q.strip()] if args.queries else None
    digest = run(args.geo, queries)
    text = json.dumps(digest, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        summary = ', '.join(f"{k} {len(v['items']) if v['ok'] else 'FAILED'}" for k, v in digest['sources'].items())
        print(f'{args.out}: {summary}')
    else:
        print(text)
    return 0 if any(v['ok'] for v in digest['sources'].values()) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
