"""Pure shape functions: existing ui_* module outputs -> the HTTP contract in publisher/ui/src/api/types.ts.

No I/O, no clock (callers pass `now`), no state. Field names, nesting, enums and nullability follow
types.ts exactly; anything a module returns that the contract does not name is dropped here, so
internal fields (payload snapshots, file paths) never reach the browser. Texts stay plain language;
nothing here ever offers "post again" for dispatching, accepted or uncertain jobs.
"""
import csv
import datetime as dt
import io
import json
import re
from zoneinfo import ZoneInfo

PLATFORMS = ('instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok')
LABELS = {'instagram': 'Instagram', 'facebook': 'Facebook', 'threads': 'Threads', 'x': 'X',
          'youtube': 'YouTube', 'bluesky': 'Bluesky', 'tiktok': 'TikTok'}
GAMES = ('scalar', 'continuum', 'whenabouts', 'tectonic')
LEDGER_STATUSES = ('ready', 'dispatching', 'accepted', 'uncertain', 'confirmed', 'failed', 'expired', 'blocked')
HISTORY_STATUSES = LEDGER_STATUSES + ('cancelled',)
UNRESOLVED = ('dispatching', 'accepted', 'uncertain')
ROUTES = ('buffer', 'instagram', 'facebook', 'threads', 'bluesky', 'disabled')
KINDS = ('post', 'comment', 'answer', 'poll')
RESERVE_BYTES = 2_000_000_000
UPLOAD_HEADROOM = 24_000_000
HEALTH_MAX_AGE = 2700       # operations.inspect: publisher health older than 45 min is stale
MONITOR_MAX_AGE = 1800      # activate.MONITOR_MAX_AGE
PAGES_LOW = 10
BUFFER_LOW = 20
HISTORY_LIMIT, HISTORY_MAX = 200, 1000
CONFIRM_LEAD_MINUTES = 30

STATUS_LABELS = {
    'ready': 'Waiting for its time', 'dispatching': 'Sending', 'accepted': 'Accepted; waiting for the platform',
    'uncertain': 'Result unknown; checking', 'confirmed': 'Posted', 'failed': 'Failed', 'expired': 'Missed its time',
    'blocked': 'Blocked', 'cancelled': 'Cancelled before sending', 'not-enqueued': 'Approved; not queued yet',
}
EPISODE_LABELS = {'awaiting_files': 'Awaiting files', 'reviewable': 'Ready for review', 'approved': 'Approved',
                  'withdrawn': 'Withdrawn', 'expired': 'Expired', 'invalid': 'Failed checks'}
RECONCILIATION_LABELS = {'dispatching': 'Sending; waiting for the result',
                         'accepted': 'Waiting for the platform to confirm',
                         'uncertain': 'Result unknown; the Pi is checking the platform'}
EVENT_LABELS = {**STATUS_LABELS, 'cancelled': 'Cancelled before sending', 'ready': 'Queued'}
TIMERS = (('scalar-social.timer', 'publisher', 'Publisher'), ('scalar-social-monitor.timer', 'monitor', 'Monitor'),
          ('scalar-social-instagram-refresh.timer', 'renewal', 'Instagram token renewal'),
          ('scalar-social-threads-refresh.timer', 'renewal', 'Threads token renewal'),
          ('scalar-social-metrics.timer', 'metrics', 'Post stats'))
SYSTEMD_RESULTS = {'success': 'Finished successfully', 'exit-code': 'Exited with an error', 'signal': 'Stopped by a signal',
                   'core-dump': 'Crashed', 'timeout': 'Timed out', 'oom-kill': 'Ran out of memory',
                   'start-limit-hit': 'Restarted too often', 'resources': 'Could not start (resources)',
                   'watchdog': 'Stopped by the watchdog', 'exec-condition': 'Skipped by a start condition'}
ISSUE_SEVERITY = {'ledger_integrity': 'error', 'instagram_token_renewal_failed': 'error', 'inspection_failed': 'error',
                  'ledger_missing': 'warning', 'publication_needs_review': 'warning', 'publication_missed': 'warning', 'publisher_health_stale': 'warning',
                  'content_exhausted': 'warning', 'threads_token_expiring': 'warning', 'instagram_token_expiring': 'warning',
                  'publisher_health_missing': 'info', 'threads_token_health_missing': 'info',
                  'instagram_token_health_missing': 'info'}
ISSUE_DETAILS = {
    'ledger_missing': 'The posting history database is not in the state folder.',
    'ledger_integrity': 'SQLite reported damage in the posting history.',
    'publication_needs_review': 'At least one post is uncertain, blocked or failed.',
    'publication_missed': 'A post expired because the Pi ran it more than the allowed lateness after its time.',
    'publisher_health_missing': 'The publisher has not written its health report yet.',
    'publisher_health_stale': 'The publisher health report is older than 45 minutes.',
    'content_exhausted': 'The publisher found no approved video left to post.',
    'threads_token_expiring': 'The Threads access token expires within two days.',
    'threads_token_health_missing': 'No Threads token health file was found.',
    'instagram_token_renewal_failed': 'The last Instagram token renewal failed.',
    'instagram_token_expiring': 'The Instagram access token expires within two days.',
    'instagram_token_health_missing': 'No Instagram token health file was found.',
    'inspection_failed': 'The health check could not read the publisher state.',
}
SYSTEMD_TIME = re.compile(r'\w{3} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+)')


# ---------- small helpers ----------

def iso_utc(value):
    """IsoUtc (`…Z`, whole seconds) from a datetime or ISO string; None when absent or unreadable."""
    if value is None or value == '':
        return None
    if not isinstance(value, dt.datetime):
        try:
            value = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            return None
    if value.tzinfo is None:
        return None
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def systemd_time(value, zone=None):
    """`Tue 2026-10-06 22:00:01 UTC` -> IsoUtc. Local abbreviations resolve only against `zone`."""
    match = SYSTEMD_TIME.fullmatch((value or '').strip())
    if not match:
        return None
    naive = dt.datetime.fromisoformat(match.group(1).replace(' ', 'T'))
    name = match.group(2)
    if name in ('UTC', 'GMT', 'Z'):
        return iso_utc(naive.replace(tzinfo=dt.timezone.utc))
    for candidate in (zone, name if '/' in name else None):
        if not candidate:
            continue
        try:
            local = naive.replace(tzinfo=ZoneInfo(candidate) if isinstance(candidate, str) else candidate)
        except (KeyError, ValueError, OSError):
            continue
        for fold in (0, 1):
            if local.replace(fold=fold).tzname() == name or candidate == name:
                return iso_utc(local.replace(fold=fold))
    return None


def problem(text, code='invalid', path=''):
    """Problem from a plain `path: message` string (ui_library's stored form) or a Report item."""
    if isinstance(text, dict):
        return {'code': str(text.get('code') or code), 'path': str(text.get('path') or path),
                'message': str(text.get('message') or '')}
    text = str(text)
    head, sep, tail = text.partition(': ')
    if sep and head and len(head) <= 120 and ' ' not in head.replace(' · ', '·'):
        return {'code': code, 'path': head, 'message': tail}
    return {'code': code, 'path': path, 'message': text}


def problems(items, code='invalid', path=''):
    return [problem(item, code, path) for item in items or []]


def platform_map(make):
    return {p: make(p) for p in PLATFORMS}


def zone_name(config):
    return (config or {}).get('timezone') or 'UTC'


def poll_view(poll):
    if not isinstance(poll, dict):
        return None
    return {'question': poll.get('question'), 'options': list(poll.get('options') or [])}


def youtube_view(value):
    if not isinstance(value, dict):
        return None
    return {'title': value.get('title') or '', 'description': value.get('description') or ''}


def plain_error(error):
    """ui_health.explain() output -> PlainError (or None)."""
    if not error:
        return None
    return {'category': error.get('category') or 'rejected', 'title': error.get('title') or 'Needs attention',
            'detail': error.get('detail') or '', 'nextAction': error.get('nextAction')}


def owner_actions(actions, job_id):
    return [a.replace('<job id>', job_id) for a in actions or []]


def reconciliation(status, job_id, last_check, next_check, actions):
    if status not in UNRESOLVED:
        return None
    return {'state': status, 'label': RECONCILIATION_LABELS[status], 'lastCheckAt': iso_utc(last_check),
            'nextCheckAt': iso_utc(next_check), 'ownerActions': owner_actions(actions, job_id)}


# ---------- health ----------

def health(version, failures, retry_after):
    """HealthResponse for the calling client only."""
    locked = retry_after > 0
    return {'ok': True, 'version': version,
            'backoff': {'locked': locked, 'retryAfterSeconds': retry_after if locked else None, 'failures': failures}}


# ---------- approval ----------

def approval_result(result, now):
    if not isinstance(result, dict):
        return None
    status = result.get('status')
    at = iso_utc(result.get('boundAt') if status == 'bound' else result.get('at')) or iso_utc(now)
    draft = result.get('draftSha256')
    if status == 'manifest-ready':
        deployment = result.get('deployment') or {}
        return {'status': status, 'draftSha256': draft, 'manifestSha256': result.get('manifestSha256'),
                'jobs': result.get('jobs') or 0,
                'deployment': {'id': deployment.get('id'), 'url': deployment.get('url'),
                               'verified': len(result.get('verifiedUrls') or []),
                               'files': deployment.get('mediaFiles') or 0},
                'at': at}
    if status == 'bound':
        return {'status': status, 'draftSha256': draft, 'manifestSha256': result.get('manifestSha256'),
                'jobs': result.get('jobs') or 0, 'at': at}
    if status == 'validated-no-deploy':
        return {'status': status, 'draftSha256': draft, 'at': at}
    if status == 'failed':
        return {'status': status, 'draftSha256': draft if isinstance(draft, str) else None,
                'category': result.get('category') or 'internal',
                'message': result.get('message') or 'Approval stopped unexpectedly. Nothing was scheduled or published.',
                'at': at}
    return {'status': 'failed', 'draftSha256': None, 'category': 'unreadable',
            'message': 'The approval result file could not be read. Approve the draft again.', 'at': at}


def request_processed(pending, result):
    """A request whose result for the same draft is already written (staging leaves it in place)."""
    return (isinstance(pending, dict) and isinstance(result, dict) and pending.get('draftSha256')
            and result.get('draftSha256') == pending.get('draftSha256')
            and str(result.get('at') or '') >= str(pending.get('requestedAt') or '~'))


def pending_request(pending, result):
    if not isinstance(pending, dict) or not pending.get('draftSha256') or request_processed(pending, result):
        return None
    return {'draftSha256': pending['draftSha256'], 'requestedAt': iso_utc(pending.get('requestedAt'))}


def approval(raw, config, manifest, now):
    """ApprovalState from ui_approval.approval_state(), config.approval and the current manifest."""
    sha = raw.get('manifestSha256')
    bound_sha = ((config or {}).get('approval') or {}).get('manifestSha256')
    manifest = manifest if isinstance(manifest, dict) else {}
    return {'manifestSha256': sha, 'approvedAt': iso_utc(manifest.get('approvedAt')) if sha else None,
            'bound': bool(sha) and bound_sha == sha,
            'scope': [p for p in manifest.get('scope') or [] if p in PLATFORMS] if sha else [],
            'pendingRequest': pending_request(raw.get('pending'), raw.get('result')),
            'lastResult': approval_result(raw.get('result'), now) if raw.get('result') else None}


# ---------- dashboard ----------

def _posting(test, ledger_present):
    if test is None:
        return {'state': 'unknown', 'label': 'Not configured', 'passedAt': None, 'permalink': None, 'detail': None}
    if test.get('passed'):
        return {'state': 'yes', 'label': 'Passed', 'passedAt': iso_utc(test.get('publishedAt')),
                'permalink': test.get('permalink'), 'detail': None}
    if not ledger_present:
        return {'state': 'unknown', 'label': 'Unknown', 'passedAt': None, 'permalink': None,
                'detail': 'The posting history could not be read.'}
    return {'state': 'no', 'label': 'Not run', 'passedAt': None, 'permalink': None,
            'detail': 'No confirmed post on this account yet.'}


def _auth(entry, channel):
    if entry is None:
        return {'state': 'unknown', 'label': 'Not configured', 'checkedAt': None, 'expiresAt': None,
                'renewalFailed': False, 'detail': None}
    state = entry.get('state')
    route = (channel or {}).get('route')
    tri, label = {'ok': ('yes', 'Authenticated'), 'expiring': ('yes', 'Authenticated; expires soon'),
                  'failed': ('no', 'Renewal failed'), 'not-connected': ('no', 'Not connected')}.get(
                      state, ('unknown', 'Not applicable (Buffer)' if route == 'buffer' else 'Unknown'))
    return {'state': tri, 'label': label, 'checkedAt': entry.get('checkedAt'), 'expiresAt': entry.get('expiresAt'),
            'renewalFailed': bool(entry.get('renewalFailed')), 'detail': entry.get('detail')}


def _recurring_platform(channel, overall):
    channel = channel or {}
    route = channel.get('route') if channel.get('route') in ROUTES else 'disabled'
    enabled = bool(channel.get('enabled'))
    if not channel:
        state, label = 'no', 'Not configured'
    elif not enabled:
        state, label = 'no', 'Disabled: route blocked' if route == 'disabled' else 'Disabled'
    elif overall == 'yes':
        state, label = 'yes', 'Enabled'
    elif overall == 'unknown':
        state, label = 'unknown', 'Channel enabled; timer state unknown'
    else:
        state, label = 'no', 'Channel enabled; publishing not running'
    return {'state': state, 'label': label, 'channelEnabled': enabled, 'route': route,
            'identityVerified': bool(channel.get('identityVerified')),
            'publishingVerified': bool(channel.get('publishingVerified')), 'detail': channel.get('reason') or None}


def _recurring(raw, config, timer):
    paused = raw['configPaused'] or raw['pausedSentinel']
    if paused:
        state, label = 'no', 'Not enabled (paused)'
    elif not timer.get('available'):
        state, label = 'unknown', 'Unknown (publisher timer state unreadable)'
    elif raw['enabled']:
        state, label = 'yes', 'Enabled'
    elif not (raw['timerEnabled'] and raw['timerActive']):
        state, label = 'no', 'Not enabled (publisher timer off)'
    else:
        state, label = 'no', 'Not enabled (no channel enabled)'
    channels = (config or {}).get('channels') or {}
    return {'state': state, 'label': label, 'configPaused': raw['configPaused'], 'pausedSentinel': raw['pausedSentinel'],
            'publisherTimerEnabled': raw['timerEnabled'], 'publisherTimerActive': raw['timerActive'],
            'platforms': platform_map(lambda p: _recurring_platform(channels.get(p), state))}


def _timer(unit, role, label, units, zone):
    timer = units.get(unit) or {'available': False}
    service = units.get(unit.replace('.timer', '.service')) or {'available': False}
    last = systemd_time(service.get('lastExit'), zone) if service.get('available') else None
    result = service.get('result')
    if not service.get('available'):
        outcome, detail = 'unknown', 'Service state unavailable'
    elif not last:
        outcome, detail = 'never', 'Has not run yet'
    elif result == 'success' and str(service.get('exitStatus') or '0') == '0':
        outcome, detail = 'success', SYSTEMD_RESULTS['success']
    else:
        outcome = 'failed'
        detail = SYSTEMD_RESULTS.get(result, 'Last run did not succeed')
        if service.get('exitStatus') not in (None, '', '0'):
            detail += f" (exit status {service['exitStatus']})"
    return {'unit': unit, 'role': role, 'label': label, 'enabled': timer.get('enabled') == 'enabled',
            'active': timer.get('active') == 'active', 'lastRunAt': last, 'lastResult': outcome,
            'lastResultDetail': detail, 'nextRunAt': systemd_time(timer.get('nextRun'), zone)}


def _ago(seconds):
    if seconds < 90:
        return 'Updated just now' if seconds < 60 else 'Updated 1 min ago'
    if seconds < 5400:
        return f'Updated {round(seconds/60)} min ago'
    if seconds < 172800:
        return f'Updated {round(seconds/3600)} h ago'
    return f'Updated {round(seconds/86400)} days ago'


def freshness(updated_at, now, max_age, ok=None):
    updated = iso_utc(updated_at)
    if not updated:
        return {'updatedAt': None, 'ageSeconds': None, 'maxAgeSeconds': max_age, 'fresh': False, 'label': 'Missing', 'ok': ok}
    age = int((now - dt.datetime.fromisoformat(updated.replace('Z', '+00:00'))).total_seconds())
    return {'updatedAt': updated, 'ageSeconds': age, 'maxAgeSeconds': max_age, 'fresh': -60 <= age <= max_age,
            'label': _ago(max(age, 0)), 'ok': ok}


def budget(used, limit, window, noun, low_margin):
    remaining = max(0, limit - used)
    return {'used': used, 'limit': limit, 'remaining': remaining, 'window': window,
            'label': f'{used} of {limit} {noun} used', 'low': remaining < low_margin}


def storage(raw):
    free, total = raw['freeBytes'], raw['totalBytes']
    low = free < RESERVE_BYTES + UPLOAD_HEADROOM
    return {'freeBytes': free, 'totalBytes': total, 'reserveBytes': RESERVE_BYTES, 'low': low,
            'label': f'{free/1e9:.1f} GB free of {total/1e9:.1f} GB' + (' (uploads refused below 2 GB + file size)' if low else '')}


def _issue_platform(code):
    for p in PLATFORMS:
        if code.startswith(p + '_'):
            return p
    return None


def issues(raw_issues, store, approval_state):
    out = []
    for item in raw_issues:
        code = item.get('code') or 'unknown'
        out.append({'id': code, 'severity': ISSUE_SEVERITY.get(code, 'warning'), 'category': code,
                    'title': item.get('title') or code, 'detail': ISSUE_DETAILS.get(code, item.get('title') or code),
                    'nextAction': item.get('nextAction'), 'platform': _issue_platform(code), 'jobId': None, 'at': None})
    if store['low']:
        out.append({'id': 'storage-low', 'severity': 'warning', 'category': 'storage-low', 'title': 'Storage is low',
                    'detail': store['label'], 'nextAction': 'Library → "Remove posted videos" frees videos that are already posted (covers stay), or delete uploads that were never scheduled.',
                    'platform': None, 'jobId': None, 'at': None})
    result = approval_state.get('lastResult')
    if result and result['status'] == 'failed':
        out.append({'id': 'approval-failed', 'severity': 'warning', 'category': f"approval-{result['category']}",
                    'title': 'Last schedule approval failed', 'detail': result['message'],
                    'nextAction': 'Open Schedule, generate a new draft if needed, and approve it again.',
                    'platform': None, 'jobId': None, 'at': result['at']})
    return out


def uncertain_job(raw):
    return {'jobId': raw['id'], 'platform': raw['platform'], 'accountId': raw.get('account') or '',
            'slotUtc': iso_utc(raw['slot']['utc']), 'episode': raw['episode'], 'status': raw['status'],
            'dispatchedAt': iso_utc(raw.get('dispatchedAt')), 'error': plain_error(raw.get('error')),
            'reconciliation': reconciliation(raw['status'], raw['id'], raw.get('lastCheck'), raw.get('nextCheck'),
                                             raw.get('ownerActions'))}


def dashboard(raw, config, approval_state, now, standing=None):
    """DashboardResponse from ui_health.dashboard() (+ approval(), + standing())."""
    zone = zone_name(config)
    units = {u['unit']: u for u in raw.get('units') or []}
    channels = config.get('channels') or {}
    ledger_present = 'ledger_missing' not in [i.get('code') for i in raw.get('issues') or []]
    recurring = _recurring(raw['recurringPublishing'], config, units.get('scalar-social.timer') or {})
    tests, auth = raw.get('postingTestPassed') or {}, raw.get('currentlyAuthenticated') or {}
    monitor = units.get('scalar-social-monitor.service') or {}
    monitor_ok = (monitor.get('result') == 'success') if monitor.get('available') else None
    monitor_at = systemd_time(monitor.get('lastExit'), zone) if monitor_ok else None
    buffer_day = next((w for w in raw['budgets']['bufferCalls'] if w['window'] == '24 hours'),
                      {'used': 0, 'limit': 200})
    pages = raw['budgets']['pagesDeployments']
    store = storage(raw['storage'])
    health_info = raw.get('publisherHealth') or {}
    return {
        'generatedAt': iso_utc(now), 'displayTimezone': zone,
        'paused': bool(recurring['configPaused'] or recurring['pausedSentinel']),
        'statuses': {
            'postingTestPassed': {'platforms': platform_map(lambda p: _posting(tests.get(p), ledger_present))},
            'currentlyAuthenticated': {'platforms': platform_map(lambda p: _auth(auth.get(p), channels.get(p)))},
            'recurringEnabled': recurring,
        },
        'timers': [_timer(unit, role, label, units, zone) for unit, role, label in TIMERS],
        'freshness': {
            'healthJson': freshness(health_info.get('checkedAt'), now, HEALTH_MAX_AGE, health_info.get('ok')),
            'monitor': freshness(monitor_at, now, MONITOR_MAX_AGE, monitor_ok),
        },
        'budgets': {'pages': budget(pages['used'], pages['limit'], 'last 31 days', 'deployments', PAGES_LOW),
                    'buffer': budget(buffer_day['used'], buffer_day['limit'], 'last 24 hours', 'Buffer calls', BUFFER_LOW)},
        'storage': store,
        'issues': issues(raw.get('issues') or [], store, approval_state),
        'approval': approval_state,
        'uncertainJobs': [uncertain_job(j) for j in raw.get('uncertainJobs') or []],
        'standing': standing or {**EMPTY_STANDING, 'nextPosts': []},
    }


def pause(already, now):
    return {'paused': True, 'alreadyPaused': already, 'at': iso_utc(now)}


# ---------- library ----------

def _measured(media):
    if not media:
        return None
    return {k: media.get(k) for k in ('bytes', 'durationSeconds', 'width', 'height', 'fps', 'videoCodec', 'pixFmt')} | {
        'videoStreams': media.get('videoStreams') or 0, 'audioStreams': media.get('audioStreams') or 0,
        'audioCodec': media.get('audioCodec'), 'audioSampleRate': media.get('audioSampleRate'),
        'audioChannels': media.get('audioChannels'), 'fastStart': media.get('fastStart')}


def eligibility(platforms, missing_reason='The video is not on the Pi yet'):
    platforms = platforms or {}
    def one(p):
        entry = platforms.get(p)
        if not isinstance(entry, dict):
            return {'eligible': False, 'reason': missing_reason if not platforms else f'Not checked for {LABELS[p]}'}
        return {'eligible': bool(entry.get('eligible')), 'reason': entry.get('reason') if not entry.get('eligible') else None}
    return platform_map(one)


def approval_record(row):
    return {'id': row['id'], 'action': row['action'], 'reviewer': row['reviewer'], 'at': iso_utc(row['at']),
            'videoSha256': row['video_sha256'], 'coverSha256': row['cover_sha256'],
            'metadataSha256': row['metadata_sha256'], 'captionSha256': row['caption_sha256'], 'note': row['note']}


def _variant(text):
    episode_id, _, revision = text.rpartition(' r')
    return f'{episode_id}@{revision}' if episode_id and revision.isdigit() else text


def library_episode(raw, batch_id, posted):
    status = raw['status']
    if raw.get('expired') and status in ('reviewable', 'approved', 'awaiting_files'):
        status = 'expired'
    approvals = [approval_record(a) for a in raw.get('approvals') or []]
    last = approvals[-1] if approvals else None
    current = (last if last and last['action'] == 'approve' and raw['status'] == 'approved'
               and (last['videoSha256'], last['coverSha256'], last['metadataSha256'])
               == (raw['videoSha256'], raw['coverSha256'], raw['metadataSha256']) else None)
    measured = _measured(raw.get('media'))
    return {
        'episodeId': raw['episodeId'], 'revision': raw['revision'], 'batchId': batch_id, 'questionId': raw['questionId'],
        'game': raw['game'], 'format': raw.get('format'), 'difficulty': raw.get('difficulty'),
        'status': status, 'statusLabel': EPISODE_LABELS.get(status, status),
        'metadataSha256': raw['metadataSha256'], 'videoSha256': raw['videoSha256'], 'coverSha256': raw.get('coverSha256'),
        'videoUrl': raw.get('videoUrl'), 'coverUrl': raw.get('coverUrl'), 'media': measured,
        'videoRemovedAt': iso_utc(raw.get('videoRemovedAt')),
        'platforms': eligibility(raw.get('platforms')),
        'problems': problems(raw.get('problems'), 'media'),
        'approvals': approvals, 'currentApproval': current,
        'inManifest': bool(raw.get('inManifest')), 'deletable': not raw.get('inManifest'),
        'legacy': bool(raw.get('legacy')),
        'variants': [_variant(v) for v in raw.get('variants') or []],
        'postedOn': posted.get(raw['questionId'], []),
        'episode': raw.get('episode'),
    }


def library_batch(raw):
    generator = raw.get('generator') or {}
    episodes = raw.get('episodes') or []
    return {'batchId': raw['batchId'], 'origin': raw['origin'] if raw['origin'] in ('mac', 'manual', 'legacy') else 'mac',
            'createdAt': iso_utc(raw.get('createdAt')), 'importedAt': iso_utc(raw.get('importedAt')),
            'batchJsonSha256': raw.get('batchJsonSha256'), 'generatorDirty': generator.get('dirty') is True,
            'repoCommit': generator.get('repoCommit') if isinstance(generator.get('repoCommit'), str) else None,
            'warnings': problems(raw.get('warnings'), 'warning', 'batch'),
            'episodeCount': len(episodes), 'awaitingFiles': sum(e['status'] == 'awaiting_files' for e in episodes)}


def posted_records(rows):
    """{questionId: [PostedRecord]} from ledger (platform, account, slot, episode, status) post rows."""
    out = {}
    for platform, account, slot, episode, status in rows:
        if '#' in episode or platform not in PLATFORMS:
            continue
        out.setdefault(episode, []).append({'platform': platform, 'accountId': account,
                                            'status': status, 'slotUtc': iso_utc(slot)})
    for records in out.values():
        records.sort(key=lambda r: (PLATFORMS.index(r['platform']), r['slotUtc'] or ''))
    return out


def library(raw_batches, posted, config, now):
    batches = [library_batch(b) for b in raw_batches]
    episodes = [library_episode(e, b['batchId'], posted) for b in raw_batches for e in b.get('episodes') or []]
    episodes.sort(key=lambda e: (e['batchId'], e['episodeId'], e['revision']))
    return {'generatedAt': iso_utc(now), 'displayTimezone': zone_name(config), 'batches': batches, 'episodes': episodes}


def batch_import(result):
    """BatchImportResponse from ui_library.import_batch_json()."""
    expected = [{'file': e['file'], 'name': e['file'].rsplit('/', 1)[-1], 'kind': e['kind'], 'episodeId': e['episodeId'],
                 'revision': e['revision'], 'sha256': e['sha256'], 'bytes': e['bytes'], 'present': bool(e['present'])}
                for e in result.get('expected') or []]
    items = result.get('problemItems')
    return {'batchId': result.get('batchId') or '', 'origin': 'mac', 'created': result.get('status') == 'imported',
            'merge': [dict(m) for m in result.get('merge') or []], 'expected': expected,
            'problems': problems(items) if items is not None else problems(result.get('problems')),
            'warnings': problems(result.get('warningItems') or result.get('warnings'), 'warning')}


def file_upload(result, computed_sha, computed_bytes):
    """FileUploadResult from ui_library.accept_batch_file(); hash/size as streamed by the server."""
    expected_sha, expected_bytes = result.get('sha256'), result.get('expectedBytes')
    sha = computed_sha or expected_sha
    matched = sha == expected_sha and computed_bytes == expected_bytes
    if not result.get('ok'):
        outcome = 'rejected'
    else:
        outcome = 'already-present' if result.get('alreadyPresent') else 'stored'
    found = problems(result.get('problems'), 'media')
    return {'file': result.get('file'), 'kind': result.get('kind'), 'episodeId': result.get('episodeId'),
            'sha256': sha, 'bytes': computed_bytes, 'expectedSha256': expected_sha, 'expectedBytes': expected_bytes,
            'matched': matched,
            'outcome': outcome, 'message': '; '.join(p['message'] for p in found) or None, 'problems': found,
            'episodeStatus': result.get('status') or 'awaiting_files'}


def library_action(result, statuses):
    """LibraryActionResponse; `statuses` maps (episodeId, revision) -> current status."""
    out = []
    for entry in result.get('results') or []:
        key = (entry.get('episodeId'), entry.get('revision'))
        out.append({'episodeId': entry.get('episodeId') or '', 'revision': entry.get('revision') or 0,
                    'ok': bool(entry.get('ok')), 'status': statuses.get(key) or 'invalid',
                    'message': entry.get('problem'), 'approvalId': entry.get('approvalId')})
    return {'results': out}


# ---------- feedback, batch notes, next batch (owner planning text; never published) ----------

FEEDBACK_TAGS = ('keep', 'tweak', 'drop', 'hook-weak', 'too-hard', 'too-easy', 'great-reveal', 'visual-issue', 'fact-check', 'music')
FEEDBACK_NOTE_MAX = 2000
BATCH_NOTE_MAX_BYTES = 65_536
MARK_USED_MAX = 1000
NEXT_POSTS = 3
PERFORMANCE_MAX = 200


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def feedback_input(body):
    """(tags in canonical order, note) from a PUT feedback body; ValueError(path, message) otherwise."""
    if not isinstance(body, dict):
        raise ValueError('body', 'Send tags and a note.')
    tags, note = body.get('tags'), body.get('note')
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError('tags', 'Tags must be a list of tag names.')
    unknown = [t for t in tags if t not in FEEDBACK_TAGS]
    if unknown:
        raise ValueError('tags', f"Unknown tag {unknown[0]!r}; use {', '.join(FEEDBACK_TAGS)}.")
    if len(set(tags)) != len(tags):
        raise ValueError('tags', 'Each tag may be given once.')
    if note is None:
        note = ''
    if not isinstance(note, str):
        raise ValueError('note', 'The note must be text.')
    if len(note) > FEEDBACK_NOTE_MAX:
        raise ValueError('note', f'The note is {len(note):,} characters; the limit is {FEEDBACK_NOTE_MAX:,}.')
    return [t for t in FEEDBACK_TAGS if t in tags], note


def mark_used_input(body):
    """[(episodeId, revision)] from a mark-used body; ValueError(path, message) otherwise."""
    items = body.get('items') if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError('items', 'Choose at least one episode.')
    if len(items) > MARK_USED_MAX:
        raise ValueError('items', f'At most {MARK_USED_MAX} episodes at a time.')
    out = []
    for i, item in enumerate(items):
        if not (isinstance(item, dict) and isinstance(item.get('episodeId'), str) and item['episodeId']
                and _int(item.get('revision')) and 0 <= item['revision'] < 2**31):
            raise ValueError(f'items[{i}]', 'Each item needs an episodeId and a whole-number revision.')
        out.append((item['episodeId'], item['revision']))
    return out


def note_input(body):
    """Note text from a PUT batch note body; ValueError(path, message) otherwise."""
    text = body.get('text') if isinstance(body, dict) else None
    if not isinstance(text, str):
        raise ValueError('text', 'Send the note as text.')
    try:
        size = len(text.encode('utf-8'))
    except UnicodeEncodeError:
        raise ValueError('text', 'The note is not valid UTF-8 text.') from None
    if size > BATCH_NOTE_MAX_BYTES:
        raise ValueError('text', f'The note is {size:,} bytes; the limit is {BATCH_NOTE_MAX_BYTES:,}.')
    return text


def episode_feedback(raw):
    """EpisodeFeedback | None."""
    if raw is None:
        return None
    return {'episodeId': raw['episodeId'], 'revision': raw['revision'], 'tags': [t for t in raw['tags'] if t in FEEDBACK_TAGS],
            'note': raw['note'], 'status': raw['status'], 'updatedAt': iso_utc(raw['updatedAt'])}


def feedback_item(raw):
    return {**episode_feedback(raw), 'batchId': raw['batchId'] or '', 'questionId': raw['questionId'] or '',
            'game': raw['game'] or '', 'format': raw['format'] or '', 'styleId': raw['styleId'] or ''}


def batch_note(raw):
    """BatchNote | None."""
    if raw is None:
        return None
    return {'batchId': raw['batchId'], 'kind': raw['kind'], 'text': raw['text'], 'sha256': raw['sha256'],
            'bytes': raw['bytes'], 'uploadedAt': iso_utc(raw['uploadedAt'])}


def batch_notes(raw):
    return {'batchId': raw['batchId'], 'brief': batch_note(raw['brief']), 'retro': batch_note(raw['retro'])}


def episode_post(row, metrics=None):
    """EpisodePost from a ledger jobs row plus its newest platform read (metrics.latest), if any."""
    return {'platform': row['platform'], 'status': row['status'],
            'at': iso_utc(row['published_at']) or iso_utc(row['dispatched_at']) or iso_utc(row['slot']),
            'permalink': row['permalink'] or None, 'metrics': metrics}


def ledger_posts(rows, episode_id=None, revision=None, metrics=None):
    """EpisodePost list from ledger post rows (companions excluded). With episode_id, rows whose payload names
    another episode revision are dropped; legacy payloads without an episodeId match by questionId alone."""
    out = []
    for row in rows:
        if '#' in row['episode'] or row['platform'] not in PLATFORMS:
            continue
        if episode_id is not None:
            try:
                named = (json.loads(row['payload']) or {}).get('episode') or {}
            except (ValueError, AttributeError, TypeError):
                named = {}
            if named.get('episodeId') not in (None, episode_id) or named.get('revision') not in (None, revision):
                continue
        out.append(episode_post(row, (metrics or {}).get(row.get('id'))))
    return out


def episode_detail(raw, posts):
    """EpisodeDetail from ui_library pieces (raw: batchId, episode, status, expired, approvedAt, notes, feedback)."""
    status = raw['status']
    if raw.get('expired') and status in ('reviewable', 'approved', 'awaiting_files'):
        status = 'expired'
    return {'batchId': raw['batchId'], 'episode': raw['episode'],
            'approval': {'status': status, 'at': iso_utc(raw.get('approvedAt'))},
            'notes': batch_notes(raw['notes']), 'feedback': episode_feedback(raw.get('feedback')), 'posts': posts}


FUNNEL_VALUES = ('views', 'engaged', 'answered', 'avgWatchSeconds', 'followsThatDay')


def episode_funnel(row):
    """EpisodeFunnel from one metrics.funnel() row; only contract fields pass."""
    counted = row.get('counted') if isinstance(row.get('counted'), dict) else {}
    platforms = row.get('platforms') if isinstance(row.get('platforms'), dict) else {}
    return {'episode': row.get('episode'), 'publishedDates': list(row.get('publishedDates') or []),
            **{k: row.get(k) for k in FUNNEL_VALUES},
            'counted': {k: list(counted.get(k) or []) for k in FUNNEL_VALUES},
            'platforms': {p: {'status': v.get('status'), **{k: v.get(k) for k in FUNNEL_VALUES},
                              'followsSource': v.get('followsSource')}
                          for p, v in platforms.items() if isinstance(v, dict)}}


def next_batch(next_batch_id, open_items, last_brief, last_retro, performance, accounts=(), funnel=()):
    performance = sorted(performance, key=lambda p: (p['at'] or '', p['platform']), reverse=True)[:PERFORMANCE_MAX]
    return {'nextBatchId': next_batch_id, 'openFeedback': [feedback_item(f) for f in open_items],
            'lastBrief': batch_note(last_brief), 'lastRetro': batch_note(last_retro),
            'performance': performance, 'accounts': list(accounts),
            'funnel': [episode_funnel(r) for r in funnel if isinstance(r, dict)], 'tags': list(FEEDBACK_TAGS)}


# ---------- post stats controls (STATE/metrics/) ----------

METRICS_TIMER, METRICS_SERVICE, METRICS_PATH = ('scalar-social-metrics.timer', 'scalar-social-metrics.service',
                                                'scalar-social-metrics.path')
METRICS_BACKFILL_MAX = 93
METRICS_TRIGGERS = ('timer', 'request')
METRICS_OUTCOMES = ('ok', 'stats-off', 'bad-request', 'error')
METRICS_PLATFORM_STATUSES = ('ok', 'not-configured', 'authorization', 'rejected', 'error', 'unsupported')


def _whole(value, low=0, high=None):
    return isinstance(value, int) and not isinstance(value, bool) and value >= low and (high is None or value <= high)


def _stamp(value):
    return iso_utc(value) if isinstance(value, str) else None


def metrics_pending(raw):
    """MetricsPendingRequest from STATE/metrics/request.json, or None when it is absent or malformed."""
    if not isinstance(raw, dict) or not _whole(raw.get('backfill'), 0, METRICS_BACKFILL_MAX):
        return None
    at = _stamp(raw.get('requestedAt'))
    return {'requestedAt': at, 'backfill': raw['backfill']} if at else None


def metrics_last_run(raw):
    """MetricsLastRun from STATE/metrics/last-run.json: typed fields only; None when a top-level field is malformed.
    A malformed platform entry is dropped on its own."""
    if not isinstance(raw, dict) or not isinstance(raw.get('platforms'), dict):
        return None
    started, finished = _stamp(raw.get('startedAt')), _stamp(raw.get('finishedAt'))
    if (not started or not finished or raw.get('trigger') not in METRICS_TRIGGERS or not _whole(raw.get('backfill'))
            or raw.get('outcome') not in METRICS_OUTCOMES):
        return None
    platforms = {}
    for name, run in raw['platforms'].items():
        if (name in PLATFORMS and isinstance(run, dict) and run.get('status') in METRICS_PLATFORM_STATUSES
                and _whole(run.get('postsRead')) and _whole(run.get('accountsRead')) and run.get('reason') in ('buffer', None)):
            platforms[name] = {'status': run['status'], 'postsRead': run['postsRead'], 'accountsRead': run['accountsRead'],
                               'reason': run.get('reason')}
    return {'startedAt': started, 'finishedAt': finished, 'trigger': raw['trigger'], 'backfill': raw['backfill'],
            'outcome': raw['outcome'], 'platforms': platforms}


def metrics_status(raw, units, zone):
    """MetricsStatus from ui_health.metrics_files() and `systemctl show` facts for the metrics units."""
    timer = units.get(METRICS_TIMER) or {}
    label = next(t[2] for t in TIMERS if t[0] == METRICS_TIMER)
    pending = metrics_pending(raw.get('pending'))
    if pending is None and isinstance(raw.get('pendingSince'), (int, float)):
        # request.json exists but cannot be read: still pending (the POST answers 409), shown with its file time.
        pending = {'requestedAt': iso_utc(dt.datetime.fromtimestamp(raw['pendingSince'], dt.timezone.utc)), 'backfill': 0}
    return {'enabled': bool(raw.get('enabled')), 'pending': pending,
            'lastRun': metrics_last_run(raw.get('lastRun')),
            'timer': _timer(METRICS_TIMER, 'metrics', label, units, zone) if timer.get('available') else None,
            'pathActive': (units.get(METRICS_PATH) or {}).get('active') == 'active'}


def metrics_input(body, allowed):
    """The body as a dict with only `allowed` keys; raises ValueError((path, message))."""
    if not isinstance(body, dict):
        raise ValueError('body', 'Send a JSON object.')
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise ValueError(unknown[0], f'Unknown field: {unknown[0][:40]}.')
    return body


def next_posts(manifest_jobs, rows, keys, now):
    """≤ 3 upcoming, not yet dispatched posts of the approved manifest; `rows` maps ledger id -> row, `keys` the
    ledger id of each manifest job."""
    out, now = [], iso_utc(now)
    for job, key in zip(manifest_jobs, keys):
        payload = job.get('payload') or {}
        at = iso_utc(job.get('slot'))
        row = rows.get(key)
        if (_kind(payload) != 'post' or job.get('platform') not in PLATFORMS or not at or at <= now
                or (row and (row['dispatched_at'] or row['status'] != 'ready'))):
            continue
        episode = payload.get('episode') or {}
        out.append({'at': at, 'platform': job['platform'], 'episodeId': str(episode.get('episodeId') or '—')})
    out.sort(key=lambda p: (p['at'], PLATFORMS.index(p['platform'])))
    return out[:NEXT_POSTS]


EMPTY_STANDING = {'lastBatch': None, 'awaitingReview': 0, 'nextPosts': [], 'openFeedback': 0, 'nextBatchId': None,
                  'postedLast7Days': 0, 'lastBriefAt': None, 'lastRetroAt': None}


def standing(raw, posts):
    """Standing from ui_library.standing() (+ nextBatchId, postedLast7Days, last brief/retro times) and next_posts()."""
    last = raw.get('lastBatch')
    return {'lastBatch': {'batchId': last['batchId'], 'importedAt': iso_utc(last['importedAt']),
                          'episodeCount': last['episodeCount'], 'awaitingFiles': last.get('awaitingFiles') or 0} if last else None,
            'awaitingReview': raw.get('awaitingReview') or 0, 'nextPosts': posts, 'openFeedback': raw.get('openFeedback') or 0,
            'nextBatchId': raw.get('nextBatchId'), 'postedLast7Days': raw.get('postedLast7Days') or 0,
            'lastBriefAt': iso_utc(raw.get('lastBriefAt')), 'lastRetroAt': iso_utc(raw.get('lastRetroAt'))}


# ---------- schedule ----------

def draft_job(job):
    return {'key': job['key'], 'platform': job['platform'], 'accountId': job.get('accountId') or '',
            'slotUtc': job['slotUtc'], 'slotLocal': job.get('slotLocal'), 'zone': job.get('zone') or '',
            'kind': job.get('kind') or 'post', 'episodeKey': job.get('episodeKey'), 'parentKey': job.get('parentKey'),
            'episodeId': job.get('episodeId'), 'revision': job.get('revision'), 'batchId': job.get('batchId'),
            'questionId': job.get('questionId'), 'game': job.get('game'),
            'videoSha256': job.get('videoSha256') if (job.get('kind') or 'post') == 'post' else None,
            'coverSha256': job.get('coverSha256'), 'text': job.get('text') or '', 'youtube': youtube_view(job.get('youtube')),
            'thread': list(job['thread']) if job.get('thread') else None, 'poll': poll_view(job.get('poll')),
            'link': job.get('link'), 'carried': bool(job.get('carried')), 'warnings': list(job.get('warnings') or [])}


def draft(body):
    """Draft (types.ts) from a stored generator draft. Companion exclusions become warnings."""
    warnings = list(body.get('warnings') or [])
    excluded = []
    for item in body.get('excluded') or []:
        if item.get('companion'):
            noun = {'reply': 'replies', 'comment': 'comments'}.get(item['companion'], item['companion'])
            line = f"{LABELS.get(item['platform'], item['platform'])} {noun} not scheduled: {item['reason']}"
            if line not in warnings:
                warnings.append(line)
        else:
            excluded.append({'platform': item['platform'], 'reason': item['reason']})
    summary = body.get('summary') or {}
    return {'version': 1, 'inputs': body.get('inputs'), 'baseManifestSha256': body.get('baseManifestSha256'),
            'libraryHash': body.get('libraryHash'), 'historyHash': body.get('historyHash'),
            'jobs': [draft_job(j) for j in body.get('jobs') or []],
            'unfilled': [{'platform': u['platform'], 'slotLocal': u.get('slotLocal'), 'slotUtc': u.get('slotUtc'),
                          'reason': u['reason']} for u in body.get('unfilled') or []],
            'excluded': excluded, 'warnings': warnings,
            'summary': {'requested': summary.get('requested', 0), 'filled': summary.get('filled', 0),
                        'companions': summary.get('companions', 0)}}


def confirmation_phrase(sha):
    return f'APPROVE {sha[:8]}'


def blocking_problems(body, *, sha, now, current_manifest_sha, approved_draft_sha, pending, library_hash, exclusions):
    """Re-checked on every read. `exclusions` maps platform -> ui_schedule._exclusion() text (or None)."""
    found = list(body.get('blocking') or [])
    jobs = body.get('jobs') or []
    if approved_draft_sha == sha:
        found.append('This draft is already the approved schedule.')
    elif (body.get('baseManifestSha256') or None) != current_manifest_sha:
        found.append('A different schedule was approved after this draft was made; generate a new draft.')
    if library_hash is not None and body.get('libraryHash') != library_hash:
        found.append('The library changed since this draft (approvals, withdrawals or expiry); generate a new draft.')
    if pending:
        found.append('This draft is already waiting for approval.' if pending.get('draftSha256') == sha
                     else 'Another approval is already pending; wait for its result.')
    if not jobs:
        found.append('The draft has no posts to schedule.')
    for platform in [p for p in PLATFORMS if any(j['platform'] == p for j in jobs)]:
        if exclusions.get(platform):
            found.append(f'{LABELS[platform]}: {exclusions[platform]}.')
    soon = now + dt.timedelta(minutes=CONFIRM_LEAD_MINUTES)
    late = [j for j in jobs if not j.get('carried') and dt.datetime.fromisoformat(j['slotUtc']) < soon]
    if late:
        found.append(f'{len(late)} job(s) start less than {CONFIRM_LEAD_MINUTES} minutes from now; '
                     'start later or remove those times.')
    return found


def draft_status(stored, sha, *, approved_draft_sha, past_draft_shas, pending, last_result):
    if sha == approved_draft_sha:
        return 'approved'
    if sha in past_draft_shas:
        return 'superseded'
    if pending and pending.get('draftSha256') == sha:
        return 'requested'
    if last_result and last_result.get('draftSha256') == sha:
        status = last_result.get('status')
        if status == 'failed':
            return 'failed'
        if status in ('manifest-ready', 'bound'):
            return 'superseded'
        return 'requested'
    return stored if stored in ('draft', 'requested') else 'draft'


def draft_response(sha, body, *, status, created_at, blocking, cover_urls):
    return {'sha256': sha, 'draft': draft(body), 'status': status, 'createdAt': iso_utc(created_at),
            'blockingProblems': blocking, 'confirmationPhrase': confirmation_phrase(sha), 'coverUrls': cover_urls}


def approve_draft(request):
    return {'status': 'requested', 'draftSha256': request['draftSha256'], 'requestedAt': iso_utc(request['requestedAt'])}


def channel_summary(platform, channel, blocked):
    channel = channel or {}
    route = channel.get('route') if channel.get('route') in ROUTES else 'disabled'
    return {'platform': platform, 'accountId': channel.get('accountId'), 'route': route,
            'enabled': bool(channel.get('enabled')), 'identityVerified': bool(channel.get('identityVerified')),
            'publishingVerified': bool(channel.get('publishingVerified')), 'blockedReason': blocked,
            'profileUrl': channel.get('profileUrl')}


def _kind(payload):
    kind = (payload or {}).get('kind') or 'post'
    return kind if kind in KINDS else 'post'


def queue_job(mjob, row, account, cover_url, parent_key, explain, zone):
    """QueueJob from one manifest job and its ledger row (or None before the runner enqueues it)."""
    payload = mjob.get('payload') or {}
    episode = payload.get('episode') or {}
    youtube = (payload.get('metadata') or {}).get('youtube')
    dispatched = bool(row and (row['dispatched_at'] or row['status'] != 'ready'))
    lock = None
    if dispatched:
        when = row['dispatched_at'] or row['published_at']
        lock = 'Already sent to the platform; read-only.'
        if iso_utc(when):
            local = dt.datetime.fromisoformat(iso_utc(when).replace('Z', '+00:00')).astimezone(ZoneInfo(zone))
            lock = f"Dispatched {local.strftime('%-d %b %H:%M')} {local.tzname()}; read-only."
    status = row['status'] if row else 'not-enqueued'
    return {'key': mjob.get('key'), 'jobId': row['id'] if row else None, 'platform': mjob['platform'],
            'accountId': row['account'] if row else (account or ''), 'slotUtc': iso_utc(mjob['slot']),
            'kind': _kind(payload), 'episodeKey': episode.get('id'), 'parentKey': parent_key,
            'episodeId': episode.get('episodeId'), 'questionId': str(episode.get('id') or '').split('#', 1)[0],
            'game': episode.get('game'), 'text': payload.get('caption') or '', 'youtube': youtube_view(youtube),
            'coverUrl': cover_url, 'status': status, 'statusLabel': STATUS_LABELS.get(status, status),
            'dispatched': dispatched, 'editable': not dispatched, 'lockReason': lock,
            'permalink': row['permalink'] if row and row['status'] == 'confirmed' else None,
            'error': plain_error(explain(row['error'])) if row and row['error'] else None}


def parent_keys(manifest_jobs):
    posts = {(j['platform'], (j['payload'].get('episode') or {}).get('id')): j.get('key')
             for j in manifest_jobs if _kind(j.get('payload')) == 'post'}
    return [None if _kind(j.get('payload')) == 'post' else
            posts.get((j['platform'], ((j['payload'].get('companion') or {}).get('parentEpisode'))))
            for j in manifest_jobs]


def schedule(*, config, manifest_sha, manifest, bound, jobs, approval_state, channels, recent):
    return {'displayTimezone': zone_name(config),
            'manifest': {'sha256': manifest_sha, 'draftSha256': manifest.get('draftSha256'),
                         'approvedAt': iso_utc(manifest.get('approvedAt')),
                         'scope': [p for p in manifest.get('scope') or [] if p in PLATFORMS], 'bound': bound,
                         'jobCount': len(manifest.get('jobs') or [])} if manifest_sha else None,
            'jobs': jobs, 'pendingRequest': approval_state['pendingRequest'], 'lastResult': approval_state['lastResult'],
            'channels': channels, 'recentDrafts': recent}


# ---------- history ----------

def history_row(raw):
    """HistoryRow from a ui_health._job_view() row (or a cancelled_jobs() row)."""
    status = raw['status']
    caption = raw.get('caption') or ''
    return {'jobId': raw['id'], 'platform': raw['platform'], 'accountId': raw.get('account') or '',
            'slotUtc': iso_utc(raw['slot']['utc']), 'episode': raw['episode'],
            'questionId': str(raw['episode']).split('#', 1)[0], 'kind': raw.get('kind') if raw.get('kind') in KINDS else 'post',
            'game': raw.get('game') if raw.get('game') in GAMES else None, 'episodeId': raw.get('episodeId'),
            'status': status, 'statusLabel': STATUS_LABELS.get(status, status), 'attempts': raw.get('attempts') or 0,
            'dispatchedAt': iso_utc(raw.get('dispatchedAt')), 'publishedAt': iso_utc(raw.get('publishedAt')),
            'permalink': raw.get('permalink') if status == 'confirmed' else None, 'error': plain_error(raw.get('error')),
            'captionPreview': caption[:140]}


def history_query(query, zone):
    """Validated HistoryQuery from parse_qs output. Raises ValueError (plain text)."""
    value = lambda k: ((query.get(k) or [None])[0] or None)
    out = {k: value(k) for k in ('platform', 'status', 'game', 'question', 'q', 'from', 'to', 'format')}
    for key, allowed in (('platform', PLATFORMS), ('status', HISTORY_STATUSES), ('game', GAMES), ('format', ('json', 'csv'))):
        if out[key] is not None and out[key] not in allowed:
            raise ValueError(f'Unknown {key}: choose one of {", ".join(allowed)}.')
    for key in ('from', 'to'):
        if out[key] is not None:
            try:
                out[key] = dt.date.fromisoformat(out[key]) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', out[key]) else None
            except ValueError:
                out[key] = None
            if out[key] is None:
                raise ValueError(f'"{key}" must be a date (YYYY-MM-DD).')
    limit = value('limit')
    if limit is None:
        out['limit'] = HISTORY_LIMIT
    elif not limit.isdigit() or not 1 <= int(limit) <= HISTORY_MAX:
        raise ValueError(f'limit must be 1–{HISTORY_MAX}.')
    else:
        out['limit'] = int(limit)
    out['format'] = out['format'] or 'json'
    out['zone'] = ZoneInfo(zone)
    return out


def history_match(row, f):
    if f['platform'] and row['platform'] != f['platform']:
        return False
    if f['status'] and row['status'] != f['status']:
        return False
    if f['game'] and row['game'] != f['game']:
        return False
    if f['question'] and row['questionId'] != f['question'].split('#', 1)[0]:
        return False
    if f['from'] or f['to']:
        local = dt.datetime.fromisoformat(row['slotUtc'].replace('Z', '+00:00')).astimezone(f['zone']).date()
        if (f['from'] and local < f['from']) or (f['to'] and local > f['to']):
            return False
    needle = (f['q'] or '').casefold().strip()
    if needle:
        haystack = ' '.join(str(row.get(k) or '') for k in ('episode', 'episodeId', 'captionPreview', 'permalink', 'jobId'))
        return needle in haystack.casefold()
    return True


def history(rows, f, config, captions=None):
    """HistoryResponse; `rows` are HistoryRow, newest first. `captions` (jobId -> full caption) widens q."""
    captions = captions or {}
    matched = [r for r in rows if history_match({**r, 'captionPreview': captions.get(r['jobId'], r['captionPreview'])}, f)]
    return {'displayTimezone': zone_name(config), 'rows': matched[:f['limit']], 'total': len(matched),
            'truncated': len(matched) > f['limit']}


CSV_FIELDS = ('jobId', 'platform', 'accountId', 'slotUtc', 'episode', 'questionId', 'kind', 'game', 'episodeId', 'status',
              'statusLabel', 'attempts', 'dispatchedAt', 'publishedAt', 'permalink', 'error', 'captionPreview')


def _cell(value):
    text = '' if value is None else str(value)
    # Spreadsheet formula injection: a leading = + - @ (or tab/CR) is neutralised.
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def history_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(CSV_FIELDS)
    for row in rows:
        writer.writerow([_cell((row['error'] or {}).get('category') if k == 'error' else row[k]) for k in CSV_FIELDS])
    return out.getvalue()


def job_detail(raw, config, manifest_sha):
    """JobDetailResponse from ui_health.job_detail() / cancelled_jobs() output (with `payload`)."""
    payload = raw.get('payload') or {}
    media = payload.get('media') or {}
    youtube = (payload.get('metadata') or {}).get('youtube')
    events = [{'seq': e['seq'], 'kind': e['kind'], 'label': EVENT_LABELS.get(e['kind'], e['kind'].replace('_', ' ').capitalize()),
               'at': iso_utc(e['at']), 'detail': e.get('detail') or ''} for e in raw.get('events') or []]
    rec = raw.get('reconciliation')
    last = raw['events'][-1]['at'] if raw.get('events') else None
    return {'displayTimezone': zone_name(config), 'job': history_row(raw),
            'payload': {'caption': payload.get('caption') or '', 'youtube': youtube_view(youtube),
                        'thread': list(payload['thread']) if payload.get('thread') else None,
                        'mediaUrl': media.get('url'), 'mediaSha256': media.get('sha256'),
                        'companionOf': (payload.get('companion') or {}).get('parentEpisode')},
            'events': events,
            'reconciliation': reconciliation(raw['status'], raw['id'], last, (rec or {}).get('nextCheck'),
                                             (rec or {}).get('ownerActions')) if rec else None,
            'manifestSha256': manifest_sha}


# ---------- activation ----------

def _check_id(label):
    return re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:48]


def activation(rows, manifest_sha, manifest, command, check_command):
    items = [{'id': _check_id(label), 'label': label, 'pass': bool(ok), 'detail': (detail or None) if ok else None,
              'nextAction': None if ok else (detail or 'Fix this on the Pi, then re-check.')}
             for label, ok, detail in rows]
    return {'ready': bool(items) and all(i['pass'] for i in items), 'items': items, 'command': command,
            'checkCommand': check_command, 'manifestSha256': manifest_sha,
            'scope': [p for p in (manifest or {}).get('scope') or [] if p in PLATFORMS],
            'explanation': ('After the owner\'s one-time first activation, the autopilot runs this checklist after every '
                            'approval and twice a day (the timer item aside), enables exactly the channels in the approved '
                            'schedule and keeps the publisher timer on. A pause from Settings stops it until the owner '
                            'removes the pause on the Pi. This page cannot change any of that.')}
