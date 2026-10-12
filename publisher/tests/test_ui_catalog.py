import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'publisher/tests'))
import ui_catalog
import ui_views
from test_ui_server import ServerTestCase


class CatalogModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'catalog.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_committed_catalog_reads_and_names_the_games(self):
        raw, catalog, sha = ui_catalog.read()
        self.assertEqual(raw, (ROOT/'publisher/catalog.json').read_bytes())
        self.assertEqual(len(sha), 64)
        self.assertEqual(ui_catalog.games(catalog), ('scalar', 'continuum', 'whenabouts', 'tectonic'))
        self.assertEqual(ui_views.GAMES, ui_catalog.games(catalog))

    def test_refuses_missing_large_invalid_and_unknown_shapes(self):
        with self.assertRaises(ui_catalog.CatalogError):
            ui_catalog.read(self.path)
        for body in (b'{', b'[]', b'{"catalogVersion": 2, "projects": [], "engines": []}', b'{"catalogVersion": 1}',
                     b'\xff\xfe', b'[' * 100000):
            self.path.write_bytes(body)
            with self.assertRaises(ui_catalog.CatalogError):
                ui_catalog.read(self.path)
        self.path.write_bytes(b'{"catalogVersion": 1, "projects": [], "engines": [], "pad": "' + b'x' * ui_catalog.MAX_BYTES + b'"}')
        with self.assertRaises(ui_catalog.CatalogError):
            ui_catalog.read(self.path)

    def test_cache_rereads_after_the_file_changes(self):
        self.path.write_text(json.dumps({'catalogVersion': 1, 'projects': [{'games': [{'id': 'a'}]}], 'engines': []}))
        cache = ui_catalog.Cache(self.path)
        self.assertEqual(ui_catalog.games(cache.get()[1]), ('a',))
        self.path.write_text(json.dumps({'catalogVersion': 1, 'projects': [{'games': [{'id': 'b'}, {'id': 'b'}, 'x']}], 'engines': []}))
        self.assertEqual(ui_catalog.games(cache.get()[1]), ('b',))
        self.path.unlink()
        with self.assertRaises(ui_catalog.CatalogError):
            cache.get()


class CatalogEndpointTests(ServerTestCase):
    def test_needs_a_session_and_serves_the_exact_bytes_with_an_etag(self):
        status, _, _ = self.request('GET', '/api/catalog', auth=False)
        self.assertEqual(status, 401)
        status, headers, data = self.request('GET', '/api/catalog')
        self.assertEqual(status, 200)
        self.assertEqual(data, (ROOT/'publisher/catalog.json').read_bytes())
        self.assertEqual(headers['Content-Type'], 'application/json; charset=utf-8')
        self.assertEqual(headers['Cache-Control'], 'private, no-cache')
        etag = headers['ETag']
        status, headers, data = self.request('GET', '/api/catalog', headers={'If-None-Match': f'"x", {etag}'})
        self.assertEqual((status, data), (304, b''))
        self.assertNotIn('Content-Length', headers)
        status, _, _ = self.request('POST', '/api/catalog', {})
        self.assertEqual(status, 404)

    def test_unreadable_catalog_is_503_without_details(self):
        self.app.catalog = ui_catalog.Cache(Path(self.tmp.name)/'missing.json')
        status, body = self.json('GET', '/api/catalog')
        self.assertEqual(status, 503)
        self.assertNotIn('missing.json', json.dumps(body))


if __name__ == '__main__':
    unittest.main()
