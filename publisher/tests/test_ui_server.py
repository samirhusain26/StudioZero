import datetime as dt
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import ui_library
import ui_server
from contract_fixtures import JPEG, FakeProbe, document, episode, write_batch
from runner import Ledger

PASSCODE = 'correct-horse-battery'
SENTINEL = 'sentinel-credential-value-9931'
ORIGIN = 'http://127.0.0.1:8765'


def fake_frame(video, out):
    Path(out).write_bytes(JPEG + b'frame')


def fake_show(unit):
    return {'unit': unit, 'available': True, 'enabled': 'disabled', 'active': 'inactive', 'result': 'success'}


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root/'state'
        self.state.mkdir()
        (self.state/'PAUSED').touch()
        self.config = json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config_path = root/'config.json'
        self.config_path.write_text(json.dumps(self.config))
        Ledger(self.state/'ledger.sqlite3').db.close()
        self.static = root/'static'
        (self.static/'assets').mkdir(parents=True)
        (self.static/'index.html').write_text('<!doctype html><title>Scalar</title>')
        (self.static/'assets/app-abc.js').write_text('console.log(1)')
        creds = root/'credentials'
        creds.mkdir()
        (creds/'UI_PASSCODE').write_text(SENTINEL)  # never used: the app gets PASSCODE explicitly
        self.clock = [dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc).timestamp()]
        self.probe = FakeProbe()
        self.app = ui_server.UiApp(self.state, self.config_path, self.static, PASSCODE, [ORIGIN],
                                   clock=lambda: self.clock[0], show=fake_show, probe=self.probe, frame_grabber=fake_frame)
        self.server = ui_server.make_server(self.app, '127.0.0.1', 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.log = io.StringIO()
        self._stderr, sys.stderr = sys.stderr, self.log

    def tearDown(self):
        sys.stderr = self._stderr
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, auth=True, mutate=None, content_type='application/json'):
        headers = dict(headers or {})
        if auth:
            headers['Authorization'] = f'Bearer {PASSCODE}'
        if mutate if mutate is not None else method in ('POST', 'PUT', 'DELETE'):
            headers.setdefault('X-Scalar-Request', '1')
            headers.setdefault('Origin', ORIGIN)
        if body is not None:
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            headers.setdefault('Content-Type', content_type)
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, dict(response.getheaders()), data

    def json(self, *args, **kwargs):
        status, headers, data = self.request(*args, **kwargs)
        return status, json.loads(data) if data else None


class AuthTests(ServerTestCase):
    def test_session_cookie_login_restore_and_logout(self):
        status, headers, data = self.request('POST', '/api/session', {}, auth=True)
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        self.assertIn('Max-Age=7776000', cookie)
        self.assertNotIn('Secure', cookie)  # the explicitly allowed loopback HTTP test origin
        token = cookie.split('=', 1)[1].split(';', 1)[0]
        self.assertEqual(json.loads(data), {'authenticated': True})
        db_bytes = (self.state/'ui-sessions.sqlite3').read_bytes()
        self.assertNotIn(token.encode(), db_bytes)
        self.assertNotIn(PASSCODE.encode(), db_bytes)
        self.assertEqual(self.request('GET', '/api/library', auth=False, headers={'Cookie': f'scalar_ui_session={token}'})[0], 200)
        # Cookie auth is independent of an unrelated caller's passcode backoff.
        self.app.record_failure('127.0.0.1')
        self.assertEqual(self.request('GET', '/api/library', auth=False, headers={'Cookie': f'scalar_ui_session={token}'})[0], 200)
        # An explicitly supplied wrong Bearer never falls back to a valid cookie.
        self.assertEqual(self.request('GET', '/api/library', auth=False, headers={'Cookie': f'scalar_ui_session={token}', 'Authorization': 'Bearer wrong'})[0], 401)
        status, body = self.json('DELETE', '/api/session', auth=False, headers={'Cookie': f'scalar_ui_session={token}'})
        self.assertEqual(status, 200)
        self.assertFalse(body['authenticated'])
        self.assertEqual(self.request('GET', '/api/library', auth=False, headers={'Cookie': f'scalar_ui_session={token}'})[0], 401)

    def test_session_mutations_keep_csrf_gate(self):
        self.assertEqual(self.request('POST', '/api/session', {}, mutate=False)[0], 403)
        self.assertEqual(self.request('DELETE', '/api/session', auth=False, mutate=False)[0], 403)
        secure_origin = 'https://publisher.example.test'
        self.app.allowed_origins.add(secure_origin)
        status, headers, _ = self.request('POST', '/api/session', {}, headers={'Origin': secure_origin})
        self.assertEqual(status, 200)
        self.assertIn('Secure', headers['Set-Cookie'])

    def test_health_open_api_closed(self):
        status, body = self.json('GET', '/api/health', auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(body, {'ok': True, 'version': ui_server.VERSION,
                                'backoff': {'locked': False, 'retryAfterSeconds': None, 'failures': 0}})
        status, body = self.json('GET', '/api/library', auth=False)
        self.assertEqual(status, 401)
        self.assertEqual(set(body), {'error', 'nextAction'})
        self.assertEqual(self.app.failures, {})  # a missing header is not a guess

    def test_health_reports_only_the_callers_backoff(self):
        for _ in range(6):  # the sixth is refused with 429 and not counted
            self.request('GET', '/api/library', headers={'Authorization': 'Bearer wrong'}, auth=False)
        status, body = self.json('GET', '/api/health', auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(body['backoff'], {'locked': True, 'retryAfterSeconds': 1, 'failures': 5})
        # Another device behind the proxy sees its own clean state, and nothing about loopback.
        status, body = self.json('GET', '/api/health', auth=False, headers={'X-Forwarded-For': '100.64.0.9'})
        self.assertEqual(body['backoff'], {'locked': False, 'retryAfterSeconds': None, 'failures': 0})
        self.assertNotIn('127.0.0.1', json.dumps(body))
        # Health itself never counts as a guess and never needs the passcode.
        self.request('GET', '/api/health', auth=False, headers={'Authorization': 'Bearer wrong'})
        self.assertEqual(self.app.failures['127.0.0.1'][0], 5)

    def test_wrong_passcode_backs_off_per_client(self):
        for _ in range(4):
            self.assertEqual(self.request('GET', '/api/library', headers={'Authorization': 'Bearer wrong'}, auth=False)[0], 401)
        self.assertEqual(self.request('GET', '/api/library', headers={'Authorization': 'Bearer wrong'}, auth=False)[0], 401)
        status, headers, data = self.request('GET', '/api/library')
        self.assertEqual(status, 429)
        self.assertEqual(headers['Retry-After'], '1')
        self.assertEqual(set(json.loads(data)), {'error', 'nextAction'})
        # Behind Tailscale Serve the forwarded device is charged, not loopback.
        status, _, _ = self.request('GET', '/api/library', headers={'X-Forwarded-For': '100.64.0.9'})
        self.assertEqual(status, 200)
        self.clock[0] += 2
        self.assertEqual(self.request('GET', '/api/library')[0], 200)
        self.assertNotIn('127.0.0.1', self.app.failures)

    def test_mutations_need_csrf_header_and_origin(self):
        status, body = self.json('POST', '/api/pause', {}, mutate=False)
        self.assertEqual(status, 403)
        status, body = self.json('POST', '/api/pause', {}, headers={'Origin': 'https://evil.example'})
        self.assertEqual(status, 403)
        status, body = self.json('POST', '/api/pause', {}, headers={'X-Scalar-Request': '1'}, mutate=False)
        self.assertEqual(status, 403)  # no Origin
        status, body = self.json('POST', '/api/pause', {'note': 'checking a post'})
        self.assertEqual(status, 200)
        self.assertEqual(body, {'paused': True, 'alreadyPaused': True, 'at': '2026-10-07T12:00:00Z'})
        self.assertTrue((self.state/'PAUSED').exists())
        (self.state/'PAUSED').unlink()
        self.assertFalse(self.json('POST', '/api/pause', {})[1]['alreadyPaused'])

    def test_security_headers(self):
        for path in ('/api/health', '/', '/assets/app-abc.js'):
            _, headers, _ = self.request('GET', path, auth=False)
            self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.request('GET', '/api/health')[1]['Cache-Control'], 'no-store')
        self.assertIn('immutable', self.request('GET', '/assets/app-abc.js', auth=False)[1]['Cache-Control'])

    def test_static_spa_fallback_and_traversal(self):
        status, headers, data = self.request('GET', '/schedule', auth=False)
        self.assertEqual((status, data), (200, b'<!doctype html><title>Scalar</title>'))
        self.assertEqual(self.request('GET', '/assets/missing.js', auth=False)[0], 404)
        status, _, data = self.request('GET', '/../config.json', auth=False)
        self.assertNotIn(b'channels', data)
        self.assertEqual(self.request('POST', '/', b'{}', auth=False)[0], 405)

    def test_unknown_route_and_bad_json(self):
        self.assertEqual(self.request('GET', '/api/nope')[0], 404)
        self.assertEqual(self.request('POST', '/api/library/approve', b'{', content_type='application/json')[0], 400)
        self.assertEqual(self.request('POST', '/api/library/approve', b'{}', content_type='text/plain')[0], 415)
        status, body = self.json('POST', '/api/library/approve', {'items': [], 'reviewer': ''})
        self.assertEqual(status, 422)
        self.assertEqual(body['problems'][0]['path'], 'reviewer')


class LibraryFlowTests(ServerTestCase):
    def test_batch_upload_review_approve_and_signed_media(self):
        folder, data, blobs = write_batch(Path(self.tmp.name)/'mac', document([episode(1)]))
        status, body = self.json('POST', '/api/library/batches', (folder/'batch.json').read_bytes())
        self.assertEqual(status, 200, body)
        self.assertEqual({e['file'] for e in body['expected']}, set(blobs))
        self.assertEqual({e['name'] for e in body['expected']}, {'scalar-clues-001.mp4', 'scalar-clues-001.jpg'})
        self.assertEqual((body['created'], body['origin'], body['problems']), (True, 'mac', []))
        self.assertEqual(body['merge'], [{'episodeId': 'scalar-clues-001', 'revision': 1, 'outcome': 'added', 'message': None}])
        again = self.json('POST', '/api/library/batches', (folder/'batch.json').read_bytes())[1]
        self.assertEqual((again['created'], again['merge'][0]['outcome']), (False, 'already-imported'))
        # Unexpected names are refused before any byte is stored.
        status, _, _ = self.request('PUT', '/api/library/batches/2026-10-fixture/files/videos/..%2F..%2Fx.mp4',
                                    b'x', content_type='video/mp4')
        self.assertEqual(status, 404)
        status, body = self.json('PUT', '/api/library/batches/2026-10-fixture/files/videos/scalar-clues-002.mp4',
                                 b'x', content_type='video/mp4')
        self.assertEqual(status, 422)
        self.assertTrue(body['problems'])
        # Same size, different bytes: streamed hash reported, nothing stored.
        video = blobs['videos/scalar-clues-001.mp4']
        status, body = self.json('PUT', '/api/library/batches/2026-10-fixture/files/videos/scalar-clues-001.mp4',
                                 b'\0' * len(video), content_type='video/mp4')
        self.assertEqual((status, body['outcome'], body['matched']), (200, 'rejected', False))
        self.assertNotEqual(body['sha256'], body['expectedSha256'])
        self.assertEqual(body['episodeStatus'], 'awaiting_files')
        for name, blob in blobs.items():
            kind = 'video/mp4' if name.endswith('.mp4') else 'image/jpeg'
            status, body = self.json('PUT', f'/api/library/batches/2026-10-fixture/files/{name}', blob, content_type=kind)
            self.assertEqual((body['outcome'], body['matched']), ('stored', True), body)
            self.assertEqual((body['bytes'], body['expectedBytes']), (len(blob), len(blob)))
        self.assertEqual(body['episodeStatus'], 'reviewable')
        status, body = self.json('GET', '/api/library')
        self.assertEqual(body['displayTimezone'], 'America/New_York')
        self.assertEqual(body['batches'][0]['awaitingFiles'], 0)
        ep = body['episodes'][0]
        self.assertEqual((ep['status'], ep['statusLabel'], ep['deletable']), ('reviewable', 'Ready for review', True))
        self.assertEqual(list(ep['platforms']), ['instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok'])
        self.assertEqual(ep['media']['videoStreams'], 1)
        self.assertEqual(ep['episode']['episodeId'], 'scalar-clues-001')
        status, body = self.json('POST', '/api/library/approve', {'items': [{'episodeId': 'scalar-clues-001', 'revision': 1}], 'reviewer': 'owner'})
        result = body['results'][0]
        self.assertEqual((result['ok'], result['status'], result['message']), (True, 'approved', None))
        self.assertIsInstance(result['approvalId'], int)
        ep = self.json('GET', '/api/library')[1]['episodes'][0]
        self.assertEqual(ep['currentApproval']['id'], result['approvalId'])
        # Signed media URLs work without the header, support ranges and expire.
        url = self.app.media_url('videos', data['episodes'][0]['video']['sha256'])
        status, headers, chunk = self.request('GET', url, auth=False, headers={'Range': 'bytes=0-9'})
        self.assertEqual((status, chunk), (206, blobs['videos/scalar-clues-001.mp4'][:10]))
        self.assertTrue(headers['Content-Range'].startswith('bytes 0-9/'))
        self.assertEqual(self.request('GET', url, auth=False, headers={'Range': 'bytes=999999-'})[0], 416)
        self.assertEqual(self.request('GET', url.replace('t=', 't=1'), auth=False)[0], 403)
        self.clock[0] += 3601
        self.assertEqual(self.request('GET', url, auth=False)[0], 403)

    def announce(self, method, path, content_type, length):
        # Headers only: the server must refuse from Content-Length before reading the body.
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        conn.putrequest(method, path)
        for k, v in {'Authorization': f'Bearer {PASSCODE}', 'X-Scalar-Request': '1', 'Origin': ORIGIN,
                     'Content-Type': content_type, 'Content-Length': str(length)}.items():
            conn.putheader(k, v)
        conn.endheaders()
        response = conn.getresponse()
        result = response.status, response.getheader('Connection')
        conn.close()
        return result

    def test_upload_limits(self):
        self.assertEqual(self.announce('POST', '/api/library/batches', 'application/json', 1_000_001), (413, 'close'))
        status, _, _ = self.request('PUT', '/api/library/batches/2026-10-fixture/files/videos/scalar-clues-001.mp4',
                                    b'x', content_type='application/json')
        self.assertEqual(status, 415)

    def test_no_credentials_or_tokens_in_logs(self):
        self.request('GET', self.app.media_url('covers', 'a'*64), auth=False)
        self.request('GET', '/api/library')
        self.request('GET', '/api/library', headers={'Authorization': 'Bearer ' + SENTINEL}, auth=False)
        log = self.log.getvalue()
        self.assertNotIn('t=', log)
        self.assertNotIn(SENTINEL, log)
        self.assertNotIn(PASSCODE, log)


class HardeningTests(ServerTestCase):
    def test_global_backoff_survives_rotating_forwarded_for(self):
        for n in range(ui_server.GLOBAL_FAILURE_LIMIT):
            self.request('GET', '/api/library', headers={'Authorization': 'Bearer wrong', 'X-Forwarded-For': f'10.0.0.{n % 250}, 100.64.{n}.1'}, auth=False)
        status, headers, _ = self.request('GET', '/api/library', headers={'X-Forwarded-For': '100.64.200.1'})
        self.assertEqual(status, 429)
        self.assertLessEqual(len(self.app.failures), ui_server.MAX_TRACKED_CLIENTS)

    def test_transfer_encoding_and_nested_json_refused(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        conn.request('POST', '/api/pause', body=iter([b'{}']), encode_chunked=True,
                     headers={'Authorization': f'Bearer {PASSCODE}', 'X-Scalar-Request': '1', 'Origin': ORIGIN,
                              'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked'})
        response = conn.getresponse()
        self.assertEqual((response.status, response.getheader('Connection')), (411, 'close'))
        conn.close()
        for depth in (5000, 100000):
            status, body = self.json('POST', '/api/library/approve', b'[' * depth + b']' * depth)
            self.assertIn(status, (400, 413, 422))

    def test_delete_refused_while_approval_pending(self):
        (self.state/'approval').mkdir()
        (self.state/'approval/request.json').write_text('{}')
        status, body = self.json('DELETE', '/api/library/episodes/scalar-clues-001/1')
        self.assertEqual(status, 409)

    def test_request_timeout_set(self):
        self.assertEqual(ui_server.Handler.timeout, ui_server.REQUEST_TIMEOUT_SECONDS)


class ActivityEndpointTests(ServerTestCase):
    def test_activity_json_csv_and_validation(self):
        self.assertEqual(self.request('GET', '/api/activity', auth=False)[0], 401)
        status, body = self.json('GET', '/api/activity?limit=5')
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {'generatedAt', 'displayTimezone', 'entries', 'nextBefore'})
        self.assertEqual(body['entries'][0]['event'], 'system.paused')
        status, headers, data = self.request('GET', '/api/activity?format=csv')
        self.assertEqual((status, headers['Content-Type']), (200, 'text/csv; charset=utf-8'))
        self.assertIn('scalar-activity-', headers['Content-Disposition'])
        self.assertTrue(data.startswith(b'id,at,kind,event,severity,title'))
        status, body = self.json('GET', '/api/activity?kind=mail')
        self.assertEqual(status, 422)
        self.assertEqual(body['problems'][0]['code'], 'query')
        self.assertNotIn(SENTINEL.encode(), self.request('GET', '/api/activity?limit=500')[2])


class PassCodeLoadingTests(unittest.TestCase):
    def test_refuses_without_passcode(self):
        old = os.environ.pop('CREDENTIALS_DIRECTORY', None)
        stderr, sys.stderr = sys.stderr, io.StringIO()
        try:
            self.assertEqual(ui_server.main(['--state', '/nonexistent', '--port', '0']), 1)
            self.assertEqual(ui_server.main(['--insecure-dev', '--allowed-origin', 'https://pi.tailnet.example', '--port', '0']), 1)
            # No origin, or one that is not an https host / loopback http, keeps the UI locked.
            for origins in ([], ['--allowed-origin', ''], ['--allowed-origin', 'https://pi.example/path']):
                self.assertEqual(ui_server.main(['--insecure-dev', *origins, '--port', '0']), 1)
            with self.assertRaises(SystemExit):
                ui_server.main(['--host', '0.0.0.0'])
        finally:
            sys.stderr = stderr
            if old is not None:
                os.environ['CREDENTIALS_DIRECTORY'] = old


if __name__ == '__main__':
    unittest.main()
