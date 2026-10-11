"""Read-only dashboard, history, job detail and backup for the Pi UI. Never publishes.

Three statuses stay separate and are never merged into one "healthy" flag:
posting test passed (confirmed ledger receipts), currently authenticated (token health
files and failure markers) and recurring publishing enabled (config, PAUSED, channels,
timer). Ledger access is read-only; nothing here takes the runner lock.
"""
import contextlib
import csv
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from zoneinfo import ZoneInfo

PLATFORM_ORDER = ('instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok')
UNITS = ('scalar-social.timer', 'scalar-social.service', 'scalar-social-monitor.timer', 'scalar-social-monitor.service',
         'scalar-social-instagram-refresh.timer', 'scalar-social-instagram-refresh.service',
         'scalar-social-threads-refresh.timer', 'scalar-social-threads-refresh.service',
         'scalar-social-approve.path', 'scalar-social-approve.service', 'scalar-social-ui.service',
         'scalar-social-metrics.timer', 'scalar-social-metrics.service', 'scalar-social-metrics.path',
         'scalar-social-autopilot.timer', 'scalar-social-autopilot.service')
UNCERTAIN = ('dispatching', 'uncertain', 'accepted')
# STATE/metrics/ (post stats switch and manual reads): the UI writes `enabled`, `request.json` and switch events;
# metrics.py writes `last-run.json` and moves consumed requests into history/. Both writers keep the newest 200.
METRICS_DIR = 'metrics'
METRICS_CAP = 64*1024
METRICS_HISTORY_NAME = re.compile(r'(request|switch)-(\d{8}T\d{6}Z)-[0-9a-f]{6}\.json')
METRICS_HISTORY_KEEP = 200
# Recorded 6 October 2026 in the private FIRST_POST_TEST record (Meta debugger); separate from token expiry.
FACEBOOK_DATA_ACCESS_DEADLINE = 1799105397
BUFFER_WINDOWS = ((900, 80, '15 minutes'), (86400, 200, '24 hours'), (2592000, 2400, '30 days'))
PAGES_LIMIT = 120

ERRORS = {
    'authorization': ('Account access refused',
                      'The platform refused the saved login or permission for this account.',
                      'Check the account connection and renew access with the documented owner command. This job will not retry on its own.'),
    'rejected': ('Platform refused the post',
                 'The platform rejected this caption or video format.',
                 'Fix the text or video for that platform and include it in a new draft.'),
    'remote_rejected': ('Platform reported a failure',
                        'The platform confirmed it did not publish this post.',
                        'Check the account on the platform, then include the video in a new draft if you still want it.'),
    'budget': ('Free-plan safety limit reached',
               'The Pi paused this job to stay inside the free API or deployment limits.',
               'Wait for the limit window to reset. Nothing is lost.'),
    'local_api_budget_exhausted': ('Free-plan safety limit reached',
                                   'The Pi paused this job to stay inside the free API limits.',
                                   'Wait for the limit window to reset. Nothing is lost.'),
    'media': ('Video could not be verified',
              'The public copy of the video was missing or did not match its fingerprint.',
              'Approve the schedule again so the video is redeployed and checked.'),
    'rate_limit': ('Platform asked to slow down',
                   'The platform limited requests for now.',
                   'No action needed; the Pi tries again after the wait.'),
    'uncertain_response': ('Result unknown, checking',
                           'The request may have reached the platform. The Pi looks for the post instead of sending it again.',
                           'Check the account profile. If the post is clearly there or clearly absent, record that with the owner resolve command. Never post it again by hand.'),
    'remote_confirmation_pending': ('Waiting for the platform to confirm',
                                    'The platform accepted the request but has not shown the finished post yet.',
                                    'No action needed unless this lasts more than a day; then check the profile.'),
    'missed_slot': ('Missed its time',
                    'The Pi was off or paused beyond the allowed lateness, so the post was skipped.',
                    'Include the video in a new draft if you still want it.'),
    'retry_limit': ('Stopped after three attempts',
                    'Three tries did not succeed.',
                    'Check the account and the video, then schedule it in a new draft.'),
    'parent_unavailable': ('Comment not sent',
                           'Its main post never confirmed, so the comment or reply was held back.',
                           'No action needed. It will not be sent.'),
    'owner_verified_absent': ('Marked not published by the owner',
                              'The owner checked the platform and recorded that this post does not exist.',
                              'Include the video in a new draft if you still want it.'),
}
ISSUES = {
    'ledger_missing': ('Posting history not found', 'Check that the publisher state folder exists.'),
    'ledger_integrity': ('Posting history failed its integrity check', 'Stop and restore from the latest backup before any posting.'),
    'publication_needs_review': ('Some posts need review', 'Open the jobs marked uncertain, blocked or failed below.'),
    'publication_missed': ('A post missed its time in the last 24 hours', 'Check that the Pi stayed on; missed posts are not retried. Approve a new schedule to use the video.'),
    'publisher_health_missing': ('Publisher has not reported yet', 'Check the publisher timer state.'),
    'publisher_health_stale': ('Publisher report is out of date', 'Check that the Pi is on and the publisher timer is running.'),
    'content_exhausted': ('Out of approved videos', 'Upload and approve more videos, then approve a new schedule.'),
    'threads_token_expiring': ('Threads access expires within two days', 'Check the Threads renewal timer result.'),
    'threads_token_renewal_failed': ('Threads access renewal failed', 'Check the Threads renewal timer result; the current token stays in use until it expires.'),
    'threads_token_health_missing': ('Threads access status unknown', 'Check the Threads renewal timer result.'),
    'instagram_token_renewal_failed': ('Instagram access renewal failed', 'Check the Instagram renewal timer result; renew with the owner command if needed.'),
    'instagram_token_expiring': ('Instagram access expires within two days', 'Check the Instagram renewal timer result.'),
    'instagram_token_health_missing': ('Instagram access status unknown', 'Check the Instagram renewal timer result.'),
}
RESOLVE_JOB = Path(__file__).resolve().parent/'resolve_job.py'  # right for the git checkout and the old copy install
OWNER_ACTIONS = [
    'Open the account profile on the platform and look for this exact post.',
    f'If it is there: sudo python3 -I -B {RESOLVE_JOB} <job id> --confirmed --permalink <post URL> --evidence "<what you saw>"',
    f'If it is definitely not there: sudo python3 -I -B {RESOLVE_JOB} <job id> --not-published --evidence "<what you checked>"',
    'Never post it again by hand while it shows as uncertain: that can create a duplicate.',
]


def explain(category):
    title, detail, action = ERRORS.get(category or '', ('Needs attention', 'The publisher recorded an unexpected state.', 'Check the job events below.'))
    return {'category': category, 'title': title, 'detail': detail, 'nextAction': action}


def utc(value):
    return value.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def display(slot, zone):
    moment = dt.datetime.fromisoformat(slot)
    local = moment.astimezone(zone)
    return {'utc': utc(moment), 'local': local.isoformat(), 'zone': local.tzname()}


@contextlib.contextmanager
def ledger_ro(state):
    path = Path(state)/'ledger.sqlite3'
    if not path.is_file():
        yield None
        return
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def _table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def read_small_json(path, cap=METRICS_CAP):
    """Parsed JSON of a regular, non-symlink file of at most `cap` bytes; None when absent, unreadable or malformed."""
    import ui_approval
    try:
        return json.loads(ui_approval.read_capped(path, cap))
    except (OSError, ValueError, RecursionError):  # FileNotFoundError is an OSError, UnicodeDecodeError a ValueError
        return None


def metrics_files(state):
    """Raw STATE/metrics/ facts (read-only): the hourly-reads flag, the pending request and the last run, unvalidated."""
    folder = Path(state)/METRICS_DIR
    request = folder/'request.json'
    try:
        waiting = request.lstat().st_mtime   # present even when unreadable: the UI must still show it as pending
    except OSError:
        waiting = None
    return {'enabled': (folder/'enabled').exists(), 'pending': read_small_json(request), 'pendingSince': waiting,
            'lastRun': read_small_json(folder/'last-run.json')}


def metrics_history(state):
    """[(stamp, kind, path)] of STATE/metrics/history/ files, oldest first (stamp, then name), newest KEEP only."""
    folder = Path(state)/METRICS_DIR/'history'
    try:
        names = [p.name for p in folder.iterdir()]
    except OSError:
        return []
    found = sorted((m.group(2), name, m.group(1)) for name in names if (m := METRICS_HISTORY_NAME.fullmatch(name)))
    return [(stamp, kind, folder/name) for stamp, name, kind in found[-METRICS_HISTORY_KEEP:]]


def systemctl_show(unit, runner=subprocess.run):
    props = 'LoadState,UnitFileState,ActiveState,SubState,Result,ExecMainStatus,ExecMainExitTimestamp,LastTriggerUSec,NextElapseUSecRealtime'
    try:
        result = runner(['systemctl', 'show', unit, '--property=' + props], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {'unit': unit, 'available': False}
    if result.returncode:
        return {'unit': unit, 'available': False}
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    return {'unit': unit, 'available': values.get('LoadState') == 'loaded',
            'enabled': values.get('UnitFileState'), 'active': values.get('ActiveState'), 'sub': values.get('SubState'),
            'result': values.get('Result'), 'exitStatus': values.get('ExecMainStatus'),
            'lastExit': values.get('ExecMainExitTimestamp') or None, 'lastTrigger': values.get('LastTriggerUSec') or None,
            'nextRun': values.get('NextElapseUSecRealtime') or None}


def _accounts(channel):
    return [a for a in [channel.get('accountId'), *channel.get('previousAccountIds', [])] if a]


def posting_tests(db, config):
    """Confirmed ledger receipts per platform (current or previous account identifiers)."""
    result = {}
    for platform, channel in config['channels'].items():
        row = None
        accounts = _accounts(channel)
        if db is not None and accounts:
            row = db.execute('SELECT permalink, published_at FROM jobs WHERE platform=? AND status=? AND account IN (%s) '
                             'ORDER BY published_at LIMIT 1' % ','.join('?'*len(accounts)), (platform, 'confirmed', *accounts)).fetchone()
        result[platform] = {'passed': bool(row), 'permalink': row['permalink'] if row else None,
                            'publishedAt': row['published_at'] if row else None}
    return result


def authentication(state, config, now):
    state = Path(state)
    out = {}
    for platform, channel in config['channels'].items():
        route = channel.get('route')
        entry = {'state': 'unknown', 'detail': None, 'expiresAt': None, 'checkedAt': None, 'renewalFailed': False}
        if route == 'disabled' or not channel.get('identityVerified'):
            entry.update(state='not-connected', detail=channel.get('reason') or 'Not connected on this Pi')
        elif route in ('threads', 'instagram'):
            failure = (state/f'{route}-token-failure.json').exists()
            health = read_json(state/f'{route}-token-health.json') or {}
            entry['renewalFailed'] = failure
            with contextlib.suppress(OSError, ValueError):  # ValueError: neither file exists
                entry['checkedAt'] = utc(dt.datetime.fromtimestamp(max(
                    p.stat().st_mtime for p in (state/f'{route}-token-health.json', state/f'{route}-token-failure.json')
                    if p.exists()), dt.timezone.utc))
            try:
                expires = dt.datetime.fromisoformat(health['expiresAt'])
                entry['expiresAt'] = utc(expires)
                left = (expires-now).total_seconds()
                entry['state'] = 'failed' if failure else 'expiring' if left < 2*86400 else 'ok'
                entry['detail'] = ('Last renewal failed' if failure else
                                   'Renewed by the timer' if health.get('renewed') else 'Initial estimate; first renewal not yet confirmed')
            except (KeyError, TypeError, ValueError):
                entry.update(state='failed' if failure else 'unknown', detail='No access status recorded yet')
        elif route == 'facebook':
            deadline = dt.datetime.fromtimestamp(channel.get('dataAccessExpiresAt') or FACEBOOK_DATA_ACCESS_DEADLINE, dt.timezone.utc)
            left = (deadline-now).total_seconds()
            entry.update(state='expiring' if left < 14*86400 else 'ok', expiresAt=utc(deadline),
                         detail='Page token does not expire; Meta data-access must be reconfirmed before this date')
        elif route == 'bluesky':
            entry.update(state='ok', detail='App password; no renewal needed. Checked at each post.')
        elif route == 'buffer':
            entry.update(state='unknown', detail='Buffer connection is checked only when a post is sent')
        out[platform] = entry
    return out


def recurring(state, config, timer):
    sentinel = (Path(state)/'PAUSED').exists()
    channels = {p: bool(c.get('enabled')) for p, c in config['channels'].items()}
    timer_on = timer.get('enabled') == 'enabled' and timer.get('active') == 'active'
    return {'enabled': bool(not config.get('paused') and not sentinel and timer_on and any(channels.values())),
            'configPaused': bool(config.get('paused')), 'pausedSentinel': sentinel,
            'timerEnabled': timer.get('enabled') == 'enabled', 'timerActive': timer.get('active') == 'active',
            'channels': channels}


def budgets(db, now):
    epoch = now.timestamp()
    pages = buffer = None
    if db is not None:
        if _table(db, 'deployments'):
            pages = db.execute('SELECT count(*) FROM deployments WHERE at>?', (epoch-31*86400,)).fetchone()[0]
        if _table(db, 'calls'):
            buffer = [{'window': label, 'used': db.execute('SELECT count(*) FROM calls WHERE at>?', (epoch-seconds,)).fetchone()[0],
                       'limit': limit} for seconds, limit, label in BUFFER_WINDOWS]
    return {'pagesDeployments': {'used': pages or 0, 'limit': PAGES_LIMIT, 'window': '31 days'},
            'bufferCalls': buffer or [{'window': label, 'used': 0, 'limit': limit} for _, limit, label in BUFFER_WINDOWS]}


def uncertain_jobs(db, zone):
    if db is None:
        return []
    rows = db.execute('SELECT * FROM jobs WHERE status IN (?,?,?) ORDER BY slot', UNCERTAIN).fetchall()
    out = []
    for row in rows:
        last = db.execute('SELECT at FROM events WHERE job=? ORDER BY seq DESC LIMIT 1', (row['id'],)).fetchone()
        out.append({'id': row['id'], 'platform': row['platform'], 'account': row['account'], 'episode': row['episode'], 'status': row['status'],
                    'slot': display(row['slot'], zone), 'dispatchedAt': row['dispatched_at'],
                    'lastCheck': last['at'] if last else None,
                    'nextCheck': utc(dt.datetime.fromtimestamp(row['retry_at'], dt.timezone.utc)) if row['retry_at'] else None,
                    'error': explain(row['error'] or 'uncertain_response'), 'ownerActions': OWNER_ACTIONS})
    return out


def dashboard(state, config_path, now=None, show=systemctl_show, approval=None):
    from operations import inspect
    state = Path(state)
    now = now or dt.datetime.now(dt.timezone.utc)
    config = json.loads(Path(config_path).read_text())
    zone = ZoneInfo(config.get('timezone') or 'UTC')
    units = {u: show(u) for u in UNITS}
    with ledger_ro(state) as db:
        tests = posting_tests(db, config)
        spend = budgets(db, now)
        waiting = uncertain_jobs(db, zone)
        counts = dict(db.execute('SELECT status, count(*) FROM jobs GROUP BY status').fetchall()) if db else {}
    try:
        issues = [{'code': i, 'title': ISSUES.get(i, (i, ''))[0], 'nextAction': ISSUES.get(i, ('', 'Check the Pi.'))[1]}
                  for i in inspect(config_path, state, now)['issues']]
    except (OSError, ValueError, KeyError, sqlite3.Error):
        issues = [{'code': 'inspection_failed', 'title': 'Health check could not read the publisher state',
                   'nextAction': 'Check storage and permissions on the Pi.'}]
    health = read_json(state/'health.json')
    health_age = None
    if health and health.get('checkedAt'):
        try:
            health_age = int((now-dt.datetime.fromisoformat(health['checkedAt'])).total_seconds())
        except ValueError:
            pass
    disk = shutil.disk_usage(state)
    return {
        'checkedAt': utc(now), 'timezone': config.get('timezone'),
        'platforms': [p for p in PLATFORM_ORDER if p in config['channels']],
        'postingTestPassed': tests,
        'currentlyAuthenticated': authentication(state, config, now),
        'recurringPublishing': recurring(state, config, units['scalar-social.timer']),
        'units': list(units.values()),
        'publisherHealth': {'checkedAt': (health or {}).get('checkedAt'), 'ageSeconds': health_age,
                            'networkEnabled': (health or {}).get('networkEnabled'), 'ok': (health or {}).get('ok')},
        'monitor': units['scalar-social-monitor.service'],
        'budgets': spend,
        'storage': {'freeBytes': disk.free, 'totalBytes': disk.total, 'libraryBytes': _size(state/'library', state/'site')},
        'jobs': counts, 'issues': issues, 'uncertainJobs': waiting,
        'approval': approval,
    }


def _size(*paths):
    """Bytes on disk under `paths`; the public site hard-links library videos, so each inode counts once."""
    total, seen = 0, set()
    for path in paths:
        for root, _, files in os.walk(path):
            for name in files:
                with contextlib.suppress(OSError):
                    info = os.lstat(os.path.join(root, name))
                    if (info.st_dev, info.st_ino) not in seen:
                        seen.add((info.st_dev, info.st_ino))
                        total += info.st_size
    return total


def _job_view(row, zone):
    payload = json.loads(row['payload'])
    episode = payload.get('episode') or {}
    return {'id': row['id'], 'platform': row['platform'], 'account': row['account'],
            'slot': display(row['slot'], zone), 'episode': row['episode'], 'episodeId': episode.get('episodeId'),
            'game': episode.get('game'), 'kind': payload.get('kind') or 'post', 'status': row['status'],
            'attempts': row['attempts'], 'error': explain(row['error']) if row['error'] else None,
            'permalink': row['permalink'], 'publishedAt': row['published_at'], 'dispatchedAt': row['dispatched_at'],
            'caption': payload.get('caption'), 'mediaSha256': (payload.get('media') or {}).get('sha256'),
            'dispatched': bool(row['dispatched_at']) or row['status'] != 'ready'}


def history(state, config, filters=None):
    filters = filters or {}
    zone = ZoneInfo(filters.get('timezone') or config.get('timezone') or 'UTC')
    clauses, params = [], []
    for key, column in (('platform', 'platform'), ('status', 'status')):
        if filters.get(key):
            clauses.append(f'{column}=?')
            params.append(filters[key])
    if filters.get('from'):
        clauses.append('slot>=?')
        params.append(dt.datetime.combine(dt.date.fromisoformat(filters['from']), dt.time(), zone).astimezone(dt.timezone.utc).isoformat())
    if filters.get('to'):
        clauses.append('slot<?')
        params.append(dt.datetime.combine(dt.date.fromisoformat(filters['to'])+dt.timedelta(days=1), dt.time(), zone).astimezone(dt.timezone.utc).isoformat())
    query = 'SELECT * FROM jobs' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY slot DESC, id'
    with ledger_ro(state) as db:
        rows = [] if db is None else [_job_view(r, zone) for r in db.execute(query, params).fetchall()]
    needle = (filters.get('q') or '').casefold().strip()
    game = filters.get('game')
    return [r for r in rows if (not game or r['game'] == game)
            and (not needle or needle in ' '.join(str(r[k] or '') for k in ('episode', 'episodeId', 'caption', 'permalink', 'id')).casefold())]


CSV_FIELDS = ('id', 'platform', 'account', 'slotLocal', 'zone', 'slotUtc', 'episode', 'episodeId', 'game', 'kind',
              'status', 'attempts', 'error', 'permalink', 'publishedAt', 'dispatchedAt', 'mediaSha256', 'caption')


def history_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, lineterminator='\n')
    writer.writeheader()
    for r in rows:
        writer.writerow({**{k: r.get(k) for k in CSV_FIELDS}, 'slotLocal': r['slot']['local'], 'zone': r['slot']['zone'],
                         'slotUtc': r['slot']['utc'], 'error': (r['error'] or {}).get('category')})
    return out.getvalue()


def job_detail(state, config, job_id):
    zone = ZoneInfo(config.get('timezone') or 'UTC')
    with ledger_ro(state) as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone() if db else None
        if row is None:
            return None
        events = [{'seq': e['seq'], 'kind': e['kind'], 'at': e['at'], 'detail': _event_detail(e['kind'], e['detail'])}
                  for e in db.execute('SELECT * FROM events WHERE job=? ORDER BY seq', (job_id,))]
    view = _job_view(row, zone)
    view['events'] = events
    view['payload'] = json.loads(row['payload'])
    view['reconciliation'] = ({'state': row['status'], 'nextCheck': utc(dt.datetime.fromtimestamp(row['retry_at'], dt.timezone.utc)) if row['retry_at'] else None,
                               'ownerActions': OWNER_ACTIONS} if row['status'] in UNCERTAIN else None)
    return view


def cancelled_jobs(state, config):
    """Rows removed before dispatch by a re-approved schedule, rebuilt from their 'cancelled' event
    (which holds the full prior row). A slot that holds a live row again is skipped."""
    zone = ZoneInfo(config.get('timezone') or 'UTC')
    out = []
    with ledger_ro(state) as db:
        if db is None:
            return out
        live = {r[0] for r in db.execute('SELECT id FROM jobs')}
        for event in db.execute("SELECT seq, job, at, detail FROM events WHERE kind='cancelled' ORDER BY seq"):
            if event['job'] in live:
                continue
            try:
                row = json.loads(event['detail'])
                view = _job_view(row, zone)
            except (ValueError, KeyError, TypeError):
                continue
            events = [{'seq': e['seq'], 'kind': e['kind'], 'at': e['at'], 'detail': _event_detail(e['kind'], e['detail'])}
                      for e in db.execute('SELECT * FROM events WHERE job=? AND seq<=? ORDER BY seq', (event['job'], event['seq']))]
            out.append({**view, 'status': 'cancelled', 'cancelledAt': event['at'], 'events': events,
                        'payload': json.loads(row['payload'])})
    return out


def _event_detail(kind, detail):
    # Events carry categories or the full prior row of a cancelled job; neither holds credentials.
    if kind == 'cancelled':
        return 'Cancelled before dispatch by a re-approved schedule'
    return detail or None


SECRET_KEY = re.compile(r'(token|secret|password|api_?key|credential)', re.I)


def redact(value):
    if isinstance(value, dict):
        return {k: ('[removed]' if SECRET_KEY.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def backup_archive(state, config, index_path=None, now=None):
    """tar.gz bytes: ledger snapshot, library index snapshot, manifests, batch metadata, config.

    No media files and no credentials (the credentials directory is never read)."""
    from operations import backup
    state = Path(state)
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix='scalar-ui-backup-') as tmp, tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        tmp = Path(tmp)
        def add_bytes(name, data):
            info = tarfile.TarInfo(f'scalar-social-backup-{stamp}/{name}')
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o600
            tar.addfile(info, io.BytesIO(data))
        if (state/'ledger.sqlite3').is_file():
            backup(state/'ledger.sqlite3', tmp/'ledger.sqlite3')
            add_bytes('ledger.sqlite3', (tmp/'ledger.sqlite3').read_bytes())
        index_path = Path(index_path or state/'library/index.sqlite3')
        if index_path.is_file():
            with contextlib.closing(sqlite3.connect(index_path.resolve().as_uri()+'?mode=ro', uri=True)) as src, \
                    contextlib.closing(sqlite3.connect(tmp/'index.sqlite3')) as dst:
                src.backup(dst)
            add_bytes('library-index.sqlite3', (tmp/'index.sqlite3').read_bytes())
            with contextlib.closing(sqlite3.connect(tmp/'index.sqlite3')) as db:
                if _table(db, 'batches'):
                    for batch_id, body in db.execute('SELECT batch_id, batch_json FROM batches ORDER BY batch_id'):
                        add_bytes(f'batches/{batch_id}/batch.json', body.encode())
        for path in sorted((state/'manifests').glob('*.json')) if (state/'manifests').is_dir() else []:
            if path.is_file() and not path.is_symlink():
                add_bytes(f'manifests/{path.name}', path.read_bytes())
        for name in ('health.json', 'threads-token-health.json', 'instagram-token-health.json', 'catalog.json'):
            if (state/name).is_file():
                add_bytes(name, (state/name).read_bytes())
        add_bytes('config.json', (json.dumps(redact(config), indent=2) + '\n').encode())
        add_bytes('README.txt', b'Scalar social backup: posting history (ledger), library index, approved manifests and '
                                b'batch metadata. Videos are not included; keep the Mac library folder as the media backup. '
                                b'No credentials are included.\n')
    return buffer.getvalue(), f'scalar-social-backup-{stamp}.tar.gz'
