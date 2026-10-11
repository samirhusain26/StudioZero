"""Pi self-update from GitHub (docs/REBUILD_CONTRACTS.md §1, publisher/docs/SELF_UPDATE.md).

Two users. The UI runs as scalar-social, has no network and never writes the checkout: it only queues
<update state>/inbox/request.json, reports its restarts in inbox/ui.json, and reads status.json.
`run-request` runs as the dedicated user scalar-social-update (scalar-social-update.service, which has network
and owns /opt/scalar-social/repo). It takes the request, fetches, and for an apply stages the confirmed commit in
a worktree under <repo>/.git/scalar-update-stage, runs the staged checks, waits for runner.lock and
fast-forwards. Never `git pull`; every comparison uses full SHAs. After a switch the UI's watcher exits 86 and
systemd restarts it on the new code; the new UI reports `serving` once listening, and verify_restart() rolls
the checkout back if it never does.
Git never reads config a scalar-social process can write: see git_env(), hardened() and SELF_UPDATE.md (Security).
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[2]
BRANCH = 'main'
# Exact ssh URLs through the root-owned github.com-scalar alias. StudioZero (public) replaces the private
# scalargame-marketing-plan; the old names stay accepted so a rollback of the move (migrate-origin.sh) keeps working.
REPOS = ('scalargame-marketing', 'scalargame-marketing-plan', 'StudioZero')
ORIGINS = tuple(f'git@github.com-scalar:samirhusain26/{name}{suffix}' for name in REPOS for suffix in ('.git', ''))
ORIGINS_ENV = 'SCALAR_UPDATE_ORIGINS'  # comma-separated extra accepted origins (tests and the Mac demo only)
APPLY_UNITS_COMMAND = 'sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh'
# After a completed update that changed unit files or pi-package*.json, this run (the update user) writes
# units-pending.json; scalar-social-apply-units.path then runs apply-units.sh --auto as root, which removes the
# trigger first and reports in units-apply.json (also written as the update user). Nothing to type on the Pi.
UNITS_PENDING = 'units-pending.json'
UNITS_APPLY = 'units-apply.json'
UNITS_APPLY_PHASES = ('queued', 'running', 'ok', 'failed')
# Hardening (security reviews M1): git and ssh read only root-owned config. HOME is this root-owned folder
# (0750 root:scalar-social-update), never a folder a scalar-social process can write. Module constants so tests
# can patch them.
UPDATE_HOME = '/etc/scalar-social-update'
SSH_CONFIG = f'{UPDATE_HOME}/ssh_config'
# Written only by scalar-social-update (0755): status.json, units-applied.json. Its inbox/ (1730
# scalar-social-update:scalar-social) is the only place the UI writes: request.json and ui.json.
UPDATE_STATE = '/var/lib/scalar-social-update'
INBOX = 'inbox'
RUNNER_LOCK = '/var/lib/scalar-social/runner.lock'  # the publisher's lock (0644); flocked read-only
RESTART_EXIT = 86
CHECK_MAX_AGE = 15*60
REQUEST_MAX_AGE = 15*60
STALE_SECONDS = 40*60
LOCK_TIMEOUT = 600
UNIT_TIMEOUT = 60*60       # TimeoutStartSec of scalar-social-update.service
SWITCH_MARGIN = 5*60       # never start the switch with less than this left before the unit timeout
RESTART_WAIT = 30          # after the switch: how long the old UI has to notice it and exit 86
VERIFY_WAIT = 120          # then: how long the new UI has to start serving before the switch is rolled back
JSON_MAX = 256*1024        # status.json / units-applied.json; requests and ui.json are capped lower
SMALL_JSON_MAX = 4096
LOG_LINES = 40
PHASES = ('idle', 'checking', 'checked', 'staging', 'waiting', 'switching', 'switched', 'restarting', 'complete', 'failed')
BUSY = ('checking', 'staging', 'waiting', 'switching', 'switched', 'restarting')
# Fetch and index-pack on a 415 MB Pi: one thread, small caches, gc (if any) inline so the oneshot never orphans it.
LOW_MEMORY = ('-c', 'pack.threads=1', '-c', 'pack.windowMemory=32m', '-c', 'pack.deltaCacheSize=16m',
              '-c', 'core.deltaBaseCacheLimit=16m', '-c', 'core.packedGitLimit=64m', '-c', 'core.packedGitWindowSize=16m',
              '-c', 'gc.autoDetach=false')
QUICK_TESTS = ('test_runner', 'test_operations', 'test_activation', 'test_credentials', 'test_ui_views', 'test_ui_health',
               'test_ui_activity', 'test_ui_schedule', 'test_ui_approval', 'test_ui_library', 'test_ui_feedback', 'test_updater')
STAGE_DIR = 'scalar-update-stage'  # <repo>/.git/<STAGE_DIR>/stage-<id>: writable only by the update user
PYCACHE = re.compile(r'(publisher|contract)/(.*/)?(__pycache__/?|[^/]+\.py[co])')
UNIT_FILE = re.compile(r'publisher/deploy/[^/]+\.(service|path|timer|conf)')
PI_PACKAGE = ('publisher/pi-package.json', 'publisher/pi-package-lock.json')
SHA40 = re.compile(r'[0-9a-f]{40}')
REF = re.compile(r'refs/[A-Za-z0-9._/-]{1,200}')
CONFIRM = re.compile(r'UPDATE TO ([0-9a-f]{40})')
BUSY_MESSAGE = 'Publisher is running a post; try again later'
_queue_lock = threading.Lock()

IMPORT_CHECK = r'''
import importlib, pathlib, sys
app = pathlib.Path(sys.argv[1])
sys.path[:0] = [str(app), str(app.parents[1]/'contract')]
bad = []
for path in sorted(app.glob('*.py')):
    try:
        importlib.import_module(path.stem)
    except BaseException as error:
        bad.append(f'{path.stem}: {type(error).__name__}: {error}'[:200])
print('\n'.join(bad))
sys.exit(1 if bad else 0)
'''
TEST_RUNNER = r'''
import sys, unittest
tests, names = sys.argv[1], sys.argv[2:]
sys.path.insert(0, tests)
loader = unittest.defaultTestLoader
suite = loader.loadTestsFromNames(names) if names else loader.discover(tests, pattern='test_*.py', top_level_dir=tests)
result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
sys.exit(0 if result.wasSuccessful() and result.testsRun else 1)
'''


class UpdateError(Exception):
    pass


class Stopped(UpdateError):
    """SIGTERM from systemd (unit timeout or shutdown): raised so rollback and cleanup still run."""


class Busy(Exception):
    pass


class Refused(Exception):
    """A start/check the UI must refuse: HTTP status, contract code, message, next action."""
    def __init__(self, status, code, message, next_action=None):
        super().__init__(message)
        self.status, self.code, self.message, self.next_action = status, code, message, next_action


def utc(stamp=None):
    return dt.datetime.fromtimestamp(time.time() if stamp is None else stamp, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_utc(value):
    try:
        return dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def redact(text):
    # SSH origins carry no secrets; strip URL userinfo anyway in case an https origin ever appears.
    return re.sub(r'(://)[^/@\s]+@', r'\1***@', text)


def run(command, cwd, timeout=60, env=None):
    # Nothing else from the environment reaches git or the staged checks. HOME is never a folder a scalar-social
    # process can write: it is the root-owned UPDATE_HOME.
    base = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8', 'GIT_TERMINAL_PROMPT': '0',
            'HOME': UPDATE_HOME, 'PYTHONDONTWRITEBYTECODE': '1'}
    for key in ('TMPDIR', 'GIT_TEST_ASSUME_DIFFERENT_OWNER'):  # the latter: tests/demo play the other user (git only gets stricter)
        if os.environ.get(key):
            base[key] = os.environ[key]
    try:
        return subprocess.run(command, cwd=cwd, env={**base, **(env or {})}, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, '', f'timed out after {timeout} s')


def git_env():
    """Git reads no global, XDG or system config and ssh reads only the root-owned SSH_CONFIG."""
    return {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_ATTR_NOSYSTEM': '1',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND': f'ssh -F {SSH_CONFIG}'}


def hardened():
    """No hooks, no fsmonitor command, ssh only. file:// only when the tests or the Mac demo list a file:// origin
    (SCALAR_UPDATE_ORIGINS, never set on the Pi). `-c` values reach every child git process (lazy fetch,
    index-pack) through GIT_CONFIG_PARAMETERS."""
    local = any(o.strip().startswith('file://') for o in os.environ.get(ORIGINS_ENV, '').split(','))
    return ('-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-c', 'protocol.allow=never',
            '-c', 'protocol.ssh.allow=always', '-c', f"protocol.file.allow={'user' if local else 'never'}")


def git(repo, *args, timeout=60, offline=False):
    """offline: the UI (scalar-social, no network) reading the checkout scalar-social-update owns. It never
    triggers a partial-clone lazy fetch or takes index.lock, and trusts exactly this one repository
    (`-c safe.directory`, honoured from the command line by git >= 2.38; the Pi has 2.47)."""
    env = git_env()
    extra = ()
    if offline:
        env.update(GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', HOME='/nonexistent')
        extra = ('-c', f'safe.directory={Path(repo).resolve()}')
    return run(['git', *hardened(), *extra, *LOW_MEMORY, *args], repo, timeout, env)


def tail(proc, size=400):
    return redact((proc.stderr or proc.stdout or '').strip())[-size:] or f'exit {proc.returncode}'


def read_small(path, cap):
    """Bytes of a regular file (never a symlink, FIFO or device; O_NONBLOCK so a FIFO cannot hang us), or None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > cap:
            return None
        data = os.read(fd, cap + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data if len(data) <= cap else None


def read_json(path, cap=JSON_MAX):
    data = read_small(path, cap)
    try:
        return json.loads(data) if data is not None else None
    except (ValueError, RecursionError):
        return None


def running_commit(repo):
    """Full SHA of HEAD in `repo`, or None when it is not a git checkout (copy install). Read from the files
    (HEAD, loose ref, packed-refs) without running git, so the UI needs no ownership exception for it."""
    git_dir = Path(repo)/'.git'
    if not git_dir.is_dir() or git_dir.is_symlink():
        return None
    data = read_small(git_dir/'HEAD', 1024)
    value = data.decode('ascii', 'replace').strip() if data else ''
    for _ in range(5):
        if SHA40.fullmatch(value):
            return value
        ref = value[5:] if value.startswith('ref: ') else ''
        if not REF.fullmatch(ref) or '..' in ref.split('/'):
            return None
        data = read_small(git_dir/ref, 1024)
        if data is not None:
            value = data.decode('ascii', 'replace').strip()
            continue
        packed = read_small(git_dir/'packed-refs', 16*1024*1024) or b''
        for line in packed.decode('ascii', 'replace').splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref and SHA40.fullmatch(parts[0]):
                return parts[0]
        return None
    return None


# --- state files ---------------------------------------------------------------------
def folder(state):
    return Path(state)


def inbox(state):
    return Path(state)/INBOX


def default_status():
    return {'phase': 'idle', 'requestId': None, 'startedAt': None, 'updatedAt': None, 'fromCommit': None,
            'toCommit': None, 'error': None, 'log': [], 'check': None}


def atomic_write(path, value, mode=0o644):
    """Temp file + rename. O_EXCL | O_NOFOLLOW: a name planted in the folder is never followed or reused. The
    mode is set explicitly (not left to the umask): the other user reads these files."""
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with open(fd, 'w', encoding='utf-8') as handle:
            os.fchmod(handle.fileno(), mode)
            json.dump(value, handle, indent=1, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def read_status(state):
    """status.json exactly as the update unit wrote it."""
    status = default_status()
    raw = read_json(folder(state)/'status.json')
    if not isinstance(raw, dict) or raw.get('phase') not in PHASES:
        return status
    status.update({k: raw[k] for k in status if k in raw})
    if not isinstance(status['log'], list):
        status['log'] = []
    return status


def write_status(state, status):
    status = {**default_status(), **status, 'updatedAt': utc()}
    status['log'] = [str(line)[:300] for line in status['log']][-LOG_LINES:]
    atomic_write(folder(state)/'status.json', status)
    return status


def log_line(status, text):
    line = f'{utc()[11:]} {redact(text)}'
    status['log'] = [*status.get('log', []), line][-LOG_LINES:]
    print(line, file=sys.stderr, flush=True)


def read_ui(state, request_id):
    """inbox/ui.json for this request: {'phase': 'restarting' | 'serving', 'running', 'at'}, or None."""
    raw = read_json(inbox(state)/'ui.json', SMALL_JSON_MAX)
    if not isinstance(raw, dict) or not request_id or raw.get('requestId') != request_id:
        return None
    running = raw.get('running')
    return {'phase': raw.get('phase') if raw.get('phase') in ('restarting', 'serving') else None,
            'running': running if isinstance(running, str) and SHA40.fullmatch(running) else None,
            'at': raw.get('at') if isinstance(raw.get('at'), str) else ''}


def write_ui(state, request_id, phase, running):
    """The UI reports a restart (old process) or that it serves (new process). Never fatal for the UI."""
    try:
        atomic_write(inbox(state)/'ui.json', {'requestId': request_id, 'phase': phase, 'running': running, 'at': utc()})
        return True
    except OSError as error:
        print(f'update: could not write ui.json ({type(error).__name__})', file=sys.stderr, flush=True)
        return False


def current_status(state):
    """status.json plus what the UI reported for the same request: a switched run shows as restarting while the
    UI restarts, then complete (or failed) once the new UI serves, even when no update unit is still waiting."""
    status = read_status(state)
    if status['phase'] != 'switched':
        return status
    ui = read_ui(state, status['requestId'])
    if not ui or not ui['phase']:
        return status
    at = ui['at'][11:] if len(ui['at']) == 20 else ''
    if ui['phase'] == 'restarting':
        status['phase'] = 'restarting'
        status['log'] = [*status['log'], f"{at} Restarting the UI on {str(status['toCommit'])[:12]}"][-LOG_LINES:]
    elif ui['running'] and ui['running'] == status['toCommit']:
        status.update(phase='complete', error=None)
        status['log'] = [*status['log'], f"{at} UI restarted on {ui['running'][:12]}; update complete"][-LOG_LINES:]
    else:
        status.update(phase='failed', error=f"The UI restarted on {(ui['running'] or 'a non-git install')[:12]}, "
                                            f"not {str(status['toCommit'])[:12]}.")
    return status


def busy(state, now=None):
    """A request is waiting/being handled, or a run is mid-flight (stale after STALE_SECONDS)."""
    now = time.time() if now is None else now
    for name in ('request.json', 'request.taken.json'):
        with contextlib.suppress(OSError):
            if now - (inbox(state)/name).lstat().st_mtime < STALE_SECONDS:
                return True
    status = current_status(state)
    updated = parse_utc(status['updatedAt'])
    return status['phase'] in BUSY and updated is not None and now - updated < STALE_SECONDS


def _write_request(state, action, sha=None):
    request = {'action': action, 'requestId': secrets.token_hex(16), 'requestedAt': utc()}
    if sha:
        request['sha'] = sha
    atomic_write(inbox(state)/'request.json', request)
    return request


def queue_request(state, action, sha=None):
    """Write inbox/request.json for the update unit (single flight). Raises Busy."""
    with _queue_lock:
        if busy(state):
            raise Busy()
        return _write_request(state, action, sha)


def start(state, repo, running, confirm):
    """Validate a confirmed apply against the last check and queue it, atomically. Raises Refused."""
    with _queue_lock:
        return _write_request(state, 'apply', check_start(state, repo, running, confirm))


# --- what the UI shows ------------------------------------------------------------------
def deploy_changes(state, repo, head):
    """(unitsChanged, piPackageChanged) between the commit apply-units.sh last installed and `head`."""
    if not head:
        return False, False
    raw = read_json(folder(state)/'units-applied.json', SMALL_JSON_MAX)
    applied = raw.get('commit') if isinstance(raw, dict) else None
    if not isinstance(applied, str) or not SHA40.fullmatch(applied):
        return True, True
    if applied == head:
        return False, False
    proc = git(repo, 'diff', '--name-only', '--no-renames', applied, head, '--', 'publisher/deploy', *PI_PACKAGE,
               timeout=30, offline=True)
    if proc.returncode:
        return True, True
    names = proc.stdout.split()
    return any(UNIT_FILE.fullmatch(n) for n in names), any(n in PI_PACKAGE for n in names)


def queue_units_apply(state, repo, sha):
    """Ask scalar-social-apply-units.path to install the unit/package changes of `sha`; False when there are none."""
    units, package = deploy_changes(state, repo, sha)
    if not (units or package):
        return False
    atomic_write(folder(state)/UNITS_APPLY, {'phase': 'queued', 'commit': sha, 'at': utc(), 'error': None, 'log': []})
    atomic_write(folder(state)/UNITS_PENDING, {'commit': sha, 'requestedAt': utc()})
    return True


def units_apply(state):
    """UnitsApply from units-apply.json (typed fields only), or None."""
    raw = read_json(folder(state)/UNITS_APPLY, SMALL_JSON_MAX*4)
    if not isinstance(raw, dict) or raw.get('phase') not in UNITS_APPLY_PHASES:
        return None
    commit, at, error, log = raw.get('commit'), parse_utc(raw.get('at')), raw.get('error'), raw.get('log')
    return {'phase': raw['phase'], 'commit': commit if isinstance(commit, str) and SHA40.fullmatch(commit) else None,
            'at': utc(at) if at is not None else None,
            'error': redact(error)[:400] if isinstance(error, str) and error else None,
            'log': [redact(line)[:300] for line in log[-20:] if isinstance(line, str)] if isinstance(log, list) else []}


def info(state, repo, running, now=None):
    now = time.time() if now is None else now
    head = running_commit(repo) if running else None
    status = current_status(state)
    updated = parse_utc(status['updatedAt'])
    if status['phase'] in ('checking', 'staging', 'waiting', 'switching') and (updated is None or now - updated >= STALE_SECONDS):
        status.update(phase='failed', error='The update service stopped before finishing. Nothing more will happen; check again.')
    units, package = deploy_changes(state, repo, head)
    return {'runningCommit': running, 'installKind': 'git' if running else 'copy', 'repoHead': head,
            'restartNeeded': bool(running and head and head != running),
            'unitsChanged': units, 'piPackageChanged': package,
            'applyUnitsCommand': APPLY_UNITS_COMMAND if units or package else None, 'unitsApply': units_apply(state),
            'status': status}


def check_start(state, repo, running, confirm, now=None):
    """Server-side re-validation of POST /api/system/update/start; returns the sha or raises Refused."""
    now = time.time() if now is None else now
    if not running:
        raise Refused(409, 'not_git', 'This Pi is not running from a git checkout.', 'The owner runs publisher/deploy/bootstrap-git.sh once.')
    match = CONFIRM.fullmatch(confirm) if isinstance(confirm, str) else None
    if not match:
        raise Refused(400, 'bad_confirm', 'Type UPDATE TO followed by the full commit shown, exactly.', 'Copy the phrase shown above the box.')
    if busy(state, now):
        raise Refused(409, 'busy', 'An update or check is already running.', 'Wait for it to finish, then refresh.')
    check = read_status(state)['check']
    checked = parse_utc((check or {}).get('checkedAt'))
    if (not isinstance(check, dict) or checked is None or now - checked > CHECK_MAX_AGE or not check.get('fetchOk')
            or check.get('head') != running_commit(repo)):
        raise Refused(409, 'stale_check', 'The last check is missing, failed or older than 15 minutes.', 'Check for updates again.')
    for key, code, message, action in (
            ('dirty', 'dirty', 'The Pi checkout has local changes. Nothing was changed.', 'The owner inspects /opt/scalar-social/repo (git status).'),
            ('diverged', 'diverged', 'The Pi checkout has commits that are not on GitHub main. Nothing was changed.', 'The owner reconciles the checkout by hand.')):
        if check.get(key):
            raise Refused(409, code, message, action)
    if not check.get('originOk'):
        raise Refused(409, 'origin', 'The checkout does not point at the expected GitHub repository.', 'The owner checks git remote -v in /opt/scalar-social/repo.')
    if not check.get('branchOk'):
        raise Refused(409, 'branch', f'The checkout is not on branch {BRANCH}.', f'The owner switches /opt/scalar-social/repo back to {BRANCH}.')
    if not check.get('behind'):
        raise Refused(409, 'up_to_date', 'Already up to date.', None)
    if match.group(1) != check.get('origin'):
        raise Refused(400, 'bad_confirm', 'That commit is not the one the last check found.', 'Copy the phrase shown above the box.')
    return match.group(1)


# --- check (runs in the update unit) --------------------------------------------------------
def accepted_origins():
    return (*ORIGINS, *(o.strip() for o in os.environ.get(ORIGINS_ENV, '').split(',') if o.strip()))


def fetch(repo):
    return git(repo, 'fetch', '--no-tags', '--quiet', 'origin', f'+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}', timeout=300)


def inspect(repo, fetch_ok=True, error=None):
    def out(*args):
        proc = git(repo, *args)
        return proc.stdout.strip() if proc.returncode == 0 else None
    head = out('rev-parse', '--verify', '-q', 'HEAD^{commit}') or ''
    origin = out('rev-parse', '--verify', '-q', f'refs/remotes/origin/{BRANCH}^{{commit}}') or None
    url = out('remote', 'get-url', 'origin') or ''
    porcelain = out('status', '--porcelain', '--ignored')
    lines = (porcelain or '').splitlines()
    # Ignored bytecode under publisher/ or contract/ would run instead of (or next to) the tracked source, so it
    # counts as a local change; every other ignored file does not.
    dirty = porcelain is None or any(not line.startswith('!! ') or PYCACHE.fullmatch(line[3:]) for line in lines)
    behind = ahead = 0
    diverged, incoming, files = False, [], []
    if origin and head:
        behind = int(out('rev-list', '--count', f'{head}..{origin}') or 0)
        ahead = int(out('rev-list', '--count', f'{origin}..{head}') or 0)
        diverged = ahead > 0 or git(repo, 'merge-base', '--is-ancestor', head, origin).returncode != 0
        for line in (out('log', '-n', '30', '--format=%H%x1f%ct%x1f%s', f'{head}..{origin}') or '').splitlines():
            sha, stamp, subject = (line.split('\x1f', 2) + ['', ''])[:3]
            incoming.append({'sha': sha, 'subject': subject[:200], 'date': utc(int(stamp)) if stamp.isdigit() else ''})
        files = sorted((out('diff', '--name-only', '--no-renames', head, origin, '--', 'publisher', 'contract') or '').split())
    return {'checkedAt': utc(), 'fetchOk': fetch_ok, 'head': head, 'origin': origin, 'behind': behind, 'ahead': ahead,
            'dirty': dirty, 'diverged': diverged,
            'branchOk': out('symbolic-ref', '--short', '-q', 'HEAD') == BRANCH,
            'originOk': url in accepted_origins(), 'originUrl': redact(url), 'incoming': incoming,
            'changes': {'units': any(UNIT_FILE.fullmatch(f) for f in files), 'piPackage': any(f in PI_PACKAGE for f in files),
                        'contract': any(f.startswith('contract/') for f in files),
                        'ui': any(f.startswith(('publisher/ui/', 'publisher/app/static/')) for f in files), 'files': files[:100]},
            'error': error}


def do_check(state, repo, status):
    status.update(phase='checking', error=None)
    log_line(status, 'Checking GitHub for updates')
    write_status(state, status)
    proc = fetch(repo)
    error = None if proc.returncode == 0 else f'git fetch failed: {tail(proc)}'
    check = inspect(repo, proc.returncode == 0, error)
    log_line(status, error or f"{check['behind']} new commit(s) on {BRANCH}" + (', local changes (git status --ignored)' if check['dirty'] else ''))
    status.update(phase='checked', check=check, fromCommit=check['head'] or None, toCommit=check['origin'])
    write_status(state, status)


# --- apply (runs in the update unit) ---------------------------------------------------------
LOCK_MISSING = ('runner.lock is missing or cannot be opened, so a post could start mid-switch; nothing was changed. '
                'The owner re-runs bootstrap-git.sh, which creates it (0644).')


def open_lock(path):
    """runner.lock opened read-only, never following a link and never blocking on a FIFO (flock needs no write
    access; the update user cannot write the publisher's state folder). Created only where the folder is writable
    (tests, demo); bootstrap-git.sh creates it (0644) on the Pi. Missing or unopenable: refuse, never switch
    without the lock."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return open_lock(path)
        except OSError:
            raise UpdateError(LOCK_MISSING) from None
    except PermissionError:
        raise UpdateError(LOCK_MISSING) from None
    except OSError as error:
        raise UpdateError(f'runner.lock is not a regular file ({type(error).__name__}); nothing was changed') from None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise UpdateError('runner.lock is not a regular file; nothing was changed')
    return fd


@contextlib.contextmanager
def runner_lock(path, timeout, poll=2.0):
    """The publisher's runner.lock (runner.lock()), retried until `timeout`; held for the whole block."""
    fd = open_lock(Path(path))
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise UpdateError(BUSY_MESSAGE) from None
                time.sleep(min(poll, max(0.05, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def check_static(static):
    """publisher/app/static must match its MANIFEST.json exactly (no npm on the Pi)."""
    try:
        files = json.loads((static/'MANIFEST.json').read_text(encoding='utf-8'))['files']
    except (OSError, ValueError, KeyError, TypeError):
        raise UpdateError('the UI bundle has no readable MANIFEST.json') from None
    if not isinstance(files, dict) or 'index.html' not in files:
        raise UpdateError('the UI bundle MANIFEST.json lists no index.html')
    found = {}
    for path in sorted(static.rglob('*')):
        if path.is_symlink():
            raise UpdateError(f'the UI bundle contains a symlink: {path.relative_to(static)}')
        if path.is_file() and path.name not in ('MANIFEST.json', '.DS_Store'):
            found[path.relative_to(static).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    problems = sorted(p for p in set(files) | set(found) if files.get(p) != found.get(p))
    if problems:
        raise UpdateError(f"the UI bundle does not match MANIFEST.json ({', '.join(problems[:3])})")


def staged_checks(stage, status, state, quick_tests=QUICK_TESTS):
    python = sys.executable or 'python3'
    tests = [t for t in quick_tests if (stage/'publisher/tests'/f'{t}.py').is_file()]
    if not tests:
        raise UpdateError('the staged commit has none of the quick publisher tests')
    # -I (isolated: no PYTHON* variables, no user site, no cwd on sys.path) and -B for every step.
    steps = (('compile', [python, '-I', '-m', 'compileall', '-q', 'publisher/app', 'contract'], 300),
             ('import every module', [python, '-I', '-B', '-c', IMPORT_CHECK, str(stage/'publisher/app')], 120),
             ('contract tests', [python, '-I', '-B', '-c', TEST_RUNNER, str(stage/'contract/tests')], 300),
             ('publisher tests', [python, '-I', '-B', '-c', TEST_RUNNER, str(stage/'publisher/tests'), *tests], 1200))
    for name, command, timeout in steps:
        log_line(status, f'Staged check: {name}')
        write_status(state, status)
        proc = run(command, stage, timeout)
        if proc.returncode != 0:
            last = [line for line in tail(proc, 1200).splitlines() if line.strip()][-4:]
            raise UpdateError(f"staged check failed ({name}): {' | '.join(last)}")
    log_line(status, 'Staged check: UI bundle matches MANIFEST.json')
    check_static(stage/'publisher/app/static')


def stage_base(repo):
    """Staging worktrees live inside the checkout's .git, which only the update user can write. Never in a folder
    a scalar-social process can write: the staged checks run code from the stage."""
    return Path(repo)/'.git'/STAGE_DIR


def remove_stages(repo, base):
    """Leftovers of a run that was killed (timeout, power loss) before its own cleanup."""
    for stage in (p for p in Path(base).glob('stage-*') if p.is_dir()):
        git(repo, 'worktree', 'remove', '--force', str(stage), timeout=120)
        shutil.rmtree(stage, ignore_errors=True)
    git(repo, 'worktree', 'prune', timeout=60)


def clear_index_lock(repo, newer_than=None, older_than=None):
    """Remove .git/index.lock left by a killed git: one of ours (mtime >= newer_than, our child is dead by now),
    or one older than `older_than` seconds, which no live git can still hold (the unit is single-instance)."""
    lock = Path(repo)/'.git'/'index.lock'
    try:
        mtime = lock.lstat().st_mtime
    except OSError:
        return False
    if (newer_than is not None and mtime >= newer_than) or (older_than is not None and time.time() - mtime > older_than):
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()
        return True
    return False


def roll_back(repo, old, started):
    """reset --hard to `old`; SIGTERM is ignored meanwhile so a stop request cannot cut the reset short."""
    previous = None
    with contextlib.suppress(ValueError):  # signal handlers can only change in the main thread
        previous = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        clear_index_lock(repo, newer_than=started - 1)
        return git(repo, 'reset', '--hard', '--quiet', old, timeout=300)
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def switch(repo, old, sha):
    started = time.time()
    try:
        merge = git(repo, 'merge', '--ff-only', '--quiet', sha, timeout=300)
        if merge.returncode != 0:
            raise UpdateError(f'git merge --ff-only failed: {tail(merge)}')
        verify_switched(repo, sha)
    except BaseException as error:  # Stopped (SIGTERM) included: never leave a half-merged checkout
        reset = roll_back(repo, old, started)
        if reset.returncode != 0 or running_commit(repo) != old:
            raise UpdateError(f'{error}; rollback to {old[:12]} also failed: {tail(reset)}') from error
        raise UpdateError(f'{error} (rolled back to {old[:12]})') from error


def verify_switched(repo, sha):
    head = running_commit(repo)
    if head != sha:
        raise UpdateError(f'HEAD is {head} after the merge, expected {sha}')
    porcelain = git(repo, 'status', '--porcelain')
    if porcelain.returncode or porcelain.stdout.strip():
        raise UpdateError('the checkout is not clean after the merge')


def do_apply(state, repo, status, sha, lock_timeout=LOCK_TIMEOUT, quick_tests=QUICK_TESTS, deadline=None,
             restart_wait=RESTART_WAIT, verify_wait=VERIFY_WAIT, lock_path=RUNNER_LOCK):
    """`deadline`: time.monotonic() at which systemd stops the unit (TimeoutStartSec)."""
    deadline = time.monotonic() + UNIT_TIMEOUT if deadline is None else deadline
    old = running_commit(repo)
    status.update(phase='staging', fromCommit=old, toCommit=sha, error=None, startedAt=utc())
    log_line(status, f'Update to {sha[:12]} requested')
    write_status(state, status)
    stage = stage_base(repo)/f"stage-{status['requestId']}"
    error = None
    switched = False
    try:
        if not old:
            raise UpdateError('this is not a git checkout')
        if clear_index_lock(repo, older_than=STALE_SECONDS):
            log_line(status, 'Removed a stale .git/index.lock left by a killed run')
        remove_stages(repo, stage_base(repo))
        proc = fetch(repo)
        if proc.returncode:
            raise UpdateError(f'git fetch failed: {tail(proc)}')
        if origin_commit(repo) != sha:
            raise UpdateError('origin changed after confirmation; check for updates again')
        check = inspect(repo)
        for bad, message in ((not check['branchOk'], f'the checkout is not on branch {BRANCH}'),
                             (not check['originOk'], 'the checkout origin is not the expected GitHub repository'),
                             (check['dirty'], 'the checkout has local changes'),
                             (check['diverged'], f'the checkout has diverged from origin/{BRANCH}'),
                             (old == sha, 'already up to date')):
            if bad:
                raise UpdateError(f'{message}; nothing was changed')
        log_line(status, f'Staging {sha[:12]}')
        write_status(state, status)
        stage.parent.mkdir(mode=0o700, exist_ok=True)
        added = git(repo, 'worktree', 'add', '--detach', '--quiet', str(stage), sha, timeout=300)
        if added.returncode:
            raise UpdateError(f'git worktree add failed: {tail(added)}')
        staged_checks(stage, status, state, quick_tests)
        status['phase'] = 'waiting'
        log_line(status, 'Staged checks passed; waiting for the publisher lock')
        write_status(state, status)
        left = deadline - time.monotonic() - SWITCH_MARGIN
        if left <= 0:
            raise UpdateError('not enough time left before the update service time limit; nothing was changed')
        with runner_lock(lock_path, min(lock_timeout, left)):
            if deadline - time.monotonic() < SWITCH_MARGIN:
                raise UpdateError('not enough time left before the update service time limit; nothing was changed')
            status['phase'] = 'switching'
            log_line(status, f'Fast-forwarding {old[:12]} -> {sha[:12]}')
            write_status(state, status)
            if running_commit(repo) != old:
                raise UpdateError('HEAD moved while staging; nothing was changed')
            switch(repo, old, sha)
            switched = True
    except UpdateError as failure:
        error = str(failure)
    except Exception as failure:
        error = f'unexpected {type(failure).__name__}: {redact(str(failure))[:200]}'
    finally:
        if stage.exists():
            git(repo, 'worktree', 'remove', '--force', str(stage), timeout=120)
            shutil.rmtree(stage, ignore_errors=True)
        git(repo, 'worktree', 'prune', timeout=60)
    if error:
        status.update(phase='failed', error=error)
        log_line(status, f'Failed: {error}')
        write_status(state, status)
        return
    status.update(phase='switched', check=inspect(repo))
    log_line(status, f'Switched to {sha[:12]}; the UI restarts on it')
    write_status(state, status)
    if switched:
        verify_restart(state, repo, status, old, sha, restart_wait, verify_wait)


def verify_restart(state, repo, status, old, sha, restart_wait=RESTART_WAIT, verify_wait=VERIFY_WAIT, poll=1.0):
    """After the switch the old UI reports `restarting` and exits 86; the new one reports `serving` once it is
    listening (inbox/ui.json). If the old UI restarted but the new one never serves within `verify_wait`
    (crash loop, never ready), reset the checkout to `old` so systemd's next restart runs the previous code. If
    the UI never restarted (not running), leave the switch in place: it is picked up when the UI next starts."""
    request = status['requestId']
    end = time.monotonic() + restart_wait
    while True:
        ui = read_ui(state, request)
        if ui and ui['phase']:
            break
        if time.monotonic() >= end:
            log_line(status, 'The UI has not restarted yet; it runs the new code when it next starts')
            write_status(state, status)
            return
        time.sleep(poll)
    end = time.monotonic() + verify_wait
    while True:
        ui = read_ui(state, request)
        if ui and ui['phase'] == 'serving':
            if ui['running'] == sha:
                status.update(phase='complete', error=None)
                log_line(status, f'UI restarted on {sha[:12]}; update complete')
                try:
                    if queue_units_apply(state, repo, sha):
                        log_line(status, 'Unit or package changes queued; the Pi applies them automatically')
                except OSError as failure:
                    log_line(status, f'Could not queue the automatic unit apply ({type(failure).__name__}); run apply-units.sh')
            else:
                status.update(phase='failed', error=f"The UI restarted on {(ui['running'] or 'a non-git install')[:12]}, not {sha[:12]}.")
                log_line(status, status['error'])
            write_status(state, status)
            return
        if time.monotonic() >= end:
            break
        time.sleep(poll)
    if running_commit(repo) != sha:
        status.update(phase='failed', error=f'The UI did not come back on {sha[:12]} and the checkout moved; see Rollback in the guide.')
        log_line(status, status['error'])
        write_status(state, status)
        return
    reset = roll_back(repo, old, time.time())
    if reset.returncode or running_commit(repo) != old:
        error = (f'The UI did not come back on {sha[:12]} within {verify_wait:g} s and the rollback to {old[:12]} failed: '
                 f'{tail(reset)}. See Rollback in the guide.')
    else:
        error = (f'The UI did not come back on {sha[:12]} within {verify_wait:g} s; rolled back to {old[:12]}. '
                 'It restarts on the previous code.')
    status.update(phase='failed', error=error, check=inspect(repo))
    log_line(status, error)
    write_status(state, status)


def origin_commit(repo):
    proc = git(repo, 'rev-parse', '--verify', '-q', f'refs/remotes/origin/{BRANCH}^{{commit}}')
    return proc.stdout.strip() if proc.returncode == 0 else None


def real_dir(path):
    path = Path(path)
    return path.is_dir() and not path.is_symlink()


def run_request(state, repo, lock_timeout=LOCK_TIMEOUT, quick_tests=QUICK_TESTS, now=None, deadline=None,
                restart_wait=RESTART_WAIT, verify_wait=VERIFY_WAIT, lock_path=RUNNER_LOCK):
    """Entry point of scalar-social-update.service: always consumes inbox/request.json first (no path-unit loop).
    A request the UI queues while this run is finishing is handled in the same run (up to 3)."""
    if not (real_dir(state) and real_dir(inbox(state))):
        print('update state folder or its inbox is missing or a symlink; refusing', file=sys.stderr)
        return 1
    for _ in range(3):
        if not take_request(state, repo, lock_timeout, quick_tests, now, deadline, restart_wait, verify_wait, lock_path):
            break
    return 0


def take_request(state, repo, lock_timeout, quick_tests, now, deadline, restart_wait, verify_wait, lock_path):
    taken = inbox(state)/'request.taken.json'
    try:
        os.replace(inbox(state)/'request.json', taken)
    except FileNotFoundError:
        return False
    try:
        request = read_json(taken, SMALL_JSON_MAX)
        if not isinstance(request, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(request.get('requestId'))):
            status = {**read_status(state), 'phase': 'failed', 'error': 'Unreadable update request.'}
            log_line(status, 'Unreadable update request ignored')
            write_status(state, status)
            return True
        status = {**read_status(state), 'requestId': request['requestId'], 'startedAt': utc(), 'log': []}
        requested = parse_utc(request.get('requestedAt'))
        age = (time.time() if now is None else now) - requested if requested is not None else None
        if age is None or age > REQUEST_MAX_AGE or age < -300:
            status.update(phase='failed', error='The update request is older than 15 minutes (or undated) and was ignored; '
                                                 'nothing was changed. Check for updates again.')
            log_line(status, 'Expired update request ignored')
            write_status(state, status)
            return True
        if request.get('action') == 'check':
            do_check(state, repo, status)
        elif request.get('action') == 'apply' and SHA40.fullmatch(str(request.get('sha'))):
            do_apply(state, repo, status, request['sha'], lock_timeout, quick_tests, deadline, restart_wait, verify_wait,
                     lock_path)
        else:
            status.update(phase='failed', error='Unknown update request.')
            write_status(state, status)
        return True
    finally:
        with contextlib.suppress(FileNotFoundError):
            taken.unlink()


# --- UI process: report restarts; it never writes status.json ------------------------------------
def reconcile(state, running):
    """At UI start, once the HTTP socket listens: report `serving` for a switched run, so the update unit (or,
    if none is waiting, current_status()) can close it as complete or failed."""
    status = read_status(state)
    if status['phase'] == 'switched' and status['requestId']:
        write_ui(state, status['requestId'], 'serving', running)
    return current_status(state)


def watch_once(state, repo, running, exit=os._exit, pause=0.5):
    status = read_status(state)
    if not running or status['phase'] not in ('switched', 'failed'):
        return False
    head = running_commit(repo)
    if not head or head == running:
        return False
    if status['phase'] == 'failed':
        # An automatic rollback happened under a UI that came up late on the new commit: restart on the old one,
        # leaving the failure (and its explanation) as it is.
        if status['toCommit'] != running or status['fromCommit'] != head:
            return False
        print(f'update watcher: rolled back to {head[:12]}; restarting', file=sys.stderr, flush=True)
    else:
        if read_ui(state, status['requestId']):
            return False  # this request's restart was already reported (and this process is not the new one)
        write_ui(state, status['requestId'], 'restarting', running)
        print(f'update watcher: restarting on {head[:12]}', file=sys.stderr, flush=True)
    time.sleep(pause)  # let in-flight responses finish
    exit(RESTART_EXIT)
    return True


def start_watcher(state, repo, running, interval=2.0, exit=os._exit):
    path = folder(state)/'status.json'

    def loop():
        seen = None
        while True:
            time.sleep(interval)
            try:
                stamp = path.stat().st_mtime_ns
            except OSError:
                continue
            if stamp != seen:
                seen = stamp
                try:
                    watch_once(state, repo, running, exit)
                except Exception as error:  # the watcher must never take the UI down by accident
                    print(f'update watcher: {type(error).__name__}', file=sys.stderr)
    thread = threading.Thread(target=loop, name='update-watcher', daemon=True)
    thread.start()
    return thread


def main(argv=None):
    parser = argparse.ArgumentParser(description='Scalar Pi self-update (run by scalar-social-update.service).')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('run-request', 'info'):
        command = sub.add_parser(name)
        command.add_argument('--state', default=UPDATE_STATE)
        command.add_argument('--repo', default=str(REPO))
        if name == 'run-request':
            command.add_argument('--runner-lock', default=RUNNER_LOCK)
            command.add_argument('--lock-timeout', type=float, default=LOCK_TIMEOUT)
            # Tests and the Mac demo only; the unit uses the defaults.
            command.add_argument('--restart-wait', type=float, default=RESTART_WAIT, help=argparse.SUPPRESS)
            command.add_argument('--verify-wait', type=float, default=VERIFY_WAIT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command == 'info':
        print(json.dumps(info(args.state, args.repo, running_commit(args.repo)), indent=1))
        return 0
    os.umask(0o022)  # the checkout must stay readable (never writable) for the scalar-social services
    deadline = time.monotonic() + UNIT_TIMEOUT
    install_sigterm()
    return run_request(args.state, Path(args.repo), args.lock_timeout, deadline=deadline,
                       restart_wait=args.restart_wait, verify_wait=args.verify_wait, lock_path=args.runner_lock)


def install_sigterm():
    """systemd stops the unit with SIGTERM (TimeoutStartSec, shutdown): raise once so switch() rolls back and the
    finally blocks remove the stage; further SIGTERMs are ignored so that cleanup can finish."""
    def stop(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise Stopped('the update service was stopped by systemd (time limit or shutdown)')
    signal.signal(signal.SIGTERM, stop)


if __name__ == '__main__':
    sys.exit(main())
