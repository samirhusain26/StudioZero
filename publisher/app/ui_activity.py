"""Activity feed for the Pi UI: one reverse-chronological timeline of everything that happened.

Read-only. Sources: ledger `events` joined to their jobs (read-only SQLite URI), the approval
request/result files and their archive, the library index (read-only), and system status from
`systemctl show`, token health/failure marker files and health.json. Never journald, never the
credentials directory, never config secrets. Event details are rebuilt from known vocabulary
(ui_health.ERRORS); free text from the ledger is never echoed, and a `cancelled` event's stored
prior row is reduced to its slot and identity.

Entries are ActivityEntry (publisher/ui/src/api/types.ts). `id` is the stable sort key
`<IsoUtc>|<source id>`; pages go newest first and `before=<id>` continues strictly older.
"""
import contextlib
import csv
import datetime as dt
import heapq
import io
import json
from pathlib import Path
import re
import sqlite3

import ui_health
import ui_views

LIMIT, MAX_LIMIT = 100, 500
KINDS = ('job', 'approval', 'library', 'system')
SEVERITIES = ('info', 'success', 'warning', 'error')
LABELS = ui_views.LABELS
CATEGORY = re.compile(r'[a-z_]{1,40}')
CURSOR = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\|[A-Za-z0-9:._#@|-]{1,180}')
PAGE = 500
HISTORY_FILES = 400
FIELDS = ('id', 'at', 'kind', 'event', 'severity', 'title', 'detail', 'platform', 'accountId', 'jobId', 'episode',
          'episodeId', 'game', 'jobKind', 'permalink', 'draftSha256', 'manifestSha256', 'batchId')
SERVICES = (('scalar-social.service', 'Publisher', None), ('scalar-social-monitor.service', 'Monitor', None),
            ('scalar-social-instagram-refresh.service', 'Instagram token renewal', 'instagram'),
            ('scalar-social-threads-refresh.service', 'Threads token renewal', 'threads'),
            ('scalar-social-approve.service', 'Schedule approval applier', None),
            ('scalar-social-autopilot.service', 'Autopilot (schedule refill)', None),
            ('scalar-social-metrics.service', 'Post stats reader', None),
            ('scalar-social-ui.service', 'Publishing UI', None))


def entry(at, source, kind, event, severity, title, detail=None, **refs):
    stamp = ui_views.iso_utc(at)
    if not stamp:
        return None
    value = {'id': f'{stamp}|{source}', 'at': stamp, 'kind': kind, 'event': event, 'severity': severity,
             'title': title, 'detail': detail}
    for key in FIELDS[7:]:
        value[key] = refs.get(key)
    return value


def query(raw):
    """Validated ActivityQuery from parse_qs output. Raises ValueError (plain text)."""
    value = lambda k: ((raw.get(k) or [None])[0] or None)
    out = {k: value(k) for k in ('platform', 'kind', 'severity', 'before', 'format')}
    for key, allowed in (('platform', ui_views.PLATFORMS), ('kind', KINDS), ('severity', SEVERITIES),
                         ('format', ('json', 'csv'))):
        if out[key] is not None and out[key] not in allowed:
            raise ValueError(f'Unknown {key}: choose one of {", ".join(allowed)}.')
    if out['before'] is not None and not CURSOR.fullmatch(out['before']):
        raise ValueError('before must be the id of an activity entry.')
    limit = value('limit')
    if limit is None:
        out['limit'] = LIMIT
    elif not limit.isdigit() or not 1 <= int(limit) <= MAX_LIMIT:
        raise ValueError(f'limit must be 1–{MAX_LIMIT}.')
    else:
        out['limit'] = int(limit)
    out['format'] = out['format'] or 'json'
    return out


# ---------- ledger ----------

def _category(detail):
    return detail if isinstance(detail, str) and CATEGORY.fullmatch(detail) else None


def _explained(category):
    if not category:
        return None
    title, detail, _ = ui_health.ERRORS.get(category, (category.replace('_', ' ').capitalize(), '', None))
    return f'{title}. {detail}'.strip() if detail else title


def _job_event(event, job, payload):
    """(severity, title, detail, extra refs) for one ledger event; detail never echoes stored text."""
    kind, platform = event['kind'], (job or {}).get('platform')
    where = LABELS.get(platform, platform or 'the platform')
    category = _category(event['detail'])
    if kind == 'ready':
        return 'info', 'Queued again for another attempt', _explained(category), {}
    if kind == 'dispatching':
        return 'info', f'Sending to {where}', None, {}
    if kind == 'accepted':
        return 'info', f'{where} accepted the post; waiting for it to appear', None, {}
    if kind == 'uncertain':
        return 'warning', 'Result unknown; the Pi is checking the platform', _explained(category or 'uncertain_response'), {}
    if kind == 'confirmed':
        permalink = job.get('permalink') if job and job.get('status') == 'confirmed' else None
        return 'success', f'Posted on {where}', None, {'permalink': permalink}
    if kind == 'failed':
        return 'error', f'Failed on {where}', _explained(category), {}
    if kind == 'blocked':
        return 'error', f'Blocked on {where}', _explained(category), {}
    if kind == 'expired':
        return 'warning', 'Not posted', _explained(category), {}
    if kind == 'cancelled':
        slot = ui_views.iso_utc((job or {}).get('slot'))
        return 'info', 'Cancelled before sending', \
            'Removed by a re-approved schedule' + (f' (was due {slot})' if slot else '') + '.', {}
    if kind == 'owner_resolved':
        try:
            detail = json.loads(event['detail'] or '{}')
        except ValueError:
            detail = {}
        if detail.get('resolution') == 'confirmed':
            link = detail.get('permalink') if isinstance(detail.get('permalink'), str) else None
            return 'success', 'Owner confirmed it was posted', 'Recorded with evidence after checking the profile.', \
                {'permalink': link if link and link.startswith('https://') else None}
        return 'info', 'Owner recorded it was not published', 'Recorded with evidence after checking the profile.', {}
    return 'info', kind.replace('_', ' ').capitalize() if CATEGORY.fullmatch(kind or '') else 'Publisher event', None, {}


def _ledger_rows(db, platform, upper):
    """Events newest first, keyset-paged on (at, seq); `upper` bounds the raw `at` from above."""
    last = None
    while True:
        clauses, params = [], []
        if upper:
            clauses.append('e.at < ?')
            params.append(upper)
        if last:
            clauses.append('(e.at < ? OR (e.at = ? AND e.seq < ?))')
            params += [last[0], last[0], last[1]]
        sql = ('SELECT e.seq, e.job, e.kind, e.at, e.detail, j.platform, j.account, j.episode, j.payload, j.status, '
               'j.permalink, j.slot FROM events e LEFT JOIN jobs j ON j.id = e.job'
               + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY e.at DESC, e.seq DESC LIMIT ?')
        rows = db.execute(sql, (*params, PAGE)).fetchall()
        if not rows:
            return
        for row in rows:
            yield row
        if len(rows) < PAGE:
            return
        last = (rows[-1]['at'], rows[-1]['seq'])


def ledger_entries(state, platform=None, upper=None):
    """Generator of job entries, newest first (consumed lazily while merging)."""
    with ui_health.ledger_ro(state) as db:
        if db is None:
            return
        for row in _ledger_rows(db, platform, upper):
            job = {k: row[k] for k in ('platform', 'account', 'episode', 'payload', 'status', 'permalink', 'slot')} \
                if row['platform'] else None
            if row['kind'] == 'cancelled' and job is None:
                try:  # the stored prior row: keep only identity and slot
                    prior = json.loads(row['detail'])
                    job = {k: prior.get(k) for k in ('platform', 'account', 'episode', 'payload', 'slot')}
                except (ValueError, AttributeError, TypeError):
                    job = None
            if row['kind'] == 'content_exhausted':
                p = _category(row['detail'])
                if platform and p != platform:
                    continue
                item = entry(row['at'], f'j:{row["seq"]:012d}', 'job', 'job.content_exhausted', 'warning',
                             f'Out of approved videos for {LABELS.get(p, "a platform")}',
                             'The publisher found no approved video left to post.', platform=p if p in LABELS else None)
                if item:
                    yield item
                continue
            if platform and (job or {}).get('platform') != platform:
                continue
            try:
                payload = json.loads((job or {}).get('payload') or '{}')
            except (ValueError, TypeError):
                payload = {}
            episode = payload.get('episode') if isinstance(payload.get('episode'), dict) else {}
            severity, title, detail, extra = _job_event(row, job, payload)
            kind = payload.get('kind') if payload.get('kind') in ui_views.KINDS else ('post' if job else None)
            event = row['kind'] if CATEGORY.fullmatch(row['kind'] or '') else 'event'
            item = entry(row['at'], f'j:{row["seq"]:012d}', 'job', f'job.{event}', severity, title, detail,
                         platform=(job or {}).get('platform') if (job or {}).get('platform') in LABELS else None,
                         accountId=(job or {}).get('account'), jobId=row['job'], episode=(job or {}).get('episode'),
                         episodeId=episode.get('episodeId') if isinstance(episode.get('episodeId'), str) else None,
                         game=episode.get('game') if episode.get('game') in ui_views.GAMES else None,
                         jobKind=kind, **extra)
            if item:
                yield item


# ---------- approval ----------

def _read(path, cap):
    import ui_approval
    try:
        return json.loads(ui_approval.read_capped(path, cap))
    except (FileNotFoundError, ValueError, OSError):
        return None


def approval_entries(state):
    import ui_approval
    folder = Path(state)/'approval'
    requests, results = [], []
    history = folder/'history'
    names = sorted(p.name for p in history.iterdir() if p.is_file()) if history.is_dir() else []
    for name in names[-HISTORY_FILES:]:
        data = _read(history/name, ui_approval.RESULT_CAP)
        if isinstance(data, dict):
            (requests if name.endswith('-request.json') else results).append(data)
    for name, target, cap in (('request.json', requests, ui_approval.REQUEST_CAP), ('result.json', results, ui_approval.RESULT_CAP)):
        data = _read(folder/name, cap)
        if isinstance(data, dict):
            target.append(data)
    out, seen = [], set()

    def add(item):
        if item and item['id'] not in seen:
            seen.add(item['id'])
            out.append(item)
    for request in requests:
        sha = request.get('draftSha256') if isinstance(request.get('draftSha256'), str) else None
        add(entry(request.get('requestedAt'), f'a:request:{(sha or "unknown")[:16]}', 'approval', 'approval.requested',
                  'info', 'Schedule approval requested', 'The applier validates the draft and deploys its media.',
                  draftSha256=sha))
    for result in results:
        status, sha = result.get('status'), result.get('draftSha256') if isinstance(result.get('draftSha256'), str) else None
        manifest = result.get('manifestSha256') if isinstance(result.get('manifestSha256'), str) else None
        key = (sha or 'unknown')[:16]
        jobs = result.get('jobs') if isinstance(result.get('jobs'), int) else None
        if status in ('manifest-ready', 'bound'):
            add(entry(result.get('at'), f'a:ready:{key}', 'approval', 'approval.manifest-ready', 'success',
                      'Schedule approved: media deployed and verified',
                      f'{jobs} jobs in the approved manifest; waiting for the bind step.' if jobs is not None else None,
                      draftSha256=sha, manifestSha256=manifest))
        if status == 'bound':
            add(entry(result.get('boundAt') or result.get('at'), f'a:bound:{key}', 'approval', 'approval.bound', 'success',
                      'Approved schedule bound in the configuration',
                      'Publishing stays paused until the owner runs the activation command.', draftSha256=sha,
                      manifestSha256=manifest))
        elif status == 'validated-no-deploy':
            add(entry(result.get('at'), f'a:staged:{key}', 'approval', 'approval.validated-no-deploy', 'info',
                      'Schedule validated (staging, not deployed)', 'Nothing was deployed and no configuration changed.',
                      draftSha256=sha))
        elif status == 'failed':
            category = _category(result.get('category')) or 'internal'
            message = result.get('message') if isinstance(result.get('message'), str) else ''
            known = message in ui_approval.MESSAGES.values() or category == 'scope'
            add(entry(result.get('at'), f'a:failed:{key}:{category}', 'approval', 'approval.failed', 'error',
                      f'Schedule approval failed ({category.replace("_", " ")})',
                      message[:400] if known else ui_approval.MESSAGES.get(category, 'Approval stopped. Nothing was scheduled or published.'),
                      draftSha256=sha))
    return out


# ---------- library ----------

@contextlib.contextmanager
def index_ro(state):
    path = Path(state)/'library'/'index.sqlite3'
    if not path.is_file():
        yield None
        return
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def _has(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def library_entries(state):
    out = []
    with index_ro(state) as db:
        if db is None:
            return out
        for row in db.execute('SELECT sha256, batch_id, origin, raw, imported_at FROM batch_documents'):
            try:
                count = len(json.loads(row['raw']).get('episodes') or [])
            except (ValueError, AttributeError):
                count = 0
            title = {'manual': 'Phone upload added to the library', 'legacy': 'Existing Pi media registered'}.get(
                row['origin'], f'Batch {row["batch_id"]} imported')
            out.append(entry(row['imported_at'], f'l:batch:{row["sha256"][:16]}', 'library', 'library.batch-imported',
                             'info', title, f'{count} episode{"" if count == 1 else "s"} in batch {row["batch_id"]}.',
                             batchId=row['batch_id']))
        episodes = {(r['episode_id'], r['revision']): r for r in db.execute(
            'SELECT episode_id, revision, batch_id, question_id, game, video_sha256, status, problems, imported_at FROM episodes')}
        for (episode_id, revision), row in episodes.items():
            if row['status'] == 'invalid':
                try:
                    problems = json.loads(row['problems'])
                except ValueError:
                    problems = []
                out.append(entry(row['imported_at'], f'l:invalid:{episode_id}:{revision}', 'library', 'library.rejected',
                                 'error', f'{episode_id} failed its checks',
                                 '; '.join(str(p) for p in problems)[:400] or None, episodeId=episode_id,
                                 game=row['game'] if row['game'] in ui_views.GAMES else None, batchId=row['batch_id']))
        users = {}
        for (episode_id, revision), row in episodes.items():
            users.setdefault(row['video_sha256'], []).append((episode_id, revision, row))
        for row in db.execute('SELECT sha256, bytes, legacy, registered_at FROM videos'):
            first = sorted(users.get(row['sha256'], []))[:1]
            out.append(entry(row['registered_at'], f'l:video:{row["sha256"][:16]}', 'library', 'library.video-stored',
                             'success', 'Existing clip registered and checked' if row['legacy'] else 'Video uploaded and verified',
                             f'{row["bytes"]:,} bytes, sha256 {row["sha256"][:12]}; measured with ffprobe.',
                             episodeId=first[0][0] if first else None,
                             batchId=first[0][2]['batch_id'] if first else None))
        for row in db.execute('SELECT sha256, bytes, extracted, registered_at FROM covers'):
            out.append(entry(row['registered_at'], f'l:cover:{row["sha256"][:16]}', 'library', 'library.cover-stored',
                             'info', 'Cover frame extracted' if row['extracted'] else 'Cover uploaded and verified',
                             f'{row["bytes"]:,} bytes, sha256 {row["sha256"][:12]}.'))
        for row in db.execute('SELECT id, episode_id, revision, action, reviewer, at, note FROM approvals'):
            meta = episodes.get((row['episode_id'], row['revision']))
            approve = row['action'] == 'approve'
            reviewer = str(row['reviewer'] or 'owner')[:64]
            note = f' Note: {str(row["note"])[:200]}' if row['note'] else ''
            out.append(entry(row['at'], f'l:decision:{row["id"]:08d}', 'library',
                             'library.approved' if approve else 'library.withdrawn', 'success' if approve else 'warning',
                             f'{row["episode_id"]} rev {row["revision"]} {"approved" if approve else "withdrawn"}',
                             f'By {reviewer}.{note}', episodeId=row['episode_id'],
                             game=meta['game'] if meta and meta['game'] in ui_views.GAMES else None,
                             batchId=meta['batch_id'] if meta else None))
        if _has(db, 'deletions'):
            for row in db.execute('SELECT id, episode_id, revision, batch_id, game, at, bytes_freed FROM deletions'):
                out.append(entry(row['at'], f'l:deleted:{row["id"]:08d}', 'library', 'library.deleted', 'info',
                                 f'{row["episode_id"]} rev {row["revision"]} deleted',
                                 f'Never scheduled; {row["bytes_freed"]:,} bytes freed.', episodeId=row['episode_id'],
                                 game=row['game'] if row['game'] in ui_views.GAMES else None, batchId=row['batch_id']))
        for row in db.execute('SELECT sha256, created_at, body FROM drafts'):
            try:
                body = json.loads(row['body'])
                jobs, carry = len(body.get('jobs') or []), bool((body.get('inputs') or {}).get('carryOnly'))
            except (ValueError, AttributeError):
                jobs, carry = 0, False
            out.append(entry(row['created_at'], f'l:draft:{row["sha256"][:16]}', 'approval', 'approval.draft', 'info',
                             'Change to the approved schedule drafted' if carry else 'Schedule draft generated',
                             f'{jobs} job{"" if jobs == 1 else "s"}; preview only until approved.', draftSha256=row['sha256']))
    return [e for e in out if e]


# ---------- system ----------

def _mtime(path):
    with contextlib.suppress(OSError):
        return dt.datetime.fromtimestamp(Path(path).stat().st_mtime, dt.timezone.utc)
    return None


def system_entries(state, show, zone):
    state, out = Path(state), []
    for unit, label, platform in SERVICES:
        info = show(unit) or {}
        if not info.get('available'):
            continue
        at = ui_views.systemd_time(info.get('lastExit'), zone)
        if not at:
            continue
        ok = info.get('result') == 'success' and str(info.get('exitStatus') or '0') == '0'
        detail = ui_views.SYSTEMD_RESULTS.get(info.get('result'), 'Last run did not succeed')
        if not ok and info.get('exitStatus') not in (None, '', '0'):
            detail += f" (exit status {info['exitStatus']})"
        out.append(entry(at, f's:{unit}', 'system', 'system.service', 'success' if ok else 'error',
                         f'{label} {"finished OK" if ok else "failed"}', detail, platform=platform))
    for platform in ('instagram', 'threads'):
        failure = state/f'{platform}-token-failure.json'
        if failure.is_file():
            out.append(entry(_mtime(failure), f's:{platform}-token-failure', 'system', 'system.token-renewal-failed', 'error',
                             f'{LABELS[platform]} token renewal failed',
                             'The current token stays in use until it expires. Check the renewal timer and renew with the owner command if needed.',
                             platform=platform))
        health = state/f'{platform}-token-health.json'
        if health.is_file():
            data = ui_health.read_json(health) or {}
            expires = ui_views.iso_utc(data.get('expiresAt'))
            renewed = data.get('renewed') is True
            out.append(entry(_mtime(health), f's:{platform}-token-health', 'system', 'system.token-health', 'success' if renewed else 'info',
                             f'{LABELS[platform]} token {"renewed" if renewed else "status recorded"}',
                             f'Access expires {expires}.' if expires else None, platform=platform))
    report = ui_health.read_json(state/'health.json')
    if isinstance(report, dict):
        jobs = report.get('jobs') if isinstance(report.get('jobs'), dict) else {}
        attention = sum(v for k, v in jobs.items() if k in ('uncertain', 'blocked', 'failed') and isinstance(v, int))
        exhausted = report.get('contentExhausted')
        severity = 'warning' if attention or exhausted else 'info'
        parts = ['paused' if report.get('paused') else 'running']
        if attention:
            parts.append(f'{attention} job{"" if attention == 1 else "s"} need review')
        if exhausted:
            parts.append('out of approved videos')
        out.append(entry(report.get('checkedAt'), 's:health-json', 'system', 'system.publisher-health', severity,
                         'Publisher health report', 'Publisher ' + ', '.join(parts) + '.'))
    out += metrics_entries(state)
    paused = state/'PAUSED'
    if paused.exists():
        out.append(entry(_mtime(paused), 's:paused', 'system', 'system.paused', 'warning', 'Publishing paused',
                         'The PAUSED file is present; the publisher stops before its next job. Resuming is an owner command.'))
    return [e for e in out if e]


def _read_request(raw):
    """(at, backfill) of a manual stats read request, or None when malformed (the collector also moves bad ones)."""
    if not isinstance(raw, dict):
        return None
    backfill = raw.get('backfill')
    if not isinstance(backfill, int) or isinstance(backfill, bool) or not 0 <= backfill <= ui_views.METRICS_BACKFILL_MAX:
        return None
    return raw.get('requestedAt') if isinstance(raw.get('requestedAt'), str) else None, backfill


def metrics_entries(state):
    """Post stats switch events and manual read requests (STATE/metrics/history/ and a pending request.json)."""
    out, seen = [], set()

    def requested(raw):
        parsed = _read_request(raw)
        if not parsed:
            return
        # One id for a request whether it is still pending or already moved to history by the collector.
        item = entry(parsed[0], 's:metrics-read', 'system', 'system.metrics-read-requested', 'info',
                     'Post stats read requested', (f'Also past {parsed[1]} day{"" if parsed[1] == 1 else "s"}.' if parsed[1] else None))
        if item and item['id'] not in seen:
            seen.add(item['id'])
            out.append(item)
    for stamp, kind, path in ui_health.metrics_history(state):
        data = ui_health.read_small_json(path, 4096)
        if kind == 'request':
            requested(data)
        elif isinstance(data, dict) and isinstance(data.get('enabled'), bool) and isinstance(data.get('at'), str):
            on = data['enabled']
            out.append(entry(data['at'], f's:metrics-{path.stem}', 'system', 'system.metrics-on' if on else 'system.metrics-off',
                             'info', f'Post stats turned {"on" if on else "off"}',
                             'Hourly reads of post and account stats are on.' if on
                             else 'Hourly reads stopped; a manual read still works.'))
    requested(ui_health.read_small_json(Path(state)/ui_health.METRICS_DIR/'request.json', 4096))
    return [e for e in out if e]


# ---------- feed ----------

def feed(state, show, config, f, now):
    """ActivityResponse for validated filters `f` (see query())."""
    zone = ui_views.zone_name(config)
    upper = None
    if f['before']:
        cut = dt.datetime.fromisoformat(f['before'][:20].replace('Z', '+00:00')) + dt.timedelta(seconds=1)
        upper = cut.isoformat()
    others = []
    if f['kind'] in (None, 'approval', 'library'):
        others += approval_entries(state) + library_entries(state)
    if f['kind'] in (None, 'system'):
        others += system_entries(state, show, zone)
    others.sort(key=lambda e: e['id'], reverse=True)
    sources = [others]
    if f['kind'] in (None, 'job'):
        sources.append(ledger_entries(state, f['platform'], upper))
    rows, more = [], False
    for item in heapq.merge(*sources, key=lambda e: e['id'], reverse=True):
        if f['before'] and item['id'] >= f['before']:
            continue
        if (f['platform'] and item['platform'] != f['platform']) or (f['kind'] and item['kind'] != f['kind']) \
                or (f['severity'] and item['severity'] != f['severity']):
            continue
        if len(rows) == f['limit']:
            more = True
            break
        rows.append(item)
    for source in sources:
        if hasattr(source, 'close'):
            source.close()
    return {'generatedAt': ui_views.iso_utc(now), 'displayTimezone': zone, 'entries': rows,
            'nextBefore': rows[-1]['id'] if more and rows else None}


def feed_csv(entries):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(FIELDS)
    for item in entries:
        writer.writerow([ui_views._cell(item[k]) for k in FIELDS])
    return out.getvalue()
