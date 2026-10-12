"""Pi proxy to the story worker agent (docs/STUDIO_PLAN.md §6; engines/story/src/agent.py). Stdlib only.

scalar-social-studio-proxy.service runs this on a unix socket that only the UI (group scalar-social) can open. The UI
forwards /api/studio/* here after its own passcode/session and same-origin checks; this process forwards allowlisted
routes to the one worker configured in a Pi-local drop-in (never in git):

    STUDIO_WORKER_URL=https://<laptop>.<tailnet>.ts.net   the worker's Tailscale Serve address (TLS name)
    STUDIO_WORKER_ADDR=100.x.y.z                           its tailnet IP: the only address the unit may reach
    LoadCredential=STUDIO_AGENT_TOKEN:…                    the agent's bearer token (never logged or returned)

Without them, or when the laptop sleeps, every route answers 503 "Worker offline". Requests and responses are size-
capped, time-limited, and streamed in 64 KB chunks (Range passes through for media); worker 401s become 502, so the
UI never mistakes them for its own passcode failing.
"""
import argparse
import http.client
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import ssl
import sys
import time
import urllib.parse

CHUNK = 65536
REQUEST_CAP = 256_000
JSON_CAP = 4_000_000
MEDIA_CAP = 300_000_000
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30
PID = r'[A-Za-z0-9_-]{1,120}'
FILE = r'[A-Za-z0-9_.~/-]{1,300}'
# (method, path pattern, allowed query keys, media?) — anything else is 404 here, before the network.
ROUTES = [
    ('GET', r'/studio/health', {}, False),
    ('GET', r'/studio/projects', {}, False),
    ('POST', r'/studio/projects', {}, False),
    ('GET', rf'/studio/projects/{PID}', {}, False),
    ('DELETE', rf'/studio/projects/{PID}', {}, False),
    ('GET', rf'/studio/projects/{PID}/events', {'since': r'\d{1,9}'}, False),
    ('GET', rf'/studio/projects/{PID}/estimate', {}, False),
    ('POST', rf'/studio/projects/{PID}/(?:run|cancel|approve-script|scene)', {}, False),
    ('PUT', rf'/studio/projects/{PID}/script', {}, False),
    ('GET', rf'/studio/projects/{PID}/artifacts', {'step': r'[a-z_]{1,30}', 'episode': r'\d{1,2}'}, False),
    ('GET', rf'/studio/projects/{PID}/files/{FILE}', {}, True),
    ('GET', r'/studio/renders', {}, False),
    ('GET', r'/studio/renders/[A-Za-z0-9_.~-]{1,300}/(?:video\.mp4|cover\.jpg)', {}, True),
    ('GET', r'/studio/settings', {}, False),
    ('PUT', r'/studio/settings', {}, False),
    ('POST', r'/studio/ideas/random', {}, False),
]
RESPONSE_HEADERS = ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified')
OFFLINE = {'error': 'Worker offline', 'nextAction': 'Wake the laptop that runs the story worker (or start it), then try again.'}
UNCONFIGURED = {'error': 'Worker offline', 'nextAction': 'The story worker is not set up on this Pi yet (publisher/deploy/studio-worker.sh).'}


class Worker:
    """The configured worker: URL host for TLS and Host, pinned IP for the connection, and the token."""
    def __init__(self, url, addr, token):
        self.url, self.addr, self.token = url, addr, token

    @classmethod
    def from_env(cls, env=os.environ):
        url = env.get('STUDIO_WORKER_URL', '').strip()
        addr = env.get('STUDIO_WORKER_ADDR', '').strip()
        token = None
        directory = env.get('CREDENTIALS_DIRECTORY')
        if directory:
            try:
                token = (Path(directory)/'STUDIO_AGENT_TOKEN').read_text().strip() or None
            except OSError:
                token = None
        parts = urllib.parse.urlsplit(url)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            ip = None
        # Only an https tailnet name with no path, and a tailnet (CGNAT or Tailscale ULA) IP.
        ok = (parts.scheme == 'https' and parts.hostname and re.fullmatch(r'[a-z0-9-]+(\.[a-z0-9-]+)+', parts.hostname)
              and parts.path in ('', '/') and not parts.query and not parts.username
              and ip is not None and (ip in ipaddress.ip_network('100.64.0.0/10') or ip in ipaddress.ip_network('fd7a:115c:a1e0::/48'))
              and token is not None and len(token) >= 32)
        return cls((parts.hostname, parts.port or 443), str(ip), token) if ok else None

    def connect(self):
        host, port = self.url
        context = ssl.create_default_context()
        raw = socket.create_connection((self.addr, port), timeout=CONNECT_TIMEOUT)
        try:
            tls = context.wrap_socket(raw, server_hostname=host)
        except Exception:
            raw.close()
            raise
        tls.settimeout(READ_TIMEOUT)
        conn = http.client.HTTPSConnection(host, port, timeout=READ_TIMEOUT, context=context)
        conn.sock = tls
        return conn


class DevWorker(Worker):
    """Development only (--dev-worker, never in the unit): a worker on this machine's loopback over plain HTTP."""
    def connect(self):
        return http.client.HTTPConnection(self.addr, self.url[1], timeout=READ_TIMEOUT)


def match(method, path, query):
    """(media?) for an allowlisted request, else None. Query keys outside the route's list, or bad values, refuse."""
    for route_method, pattern, keys, media in ROUTES:
        if route_method == method and re.fullmatch(pattern, path):
            if '..' in path.split('/'):
                return None
            for key, values in query.items():
                if key not in keys or len(values) != 1 or not re.fullmatch(keys[key], values[0]):
                    return None
            return media
    return None


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'studio-proxy'
    sys_version = ''
    timeout = 60

    def log_message(self, format, *args):  # no client addresses (unix socket) and no query strings
        pass

    def do_GET(self):
        self.handle_one('GET')

    def do_POST(self):
        self.handle_one('POST')

    def do_PUT(self):
        self.handle_one('PUT')

    def do_DELETE(self):
        self.handle_one('DELETE')

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def handle_one(self, method):
        started = time.monotonic()
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        status = 0
        try:
            if self.headers.get('Transfer-Encoding'):
                status = 411
                return self.reply(411, {'error': 'Content-Length required.'})
            length = self.headers.get('Content-Length') or '0'
            if not re.fullmatch(r'\d{1,15}', length) or int(length) > REQUEST_CAP:
                status = 413
                return self.reply(413, {'error': 'Request too large.'})
            body = self.rfile.read(int(length)) if int(length) else None
            # Origin-form targets only ("/studio/…"): no absolute URLs, no "//host" forms.
            media = match(method, path, query) if self.path.startswith('/') and not self.path.startswith('//') and not url.netloc else None
            if media is None:
                status = 404
                return self.reply(404, {'error': 'Not found.'})
            worker = self.server.worker
            if worker is None:
                status = 503
                return self.reply(503, UNCONFIGURED)
            status = self.forward(worker, method, path, url.query, body, media)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        finally:
            sys.stderr.write(f'{method} {route_name(path)} {status} {int((time.monotonic() - started) * 1000)}ms\n')

    def forward(self, worker, method, path, query, body, media):
        headers = {'Authorization': f'Bearer {worker.token}', 'Host': worker.url[0], 'Accept-Encoding': 'identity'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if media and self.headers.get('Range'):
            headers['Range'] = self.headers['Range'][:100]
        try:
            conn = worker.connect()
            conn.request(method, path + (f'?{query}' if query else ''), body=body, headers=headers)
            response = conn.getresponse()
        except (OSError, http.client.HTTPException, ssl.SSLError):
            self.reply(503, OFFLINE)
            return 503
        try:
            status = response.status
            if status == 401:
                self.reply(502, {'error': 'The story worker refused this Pi.', 'nextAction': 'Set the worker token again (publisher/deploy/studio-worker.sh).'})
                return 502
            cap = MEDIA_CAP if media else JSON_CAP
            declared = response.getheader('Content-Length')
            if declared is not None and (not re.fullmatch(r'\d{1,15}', declared) or int(declared) > cap):
                self.reply(502, {'error': 'The story worker sent too much data.'})
                return 502
            self.send_response(status)
            for name in RESPONSE_HEADERS:
                value = response.getheader(name)
                if value is not None:
                    self.send_header(name, value)
            if declared is None:
                self.send_header('Connection', 'close')
                self.close_connection = True
            self.end_headers()
            sent = 0
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                sent += len(chunk)
                if sent > cap:
                    self.close_connection = True
                    break
                self.wfile.write(chunk)
            return status
        except (OSError, http.client.HTTPException):
            self.close_connection = True
            return 504
        finally:
            conn.close()


def route_name(path):
    """The path with ids replaced, for the journal."""
    path = re.sub(rf'^/studio/projects/{PID}', '/studio/projects/<id>', path)
    path = re.sub(r'^/studio/renders/[^/]+', '/studio/renders/<id>', path)
    return re.sub(r'/files/.*$', '/files/<path>', path)[:120]


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, path, worker):
        self.worker = worker
        super().__init__(path, Handler)

    def get_request(self):  # BaseHTTPRequestHandler expects (host, port)-style client addresses
        request, _ = super().get_request()
        return request, ('unix', 0)


def serve(socket_path, worker):
    path = Path(socket_path)
    if path.exists() or path.is_symlink():
        path.unlink()
    old = os.umask(0o117)  # 0660: the proxy user and group scalar-social (the UI) only
    try:
        server = Server(str(path), worker)
    finally:
        os.umask(old)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Pi proxy to the story worker agent (unix socket).')
    parser.add_argument('--socket', default='/run/scalar-social-studio/proxy.sock')
    parser.add_argument('--dev-worker', metavar='127.0.0.1:PORT', help='development only: a local worker over HTTP')
    args = parser.parse_args(argv)
    worker = Worker.from_env()
    if args.dev_worker:
        m = re.fullmatch(r'127\.0\.0\.1:(\d{1,5})', args.dev_worker)
        directory = os.environ.get('CREDENTIALS_DIRECTORY')
        if not m or not directory:
            parser.error('--dev-worker takes 127.0.0.1:PORT and needs CREDENTIALS_DIRECTORY with STUDIO_AGENT_TOKEN')
        worker = DevWorker(('127.0.0.1', int(m.group(1))), '127.0.0.1', (Path(directory)/'STUDIO_AGENT_TOKEN').read_text().strip())
    server = serve(args.socket, worker)
    print(f"Studio proxy on {args.socket}; worker {'configured' if worker else 'not configured (answers Worker offline)'}", file=sys.stderr)
    try:
        server.serve_forever(poll_interval=1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
