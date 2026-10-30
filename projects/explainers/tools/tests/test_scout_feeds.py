import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scout_feeds as sf  # noqa: E402

TRENDS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>robot vacuum</title><ht:approx_traffic>2000+</ht:approx_traffic><pubDate>Tue, 13 Oct 2026 20:50:00 -0700</pubDate>
<ht:news_item><ht:news_item_title>New robot vacuum</ht:news_item_title><ht:news_item_url>https://example.com/a</ht:news_item_url><ht:news_item_source>Example</ht:news_item_source></ht:news_item>
<ht:news_item><ht:news_item_title>Second story</ht:news_item_title><ht:news_item_url>https://example.com/b</ht:news_item_url><ht:news_item_source>Other</ht:news_item_source></ht:news_item>
</item>
<item><title>empty</title></item>
</channel></rss>"""


class ParseTests(unittest.TestCase):
    def test_trends(self):
        items = sf.parse_trends_rss(TRENDS)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['title'], 'robot vacuum')
        self.assertEqual(items[0]['traffic'], '2000+')
        self.assertEqual([n['url'] for n in items[0]['news']], ['https://example.com/a', 'https://example.com/b'])
        self.assertEqual(items[1]['news'], [])

    def test_hn_item(self):
        self.assertEqual(sf.parse_hn_item({'type': 'story', 'id': 5, 'title': 'T', 'score': 9, 'descendants': 2})['url'],
                         'https://news.ycombinator.com/item?id=5')
        self.assertIsNone(sf.parse_hn_item({'type': 'comment', 'id': 6}))
        self.assertIsNone(sf.parse_hn_item({'type': 'story', 'id': 7, 'dead': True}))
        self.assertIsNone(sf.parse_hn_item(None))

    def test_wiki_filters_junk(self):
        data = {'items': [{'articles': [{'article': 'Main_Page', 'views': 9}, {'article': 'Special:Search', 'views': 8},
                                        {'article': 'Robot_vacuum', 'views': 7}, {'article': '-', 'views': 6},
                                        {'article': 'Wikipedia:Featured_pictures', 'views': 5}]}]}
        out = sf.parse_wiki_top(data)
        self.assertEqual([a['title'] for a in out], ['Robot vacuum'])
        self.assertEqual(out[0]['url'], 'https://en.wikipedia.org/wiki/Robot_vacuum')

    def test_gdelt(self):
        data = {'articles': [{'title': 'A', 'url': 'https://x', 'domain': 'x.com', 'seendate': '20261013T120000Z'}]}
        self.assertEqual(sf.parse_gdelt(data), [{'title': 'A', 'url': 'https://x', 'source': 'x.com', 'seen': '20261013T120000Z'}])
        self.assertEqual(sf.parse_gdelt({}), [])


class RunTests(unittest.TestCase):
    def test_gdelt_retries_after_plain_text_notice(self):
        answers = iter(['Please limit requests to one every 5 seconds', json.dumps({'articles': []})])
        sleeps = []
        with mock.patch.object(sf, 'fetch', lambda url: next(answers)):
            _, results = sf.gdelt(['patent'], sleep=sleeps.append)
        self.assertEqual(results, [{'query': 'patent', 'items': []}])
        self.assertEqual(sleeps, [sf.GDELT_GAP])

    def test_gdelt_backs_off_on_429(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise sf.urllib.error.HTTPError(url, 429, 'Too Many Requests', None, None)
            return json.dumps({'articles': [{'title': 'A', 'url': 'https://x', 'domain': 'x.com'}]})
        sleeps = []
        with mock.patch.object(sf, 'fetch', fake_fetch):
            _, results = sf.gdelt(['patent'], sleep=sleeps.append)
        self.assertEqual(results[0]['items'][0]['title'], 'A')
        self.assertEqual(sleeps, [sf.GDELT_GAP])

    def test_one_failing_source_does_not_stop_the_digest(self):
        def fake_fetch(url):
            if 'trends.google.com' in url:
                return TRENDS
            raise OSError('offline')
        with mock.patch.object(sf, 'fetch', fake_fetch), mock.patch.object(sf.time, 'sleep', lambda s: None):
            digest = sf.run('US', ['patent'])
        self.assertTrue(digest['sources']['googleTrends']['ok'])
        self.assertFalse(digest['sources']['hackerNews']['ok'])
        self.assertIn('offline', digest['sources']['wikimediaTop']['error'])
        self.assertIn('GDELT', digest['citation'])


if __name__ == '__main__':
    unittest.main()
