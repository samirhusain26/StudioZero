"""Private Pi management UI: stdlib ThreadingHTTPServer on loopback, behind tailnet-only
Tailscale Serve. Never publishes, never enables channels or timers, never writes /etc.

Access mirrors Finalyst: every /api/* route except GET /api/health needs
`Authorization: Bearer <UI_PASSCODE>` (systemd LoadCredential). Mutations also need
`X-Scalar-Request: 1` and an allowed same-origin `Origin`. Wrong passcodes back off per
client. Media for <video>/<img> uses short-lived signed URLs instead of the header.
Responses and logs never carry credential values or vendor response bodies.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import hmac
import http.client
import http.server
import json
import math
import mimetypes
import os
from pathlib import Path
import posixpath
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
# In the repo the shared contract lives in <repo>/contract; on the Pi the installer copies it next to this file.
_CONTRACT = Path(__file__).resolve().parents[2] / 'contract'
if _CONTRACT.is_dir() and str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))
import updater  # noqa: E402
# The commit this process runs, read before the other app modules load so it matches the code in memory.
STARTED_HEAD = updater.running_commit(updater.REPO) if __name__ == '__main__' else None
import ui_sessions  # noqa: E402
import library_contract  # noqa: E402
import ui_assets  # noqa: E402
import ui_catalog  # noqa: E402
import ui_views  # noqa: E402

VERSION = 'ui-2026.10.06'
CSRF_HEADER = 'X-Scalar-Request'
AUTH_FREE_FAILURES = 5
AUTH_MAX_BACKOFF_SECONDS = 900
# 20 wrong passcodes from all clients in 15 minutes locks the API for 15 minutes: a 4-digit PIN
# then needs days of guessing from inside the tailnet.
GLOBAL_FAILURE_LIMIT = 20
MAX_TRACKED_CLIENTS = 256
REQUEST_TIMEOUT_SECONDS = 60
LOOPBACK = {'127.0.0.1', '::1', 'localhost'}
JSON_CAP = 256_000
MEDIA_TTL = 3600
STUDIO_SOCKET = '/run/scalar-social-studio/proxy.sock'  # scalar-social-studio-proxy.service (studio_proxy.py)
STUDIO_BODY_CAP = 256_000
STUDIO_TIMEOUT = 60
STUDIO_HEADERS = ('Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified')
# The worker never chooses how this origin serves its bytes (security review F1): JSON routes are JSON, worker files
# get a type from this list by suffix or are downloads, and every studio response is a sandboxed, script-less document.
STUDIO_FILE_TYPES = {'.mp4': 'video/mp4', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                     '.json': 'application/json', '.txt': 'text/plain; charset=utf-8'}
STUDIO_CSP = "sandbox; default-src 'none'; frame-ancestors 'none'"
# Studio › Export (in-browser rendering): the mastered mix is fetched from a blob: URL, the encoders run in blob:
# workers and the AAC fallback encoder is WebAssembly ('wasm-unsafe-eval' allows compiling Wasm, not JS eval).
# Nothing may connect anywhere but this origin (Remotion's usage ping to its own site stays blocked).
CSP = ("default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self'; "
       "script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
SECURITY_HEADERS = {'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                    'X-Frame-Options': 'DENY', 'Cross-Origin-Opener-Policy': 'same-origin',
                    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()'}
SHA = r'[0-9a-f]{64}'
APP_DIR = Path(__file__).resolve().parent  # /opt/scalar-social/repo/publisher/app (git) or /opt/scalar-social/scripts/social (copy)
# -I: root never loads PYTHON* variables or a user site (.pth, usercustomize) from scalar-social's HOME;
# -B: root never writes __pycache__ into the checkout.
ACTIVATE_COMMAND = f'sudo python3 -I -B {APP_DIR}/activate.py --apply --confirm-zero-spend'
CHECK_COMMAND = f'sudo python3 -I -B {APP_DIR}/activate.py --check'



def studio_content_type(path):
    """(Content-Type, attachment?) for a forwarded studio path: files by suffix from STUDIO_FILE_TYPES, else a download."""
    if re.match(r'/studio/projects/[^/]+/files/', path) or re.match(r'/studio/renders/[^/]+/[^/]+$', path):
        suffix = os.path.splitext(path)[1].lower()
        known = STUDIO_FILE_TYPES.get(suffix)
        return (known, False) if known else ('application/octet-stream', True)
    return 'application/json; charset=utf-8', False

class ApiError(Exception):
    """Non-2xx reply with body ApiError {error, nextAction, problems?} (types.ts)."""
    def __init__(self, status, message, next_action=None, problems=None, retry=None, code=None):
        super().__init__(message)
        self.status, self.message, self.next_action = status, message, next_action
        self.problems, self.retry, self.code = problems, retry, code

    def body(self):
        body = {'error': self.message, 'nextAction': self.next_action}
        if self.code is not None:
            body['code'] = self.code
        if self.problems is not None:
            body['problems'] = self.problems
        return body


class Reply:
    """JSON body with a non-200 success status (e.g. 202 for a queued approval request)."""
    def __init__(self, status, body):
        self.status, self.body = status, body


class Counting:
    """Request body reader that remembers how much was consumed (keep-alive safety) and hashes it."""
    def __init__(self, stream):
        self.stream, self.count, self.digest = stream, 0, hashlib.sha256()

    def read(self, size=-1):
        chunk = self.stream.read(size)
        self.count += len(chunk)
        self.digest.update(chunk)
        return chunk


class Raw:
    """Non-JSON response (file download, media, CSV)."""
    def __init__(self, body=b'', content_type='application/octet-stream', status=200, headers=None, path=None, length=None, offset=0):
        self.body, self.content_type, self.status = body, content_type, status
        self.headers, self.path, self.length, self.offset = headers or {}, path, length, offset


def load_passcode():
    directory = os.environ.get('CREDENTIALS_DIRECTORY')
    if not directory:
        return None
    try:
        value = (Path(directory)/'UI_PASSCODE').read_text().strip()
    except OSError:
        return None
    return value or None


class UiApp:
    def __init__(self, state, config_path, static_dir, passcode, allowed_origins, *, clock=time.time,
                 media_key=None, show=None, probe=None, frame_grabber=None, run=None, repo=None, running=None,
                 update_state=None, catalog_path=None, assets=None, studio_socket=STUDIO_SOCKET):
        import ui_health
        import ui_library
        self.state, self.config_path = Path(state), Path(config_path)
        self.static_dir = Path(static_dir).resolve() if static_dir else None
        self.passcode, self.allowed_origins = passcode, set(allowed_origins)
        self.sessions = ui_sessions.Sessions(self.state, clock)
        self.clock = clock
        self.media_key = media_key or secrets.token_bytes(32)
        self.show = show or ui_health.systemctl_show
        if run is None:
            import activate
            run = activate.system
        self.run = run
        self.probe = probe or library_contract.run_ffprobe
        self.frame_grabber = frame_grabber or ui_library.frame_grab
        self.failures, self.failures_lock = {}, threading.Lock()
        # All clients together: a loopback process could rotate X-Forwarded-For to dodge per-client backoff.
        self.global_failures = []
        # SQLite serializes writers anyway; one lock keeps import/approve sequences atomic.
        self.write_lock = threading.Lock()
        self.legacy_status = {'state': 'not-started'}
        # Self-update: the checkout this process runs from and its commit, read once at start (None = copy install).
        self.repo, self.running = Path(repo) if repo else updater.REPO, running
        # The update user's folder (status.json, units-applied.json; this process writes only its inbox/).
        self.update_state = Path(update_state) if update_state else self.state.parent/'scalar-social-update'
        # publisher/catalog.json in this checkout (Mac-generated, committed): GET /api/catalog.
        self.catalog = ui_catalog.Cache(catalog_path or ui_catalog.PATH)
        # engines/motion/public files listed in publisher/motion-assets.json: GET /api/assets/motion/…
        self.assets = assets or ui_assets.Assets()
        # /api/studio/* goes to the story worker through the proxy's unix socket (never directly to the network).
        self.studio_socket = studio_socket

    # --- state helpers -------------------------------------------------------------
    def config(self):
        try:
            return json.loads(self.config_path.read_text())
        except (OSError, ValueError):
            raise ApiError(503, 'Publisher configuration is unreadable.', 'Check /etc/scalar-social/config.json permissions (0640 root:scalar-social).') from None

    @contextlib.contextmanager
    def index(self):
        import ui_library
        db = ui_library.open_index(self.state)
        try:
            with db:
                yield db
        finally:
            db.close()

    def media_url(self, kind, sha):
        expires = int(self.clock()) + MEDIA_TTL
        ext = 'mp4' if kind == 'videos' else 'jpg'
        return f'/api/media/{kind}/{sha}.{ext}?t={expires}.{self._sign(kind, sha, expires)}'

    def _sign(self, kind, sha, expires):
        return hmac.new(self.media_key, f'{kind}:{sha}:{expires}'.encode(), hashlib.sha256).hexdigest()

    def media_token_ok(self, kind, sha, token):
        try:
            expires, signature = token.split('.', 1)
            expires = int(expires)
        except (AttributeError, ValueError):
            return False
        return expires >= self.clock() and hmac.compare_digest(signature, self._sign(kind, sha, expires))

    # --- auth ----------------------------------------------------------------------
    def client_key(self, peer, forwarded):
        # Behind Tailscale Serve every request arrives from loopback; the proxy's
        # appended X-Forwarded-For hop names the device.
        if forwarded and peer in LOOPBACK:
            return forwarded.rsplit(',', 1)[-1].strip() or peer
        return peer

    def backoff(self, client):
        """(failures, seconds to wait) for one client only."""
        with self.failures_lock:
            count = self.failures.get(client, (0, 0.0))[0]
        return count, self.retry_after(client)

    def retry_after(self, client):
        now = self.clock()
        with self.failures_lock:
            locked = self.failures.get(client, (0, 0.0))[1]
            self.global_failures = [t for t in self.global_failures if t > now - AUTH_MAX_BACKOFF_SECONDS]
            if len(self.global_failures) >= GLOBAL_FAILURE_LIMIT:
                locked = max(locked, self.global_failures[0] + AUTH_MAX_BACKOFF_SECONDS)
        return math.ceil(locked - now) if locked > now else 0

    def record_failure(self, client):
        with self.failures_lock:
            now = self.clock()
            count = self.failures.get(client, (0, 0.0))[0] + 1
            backoff = min(AUTH_MAX_BACKOFF_SECONDS, 2 ** (count - AUTH_FREE_FAILURES)) if count >= AUTH_FREE_FAILURES else 0
            self.failures[client] = (count, now + backoff)
            self.global_failures.append(now)
            if len(self.failures) > MAX_TRACKED_CLIENTS:
                # Bounded memory: forget the client whose lock ended longest ago.
                del self.failures[min(self.failures, key=lambda k: self.failures[k][1])]

    def clear_failures(self, client):
        with self.failures_lock:
            self.failures.pop(client, None)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    # A stalled client (e.g. a paused upload) cannot hold a connection or the write lock forever.
    timeout = REQUEST_TIMEOUT_SECONDS
    server_version = 'scalar-social-ui'
    sys_version = ''
    app = None  # set by make_server

    # Never log query strings (signed media tokens) or headers.
    def log_request(self, code='-', size='-'):
        sys.stderr.write(f'{self.command} {urllib.parse.urlsplit(self.path).path} {code}\n')

    def log_error(self, format, *args):
        sys.stderr.write(f'{self.command or "-"} request error {args[0] if args else ""}\n')

    def do_GET(self):
        self.dispatch('GET')

    def do_HEAD(self):
        self.dispatch('HEAD')

    def do_POST(self):
        self.dispatch('POST')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_DELETE(self):
        self.dispatch('DELETE')

    # --- plumbing ------------------------------------------------------------------
    def dispatch(self, method):
        self.body_consumed = method in ('GET', 'HEAD', 'DELETE') and not self.headers.get('Content-Length')
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        query = urllib.parse.parse_qs(url.query, keep_blank_values=False)
        try:
            if self.headers.get('Transfer-Encoding'):
                # Only Content-Length bodies are read; anything else would desynchronize keep-alive.
                self.body_consumed = False
                raise ApiError(411, 'Content-Length required.')
            if not path.startswith('/api/'):
                if method not in ('GET', 'HEAD'):
                    raise ApiError(405, 'Method not allowed.')
                return self.send_raw(self.static(path))
            if path == '/api/health' and method in ('GET', 'HEAD'):
                return self.send_json(ui_views.health(VERSION, *self.app.backoff(self.client())))
            if path == '/api/session':
                if method == 'GET':
                    token = self.cookie_token()
                    return self.send_json({'authenticated': bool(self.app.sessions.valid(token, self.app.passcode))})
                self.check_mutation()
                if method == 'POST':
                    self.read_json()
                token = self.cookie_token()
                if method == 'POST':
                    supplied = self.headers.get('Authorization', '')
                    expected = f'Bearer {self.app.passcode}' if self.app.passcode else None
                    client = self.client()
                    wait = self.app.retry_after(client)
                    if wait:
                        raise ApiError(429, f'Too many wrong passcodes. Try again in {wait} seconds.',
                                       'Wait, then enter the passcode again.', retry=wait)
                    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
                        if supplied:
                            self.app.record_failure(client)
                        raise ApiError(401, 'That passcode was not accepted.' if supplied else 'Passcode required.', 'Enter the UI passcode.')
                    self.app.clear_failures(client)
                    token = self.app.sessions.create(self.app.passcode)
                    secure = self.session_cookie_secure()
                    return self.send_json({'authenticated': True}, extra={'Set-Cookie': f'scalar_ui_session={token}; Path=/api; Max-Age={ui_sessions.TTL_SECONDS}; HttpOnly; SameSite=Strict' + ('; Secure' if secure else '')})
                if method == 'DELETE':
                    self.app.sessions.revoke(token)
                    secure = self.session_cookie_secure()
                    return self.send_json({'authenticated': False}, extra={'Set-Cookie': 'scalar_ui_session=; Path=/api; Max-Age=0; HttpOnly; SameSite=Strict' + ('; Secure' if secure else '')})
                raise ApiError(405, 'Method not allowed.')
            media = re.fullmatch(rf'/api/media/(videos|covers)/({SHA})\.(mp4|jpg)', path)
            if media and method in ('GET', 'HEAD'):
                kind, sha, ext = media.groups()
                if (kind == 'videos') != (ext == 'mp4') or not self.app.media_token_ok(kind, sha, (query.get('t') or [''])[0]):
                    raise ApiError(403, 'Media link expired.', 'Reload the page.')
                return self.send_raw(self.media(kind, sha))
            self.authenticate()
            if method in ('POST', 'PUT', 'DELETE'):
                self.check_mutation()
            if path.startswith('/api/studio/'):
                return self.studio(method, path[len('/api'):], url.query)
            for route_method, pattern, name in ROUTES:
                if route_method == method or (route_method == 'GET' and method == 'HEAD'):
                    match = re.fullmatch(pattern, path)
                    if match:
                        result = getattr(self, name)(*match.groups(), query=query)
                        if isinstance(result, Raw):
                            return self.send_raw(result)
                        if isinstance(result, Reply):
                            return self.send_json(result.body, result.status)
                        return self.send_json(result)
            raise ApiError(404, 'Not found.')
        except ApiError as error:
            self.send_json(error.body(), error.status, {'Retry-After': str(error.retry)} if error.retry else None)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            # Internal details stay on the Pi; the owner gets a plain message.
            sys.stderr.write(f'{method} {path} internal error {sys.exc_info()[0].__name__}\n')
            self.send_json({'error': 'The Pi could not complete this request.', 'nextAction': 'Try again; if it repeats, check the UI service log on the Pi.'}, 500)

    def client(self):
        return self.app.client_key(self.client_address[0], self.headers.get('X-Forwarded-For', ''))

    def cookie_token(self):
        for part in self.headers.get('Cookie', '').split(';'):
            key, sep, value = part.strip().partition('=')
            if sep and key == 'scalar_ui_session':
                return value
        return None

    def session_cookie_secure(self):
        origin = self.headers.get('Origin', '')
        parts = urllib.parse.urlsplit(origin)
        if parts.scheme == 'https':
            return True
        return not (origin in self.app.allowed_origins and parts.scheme == 'http' and parts.hostname in LOOPBACK)

    def authenticate(self):
        app = self.app
        client = self.client()
        supplied = self.headers.get('Authorization', '')
        expected = f'Bearer {app.passcode}' if app.passcode else None
        if expected is None:
            return  # --insecure-dev on loopback only
        if supplied:
            wait = app.retry_after(client)
            if wait:
                raise ApiError(429, f'Too many wrong passcodes. Try again in {wait} seconds.',
                               'Wait, then enter the passcode again.', retry=wait)
            if not hmac.compare_digest(supplied.encode(), expected.encode()):
                if supplied:
                    app.record_failure(client)
                raise ApiError(401, 'That passcode was not accepted.', 'Enter the UI passcode.')
            app.clear_failures(client)
            return
        if app.sessions.valid(self.cookie_token(), app.passcode):
            return
        raise ApiError(401, 'Passcode required.', 'Sign in again.')

    def check_mutation(self):
        if self.headers.get(CSRF_HEADER) != '1':
            raise ApiError(403, f'Missing {CSRF_HEADER} header.', 'Reload the page and try again.')
        if self.headers.get('Origin') not in self.app.allowed_origins:
            raise ApiError(403, 'Request did not come from this site.', 'Open the UI from its own address and try again.')

    def headers_common(self, api=True, csp=None):
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, csp if csp and key == 'Content-Security-Policy' else value)
        if api:
            self.send_header('Cache-Control', 'no-store')

    def finish_body(self):
        if not self.body_consumed:
            # An unread request body would desynchronize keep-alive; close instead.
            self.close_connection = True

    def send_json(self, value, status=200, extra=None):
        body = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        self.finish_body()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        if self.close_connection:
            self.send_header('Connection', 'close')
        self.headers_common()
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_raw(self, raw):
        self.finish_body()
        length = raw.length if raw.path is not None else len(raw.body)
        self.send_response(raw.status)
        if raw.status not in (204, 304):  # 204 and 304 carry no body and no Content-Length
            self.send_header('Content-Type', raw.content_type)
            self.send_header('Content-Length', str(length))
        for key, value in raw.headers.items():
            self.send_header(key, value)
        if self.close_connection:
            self.send_header('Connection', 'close')
        self.headers_common(api='Cache-Control' not in raw.headers)
        self.end_headers()
        if self.command == 'HEAD':
            return
        if raw.path is None:
            self.wfile.write(raw.body)
            return
        with open(raw.path, 'rb') as handle:
            handle.seek(raw.offset)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def content_length(self, cap):
        value = self.headers.get('Content-Length')
        if value is None:
            raise ApiError(411, 'Content-Length required.', 'Choose the file again.')
        if not re.fullmatch(r'\d{1,15}', value):
            self.close_connection = True
            raise ApiError(400, 'Content-Length must be a whole number of bytes.', 'Reload the page and try again.')
        length = int(value)
        if length > cap:
            raise ApiError(413, f'Too large: the limit is {cap:,} bytes.')
        return length

    def read_json(self, cap=JSON_CAP):
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise ApiError(415, 'Send JSON.')
        length = self.content_length(cap)
        raw = self.rfile.read(length)
        self.body_consumed = len(raw) == length
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise ApiError(400, 'The request was not valid JSON.', 'Reload the page and try again.') from None
        try:  # JSON may escape lone surrogates (\ud800), which no UTF-8 store or response can hold
            json.dumps(value, ensure_ascii=False).encode('utf-8')
        except UnicodeEncodeError:
            raise ApiError(422, 'The text contains characters that cannot be stored (unpaired surrogates).',
                           'Remove the unusual characters, then try again.') from None
        return value

    def upload(self, content_type, cap):
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != content_type:
            raise ApiError(415, f'Send the file as {content_type}.')
        return self.content_length(cap)

    # --- static and media ------------------------------------------------------------
    def static(self, path):
        root = self.app.static_dir
        if root is None or not root.is_dir():
            raise ApiError(404, 'The UI has not been built on this Pi.')
        relative = posixpath.normpath('/' + path).lstrip('/') or 'index.html'
        if relative == 'MANIFEST.json':  # build metadata in a git checkout; the copy installer never shipped it
            raise ApiError(404, 'Not found.')
        candidate = (root/relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            if '.' in Path(relative).name and not relative.endswith('.html'):
                raise ApiError(404, 'Not found.')
            candidate = root/'index.html'
        cache = ('public, max-age=31536000, immutable' if candidate.parent.name == 'assets' and candidate.parent.parent == root
                 else 'no-cache')
        content_type = mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type in ('application/javascript', 'application/json'):
            content_type += '; charset=utf-8'
        return Raw(path=candidate, length=candidate.stat().st_size, content_type=content_type, headers={'Cache-Control': cache})

    def media(self, kind, sha):
        with self.app.index() as db:
            table = 'videos' if kind == 'videos' else 'covers'
            row = db.execute(f'SELECT path FROM {table} WHERE sha256=?', (sha,)).fetchone()
        if not row:
            raise ApiError(404, 'Not found.')
        path = (self.app.state/row[0]).resolve()
        if not path.is_relative_to(self.app.state.resolve()) or not path.is_file():
            raise ApiError(404, 'Not found.')
        content_type = 'video/mp4' if kind == 'videos' else 'image/jpeg'
        return self.ranged(path, path.stat().st_size, content_type, {'Cache-Control': 'private, max-age=3600'})

    def ranged(self, path, size, content_type, headers):
        """A file response honouring one `Range: bytes=…` request; send_raw streams it in 64 KB chunks."""
        headers = {'Accept-Ranges': 'bytes', **headers}
        spec = self.headers.get('Range')
        if not spec:
            return Raw(path=path, length=size, content_type=content_type, headers=headers)
        match = re.fullmatch(r'bytes=(\d{0,15})-(\d{0,15})', spec.strip())
        if not match or match.groups() == ('', ''):
            return Raw(b'', content_type, 416, {**headers, 'Content-Range': f'bytes */{size}'})
        first, last = match.groups()
        if first == '':
            start, end = max(0, size-int(last)), size-1
        else:
            start, end = int(first), min(int(last) if last else size-1, size-1)
        if start > end or start >= size:
            return Raw(b'', content_type, 416, {**headers, 'Content-Range': f'bytes */{size}'})
        return Raw(path=path, offset=start, length=end-start+1, content_type=content_type, status=206,
                   headers={**headers, 'Content-Range': f'bytes {start}-{end}/{size}'})

    # --- Studio worker (through studio_proxy.py, which holds the allowlist and the worker's address and token) ---
    def studio(self, method, path, query_string):
        if method not in ('GET', 'HEAD', 'POST', 'PUT', 'DELETE'):
            raise ApiError(405, 'Method not allowed.')
        body = None
        if self.headers.get('Content-Length') not in (None, '0'):
            body = json.dumps(self.read_json(STUDIO_BODY_CAP)).encode()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(STUDIO_TIMEOUT)
        try:
            sock.connect(self.app.studio_socket)
        except OSError:
            sock.close()
            raise ApiError(503, 'Worker offline', 'The Studio proxy is not running on this Pi; run apply-units.sh, then try again.') from None
        conn = http.client.HTTPConnection('studio-proxy', timeout=STUDIO_TIMEOUT)
        conn.sock = sock
        headers = {'Content-Type': 'application/json'} if body is not None else {}
        if self.headers.get('Range'):
            headers['Range'] = self.headers['Range'][:100]
        started = False
        try:
            try:
                conn.request('GET' if method == 'HEAD' else method, path + (f'?{query_string}' if query_string else ''), body=body, headers=headers)
                response = conn.getresponse()
            except (OSError, http.client.HTTPException):
                raise ApiError(504, 'The story worker did not answer in time.', 'Try again; if it repeats, check the laptop.') from None
            started = True
            self.finish_body()
            self.send_response(response.status)
            for name in STUDIO_HEADERS:
                value = response.getheader(name)
                if value is not None:
                    self.send_header(name, value)
            content_type, attachment = studio_content_type(path)
            self.send_header('Content-Type', content_type)
            if attachment:
                self.send_header('Content-Disposition', 'attachment')
            if response.getheader('Content-Length') is None:
                self.close_connection = True
                self.send_header('Connection', 'close')
            self.headers_common(csp=STUDIO_CSP)
            self.end_headers()
            while method != 'HEAD':
                chunk = response.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (OSError, http.client.HTTPException):
            if not started:
                raise
            self.close_connection = True  # mid-stream: the client sees a short body and retries
        finally:
            conn.close()

    # --- endpoints (bodies shaped by ui_views to publisher/ui/src/api/types.ts) ----------------------
    def motion_assets(self):
        try:
            return self.app.assets.current()
        except ui_assets.AssetError:
            raise ApiError(503, 'The motion assets are unavailable on this Pi.',
                           'Run Settings → Update; if it repeats, check the UI service log on the Pi.') from None

    def get_motion_manifest(self, query):
        version, files = self.motion_assets()
        return {'version': version, 'base': f'/api/assets/motion/{version}',
                'files': {path: {'bytes': entry['bytes'], 'sha256': entry['sha256']} for path, entry in sorted(files.items())}}

    def get_motion_asset(self, version, path, query):
        self.motion_assets()
        try:
            found = self.app.assets.lookup(version, path)
        except ui_assets.AssetError:
            raise ApiError(503, 'A motion asset differs from its manifest on this Pi.', 'Run Settings → Update.') from None
        if found is None:
            raise ApiError(404, 'Not found.', 'Reload the page: the assets may have been updated.')
        file, size, content_type, sha = found
        etag = f'"{sha}"'
        headers = {'Cache-Control': 'private, max-age=31536000, immutable', 'ETag': etag}
        if etag in (tag.strip() for tag in self.headers.get('If-None-Match', '').split(',')):
            return Raw(b'', content_type, 304, headers)
        return self.ranged(file, size, content_type, headers)

    def get_catalog(self, query):
        try:
            raw, _catalog, sha = self.app.catalog.get()
        except ui_catalog.CatalogError:
            raise ApiError(503, 'The studio catalog is unavailable on this Pi.',
                           'Run Settings → Update; if it repeats, check the UI service log on the Pi.') from None
        etag = f'"{sha}"'
        headers = {'Cache-Control': 'private, no-cache', 'ETag': etag}
        if etag in (tag.strip() for tag in self.headers.get('If-None-Match', '').split(',')):
            return Raw(b'', 'application/json', 304, headers)
        return Raw(raw, 'application/json; charset=utf-8', headers=headers)

    def now(self):
        return dt.datetime.fromtimestamp(self.app.clock(), dt.timezone.utc)

    def zone(self, config):
        try:
            return ZoneInfo(ui_views.zone_name(config))
        except (KeyError, ValueError, OSError):
            return ZoneInfo('UTC')

    def approval(self, config):
        """(ApprovalState, raw approval_state, manifest sha, manifest)."""
        import ui_approval
        try:
            sha, manifest = ui_approval.current_manifest(self.app.state)
        except ValueError:
            sha, manifest = None, None
        raw = ui_approval.approval_state(self.app.state)
        return ui_views.approval(raw, config, manifest, self.now()), raw, sha, manifest

    def ledger(self, sql, params=()):
        import ui_health
        with ui_health.ledger_ro(self.app.state) as db:
            return [] if db is None else [dict(r) for r in db.execute(sql, params)]

    def get_dashboard(self, query):
        import ui_health
        config = self.app.config()
        state, _, _, manifest = self.approval(config)
        raw = ui_health.dashboard(self.app.state, self.app.config_path, self.now(), self.app.show)
        return ui_views.dashboard(raw, config, state, self.now(), self.standing(config, manifest))

    def manifest_rows(self, config, mjobs):
        """(ledger id per manifest job, {ledger id: row}) for the approved manifest (read-only)."""
        import ui_approval
        channels = config.get('channels') or {}
        ids = [ui_approval.ledger_key(j.get('platform'), (channels.get(j.get('platform')) or {}).get('accountId'), j.get('slot'))
               for j in mjobs]
        rows = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start+500]
            for r in self.ledger(f"SELECT * FROM jobs WHERE id IN ({','.join('?'*len(chunk))})", chunk):
                rows[r['id']] = r
        return ids, rows

    def standing(self, config, manifest):
        import ui_library
        today = self.now().astimezone(self.zone(config)).date()
        with self.app.index() as db:
            raw = ui_library.standing(db, today)
            raw['nextBatchId'] = ui_library.next_batch_id(db, self.now())
            for kind in ('brief', 'retro'):
                note = ui_library.last_note(db, kind)
                raw[f'last{kind.title()}At'] = note and note['uploadedAt']
        since = ui_views.iso_utc(self.now() - dt.timedelta(days=7))
        raw['postedLast7Days'] = sum((ui_views.iso_utc(r['published_at']) or '') >= since for r in self.ledger(
            "SELECT published_at FROM jobs WHERE status='confirmed' AND episode NOT LIKE '%#%'"))
        mjobs = (manifest or {}).get('jobs') or []
        ids, rows = self.manifest_rows(config, mjobs)
        return ui_views.standing(raw, ui_views.next_posts(mjobs, rows, ids, self.now()))

    def get_library(self, query):
        import ui_library
        config = self.app.config()
        today = self.now().astimezone(self.zone(config)).date()
        with self.app.index() as db:
            raw = ui_library.library_view(db, self.app.state, self.app.media_url, today)
        rows = [(r['platform'], r['account'], r['slot'], r['episode'], r['status'])
                for r in self.ledger('SELECT platform, account, slot, episode, status FROM jobs')]
        return ui_views.library(raw, ui_views.posted_records(rows), config, self.now())

    def post_batch(self, query):
        import ui_library
        length = self.content_length(library_contract.MAX_BATCH_JSON_BYTES)
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise ApiError(415, 'Send batch.json as JSON.', None)
        raw = self.rfile.read(length)
        self.body_consumed = len(raw) == length
        with self.app.write_lock, self.app.index() as db:
            result = ui_library.import_batch_json(db, self.app.state, raw, self.now())
        if not result.get('batchId'):
            raise ApiError(422, 'batch.json was not accepted.', 'Choose batch.json from a finalized batch folder on the Mac.',
                           ui_views.problems(result.get('problemItems') or result.get('problems')))
        return ui_views.batch_import(result)

    def put_batch_file(self, batch_id, folder, name, query):
        import ui_library
        kind = 'video/mp4' if folder == 'videos' else 'image/jpeg'
        cap = library_contract.MAX_VIDEO_BYTES if folder == 'videos' else library_contract.MAX_COVER_BYTES
        length = self.upload(kind, cap)
        body = Counting(self.rfile)
        with self.app.write_lock, self.app.index() as db:
            result = ui_library.accept_batch_file(db, self.app.state, batch_id, f'{folder}/{name}', body, length,
                                                  self.app.probe, self.app.frame_grabber, self.now())
        self.body_consumed = body.count == length
        if not result.get('episodeId'):
            raise ApiError(422, (result.get('problems') or ['This file is not part of the batch.'])[0],
                           'Upload only the files that batch.json lists.',
                           ui_views.problems(result.get('problems'), 'file', f'{folder}/{name}'))
        computed = body.digest.hexdigest() if body.count == length else None
        return ui_views.file_upload(result, computed, length)

    def post_legacy(self, query):
        self.start_legacy()
        return {'legacy': self.app.legacy_status}

    def start_legacy(self):
        app = self.app
        if app.legacy_status.get('state') == 'running':
            return

        def work():
            import ui_library
            app.legacy_status = {'state': 'running'}
            try:
                with app.write_lock, app.index() as db:
                    result = ui_library.register_legacy(db, app.state, app.probe, app.frame_grabber,
                                                        dt.datetime.fromtimestamp(app.clock(), dt.timezone.utc))
                app.legacy_status = {'state': 'done', 'result': result}
            except Exception as error:
                app.legacy_status = {'state': 'failed', 'message': 'Existing Pi media could not be registered.',
                                     'category': type(error).__name__}
        threading.Thread(target=work, daemon=True).start()

    def decision_body(self):
        body = self.read_json()
        if not isinstance(body, dict):
            raise ApiError(422, 'Send items and a reviewer.', None, [])
        reviewer = body.get('reviewer')
        reviewer = reviewer.strip() if isinstance(reviewer, str) else ''
        if not reviewer or len(reviewer) > 80:
            raise ApiError(422, 'Enter the reviewer name.', None,
                           [{'code': 'reviewer', 'path': 'reviewer', 'message': 'Enter a reviewer name (1–80 characters).'}])
        items = body.get('items')
        if not isinstance(items, list) or not items:
            raise ApiError(422, 'Choose at least one episode.', None,
                           [{'code': 'items', 'path': 'items', 'message': 'Choose at least one episode.'}])
        note = body.get('note')
        if note is not None and (not isinstance(note, str) or len(note) > 500):
            raise ApiError(422, 'The note must be text of at most 500 characters.', None,
                           [{'code': 'note', 'path': 'note', 'message': 'At most 500 characters.'}])
        return items, reviewer, note or None

    def statuses(self, db):
        return {(r[0], r[1]): r[2] for r in db.execute('SELECT episode_id, revision, status FROM episodes')}

    def post_approve(self, query):
        import ui_library
        items, reviewer, _ = self.decision_body()
        with self.app.write_lock, self.app.index() as db:
            result = ui_library.approve(db, items, reviewer, self.now(), state=self.app.state)
            return ui_views.library_action(result, self.statuses(db))

    def post_withdraw(self, query):
        import ui_library
        items, reviewer, note = self.decision_body()
        with self.app.write_lock, self.app.index() as db:
            result = ui_library.withdraw(db, items, reviewer, self.now(), note=note)
            return ui_views.library_action(result, self.statuses(db))

    def delete_episode(self, episode_id, revision, query):
        import ui_library
        revision = int(revision)
        # L11 race: an approval being applied may reference this video before its manifest is recorded.
        if (self.app.state/'approval'/'request.json').exists():
            raise ApiError(409, 'A schedule approval is being processed.', 'Wait for it to finish, then try again.')
        with self.app.write_lock, self.app.index() as db:
            if db.execute("SELECT 1 FROM drafts WHERE status='requested' LIMIT 1").fetchone():
                raise ApiError(409, 'A schedule approval is being processed.', 'Wait for it to finish, then try again.')
            row = db.execute('SELECT video_sha256, cover_sha256 FROM episodes WHERE episode_id=? AND revision=?',
                             (episode_id, revision)).fetchone()
            sizes = {}
            for table, sha in (('videos', row and row[0]), ('covers', row and row[1])):
                found = db.execute(f'SELECT path, bytes FROM {table} WHERE sha256=?', (sha,)).fetchone() if sha else None
                if found:
                    sizes[found[0]] = found[1]
            result = ui_library.delete_episode(db, self.app.state, episode_id, revision, self.now())
        if not result.get('ok'):
            if row is None:
                raise ApiError(404, result.get('problem') or 'Not found.', None)
            raise ApiError(409, result.get('problem') or 'This video cannot be deleted.', 'Withdraw it instead to stop future use.')
        return {'deleted': True, 'episodeId': episode_id, 'revision': revision,
                'bytesFreed': sum(sizes.get(path, 0) for path in result.get('removedFiles') or [])}

    def cleanup_inputs(self):
        """(ledger rows, approved manifest, {platform: account id}) for ui_library.cleanup_candidates."""
        config = self.app.config()
        _, _, _, manifest = self.approval(config)
        rows = self.ledger('SELECT id, platform, status, payload FROM jobs')
        accounts = {p: (c or {}).get('accountId') for p, c in (config.get('channels') or {}).items()}
        return rows, manifest, accounts

    def approval_busy(self, db):
        return ((self.app.state/'approval'/'request.json').exists()
                or db.execute("SELECT 1 FROM drafts WHERE status='requested' LIMIT 1").fetchone() is not None)

    def get_cleanup(self, query):
        import ui_library
        rows, manifest, accounts = self.cleanup_inputs()
        with self.app.index() as db:
            candidates = ui_library.cleanup_candidates(db, self.app.state, rows, manifest, accounts)
            busy = self.approval_busy(db)
        return {'candidates': candidates, 'totalBytes': sum(c['bytes'] for c in candidates),
                'blockedReason': 'A schedule approval is being processed; wait for it to finish.' if busy else None}

    def post_cleanup(self, query):
        import ui_library
        body = self.read_json()
        shas = body.get('videoSha256') if isinstance(body, dict) else None
        if (not isinstance(shas, list) or not shas or len(shas) > 1000
                or not all(isinstance(s, str) and re.fullmatch(r'[0-9a-f]{64}', s) for s in shas)):
            raise ApiError(422, 'Choose the posted videos to remove.', 'Reload the list and try again.')
        rows, manifest, accounts = self.cleanup_inputs()
        with self.app.write_lock, self.app.index() as db:
            # Same L11 race as deletion: an approval being applied may still need these files.
            if self.approval_busy(db):
                raise ApiError(409, 'A schedule approval is being processed.', 'Wait for it to finish, then try again.')
            return ui_library.archive_videos(db, self.app.state, shas, rows, manifest, accounts, self.now())

    # --- feedback, batch notes, next batch (owner planning text; never read by scheduling or publishing) ---
    def invalid(self, error, message):
        path, text = error.args
        raise ApiError(422, message, 'Fix the fields listed, then save again.', [{'code': 'invalid', 'path': path, 'message': text}])

    def episode_or_404(self, db, episode_id, revision):
        import ui_library
        row = ui_library.episode_row(db, episode_id, revision)
        if row is None:
            raise ApiError(404, 'No such video revision in the library.', 'Refresh the library.')
        return row

    def get_episode(self, episode_id, revision, query):
        import metrics
        import ui_library
        revision = int(revision)
        config = self.app.config()
        today = self.now().astimezone(self.zone(config)).date()
        with self.app.index() as db:
            row = self.episode_or_404(db, episode_id, revision)
            meta = json.loads(row['metadata'])
            last = db.execute('SELECT at FROM approvals WHERE episode_id=? AND revision=? ORDER BY id DESC LIMIT 1',
                              (episode_id, revision)).fetchone()
            raw = {'batchId': row['batch_id'], 'status': row['status'], 'expired': ui_library._expired(meta, today),
                   'episode': ui_library.stored_episode(db, row['batch_id'], episode_id, revision, meta),
                   'approvedAt': last['at'] if last else None, 'notes': ui_library.batch_notes(db, row['batch_id']),
                   'feedback': ui_library.get_feedback(db, episode_id, revision)}
        rows = self.ledger('SELECT * FROM jobs WHERE episode=? ORDER BY slot, platform, id', (row['question_id'],))
        stats = metrics.latest(self.app.state, [r['id'] for r in rows])
        return ui_views.episode_detail(raw, ui_views.ledger_posts(rows, episode_id, revision, stats))

    def put_feedback(self, episode_id, revision, query):
        import ui_library
        revision = int(revision)
        try:
            tags, note = ui_views.feedback_input(self.read_json())
        except ValueError as error:
            self.invalid(error, 'The feedback was not saved.')
        with self.app.write_lock, self.app.index() as db:
            self.episode_or_404(db, episode_id, revision)
            return ui_views.episode_feedback(ui_library.set_feedback(db, episode_id, revision, tags, note, self.now()))

    def delete_feedback(self, episode_id, revision, query):
        import ui_library
        revision = int(revision)
        with self.app.write_lock, self.app.index() as db:
            # Feedback on a revision deleted since stays clearable.
            if ui_library.get_feedback(db, episode_id, revision) is None:
                self.episode_or_404(db, episode_id, revision)
            ui_library.clear_feedback(db, episode_id, revision)
        return Raw(status=204)

    def post_mark_used(self, query):
        import ui_library
        try:
            items = ui_views.mark_used_input(self.read_json())
        except ValueError as error:
            self.invalid(error, 'Choose the feedback to mark as used.')
        with self.app.write_lock, self.app.index() as db:
            return {'updated': ui_library.mark_feedback_used(db, items)}

    def get_batch_notes(self, batch_id, query):
        import ui_library
        with self.app.index() as db:
            if not ui_library.batch_known(db, batch_id):
                raise ApiError(404, 'No such batch in the library.', 'Refresh the library.')
            return ui_views.batch_notes(ui_library.batch_notes(db, batch_id))

    def put_batch_note(self, batch_id, kind, query):
        import ui_library
        try:
            text = ui_views.note_input(self.read_json())
        except ValueError as error:
            self.invalid(error, 'The note was not saved.')
        with self.app.write_lock, self.app.index() as db:
            if not ui_library.batch_known(db, batch_id):
                raise ApiError(404, 'No such batch in the library.', 'Refresh the library.')
            return ui_views.batch_note(ui_library.set_batch_note(db, batch_id, kind, text, self.now()))

    def get_next_batch(self, query):
        import metrics
        import ui_library
        with self.app.index() as db:
            next_id = ui_library.next_batch_id(db, self.now())
            items = ui_library.open_feedback(db)
            brief, retro = ui_library.last_note(db, 'brief'), ui_library.last_note(db, 'retro')
        rows = self.ledger("SELECT * FROM jobs WHERE permalink IS NOT NULL AND permalink != ''")
        stats = metrics.latest(self.app.state, [r['id'] for r in rows])
        zone = self.zone(self.app.config())
        today = self.now().astimezone(zone).date()
        confirmed = self.ledger("SELECT * FROM jobs WHERE status='confirmed'")
        return ui_views.next_batch(next_id, items, brief, retro, ui_views.ledger_posts(rows, metrics=stats),
                                   metrics.account_summary(self.app.state, today),
                                   metrics.funnel(self.app.state, confirmed, zone))

    # --- post stats controls: this process only writes files in STATE/metrics/; scalar-social-metrics.{timer,path} read ---
    def metrics_status(self):
        import ui_health
        units = {u: self.app.show(u) for u in (ui_views.METRICS_TIMER, ui_views.METRICS_SERVICE, ui_views.METRICS_PATH)}
        return ui_views.metrics_status(ui_health.metrics_files(self.app.state), units, ui_views.zone_name(self.app.config()))

    def metrics_folder(self):
        import ui_health
        folder = self.app.state/ui_health.METRICS_DIR
        folder.mkdir(mode=0o700, exist_ok=True)
        (folder/'history').mkdir(mode=0o700, exist_ok=True)
        return folder

    def metrics_switch_event(self, folder, enabled):
        """history/switch-<stamp>-<hex>.json {at, enabled}, then the collector's own pruning (newest 200 kept)."""
        import metrics
        import ui_approval
        now = self.now()
        name = f'switch-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}.json'
        ui_approval.write_atomic(folder/'history'/name, library_contract.canonical({'at': ui_views.iso_utc(now), 'enabled': enabled}))
        metrics.prune_history(folder/'history')

    def get_metrics_status(self, query):
        return self.metrics_status()

    def put_metrics_enabled(self, query):
        import ui_approval
        try:
            body = ui_views.metrics_input(self.read_json(), ('enabled',))
            if not isinstance(body.get('enabled'), bool):
                raise ValueError('enabled', 'Must be true or false.')
        except ValueError as error:
            self.invalid(error, 'Post stats were not switched.')
        enabled = body['enabled']
        with self.app.write_lock:
            folder = self.metrics_folder()
            flag = folder/'enabled'
            if enabled != flag.exists():
                if enabled:
                    ui_approval.write_atomic(flag, (ui_views.iso_utc(self.now()) + '\n').encode())
                else:
                    flag.unlink(missing_ok=True)
                self.metrics_switch_event(folder, enabled)
                sys.stderr.write(f'post stats turned {"on" if enabled else "off"} from the UI\n')
        return self.metrics_status()

    def post_metrics_read(self, query):
        import ui_approval
        try:
            body = ui_views.metrics_input(self.read_json() if self.headers.get('Content-Length') not in (None, '0') else {},
                                          ('backfill',))
            backfill = body.get('backfill', 0)
            if not ui_views._whole(backfill, 0, ui_views.METRICS_BACKFILL_MAX):
                raise ValueError('backfill', f'A whole number of days from 0 to {ui_views.METRICS_BACKFILL_MAX}.')
        except ValueError as error:
            self.invalid(error, 'The stats read was not requested.')
        with self.app.write_lock:
            folder = self.metrics_folder()
            request = folder/'request.json'
            if os.path.lexists(request):
                raise ApiError(409, 'A stats read is already waiting to run.', 'Wait for it to finish, then refresh.', code='busy')
            ui_approval.write_atomic(request, library_contract.canonical({'requestedAt': ui_views.iso_utc(self.now()),
                                                                          'backfill': backfill}))
        sys.stderr.write(f'post stats read requested from the UI (backfill {backfill})\n')
        return Reply(202, self.metrics_status())

    def queue(self, config, manifest):
        """QueueJob list for the approved manifest joined with its ledger rows (read-only)."""
        import ui_approval
        import ui_health
        if not manifest:
            return []
        channels = config.get('channels') or {}
        mjobs = manifest.get('jobs') or []
        accounts = [(channels.get(j['platform']) or {}).get('accountId') for j in mjobs]
        ids = [ui_approval.ledger_key(j['platform'], a, j['slot']) for j, a in zip(mjobs, accounts)]
        rows = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start+500]
            for r in self.ledger(f"SELECT * FROM jobs WHERE id IN ({','.join('?'*len(chunk))})", chunk):
                rows[r['id']] = r
        with self.app.index() as db:
            covers = {(r[0], r[1]): (r[2], r[3]) for r in db.execute(
                'SELECT e.episode_id, e.revision, c.sha256, c.path FROM episodes e JOIN covers c ON c.sha256=e.cover_sha256')}
        zone = ui_views.zone_name(config)
        out = []
        for j, account, key, parent in zip(mjobs, accounts, ids, ui_views.parent_keys(mjobs)):
            episode = (j.get('payload') or {}).get('episode') or {}
            cover = covers.get((episode.get('episodeId'), episode.get('revision')))
            url = self.app.media_url('covers', cover[0]) if cover and (self.app.state/cover[1]).is_file() else None
            out.append(ui_views.queue_job(j, rows.get(key), account, url, parent, ui_health.explain, zone))
        return out

    def draft_status(self, db, sha, stored, raw, manifest, state):
        approved = (manifest or {}).get('draftSha256')
        past = {r[0] for r in db.execute('SELECT draft_sha256 FROM manifests') if r[0]} - {approved}
        return ui_views.draft_status(stored, sha, approved_draft_sha=approved, past_draft_shas=past,
                                     pending=state['pendingRequest'], last_result=raw.get('result'))

    def get_schedule(self, query):
        import ui_schedule
        config = self.app.config()
        state, raw, sha, manifest = self.approval(config)
        channels = config.get('channels') or {}
        with self.app.index() as db:
            recent = []
            for r in db.execute('SELECT sha256, created_at, status, body FROM drafts ORDER BY created_at DESC, sha256 LIMIT 10'):
                try:
                    jobs = len(json.loads(r[3]).get('jobs') or [])
                except (ValueError, AttributeError):
                    jobs = 0
                recent.append({'sha256': r[0], 'status': self.draft_status(db, r[0], r[2], raw, manifest, state),
                               'createdAt': ui_views.iso_utc(r[1]), 'jobs': jobs})
        return ui_views.schedule(
            config=config, manifest_sha=sha, manifest=manifest or {}, bound=state['bound'],
            jobs=self.queue(config, manifest), approval_state=state,
            channels=[ui_views.channel_summary(p, channels.get(p), ui_schedule._exclusion(p, channels.get(p)))
                      for p in ui_views.PLATFORMS],
            recent=recent)

    def draft_response(self, sha):
        """(DraftResponse, blocking problems); blocking is recomputed on every read."""
        import ui_library
        import ui_schedule
        config = self.app.config()
        state, raw, manifest_sha, manifest = self.approval(config)
        now = self.now()
        with self.app.index() as db:
            row = db.execute('SELECT body, status, created_at FROM drafts WHERE sha256=?', (sha,)).fetchone()
            if not row:
                raise ApiError(404, 'Draft not found.', 'Generate the schedule again.')
            body = json.loads(row[0])
            try:
                today = now.astimezone(ui_schedule.zone_for(body['inputs']['timezone'])).date()
                library_hash = hashlib.sha256(library_contract.canonical(ui_library.schedulable_videos(db, today))).hexdigest()
            except (KeyError, TypeError, ValueError):
                library_hash = None
            status = self.draft_status(db, sha, row[1], raw, manifest, state)
            wanted = sorted({j.get('coverSha256') for j in body.get('jobs') or []} - {None})
            covers = {r[0]: r[1] for r in db.execute(
                f"SELECT sha256, path FROM covers WHERE sha256 IN ({','.join('?'*len(wanted))})", wanted)} if wanted else {}
        cover_urls = {c: self.app.media_url('covers', c) for c in wanted if c in covers and (self.app.state/covers[c]).is_file()}
        channels = config.get('channels') or {}
        blocking = ui_views.blocking_problems(
            body, sha=sha, now=now, current_manifest_sha=manifest_sha,
            approved_draft_sha=(manifest or {}).get('draftSha256'), pending=state['pendingRequest'],
            library_hash=library_hash, exclusions={p: ui_schedule._exclusion(p, channels.get(p)) for p in ui_views.PLATFORMS})
        return ui_views.draft_response(sha, body, status=status, created_at=row[2], blocking=blocking,
                                       cover_urls=cover_urls), blocking

    def post_draft(self, query, inputs=None):
        import ui_approval
        import ui_library
        import ui_schedule
        inputs = inputs if inputs is not None else self.read_json()
        config = self.app.config()
        now = self.now()
        try:
            zone = ui_schedule.zone_for(inputs.get('timezone') if isinstance(inputs, dict) else None)
            today = now.astimezone(zone).date()
            normalized = ui_schedule.validate_inputs(inputs, config, today)
        except ValueError as error:
            raise ApiError(422, str(error), 'Check the schedule settings, then generate again.',
                           [{'code': 'inputs', 'path': 'inputs', 'message': str(error)}]) from None
        base_sha, base = ui_approval.current_manifest(self.app.state)
        history = ui_schedule.ledger_history(self.app.state/'ledger.sqlite3', config, now)
        with self.app.write_lock, self.app.index() as db:
            videos = ui_library.schedulable_videos(db, today)
            draft = ui_schedule.generate(normalized, videos, history, config, base, base_sha)
            sha = ui_schedule.draft_sha256(draft)
            db.execute('INSERT OR IGNORE INTO drafts(sha256, created_at, base_manifest_sha256, body, status) VALUES(?,?,?,?,?)',
                       (sha, ui_views.iso_utc(now), base_sha, library_contract.canonical(draft).decode(), 'draft'))
        return self.draft_response(sha)[0]

    def get_draft(self, sha, query):
        return self.draft_response(sha)[0]

    def release_processed_request(self):
        """Staging (--no-deploy) leaves a processed request in place; archive it so a new draft can be requested."""
        import ui_approval
        raw = ui_approval.approval_state(self.app.state)
        pending, result = raw.get('pending'), raw.get('result')
        if not (ui_views.request_processed(pending, result) and result.get('status') == 'validated-no-deploy'):
            return
        folder = self.app.state/'approval'
        history = folder/'history'
        history.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = self.now().strftime('%Y%m%dT%H%M%S%fZ') + f"-{pending['draftSha256'][:8]}-request.json"
        with contextlib.suppress(FileNotFoundError):
            os.replace(folder/'request.json', history/name)

    def post_approve_draft(self, sha, query):
        import ui_approval
        body = self.read_json()
        response, blocking = self.draft_response(sha)
        phrase = response['confirmationPhrase']
        if not isinstance(body, dict) or body.get('confirmation') != phrase:
            raise ApiError(422, f'Type {phrase} exactly to approve this draft.', None,
                           [{'code': 'confirmation', 'path': 'confirmation', 'message': f'Type {phrase} exactly.'}])
        if blocking:
            raise ApiError(409, 'This draft cannot be approved right now.', 'Resolve the listed problems, then approve again.',
                           [{'code': 'blocking', 'path': 'draft', 'message': m} for m in blocking])
        with self.app.write_lock:
            self.release_processed_request()
            try:
                request = ui_approval.request_approval(self.app.state, sha, phrase, draft_exists=True, now=self.now())
            except ui_approval.Conflict:
                raise ApiError(409, 'An approval is already being processed.', 'Wait for its result, then refresh.') from None
            except ValueError as error:
                raise ApiError(422, str(error), None) from None
            with self.app.index() as db:
                db.execute("UPDATE drafts SET status='requested' WHERE sha256=?", (sha,))
        return Reply(202, ui_views.approve_draft(request))

    def editable(self, keys):
        """409 unless every key is an undispatched job of the approved schedule."""
        import ui_approval
        config = self.app.config()
        _, manifest = ui_approval.current_manifest(self.app.state)
        if not manifest:
            raise ApiError(409, 'There is no approved schedule to change.', 'Generate and approve a schedule first.')
        jobs = {j['key']: j for j in self.queue(config, manifest)}
        unknown = [k for k in keys if k not in jobs]
        if unknown:
            raise ApiError(422, 'That job is not in the approved schedule.', 'Refresh the schedule and try again.',
                           [{'code': 'key', 'path': 'keys', 'message': f'Not in the approved schedule: {k}'} for k in unknown])
        sent = [k for k in keys if jobs[k]['dispatched']]
        if sent:
            raise ApiError(409, 'Already sent to the platform; it cannot be changed or cancelled.',
                           'Leave it as it is. Check its result in History.')

    def post_cancel(self, query):
        body = self.read_json()
        keys = body.get('keys') if isinstance(body, dict) else None
        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
            raise ApiError(422, 'Choose at least one job.', None, [{'code': 'keys', 'path': 'keys', 'message': 'Choose at least one job.'}])
        self.editable(keys)
        return self.redraft({k: {'remove': True} for k in keys})

    def post_edit(self, query):
        body = self.read_json()
        if (not isinstance(body, dict) or not isinstance(body.get('key'), str) or not isinstance(body.get('text'), str)
                or not body['text'].strip()):
            raise ApiError(422, 'Choose a job and enter the new text.', None,
                           [{'code': 'text', 'path': 'text', 'message': 'Enter the new text.'}])
        self.editable([body['key']])
        return self.redraft({body['key']: {'text': body['text']}})

    def redraft(self, edits):
        import ui_approval
        _, manifest = ui_approval.current_manifest(self.app.state)
        with self.app.index() as db:
            row = db.execute('SELECT body FROM drafts WHERE sha256=?', ((manifest or {}).get('draftSha256'),)).fetchone()
        if not row:
            raise ApiError(409, 'The approved draft is missing from the library index.', 'Generate a new schedule instead.')
        inputs = json.loads(row[0])['inputs']
        # Re-approval of the current manifest with edits: no new slots are generated.
        inputs = {**inputs, 'edits': {**(inputs.get('edits') or {}), **edits}, 'carryOnly': True}
        return self.post_draft({}, inputs=inputs)

    def get_history(self, query):
        import ui_health
        config = self.app.config()
        try:
            filters = ui_views.history_query(query, ui_views.zone_name(config))
        except ValueError as error:
            raise ApiError(422, str(error), 'Check the filters, then search again.',
                           [{'code': 'query', 'path': 'query', 'message': str(error)}]) from None
        raw = ui_health.history(self.app.state, config) + ui_health.cancelled_jobs(self.app.state, config)
        rows = sorted((ui_views.history_row(r) for r in raw), key=lambda r: r['jobId'])
        rows.sort(key=lambda r: r['slotUtc'] or '', reverse=True)
        body = ui_views.history(rows, filters, config, {r['id']: r.get('caption') or '' for r in raw})
        if filters['format'] == 'csv':
            stamp = self.now().strftime('%Y%m%dT%H%M%SZ')
            return Raw(ui_views.history_csv(body['rows']).encode(), 'text/csv; charset=utf-8',
                       headers={'Content-Disposition': f'attachment; filename="scalar-history-{stamp}.csv"',
                                'Cache-Control': 'no-store'})
        return body

    def get_activity(self, query):
        import ui_activity
        config = self.app.config()
        try:
            filters = ui_activity.query(query)
        except ValueError as error:
            raise ApiError(422, str(error), 'Check the filters, then try again.',
                           [{'code': 'query', 'path': 'query', 'message': str(error)}]) from None
        body = ui_activity.feed(self.app.state, self.app.show, config, filters, self.now())
        if filters['format'] == 'csv':
            stamp = self.now().strftime('%Y%m%dT%H%M%SZ')
            return Raw(ui_activity.feed_csv(body['entries']).encode(), 'text/csv; charset=utf-8',
                       headers={'Content-Disposition': f'attachment; filename="scalar-activity-{stamp}.csv"',
                                'Cache-Control': 'no-store'})
        return body

    def get_job(self, job_id, query):
        import ui_approval
        import ui_health
        config = self.app.config()
        detail = ui_health.job_detail(self.app.state, config, job_id)
        if detail is None:
            detail = next((r for r in ui_health.cancelled_jobs(self.app.state, config) if r['id'] == job_id), None)
        if detail is None:
            raise ApiError(404, 'Job not found.', 'Refresh History; it may have been cancelled before dispatch.')
        sha, manifest = ui_approval.current_manifest(self.app.state)
        channels = config.get('channels') or {}
        listed = any(ui_approval.ledger_key(j['platform'], (channels.get(j['platform']) or {}).get('accountId'), j['slot']) == job_id
                     for j in (manifest or {}).get('jobs') or [])
        return ui_views.job_detail(detail, config, sha if listed else None)

    def post_pause(self, query):
        body = self.read_json()
        note = body.get('note') if isinstance(body, dict) else None
        if note is not None and (not isinstance(note, str) or len(note) > 500):
            raise ApiError(422, 'The note must be text of at most 500 characters.', None,
                           [{'code': 'note', 'path': 'note', 'message': 'At most 500 characters.'}])
        path = self.app.state/'PAUSED'
        already = path.exists()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        clean = re.sub(r'[^\w .,:;!?()/-]', ' ', note or '')[:200].strip()
        sys.stderr.write('pause requested from the UI' + (f': {clean}' if clean else '') + '\n')
        return ui_views.pause(already, self.now())

    def get_activation(self, query):
        import activate
        import ui_approval
        rows, _ = activate.checklist(self.app.config_path, self.app.state, run=self.app.run)
        try:
            sha, manifest = ui_approval.current_manifest(self.app.state)
        except ValueError:
            sha, manifest = None, None
        return ui_views.activation(rows, sha, manifest, ACTIVATE_COMMAND, CHECK_COMMAND)

    # --- self-update (docs/REBUILD_CONTRACTS.md §1): this process never fetches; the update unit does ---
    def get_update_status(self, query):
        return updater.info(self.app.update_state, self.app.repo, self.app.running)

    def post_update_check(self, query):
        if self.headers.get('Content-Length') not in (None, '0'):
            self.read_json()
        if not self.app.running:
            raise ApiError(409, 'This Pi is not running from a git checkout.', 'The owner runs publisher/deploy/bootstrap-git.sh once.', code='not_git')
        try:
            updater.queue_request(self.app.update_state, 'check')
        except updater.Busy:
            raise ApiError(409, 'An update or check is already running.', 'Wait for it to finish, then refresh.', code='busy') from None
        return Reply(202, {'queued': True})

    def post_update_start(self, query):
        body = self.read_json()
        try:
            request = updater.start(self.app.update_state, self.app.repo, self.app.running,
                                    body.get('confirm') if isinstance(body, dict) else None)
        except updater.Refused as refused:
            raise ApiError(refused.status, refused.message, refused.next_action, code=refused.code) from None
        sys.stderr.write(f"update to {request['sha'][:12]} requested from the UI\n")
        return Reply(202, {'queued': True})

    def get_backup(self, query):
        import ui_health
        body, name = ui_health.backup_archive(self.app.state, self.app.config(), now=self.now())
        return Raw(body, 'application/gzip', headers={'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'no-store'})


NAME = r'([a-z0-9-]+)'
ROUTES = [
    ('GET', r'/api/catalog', 'get_catalog'),
    ('GET', r'/api/assets/motion/manifest', 'get_motion_manifest'),
    ('GET', r'/api/assets/motion/([0-9a-f]{16})/((?:episodes/fonts|episodes/music|sfx)/[a-z0-9-]{1,80}\.(?:woff2|m4a|wav))', 'get_motion_asset'),
    ('GET', r'/api/dashboard', 'get_dashboard'),
    ('GET', r'/api/library', 'get_library'),
    ('POST', r'/api/library/batches', 'post_batch'),
    ('PUT', r'/api/library/batches/([a-z0-9-]{1,64})/files/(videos|covers)/([a-z0-9-]{1,80}\.(?:mp4|jpg))', 'put_batch_file'),
    ('POST', r'/api/library/legacy', 'post_legacy'),
    ('POST', r'/api/library/approve', 'post_approve'),
    ('POST', r'/api/library/withdraw', 'post_withdraw'),
    ('DELETE', r'/api/library/episodes/([a-z0-9-]{1,80})/([0-9]{1,6})', 'delete_episode'),
    ('GET', r'/api/library/cleanup', 'get_cleanup'),
    ('POST', r'/api/library/cleanup', 'post_cleanup'),
    ('GET', r'/api/library/episodes/([a-z0-9-]{1,80})/([0-9]{1,6})', 'get_episode'),
    ('PUT', r'/api/library/episodes/([a-z0-9-]{1,80})/([0-9]{1,6})/feedback', 'put_feedback'),
    ('DELETE', r'/api/library/episodes/([a-z0-9-]{1,80})/([0-9]{1,6})/feedback', 'delete_feedback'),
    ('POST', r'/api/feedback/mark-used', 'post_mark_used'),
    ('GET', r'/api/library/batches/([a-z0-9-]{1,64})/notes', 'get_batch_notes'),
    ('PUT', r'/api/library/batches/([a-z0-9-]{1,64})/notes/(brief|retro)', 'put_batch_note'),
    ('GET', r'/api/next-batch', 'get_next_batch'),
    ('GET', r'/api/metrics/status', 'get_metrics_status'),
    ('PUT', r'/api/metrics/enabled', 'put_metrics_enabled'),
    ('POST', r'/api/metrics/read', 'post_metrics_read'),
    ('GET', r'/api/schedule', 'get_schedule'),
    ('POST', r'/api/schedule/drafts', 'post_draft'),
    ('GET', rf'/api/schedule/drafts/({SHA})', 'get_draft'),
    ('POST', rf'/api/schedule/drafts/({SHA})/approve', 'post_approve_draft'),
    ('POST', r'/api/schedule/cancel', 'post_cancel'),
    ('POST', r'/api/schedule/edit', 'post_edit'),
    ('GET', r'/api/history', 'get_history'),
    ('GET', r'/api/activity', 'get_activity'),
    ('GET', r'/api/jobs/([0-9a-f]{24})', 'get_job'),
    ('POST', r'/api/pause', 'post_pause'),
    ('GET', r'/api/activation', 'get_activation'),
    ('GET', r'/api/backup', 'get_backup'),
    ('GET', r'/api/system/update/status', 'get_update_status'),
    ('POST', r'/api/system/update/check', 'post_update_check'),
    ('POST', r'/api/system/update/start', 'post_update_start'),
]


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16


def make_server(app, host='127.0.0.1', port=8765):
    handler = type('BoundHandler', (Handler,), {'app': app})
    return Server((host, port), handler)


def sd_notify(message):
    """systemd Type=notify readiness (stdlib only); a no-op outside systemd."""
    address = os.environ.get('NOTIFY_SOCKET')
    if not address:
        return False
    if address.startswith('@'):
        address = '\0' + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:  # Python sockets are non-inheritable
            sock.connect(address)
            sock.sendall(message.encode())
        return True
    except OSError:
        return False


def main(argv=None):
    # The code this process loaded: read at import, before the other app modules (STARTED_HEAD).
    running = STARTED_HEAD if __name__ == '__main__' else updater.running_commit(updater.REPO)
    parser = argparse.ArgumentParser(description='Scalar social Pi UI (loopback only).')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--update-state', default=updater.UPDATE_STATE)
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--static', default=str(Path(__file__).resolve().parent/'static'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--allowed-origin', action='append', default=None)
    parser.add_argument('--insecure-dev', action='store_true', help='No passcode; loopback http origins only')
    parser.add_argument('--no-legacy', action='store_true', help='Skip registering existing Pi media at start')
    parser.add_argument('--studio-socket', default=STUDIO_SOCKET, help='Studio proxy socket (studio_proxy.py)')
    args = parser.parse_args(argv)
    origins = args.allowed_origin or []
    if args.host not in LOOPBACK:
        parser.error('The UI binds to loopback only; Tailscale Serve provides tailnet access.')
    # The Pi's tailnet address is not in git: the unit passes SCALAR_UI_ORIGIN from /etc/scalar-social/ui.env.
    if not origins or any(not re.fullmatch(r'https://[a-z0-9-]+(\.[a-z0-9-]+)+|http://(127\.0\.0\.1|localhost)(:\d+)?', o)
                          for o in origins):
        print('UI locked: --allowed-origin missing or malformed. Set SCALAR_UI_ORIGIN in /etc/scalar-social/ui.env.',
              file=sys.stderr)
        return 1
    passcode = load_passcode()
    if not passcode:
        if not args.insecure_dev or any(not re.fullmatch(r'http://(127\.0\.0\.1|localhost)(:\d+)?', o) for o in origins):
            print('UI locked: UI_PASSCODE credential missing. Enter it with credential_entry.py and restart.', file=sys.stderr)
            return 1
    import ui_library
    ui_library.cleanup_incoming(args.state, all_files=True)
    app = UiApp(args.state, args.config, args.static, passcode, origins, running=running, update_state=args.update_state,
                studio_socket=args.studio_socket)
    server = make_server(app, args.host, args.port)
    # Only now, with the socket listening, does the UI report `serving` for a switched update and tell systemd it
    # is ready (Type=notify). The update unit rolls the checkout back if this never happens after a restart.
    updater.reconcile(args.update_state, running)
    sd_notify('READY=1')
    if running:
        updater.start_watcher(args.update_state, updater.REPO, running)
    if not args.no_legacy and (Path(args.state)/'catalog.json').is_file():
        Handler.start_legacy(type('Starter', (), {'app': app})())
    print(f'Scalar UI listening on {args.host}:{args.port} (paused publisher untouched).', file=sys.stderr)
    try:
        server.serve_forever(poll_interval=1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
