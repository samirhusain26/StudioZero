"""Paused-safe operational checks and consistent SQLite backups. Never publishes."""
import argparse
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from zoneinfo import ZoneInfo
from runner import REVIEW, attention as runner_attention, recent_missed


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file() or destination.exists():
        raise ValueError('Backup requires an existing source and a new destination')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=destination.parent, prefix='.backup-')
    os.close(fd)
    temporary = Path(name)
    try:
        with contextlib.closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as src, contextlib.closing(sqlite3.connect(temporary)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity failed')
        # Hard link fails rather than overwriting a backup created concurrently.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def inspect(config_path, state, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    config = json.loads(Path(config_path).read_text())
    state = Path(state)
    paused = bool(config['paused'] or (state/'PAUSED').exists())
    issues = []
    counts = {}
    attention, missed = {}, 0
    db_path = state/'ledger.sqlite3'
    if not db_path.exists():
        issues.append('ledger_missing')
    else:
        with contextlib.closing(sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                issues.append('ledger_integrity')
            counts = dict(db.execute('SELECT status,count(*) FROM jobs GROUP BY status'))
            if any(counts.get(k) for k in REVIEW):
                issues.append('publication_needs_review')
            attention = runner_attention(db)
            missed = recent_missed(db, now)
            if missed:
                issues.append('publication_missed')
    if not paused:
        health_path = state/'health.json'
        if not health_path.exists():
            issues.append('publisher_health_missing')
        else:
            health = json.loads(health_path.read_text())
            age = (now-dt.datetime.fromisoformat(health['checkedAt'])).total_seconds()
            if age < -60 or age > 2700:
                issues.append('publisher_health_stale')
            if health.get('contentExhausted'):
                issues.append('content_exhausted')
    if config.get('channels', {}).get('threads', {}).get('identityVerified'):
        if (state/'threads-token-failure.json').exists():
            issues.append('threads_token_renewal_failed')
        token_health = state/'threads-token-health.json'
        try:
            expiry = dt.datetime.fromisoformat(json.loads(token_health.read_text())['expiresAt'])
            if (expiry-now).total_seconds() < 2*86400:
                issues.append('threads_token_expiring')
        except (OSError, ValueError, KeyError):
            issues.append('threads_token_health_missing')
    instagram = config.get('channels', {}).get('instagram', {})
    if instagram.get('route') == 'instagram' and instagram.get('identityVerified'):
        if (state/'instagram-token-failure.json').exists():
            issues.append('instagram_token_renewal_failed')
        try:
            expiry = dt.datetime.fromisoformat(json.loads((state/'instagram-token-health.json').read_text())['expiresAt'])
            if (expiry-now).total_seconds() < 2*86400:
                issues.append('instagram_token_expiring')
        except (OSError, ValueError, KeyError):
            issues.append('instagram_token_health_missing')
    return {'checkedAt': now.isoformat(), 'paused': paused, 'jobs': counts, 'attention': attention,
            'missedLast24h': missed, 'issues': issues, 'healthy': not issues, 'publicationEnabled': False}


def posting_schedule(config_path, state, catalog_path=None, now=None):
    """Read the real ledger and clip catalogue without reserving or sending jobs."""
    from runner import fingerprint, slots
    config = json.loads(Path(config_path).read_text())
    state = Path(state)
    now = now or dt.datetime.now(dt.timezone.utc)
    zone = ZoneInfo(config['timezone'])
    catalog = json.loads(Path(catalog_path).read_text()) if catalog_path else {}
    clips = catalog.get('clips', {})
    jobs = []
    db_path = state/'ledger.sqlite3'
    if db_path.is_file():
        with contextlib.closing(sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            for row in db.execute('SELECT * FROM jobs ORDER BY slot,platform,id'):
                payload = json.loads(row['payload'])
                episode = payload.get('episode', {})
                mode = payload.get('format')
                parts = []
                if mode == 'self-contained':
                    parts = [row['episode']+':self']
                elif mode == 'chained':
                    previous = payload.get('previous')
                    # An unprepared chain's predecessor is selected at dispatch
                    # from confirmed posts, never predicted by this export.
                    parts = [row['episode']+':hook', row['episode']+':challenge']
                    if 'previous' in payload:
                        parts.insert(1, previous['episode']['id']+':reminder' if previous else 'intro')
                media = payload.get('media') or {}
                jobs.append({'id': row['id'], 'platform': row['platform'],
                    'account': row['account'], 'slotUtc': row['slot'],
                    'slotLocal': dt.datetime.fromisoformat(row['slot']).astimezone(zone).isoformat(),
                    'episode': row['episode'], 'game': episode.get('game'), 'format': mode,
                    'status': row['status'], 'files': [
                        {'clip': part, 'path': clips[part]['path'], 'sha256': clips[part]['sha256']}
                        for part in parts if part in clips],
                    'predecessorPending': mode == 'chained' and 'previous' not in payload,
                    'mediaUrl': media.get('url'), 'mediaSha256': media.get('sha256'),
                    'permalink': row['permalink'], 'publishedAt': row['published_at']})
    approval = config.get('approval') or {}
    return {'version': 1, 'generatedAt': now.isoformat(), 'timezone': config['timezone'],
        'paused': bool(config['paused'] or (state/'PAUSED').exists()),
        'scheduleApproved': bool(approval.get('approvedAt') and approval.get('scopeHash') == fingerprint(config)),
        'configuredSchedule': config['schedule'],
        'candidateSlots': list(slots(config, now)),
        'enabledChannels': [p for p, c in config['channels'].items() if c['enabled']],
        'ledgerMissing': not db_path.is_file(), 'jobs': jobs, 'publicationEnabled': False,
        'note': 'Candidate slots are configuration previews. Only ledger jobs reserve episodes; this export never schedules or publishes.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('check', 'backup', 'used', 'alert-test', 'schedule'))
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--destination')
    parser.add_argument('--catalog', help='Optional batch catalogue for exact clip file references')
    parser.add_argument('--require-heartbeat', action='store_true')
    args = parser.parse_args()
    state = Path(args.state)
    if args.command == 'schedule':
        result = json.dumps(posting_schedule(args.config, state, args.catalog), indent=2)+'\n'
        if args.destination:
            # Private snapshot; exclusive creation preserves previous exports.
            fd = os.open(args.destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                handle.write(result)
            print('Posting schedule exported; no jobs reserved or published.')
        else:
            print(result, end='')
    elif args.command == 'backup':
        if not args.destination:
            parser.error('--destination required')
        backup(state/'ledger.sqlite3', args.destination)
        print('Consistent backup verified; no credentials included.')
    elif args.command == 'used':
        with contextlib.closing(sqlite3.connect((state/'ledger.sqlite3').resolve().as_uri()+'?mode=ro', uri=True)) as db:
            print(json.dumps([r[0] for r in db.execute('SELECT DISTINCT episode FROM jobs ORDER BY episode')]))
    elif args.command == 'alert-test':
        from monitored import ping
        if not ping(1):
            raise SystemExit('External failure signal failed; check private credential or connectivity.')
        print('External failure signal acknowledged. Owner must verify email receipt; then run check to recover.')
    else:
        from monitored import ping
        from monitored import alert_text
        try:
            result = inspect(args.config, state)
            code = 0 if result['healthy'] else 2
            print(json.dumps(result, indent=2))
            body = alert_text(code, result['issues'], result['attention'], result['missedLast24h'])
        except (OSError, ValueError, KeyError, sqlite3.Error):
            code = 1
            print('Operational check failed: configuration or storage unavailable.')
            body = alert_text(code, ['inspection_failed'])
        sent = ping(code, body)
        print(json.dumps({'externalHeartbeatSent': sent}))
        if args.require_heartbeat and not sent:
            code = code or 1
        raise SystemExit(code)


if __name__ == '__main__':
    main()
