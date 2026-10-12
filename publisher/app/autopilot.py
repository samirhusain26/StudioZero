"""Autopilot: keeps an approved schedule ahead of today with no owner step (docs/AUTOPILOT_PLAN.md).

verify-channels (root, ExecStartPre=+): a Buffer channel whose identity is verified but whose posting test is not yet
recorded gets it from a confirmed post on its current account (configure_paused.confirm_publishing). Never enables.

refill (scalar-social): when fewer than RUNWAY_DAYS remain in the approved schedule, generates the recommended draft
(the UI's "Recommended" preset: every verified platform, daily, one post at its set time, first comment and answer
reply; the project mix from the catalog's targets once the owner sets them, else game round-robin) and requests its approval exactly as the UI's Approve button does. The approve units deploy and verify the
media, bind the hash and run activate.py --auto. Nothing happens while the owner has paused publishing in the UI, an
approval is pending, or the draft is blocked or empty (the library is used up: render a new batch).
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent))  # root runs this with python3 -I, which omits the script folder
# In the repo the shared contract lives in <repo>/contract; on the Pi the installer copies it next to this file.
_CONTRACT = Path(__file__).resolve().parents[2] / 'contract'
if _CONTRACT.is_dir() and str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))

UTC = dt.timezone.utc
RUNWAY_DAYS = 7
# Mirrors publisher/ui/src/lib/scheduleForm.ts (SUGGESTED_TIMEZONE, RECOMMENDED_TIMES, RECOMMENDED_DAYS).
SUGGESTED_TIMEZONE = 'America/New_York'
RECOMMENDED_TIMES = {'threads': '09:00', 'x': '09:30', 'bluesky': '10:30', 'facebook': '12:15', 'youtube': '16:00',
                     'instagram': '18:00', 'tiktok': '19:00'}
RECOMMENDED_DAYS = 21


def verify_channels(config_path, state, out=print):
    """Record the posting test for each eligible Buffer channel. Returns the platforms recorded."""
    import activate
    from configure_paused import confirm_publishing, save
    config = json.loads(Path(config_path).read_text())
    db_path = Path(state)/'ledger.sqlite3'
    if not db_path.is_file():
        return []
    recorded = []
    with activate.ledger_owner_preserved(db_path), \
            contextlib.closing(sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True)) as ledger:
        for platform, channel in sorted(config['channels'].items()):
            if (channel.get('route') != 'buffer' or not channel.get('identityVerified') or channel.get('enabled')
                    or channel.get('publishingVerified') or not channel.get('accountId')):
                continue
            row = ledger.execute("SELECT permalink FROM jobs WHERE platform=? AND account=? AND status='confirmed' "
                                 "AND permalink IS NOT NULL AND permalink != '' ORDER BY published_at DESC, slot DESC LIMIT 1",
                                 (platform, channel['accountId'])).fetchone()
            if not row:
                out(f'{platform}: no confirmed post on its current account yet; posting test not recorded.')
                continue
            config = confirm_publishing(config, ledger, platform, row[0])
            recorded.append(platform)
            out(f'{platform}: posting test recorded from {row[0]}.')
    if recorded:
        save(config_path, config)
    return recorded


def catalog_mix(catalog):
    """{project: target share} from the studio catalog when any project has a target, else None (game round-robin,
    exactly as before targets existed). A project without a target gets share 0."""
    import ui_schedule
    projects = (catalog or {}).get('projects') if isinstance(catalog, dict) else None
    if not isinstance(projects, list):
        return None
    projects = [p for p in projects if isinstance(p, dict) and isinstance(p.get('id'), str)]
    targets = {p['id']: (p.get('mix') if isinstance(p.get('mix'), dict) else {}).get('target') for p in projects}
    if all(t is None for t in targets.values()):
        return None
    mix = {k: t if isinstance(t, (int, float)) and not isinstance(t, bool) else 0 for k, t in targets.items()}
    # A mix the generator would refuse falls back to the round-robin, so refill never stops on a bad target.
    if (not all(ui_schedule.PROJECT.fullmatch(k) and 0 <= v <= 1 for k, v in mix.items()) or not sum(mix.values()) > 0
            or len(mix) > 20):
        return None
    return mix


def recommended_inputs(config, today, catalog=None):
    """The UI's recommended form as generator inputs, starting tomorrow; platforms that cannot post stay out.
    With mix targets in the catalog the content order is the project mix."""
    import ui_schedule
    start = today + dt.timedelta(days=1)
    mix = catalog_mix(catalog)
    channels = config.get('channels') or {}
    included = [p for p in ui_schedule.PLATFORM_ORDER if not ui_schedule._exclusion(p, channels.get(p))]
    return {'timezone': SUGGESTED_TIMEZONE, 'startDate': start.isoformat(),
            'endDate': (start + dt.timedelta(days=RECOMMENDED_DAYS - 1)).isoformat(),
            'platforms': {p: {'include': True, 'weekdays': [0, 1, 2, 3, 4, 5, 6], 'times': [RECOMMENDED_TIMES[p]],
                              'maxPerDay': 1} for p in included},
            'minGapHours': {p: 2 for p in included}, 'staggerMinutes': 0,
            **({'ordering': 'project-mix', 'mix': mix} if mix else {'ordering': 'game-round-robin'}),
            'companions': {'firstComment': True, 'answerReply': True}, 'edits': {}}


def runway(manifest, zone, today):
    """(last scheduled local date or None, whole days from today to it)."""
    slots = [dt.datetime.fromisoformat(j['slot']) for j in (manifest or {}).get('jobs') or []]
    if not slots:
        return None, -1
    last = max(slots).astimezone(zone).date()
    return last, (last - today).days


def catalog():
    """The studio catalog (mix targets), or None when it cannot be read: then the order stays game round-robin."""
    import ui_catalog
    try:
        return ui_catalog.read()[1]
    except ui_catalog.CatalogError:
        return None


def refill(config_path, state, now=None, out=print):
    """Returns a plain message. Requests at most one approval per run."""
    import library_contract
    import ui_approval
    import ui_library
    import ui_schedule
    import ui_views
    state = Path(state)
    now = now or dt.datetime.now(UTC)
    if (state/'PAUSED').exists():
        return 'Paused in the UI: autopilot schedules nothing until publishing is resumed.'
    if (state/'approval'/'request.json').exists():
        return 'An approval is already being processed; nothing to do.'
    config = json.loads(Path(config_path).read_text())
    base_sha, base = ui_approval.current_manifest(state)
    zone = ZoneInfo(config.get('timezone') or SUGGESTED_TIMEZONE)
    last, left = runway(base, zone, now.astimezone(zone).date())
    if last and left >= RUNWAY_DAYS:
        return f'Runway ok: the approved schedule runs to {last} ({left} days left); nothing to do.'
    ending = f'ends {last}' if last else 'is empty'
    today = now.astimezone(ZoneInfo(SUGGESTED_TIMEZONE)).date()
    inputs = recommended_inputs(config, today, catalog())
    normalized = ui_schedule.validate_inputs(inputs, config, today)
    history = ui_schedule.ledger_history(state/'ledger.sqlite3', config, now)
    channels = config.get('channels') or {}
    db = ui_library.open_index(state)
    try:
        with db:
            videos = ui_library.schedulable_videos(db, today)
            draft = ui_schedule.generate(normalized, videos, history, config, base, base_sha)
            sha = ui_schedule.draft_sha256(draft)
            blocking = ui_views.blocking_problems(
                draft, sha=sha, now=now, current_manifest_sha=base_sha,
                approved_draft_sha=(base or {}).get('draftSha256'), pending=None,
                library_hash=hashlib.sha256(library_contract.canonical(videos)).hexdigest(),
                exclusions={p: ui_schedule._exclusion(p, channels.get(p)) for p in ui_views.PLATFORMS})
            if not draft['summary']['filled']:
                return (f'Runway low (the approved schedule {ending}), but no approved video is left to schedule: '
                        'render and upload a new batch.')
            if blocking:
                out('\n'.join(f'  - {problem}' for problem in blocking))
                return f'Runway low (the approved schedule {ending}), but the new draft is blocked; nothing requested.'
            db.execute('INSERT OR IGNORE INTO drafts(sha256, created_at, base_manifest_sha256, body, status) VALUES(?,?,?,?,?)',
                       (sha, ui_views.iso_utc(now), base_sha, library_contract.canonical(draft).decode(), 'draft'))
        try:
            ui_approval.request_approval(state, sha, f'APPROVE {sha[:8]}', draft_exists=True, now=now)
        except ui_approval.Conflict:
            return 'An approval is already being processed; nothing to do.'
        with db:
            db.execute("UPDATE drafts SET status='requested' WHERE sha256=?", (sha,))
    finally:
        db.close()
    summary = draft['summary']
    return (f'Runway low (the approved schedule {ending}): requested approval of draft {sha[:8]} with '
            f'{summary["filled"]} new posts and {summary["companions"]} companions, {inputs["startDate"]} to '
            f'{inputs["endDate"]}. The approve service deploys and verifies the media, then publishing continues.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Autopilot: record posting tests and keep the schedule filled.')
    parser.add_argument('command', choices=('verify-channels', 'refill'))
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--allow-non-root-for-tests', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'verify-channels':
        if os.geteuid() != 0 and not args.allow_non_root_for_tests:
            print('verify-channels must run as root (systemd ExecStartPre=+).', file=sys.stderr)
            return 1
        try:
            recorded = verify_channels(args.config, args.state)
            print(f'Posting tests recorded: {", ".join(recorded)}.' if recorded else 'No posting test to record.')
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            print('Posting tests not recorded: configuration or ledger unavailable. The next run retries.')
        return 0
    try:
        print(refill(args.config, args.state))
        return 0
    except ValueError as error:
        print(f'Refill stopped: {error}. Nothing was requested.', file=sys.stderr)
    except (OSError, KeyError, TypeError, sqlite3.Error):
        print('Refill stopped: configuration, library or ledger unavailable. Nothing was requested.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
