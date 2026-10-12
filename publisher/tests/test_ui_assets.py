import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'publisher/tests'))
import ui_assets
from test_ui_server import ServerTestCase

WAV = b'RIFF' + bytes(range(256)) * 4
FONT = b'wOF2' + b'\x00' * 100


def write_repo(root, files, extra=None):
    """A fake checkout: engines/motion/public/<files> and publisher/motion-assets.json listing them (+ extra)."""
    public = root/'engines/motion/public'
    entries = {}
    for path, data in files.items():
        (public/path).parent.mkdir(parents=True, exist_ok=True)
        (public/path).write_bytes(data)
        entries[path] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    entries.update(extra or {})
    manifest = root/'publisher/motion-assets.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'motionAssetsVersion': 1, 'root': 'engines/motion/public', 'files': entries}))
    return manifest


class AssetModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.skipUnless((ROOT/'engines/motion/public').is_dir(), 'engines/motion/public is not in this checkout yet')
    def test_committed_manifest_is_valid_and_matches_the_checkout(self):
        assets = ui_assets.Assets()
        version, files = assets.current()
        self.assertRegex(version, r'^[0-9a-f]{16}$')
        self.assertGreater(len(files), 100)
        self.assertFalse(any(p.startswith('episodes/music/') and p.count('-') == 1 for p in files))  # retired <game>-<n>.m4a beds
        path = next(iter(files))
        found = assets.lookup(version, path)
        self.assertEqual(found[1], files[path]['bytes'])

    def test_refuses_unknown_versions_paths_outside_the_list_and_symlinks(self):
        manifest = write_repo(self.root, {'sfx/ding.wav': WAV})
        assets = ui_assets.Assets(manifest, self.root)
        version, _ = assets.current()
        self.assertIsNotNone(assets.lookup(version, 'sfx/ding.wav'))
        self.assertIsNone(assets.lookup('0' * 16, 'sfx/ding.wav'))
        self.assertIsNone(assets.lookup(version, 'sfx/tick.wav'))
        outside = self.root/'secret.wav'
        outside.write_bytes(WAV)
        (self.root/'engines/motion/public/sfx/link.wav').symlink_to(outside)
        manifest = write_repo(self.root, {'sfx/ding.wav': WAV}, {'sfx/link.wav': {'sha256': 'a' * 64, 'bytes': len(WAV)}})
        version, _ = assets.current()
        self.assertIsNone(assets.lookup(version, 'sfx/link.wav'))

    def test_a_changed_file_is_an_error_not_a_silent_serve(self):
        manifest = write_repo(self.root, {'sfx/ding.wav': WAV})
        assets = ui_assets.Assets(manifest, self.root)
        version, _ = assets.current()
        (self.root/'engines/motion/public/sfx/ding.wav').write_bytes(WAV + b'x')
        with self.assertRaises(ui_assets.AssetError):
            assets.lookup(version, 'sfx/ding.wav')

    def test_manifest_shape_is_checked(self):
        for doc in ({'motionAssetsVersion': 2, 'root': 'engines/motion/public', 'files': {}},
                    {'motionAssetsVersion': 1, 'root': '/etc', 'files': {}},
                    {'motionAssetsVersion': 1, 'root': 'engines/motion/public', 'files': {'../x.wav': {'sha256': 'a' * 64, 'bytes': 1}}},
                    {'motionAssetsVersion': 1, 'root': 'engines/motion/public', 'files': {'sfx/a.wav': {'sha256': 'x', 'bytes': 1}}},
                    {'motionAssetsVersion': 1, 'root': 'engines/motion/public', 'files': {'sfx/a.wav': {'sha256': 'a' * 64, 'bytes': True}}}):
            with self.assertRaises(ui_assets.AssetError):
                ui_assets.parse(json.dumps(doc).encode())
        with self.assertRaises(ui_assets.AssetError):
            ui_assets.parse(b'{' * 10 + b' ' * ui_assets.MAX_MANIFEST_BYTES)
        with self.assertRaises(ui_assets.AssetError):
            ui_assets.Assets(self.root/'missing.json', self.root).current()


class AssetEndpointTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.repo = Path(self.tmp.name)/'repo'
        manifest = write_repo(self.repo, {'sfx/ding.wav': WAV, 'episodes/fonts/a-b.woff2': FONT})
        self.app.assets = ui_assets.Assets(manifest, self.repo)
        self.version = self.app.assets.current()[0]

    def test_manifest_and_files_need_a_session(self):
        for path in ('/api/assets/motion/manifest', f'/api/assets/motion/{self.version}/sfx/ding.wav'):
            status, _, _ = self.request('GET', path, auth=False)
            self.assertEqual(status, 401)
        status, body = self.json('GET', '/api/assets/motion/manifest')
        self.assertEqual(status, 200)
        self.assertEqual(body['base'], f'/api/assets/motion/{self.version}')
        self.assertEqual(body['files']['sfx/ding.wav'], {'bytes': len(WAV), 'sha256': hashlib.sha256(WAV).hexdigest()})

    def test_serves_with_types_immutable_caching_and_etag_revalidation(self):
        status, headers, data = self.request('GET', f'/api/assets/motion/{self.version}/sfx/ding.wav')
        self.assertEqual((status, data), (200, WAV))
        self.assertEqual(headers['Content-Type'], 'audio/wav')
        self.assertEqual(headers['Cache-Control'], 'private, max-age=31536000, immutable')
        self.assertEqual(headers['Accept-Ranges'], 'bytes')
        self.assertEqual(headers['ETag'], f'"{hashlib.sha256(WAV).hexdigest()}"')
        status, headers, data = self.request('GET', f'/api/assets/motion/{self.version}/sfx/ding.wav', headers={'If-None-Match': headers['ETag']})
        self.assertEqual((status, data), (304, b''))
        status, headers, _ = self.request('GET', f'/api/assets/motion/{self.version}/episodes/fonts/a-b.woff2')
        self.assertEqual((status, headers['Content-Type']), (200, 'font/woff2'))
        status, headers, data = self.request('HEAD', f'/api/assets/motion/{self.version}/sfx/ding.wav')
        self.assertEqual((status, data, headers['Content-Length']), (200, b'', str(len(WAV))))

    def test_ranges(self):
        url = f'/api/assets/motion/{self.version}/sfx/ding.wav'
        for spec, status, body, content_range in (('bytes=0-3', 206, WAV[:4], f'bytes 0-3/{len(WAV)}'),
                                                  ('bytes=-4', 206, WAV[-4:], f'bytes {len(WAV) - 4}-{len(WAV) - 1}/{len(WAV)}'),
                                                  ('bytes=1000-', 206, WAV[1000:], f'bytes 1000-{len(WAV) - 1}/{len(WAV)}'),
                                                  ('bytes=99999-', 416, b'', f'bytes */{len(WAV)}'),
                                                  ('bytes=5-2', 416, b'', f'bytes */{len(WAV)}'),
                                                  ('bytes=' + '9' * 40 + '-', 416, b'', f'bytes */{len(WAV)}'),
                                                  ('bytes=0-1,4-5', 416, b'', f'bytes */{len(WAV)}')):
            got, headers, data = self.request('GET', url, headers={'Range': spec})
            self.assertEqual((got, data, headers.get('Content-Range')), (status, body, content_range), spec)

    def test_traversal_unknown_and_stale_versions_are_404(self):
        for path in (f'/api/assets/motion/{self.version}/sfx/tick.wav', f'/api/assets/motion/{"0" * 16}/sfx/ding.wav',
                     f'/api/assets/motion/{self.version}/sfx/../../../publisher/motion-assets.json',
                     f'/api/assets/motion/{self.version}/sfx/%2e%2e%2fding.wav', f'/api/assets/motion/{self.version}/beds.json',
                     f'/api/assets/motion/{self.version}/episodes/music/../fonts/a-b.woff2'):
            status, _, _ = self.request('GET', path)
            self.assertEqual(status, 404, path)
        status, _, _ = self.request('POST', f'/api/assets/motion/{self.version}/sfx/ding.wav', {})
        self.assertEqual(status, 404)

    def test_missing_manifest_is_503(self):
        self.app.assets = ui_assets.Assets(Path(self.tmp.name)/'none.json', self.repo)
        status, body = self.json('GET', '/api/assets/motion/manifest')
        self.assertEqual(status, 503)
        self.assertNotIn('none.json', json.dumps(body))


if __name__ == '__main__':
    unittest.main()
