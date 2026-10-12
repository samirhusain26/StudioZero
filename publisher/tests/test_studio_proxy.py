"""Studio proxy (studio_proxy.py) and the UI's /api/studio/* forwarding, against a fake worker on loopback."""
import http.client
import io
import http.server
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'publisher/tests'))
import studio_proxy
from test_ui_server import ORIGIN, PASSCODE, ServerTestCase

TOKEN = 'k' * 40
BIG = bytes(range(256)) * 4096  # 1 MiB


class FakeWorker(http.server.BaseHTTPRequestHandler):
    """Records what reaches it; answers by path."""
    protocol_version = 'HTTP/1.1'
    seen = []

    def log_message(self, *args):
        pass

    def answer(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else b''
        FakeWorker.seen.append({'method': self.command, 'path': self.path, 'auth': self.headers.get('Authorization'),
                                'range': self.headers.get('Range'), 'body': body, 'host': self.headers.get('Host')})
        if self.path.startswith('/studio/unauthorized') or self.path == '/studio/renders':
            data, status = b'{"error": "Not authorized."}', 401
        elif '/files/' in self.path:
            spec = self.headers.get('Range')
            if spec:
                start, end = (int(x) for x in spec.split('=')[1].split('-'))
                data, status = BIG[start:end + 1], 206
            else:
                data, status = BIG, 200
            self.send_response(status)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Set-Cookie', 'leak=1')
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{len(BIG)}')
            self.end_headers()
            self.wfile.write(data)
            return
        elif self.path == '/studio/settings' and self.command == 'GET':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(studio_proxy.JSON_CAP + 1))
            self.end_headers()
            return
        else:
            data, status = json.dumps({'ok': True, 'path': self.path, 'method': self.command}).encode(), 200
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Server-Secret', 'x')
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = answer


class ProxyCase(unittest.TestCase):
    def setUp(self):
        FakeWorker.seen = []
        self.tmp = tempfile.TemporaryDirectory()
        self.worker_http = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeWorker)
        threading.Thread(target=self.worker_http.serve_forever, daemon=True).start()
        port = self.worker_http.server_address[1]
        self.worker = studio_proxy.Worker(('laptop.tailnet.ts.net', 443), '100.64.0.9', TOKEN)
        # Tests talk plain HTTP to the fake worker on loopback instead of TLS to the tailnet IP.
        patch = mock.patch.object(studio_proxy.Worker, 'connect', lambda w: http.client.HTTPConnection('127.0.0.1', port, timeout=5))
        patch.start()
        self.addCleanup(patch.stop)
        self.socket_path = str(Path(self.tmp.name)/'proxy.sock')
        self.proxy = studio_proxy.serve(self.socket_path, self.worker)
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()
        self.log = mock.patch('sys.stderr', new_callable=io.StringIO)
        self.log.start()

    def tearDown(self):
        self.log.stop()
        self.proxy.shutdown()
        self.proxy.server_close()
        self.worker_http.shutdown()
        self.worker_http.server_close()
        self.tmp.cleanup()

    def via_socket(self, method, path, body=None, headers=None):
        sock = socket.socket(socket.AF_UNIX)
        sock.connect(self.socket_path)
        conn = http.client.HTTPConnection('proxy')
        conn.sock = sock
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, dict(r.getheaders()), data


class ProxyTests(ProxyCase):
    def test_socket_is_group_only(self):
        self.assertEqual(os.stat(self.socket_path).st_mode & 0o777, 0o660)

    def test_allowlisted_routes_reach_the_worker_with_the_token(self):
        status, headers, data = self.via_socket('GET', '/studio/projects/My_Show/events?since=4')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['path'], '/studio/projects/My_Show/events?since=4')
        self.assertEqual(FakeWorker.seen[-1]['auth'], f'Bearer {TOKEN}')
        self.assertEqual(FakeWorker.seen[-1]['host'], 'laptop.tailnet.ts.net')
        self.assertNotIn('Server-Secret', headers)
        status, _, _ = self.via_socket('POST', '/studio/projects/x/run', body=b'{"confirm": null}', headers={'Content-Length': '17'})
        self.assertEqual((status, FakeWorker.seen[-1]['body']), (200, b'{"confirm": null}'))

    def test_everything_else_is_refused_before_the_network(self):
        for method, path in (('GET', '/studio/secret'), ('POST', '/studio/projects/x/delete-everything'), ('GET', '/studio/projects/x/files/../../.env'),
                             ('GET', '/studio/projects/x/events?since=1&x=2'), ('GET', '/studio/projects/x/events?since=abc'),
                             ('PATCH', '/studio/settings'), ('GET', '/studio/projects/..'), ('GET', 'http://evil.example/studio/health'),
                             ('GET', '/studio/renders/x/secret.txt'), ('GET', '//evil.example/studio/health')):
            status, _, _ = self.via_socket(method, path)
            self.assertIn(status, (404, 501), (method, path))
        self.assertEqual(FakeWorker.seen, [])

    def test_media_streams_with_range_and_drops_other_headers(self):
        status, headers, data = self.via_socket('GET', '/studio/projects/x/files/episodes/episode_1/final.mp4', headers={'Range': 'bytes=10-1033'})
        self.assertEqual((status, data, headers['Content-Range']), (206, BIG[10:1034], f'bytes 10-1033/{len(BIG)}'))
        self.assertNotIn('Set-Cookie', headers)
        status, headers, data = self.via_socket('GET', '/studio/projects/x/files/episodes/episode_1/final.mp4')
        self.assertEqual((status, len(data)), (200, len(BIG)))
        self.assertEqual(FakeWorker.seen[0]['range'], 'bytes=10-1033')
        # Range never goes to JSON routes
        self.via_socket('GET', '/studio/projects/x', headers={'Range': 'bytes=0-1'})
        self.assertIsNone(FakeWorker.seen[-1]['range'])

    def test_absurd_content_length_from_a_client_is_refused(self):
        status, _, _ = self.via_socket('POST', '/studio/projects', body=b'{}', headers={'Content-Length': '9' * 5000})
        self.assertEqual(status, 413)

    def test_caps_and_worker_errors(self):
        status, _, _ = self.via_socket('POST', '/studio/projects', body=b'x' * 10, headers={'Content-Length': str(studio_proxy.REQUEST_CAP + 1)})
        self.assertEqual(status, 413)
        status, _, data = self.via_socket('GET', '/studio/settings')  # declared body over the JSON cap
        self.assertEqual(status, 502)
        status, _, data = self.via_socket('GET', '/studio/renders')  # the worker answers 401
        self.assertEqual(status, 502)
        self.assertNotIn(TOKEN.encode(), data)

    def test_offline_and_unconfigured(self):
        self.worker_http.shutdown()
        self.worker_http.server_close()
        status, _, data = self.via_socket('GET', '/studio/health')
        self.assertEqual((status, json.loads(data)['error']), (503, 'Worker offline'))
        self.proxy.worker = None
        status, _, data = self.via_socket('GET', '/studio/health')
        self.assertEqual(status, 503)
        self.assertIn('not set up', json.loads(data)['nextAction'])


class ConfigTests(unittest.TestCase):
    def test_only_a_tailnet_https_name_a_tailnet_ip_and_a_token_configure_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'STUDIO_AGENT_TOKEN').write_text(TOKEN + '\n')
            good = {'STUDIO_WORKER_URL': 'https://laptop.tailnet.ts.net', 'STUDIO_WORKER_ADDR': '100.101.102.103', 'CREDENTIALS_DIRECTORY': tmp}
            worker = studio_proxy.Worker.from_env(good)
            self.assertEqual((worker.url, worker.addr, worker.token), (('laptop.tailnet.ts.net', 443), '100.101.102.103', TOKEN))
            for change in ({'STUDIO_WORKER_URL': 'http://laptop.tailnet.ts.net'}, {'STUDIO_WORKER_URL': 'https://laptop.ts.net/api'},
                           {'STUDIO_WORKER_URL': 'https://user@laptop.ts.net'}, {'STUDIO_WORKER_ADDR': '192.168.1.5'},
                           {'STUDIO_WORKER_ADDR': '8.8.8.8'}, {'STUDIO_WORKER_ADDR': 'laptop'}, {'CREDENTIALS_DIRECTORY': ''},
                           {'STUDIO_WORKER_URL': ''}):
                self.assertIsNone(studio_proxy.Worker.from_env({**good, **change}), change)
            (Path(tmp)/'STUDIO_AGENT_TOKEN').write_text('short')
            self.assertIsNone(studio_proxy.Worker.from_env(good))

    def test_journal_lines_hide_ids_and_files(self):
        self.assertEqual(studio_proxy.route_name('/studio/projects/My_Show/files/a/b.mp4'), '/studio/projects/<id>/files/<path>')


class UiForwardingTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        FakeWorker.seen = []
        self.worker_http = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeWorker)
        threading.Thread(target=self.worker_http.serve_forever, daemon=True).start()
        port = self.worker_http.server_address[1]
        patch = mock.patch.object(studio_proxy.Worker, 'connect', lambda w: http.client.HTTPConnection('127.0.0.1', port, timeout=5))
        patch.start()
        self.addCleanup(patch.stop)
        self.socket_path = str(Path(self.tmp.name)/'proxy.sock')
        self.proxy = studio_proxy.serve(self.socket_path, studio_proxy.Worker(('laptop.tailnet.ts.net', 443), '100.64.0.9', TOKEN))
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()
        self.app.studio_socket = self.socket_path

    def tearDown(self):
        self.proxy.shutdown()
        self.proxy.server_close()
        self.worker_http.shutdown()
        self.worker_http.server_close()
        super().tearDown()

    def test_needs_the_session_and_same_origin_mutations(self):
        status, _, _ = self.request('GET', '/api/studio/health', auth=False)
        self.assertEqual(status, 401)
        status, _, _ = self.request('POST', '/api/studio/projects', {'route': 'recap', 'name': 'x'}, mutate=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request('POST', '/api/studio/projects', {'route': 'recap', 'name': 'x'}, headers={'Origin': 'https://evil.example'})
        self.assertEqual(status, 403)
        self.assertEqual(FakeWorker.seen, [])

    def test_forwards_json_and_media_without_the_passcode(self):
        status, body = self.json('GET', '/api/studio/projects/Show/events?since=2')
        self.assertEqual((status, body['path']), (200, '/studio/projects/Show/events?since=2'))
        self.assertEqual(FakeWorker.seen[-1]['auth'], f'Bearer {TOKEN}')
        status, body = self.json('POST', '/api/studio/projects', {'route': 'recap', 'name': 'Arrival'})
        self.assertEqual((status, json.loads(FakeWorker.seen[-1]['body'])), (200, {'route': 'recap', 'name': 'Arrival'}))
        status, headers, data = self.request('GET', '/api/studio/projects/x/files/final.mp4', headers={'Range': 'bytes=0-99'})
        self.assertEqual((status, data), (206, BIG[:100]))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(PASSCODE, json.dumps(FakeWorker.seen, default=str))

    def test_absurd_content_lengths_are_refused(self):
        status, _, _ = self.request('POST', '/api/studio/projects', b'{}', headers={'Content-Length': '9' * 5000})
        self.assertIn(status, (400, 413))

    def test_the_worker_never_chooses_how_this_origin_serves_its_bytes(self):
        # A worker file that would be HTML or script on this origin is a sandboxed download (security review F1).
        for name in ('x.html', 'x.js', 'x.svg', 'noext'):
            status, headers, _ = self.request('GET', f'/api/studio/projects/x/files/{name}')
            self.assertEqual((status, headers['Content-Type'], headers.get('Content-Disposition')), (200, 'application/octet-stream', 'attachment'), name)
            self.assertIn("sandbox; default-src 'none'", headers.get('Content-Security-Policy', ''))
        status, headers, _ = self.request('GET', '/api/studio/projects/x/files/clips/scene_1.MP4')
        self.assertEqual(headers['Content-Type'], 'video/mp4')
        status, headers, _ = self.request('GET', '/api/studio/projects/x/files/characters/a.png')
        self.assertEqual(headers['Content-Type'], 'image/png')
        status, headers, _ = self.request('GET', '/api/studio/health')
        self.assertEqual(headers['Content-Type'], 'application/json; charset=utf-8')

    def test_offline_paths(self):
        status, body = self.json('GET', '/api/studio/projects/x/nope')
        self.assertEqual(status, 404)
        self.worker_http.shutdown()
        self.worker_http.server_close()
        status, body = self.json('GET', '/api/studio/health')
        self.assertEqual((status, body['error']), (503, 'Worker offline'))
        self.app.studio_socket = str(Path(self.tmp.name)/'missing.sock')
        status, body = self.json('GET', '/api/studio/health')
        self.assertEqual((status, body['error']), (503, 'Worker offline'))
        self.assertIn('proxy is not running', body['nextAction'])
        status, _ = self.json('POST', '/api/studio/projects', b'x' * 10, headers={'Content-Length': '300000'})
        self.assertIn(status, (413, 400))


if __name__ == '__main__':
    unittest.main()


class UnitTests(unittest.TestCase):
    def test_unit_is_sandboxed_and_holds_no_worker_details(self):
        unit = (ROOT/'publisher/deploy/scalar-social-studio-proxy.service').read_text()
        for line in ('DynamicUser=yes', 'Group=scalar-social', 'IPAddressDeny=any', 'MemoryMax=48M', 'NoNewPrivileges=true',
                     'ProtectSystem=strict', 'CapabilityBoundingSet=', 'RuntimeDirectoryMode=0750'):
            self.assertIn(f'\n{line}\n', unit, line)
        for absent in ('IPAddressAllow', 'STUDIO_WORKER_URL=', 'LoadCredential'):
            self.assertNotIn(absent, unit.replace('# STUDIO_WORKER_URL, STUDIO_WORKER_ADDR, LoadCredential=STUDIO_AGENT_TOKEN and IPAddressAllow=<that address>', ''))
        import ui_server
        self.assertIn(f'--socket {ui_server.STUDIO_SOCKET}', unit)

    def test_apply_units_enables_it_and_the_setup_script_never_prints_the_token(self):
        apply_units = (ROOT/'publisher/deploy/apply-units.sh').read_text()
        self.assertIn('scalar-social-autopilot.timer scalar-social-studio-proxy.service; do', apply_units)
        setup = (ROOT/'publisher/deploy/studio-worker.sh').read_text()
        self.assertNotRegex(setup, r'echo[^\n]*\$TOKEN')
        self.assertIn('IPAddressAllow=$ADDR', setup)
        self.assertIn('umask 077', setup)
