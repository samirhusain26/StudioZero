"""Deterministic schedule drafts for the Pi UI (PUBLISHING_PIPELINE_PLAN.md "Schedule generator",
"Polls and comments"). generate() is pure: no clock, no randomness, sorted iteration, so the same
inputs, library and ledger history give a byte-identical draft. ledger_history() is the only
state reader and opens the ledger read-only. Nothing here publishes or writes state.
"""
import collections
import copy
import datetime as dt
import hashlib
import math
from pathlib import Path
import re
import sqlite3
import sys
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# In the repo the shared contract lives in <repo>/contract; on the Pi the installer copies it next to this file.
_CONTRACT = Path(__file__).resolve().parents[2] / 'contract'
if _CONTRACT.is_dir() and str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))
import library_contract as lc  # noqa: E402

UTC = dt.timezone.utc
PLATFORM_ORDER = ('instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok')
LABELS = {'instagram': 'Instagram', 'facebook': 'Facebook', 'threads': 'Threads', 'x': 'X',
          'youtube': 'YouTube', 'bluesky': 'Bluesky', 'tiktok': 'TikTok'}
ORDERINGS = ('game-round-robin',)
PROVIDER_DAILY_CAPS = {'facebook': 30, 'instagram': 25, 'threads': 250, 'bluesky': 25, 'tiktok': 25}
BUFFER_DAILY_CAP = 40          # posts/day shared by every Buffer-routed channel (≈200 calls)
PAGES_DEPLOYMENT_LIMIT = 120   # per 31 days (prepare.deploy_site)
BUFFER_CALL_LIMIT = 200        # per 24 h (runner.Ledger.consume_call)
MAX_RANGE_DAYS = 92
MAX_TIMES = 6
MAX_STAGGER = 240
MAX_EDIT_CHARS = 10000
COMMENT_DELAY_MINUTES = 2
COMPANION_SHIFT_LIMIT = 60
THREADS_REPLY_SCOPE = 'threads_manage_replies'
NO_VIDEO = "No approved video left that hasn't already posted on this account"
SENT = 'Already sent to the platform; cannot change'
OCCUPIED = 'This time already has a post on this account'
TIKTOK_MAX_HASHTAGS = 5       # Buffer's TikTok route (support.buffer.com, using-tiktok-with-buffer)
THREADS_SCOPE_MISSING = 'Threads replies need the threads_manage_replies grant'
KIND_ORDER = ('post', 'comment', 'poll', 'answer')

# Per-route companion capability (PUBLISHING_PIPELINE_PLAN.md "Polls and comments").
# available: separate reply job; requires-scope: needs `scope` in channels.<p>.observedScopes;
# unverified: native form untested, the generator uses the text-reply fallback; thread: X
# first comment travels as Buffer thread item 2 inside the parent payload, only once
# buffer_adapter.X_THREAD_VERIFIED is True (see companion_capabilities); unavailable: none.
COMPANIONS = {
    'instagram': {'comment': 'available', 'answer': 'available', 'poll': 'unavailable'},
    'facebook': {'comment': 'unavailable', 'answer': 'unavailable', 'poll': 'unavailable',
                 'reason': 'Facebook comments need a separate owner grant decision (pages_manage_engagement)'},
    'threads': {'comment': 'requires-scope', 'answer': 'requires-scope', 'poll': 'unverified',
                'scope': THREADS_REPLY_SCOPE},
    'x': {'comment': 'thread', 'thread': 'unverified', 'answer': 'unavailable', 'poll': 'unavailable'},
    'youtube': {'comment': 'unavailable', 'answer': 'unavailable', 'poll': 'unavailable',
                'reason': 'YouTube comments are not available through Buffer'},
    'bluesky': {'comment': 'available', 'answer': 'available', 'poll': 'unavailable'},
    'tiktok': {'comment': 'unavailable', 'answer': 'unavailable', 'poll': 'unavailable',
               'reason': 'TikTok has no comment API'},
}

INPUT_KEYS = ('timezone', 'startDate', 'endDate', 'platforms', 'minGapHours', 'staggerMinutes',
              'ordering', 'companions', 'edits', 'carryOnly')
X_THREAD_SKIPPED = 'X first comment skipped: Buffer thread posting with video is not yet verified (choices stay in the caption)'
TIME = re.compile(r'([01]\d|2[0-3]):[0-5]\d')
ZONE_NAME = re.compile(r'[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*')


def x_thread_verified():
    import buffer_adapter  # lazy: stdlib-only, read at call time so tests can patch it
    return bool(buffer_adapter.X_THREAD_VERIFIED)


def companion_capabilities():
    table = copy.deepcopy(COMPANIONS)
    table['x']['thread'] = 'verified' if x_thread_verified() else 'unverified'
    return table


def iso(value):
    return value.astimezone(UTC).isoformat()


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def zone_for(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Choose a timezone')
    if not ZONE_NAME.fullmatch(name):
        raise ValueError(f'Unknown timezone: {name}')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError(f'Unknown timezone: {name}') from None


def _date(value, label):
    if not isinstance(value, str) or not lc.DATE.fullmatch(value):
        raise ValueError(f'{label} must be a date (YYYY-MM-DD)')
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{label} is not a real date') from None


def _normalize(inputs):
    """Shape checks that do not depend on today; idempotent."""
    if not isinstance(inputs, dict):
        raise ValueError('Schedule settings are missing')
    unknown = sorted(set(inputs) - set(INPUT_KEYS))
    if unknown:
        raise ValueError(f'Unknown schedule setting: {unknown[0]}')
    zone_for(inputs.get('timezone'))
    start = _date(inputs.get('startDate'), 'Start date')
    end = _date(inputs.get('endDate'), 'End date')
    if end < start:
        raise ValueError('End date is before the start date')
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f'Choose at most {MAX_RANGE_DAYS} days')
    carry_only = inputs.get('carryOnly', False)
    if not isinstance(carry_only, bool):
        raise ValueError('carryOnly must be true or false')
    platforms = inputs.get('platforms')
    if not isinstance(platforms, dict):
        raise ValueError('Choose at least one platform')
    for name in sorted(set(platforms) - set(PLATFORM_ORDER)):
        raise ValueError(f'Unknown platform: {name}')
    gaps = inputs.get('minGapHours')
    if not isinstance(gaps, dict):
        raise ValueError('Set a minimum gap for each chosen platform (0 for none)')
    for name in sorted(set(gaps) - set(PLATFORM_ORDER)):
        raise ValueError(f'Unknown platform in minimum gaps: {name}')
    norm_platforms, norm_gaps = {}, {}
    for p in PLATFORM_ORDER:
        label, entry = LABELS[p], platforms.get(p, {'include': False})
        if not isinstance(entry, dict):
            raise ValueError(f'{label}: settings must be an object')
        include = entry.get('include', False)
        if not isinstance(include, bool):
            raise ValueError(f'{label}: include must be true or false')
        if not include:
            norm_platforms[p] = {'include': False, 'weekdays': [], 'times': [], 'maxPerDay': 1}
            continue
        weekdays = entry.get('weekdays')
        if (not isinstance(weekdays, list) or not weekdays or not all(_int(d) and 0 <= d <= 6 for d in weekdays)
                or len(set(weekdays)) != len(weekdays)):
            raise ValueError(f'{label}: choose posting weekdays (Monday=0 … Sunday=6), each once')
        times = entry.get('times')
        if not isinstance(times, list) or not times or not all(isinstance(t, str) and TIME.fullmatch(t) for t in times):
            raise ValueError(f'{label}: give posting times as HH:MM (24-hour)')
        if len(times) > MAX_TIMES:
            raise ValueError(f'{label}: at most {MAX_TIMES} times per day')
        if len(set(times)) != len(times):
            raise ValueError(f'{label}: each time only once')
        cap = entry.get('maxPerDay')
        if not _int(cap) or cap < 1:
            raise ValueError(f'{label}: maximum posts per day must be at least 1')
        gap = gaps.get(p)
        if not _number(gap) or gap < 0:
            raise ValueError(f'{label}: set a minimum gap in hours (0 for none)')
        norm_platforms[p] = {'include': True, 'weekdays': sorted(weekdays), 'times': sorted(times), 'maxPerDay': cap}
        norm_gaps[p] = int(gap) if float(gap).is_integer() else gap
    if not carry_only and not any(v['include'] for v in norm_platforms.values()):
        raise ValueError('Choose at least one platform')
    stagger = inputs.get('staggerMinutes')
    if not _int(stagger) or not 0 <= stagger <= MAX_STAGGER:
        raise ValueError(f'Stagger must be 0–{MAX_STAGGER} minutes')
    if inputs.get('ordering') not in ORDERINGS:
        raise ValueError('Choose a content order (game round-robin)')
    companions = inputs.get('companions')
    if (not isinstance(companions, dict) or set(companions) != {'firstComment', 'answerReply'}
            or not all(isinstance(v, bool) for v in companions.values())):
        raise ValueError('Companions need firstComment and answerReply set to true or false')
    edits = inputs.get('edits', {})
    if not isinstance(edits, dict):
        raise ValueError('Edits must be an object keyed by job')
    norm_edits = {}
    for key, edit in edits.items():
        if not isinstance(key, str) or not key:
            raise ValueError('Edit keys must name a job')
        if edit == {'remove': True}:
            norm_edits[key] = {'remove': True}
        elif (isinstance(edit, dict) and set(edit) == {'text'} and isinstance(edit['text'], str)
              and edit['text'].strip() and len(edit['text']) <= MAX_EDIT_CHARS):
            norm_edits[key] = {'text': edit['text']}
        else:
            raise ValueError('Each edit is either {"text": "…"} with new text or {"remove": true}')
    return {'timezone': inputs['timezone'], 'startDate': start.isoformat(), 'endDate': end.isoformat(),
            'platforms': norm_platforms, 'minGapHours': norm_gaps, 'staggerMinutes': stagger,
            'ordering': inputs['ordering'], 'companions': dict(companions), 'edits': norm_edits,
            'carryOnly': carry_only}


def validate_inputs(inputs, config, today):
    """Normalized explicit inputs, or ValueError with plain text. `today` is the Pi's local date
    (date or YYYY-MM-DD). Nothing is assumed: no default timezone, platform, time or cadence.
    carryOnly (cancel/edit of the approved manifest) re-uses an approved draft's inputs, so its
    dates may be past and no platform needs to be chosen."""
    normalized = _normalize(inputs)
    today = today if isinstance(today, dt.date) else _date(today, 'Today')
    if not normalized['carryOnly'] and dt.date.fromisoformat(normalized['startDate']) < today:
        raise ValueError('Start date is in the past')
    return normalized


def _norm_slot(slot):
    try:
        value = dt.datetime.fromisoformat(slot)
    except (TypeError, ValueError):
        return slot
    return iso(value) if value.tzinfo else slot


def _parse(slot):
    try:
        value = dt.datetime.fromisoformat(slot)
    except (TypeError, ValueError):
        return None
    return value.astimezone(UTC) if value.tzinfo else None


def _count(db, table, since):
    try:
        return db.execute(f'SELECT count(*) FROM {table} WHERE at>?', (since,)).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def ledger_history(ledger_path, config, now=None):
    """Read-only ledger summary for generate(). `now` (datetime or epoch seconds) only sets the
    budget windows, which stay outside the draft hash."""
    now = time.time() if now is None else now.timestamp() if isinstance(now, dt.datetime) else float(now)
    channels = {p: c for p, c in sorted((config.get('channels') or {}).items()) if p in PLATFORM_ORDER}
    history = {'ledgerMissing': False, 'dispatched': [], 'deploymentsLast31d': 0, 'bufferCallsLast24h': 0}
    for p in channels:
        history[p] = {'used': [], 'slots': [], 'postSlots': []}
    path = Path(ledger_path)
    if not path.is_file():
        history['ledgerMissing'] = True
        return history
    db = sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True)
    try:
        dispatched = set()
        for p, c in channels.items():
            current = c.get('accountId')
            accounts = [a for a in [current, *(c.get('previousAccountIds') or [])] if a]
            if not accounts:
                continue
            marks = ','.join('?' for _ in accounts)
            rows = db.execute(f'SELECT account, slot, episode, status, dispatched_at FROM jobs '
                              f'WHERE platform=? AND account IN ({marks})', (p, *accounts)).fetchall()
            used, slots, posts = set(), set(), set()
            for account, slot, episode, status, dispatched_at in rows:
                slot = _norm_slot(slot)
                used.add(episode.split('#', 1)[0])
                if account == current:
                    slots.add(slot)
                    if '#' not in episode:
                        posts.add(slot)
                if status != 'ready' or dispatched_at:
                    dispatched.add(f'{p}|{slot}|{episode}')
            history[p] = {'used': sorted(used), 'slots': sorted(slots), 'postSlots': sorted(posts)}
        history['dispatched'] = sorted(dispatched)
        history['deploymentsLast31d'] = _count(db, 'deployments', now - 31 * 86400)
        history['bufferCallsLast24h'] = _count(db, 'calls', now - 86400)
    finally:
        db.close()
    return history


def _dispatched(values):
    """Accepts 'platform|slot|episode' keys, 'platform|slot' pairs or (platform, slot) tuples."""
    out = set()
    for value in values or ():
        parts = list(value) if isinstance(value, (tuple, list)) else str(value).split('|', 2)
        if len(parts) >= 2:
            parts[1] = _norm_slot(parts[1])
            out.add('|'.join(str(p) for p in parts))
    return out


def _history_core(history):
    """The part of the history that decides the draft (hashed); budget counts are excluded."""
    history = history or {}
    core = {'ledgerMissing': bool(history.get('ledgerMissing')), 'dispatched': sorted(_dispatched(history.get('dispatched')))}
    for p in PLATFORM_ORDER:
        h = history.get(p) or {}
        core[p] = {'used': sorted({str(u).split('#', 1)[0] for u in h.get('used', [])}),
                   'slots': sorted({_norm_slot(s) for s in h.get('slots', [])}),
                   'postSlots': sorted({_norm_slot(s) for s in h.get('postSlots', h.get('slots', []))})}
    return core


def _video_key(video):
    return (video['batchId'], video['episodeId'], video['revision'])


def _interleave(lists):
    out = []
    for i in range(max((len(items) for items in lists), default=0)):
        out += [items[i] for items in lists if i < len(items)]
    return out


def round_robin(videos):
    """scalar → continuum → whenabouts → tectonic; within a game approachable → moderate →
    challenging; ties by (batchId, episodeId, revision)."""
    videos = sorted(videos, key=_video_key)
    per_game = []
    for game in lc.GAMES:
        items = [v for v in videos if v.get('game') == game]
        buckets = [[v for v in items if v.get('difficulty') == d] for d in lc.DIFFICULTIES]
        per_game.append(_interleave(buckets) + [v for v in items if v.get('difficulty') not in lc.DIFFICULTIES])
    return _interleave(per_game) + [v for v in videos if v.get('game') not in lc.GAMES]


def _exclusion(platform, channel):
    if not channel:
        return f'No {LABELS[platform]} channel is configured'
    if channel.get('route') == 'disabled':
        return 'Channel route is disabled' + (f": {channel['reason']}" if channel.get('reason') else '')
    if not channel.get('accountId'):
        return 'No account identifier is configured'
    if not channel.get('identityVerified'):
        return 'Account identity is not verified'
    if not channel.get('publishingVerified'):
        return 'Publishing is not verified (posting test pending)'
    return None


def _static_reason(video, platform):
    media = (video.get('platforms') or {}).get(platform) or {}
    if not media.get('eligible'):
        return media.get('reason') or f'Video was not checked for {LABELS[platform]}'
    publication = video['episode']['publication']
    if platform == 'youtube':
        return None if publication.get('youtube') else 'No YouTube title and description'
    if platform == 'tiktok' and len(re.findall(r'(?<!\w)#\w+', (publication.get('captions') or {}).get('tiktok') or '')) > TIKTOK_MAX_HASHTAGS:
        return f'TikTok caption has more than {TIKTOK_MAX_HASHTAGS} hashtags (Buffer limit)'
    return None if (publication.get('captions') or {}).get(platform) is not None else f'No {LABELS[platform]} caption'


def _date_reason(video, day):
    window = video.get('eligibility') or {}
    if window.get('notBefore') and day < dt.date.fromisoformat(window['notBefore']):
        return f"Not before {window['notBefore']}"
    if window.get('expiresAt') and day > dt.date.fromisoformat(window['expiresAt']):
        return f"Expired on {window['expiresAt']}"
    if window.get('reviewBy') and day > dt.date.fromisoformat(window['reviewBy']):
        return f"Review was due by {window['reviewBy']}"
    return None


def _local_slot(day, hhmm, zone, name):
    """Same rule as runner.slots: nonexistent wall times skipped, ambiguous ones use fold=0."""
    hour, minute = map(int, hhmm.split(':'))
    value = dt.datetime.combine(day, dt.time(hour, minute), zone)
    if value.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != value.replace(tzinfo=None):
        return None, f'{day} {hhmm} does not exist in {name} (clocks spring forward); that slot was skipped'
    if value.replace(fold=1).utcoffset() != value.utcoffset():
        return value, (f'{day} {hhmm} happens twice in {name} (clocks fall back); '
                       f'using the first occurrence ({value.tzname()})')
    return value, None


def slot_display(slot_utc, tz):
    value = _parse(slot_utc) if isinstance(slot_utc, str) else slot_utc.astimezone(UTC)
    local = value.astimezone(tz if isinstance(tz, dt.tzinfo) else zone_for(tz))
    return {'local': local.isoformat(), 'utc': iso(value), 'zone': local.tzname()}


def _job(platform, account, when, zone, **fields):
    slot = fields.pop('slotUtc', None) or iso(when)
    job = {'key': None, 'platform': platform, 'accountId': account, 'slotUtc': slot,
           'slotLocal': when.astimezone(zone).isoformat() if when else None,
           'zone': when.astimezone(zone).tzname() if when else None,
           'kind': 'post', 'episodeKey': None, 'parentKey': None, 'episodeId': None, 'revision': None,
           'batchId': None, 'questionId': None, 'game': None, 'videoSha256': None, 'coverSha256': None,
           'text': None, 'youtube': None, 'thread': None, 'poll': None, 'link': None, 'companion': None,
           'carried': False, 'edited': False, 'basePayload': None, 'warnings': []}
    job.update(fields)
    job['key'] = job['key'] or f"{platform}|{slot}|{job['episodeKey']}"
    return job


def _identity(video):
    return {'episodeId': video['episodeId'], 'revision': video['revision'], 'batchId': video['batchId'],
            'questionId': video['questionId'], 'game': video['game']}


def _post_job(platform, channel, when, zone, video, inputs, thread_ok, warn):
    episode, question = video['episode'], video['questionId']
    publication = episode['publication']
    youtube = thread = link = None
    if platform == 'youtube':
        youtube = {'title': publication['youtube']['title'], 'description': publication['youtube']['description']}
        text = youtube['description']
    else:
        raw = publication['captions'][platform]
        text = lc.expand(episode, platform, raw)
        link = lc.link_for(episode, platform) if '{link}' in raw else None
    if platform == 'x' and inputs['companions']['firstComment']:
        item = (publication.get('firstComment') or {}).get('x')
        if item and thread_ok:
            thread = [lc.expand(episode, 'x', item)]
        elif item:
            warn(X_THREAD_SKIPPED)
    return _job(platform, channel['accountId'], when, zone, episodeKey=question, videoSha256=video['videoSha256'],
                coverSha256=video.get('coverSha256'), text=text, youtube=youtube, thread=thread, link=link,
                **_identity(video))


def poll_fallback_text(poll):
    lines = [poll['question'], *(f'{k}) {o}' for k, o in zip('ABCD', poll['options'])), 'Reply with your letter.']
    return '\n'.join(lines)


def _carried_jobs(base_manifest, zone, channels, by_sha):
    jobs = []
    for mjob in (base_manifest or {}).get('jobs', []):
        payload, platform = mjob['payload'], mjob['platform']
        episode = payload.get('episode') or {}
        media = payload.get('media') or {}
        youtube = (payload.get('metadata') or {}).get('youtube')
        video = by_sha.get(media.get('sha256')) or {}
        jobs.append(_job(platform, (channels.get(platform) or {}).get('accountId'), _parse(mjob['slot']), zone,
                         key=mjob.get('key'), slotUtc=mjob['slot'], kind=payload.get('kind', 'post'),
                         episodeKey=episode.get('id'), episodeId=episode.get('episodeId'),
                         revision=episode.get('revision'), batchId=episode.get('batchId'),
                         questionId=str(episode.get('id', '')).split('#', 1)[0], game=episode.get('game'),
                         videoSha256=media.get('sha256'), coverSha256=video.get('coverSha256'),
                         text=payload.get('caption'), link=payload.get('link'), thread=payload.get('thread'),
                         poll=payload.get('poll'), companion=payload.get('companion'),
                         youtube={'title': youtube.get('title'), 'description': youtube.get('description')} if youtube else None,
                         carried=True, basePayload=payload))
    posts = {(j['platform'], j['episodeKey']): j['key'] for j in jobs if j['kind'] == 'post'}
    for j in jobs:
        if j['kind'] != 'post':
            j['parentKey'] = posts.get((j['platform'], (j['companion'] or {}).get('parentEpisode')))
    return jobs


def _answer_terms(episode):
    creative = episode.get('creative') or {}
    terms = sorted({lc.normalize(t) for t in [creative.get('answer') or '', *(creative.get('answerAliases') or [])]
                    if lc.normalize(t)})
    labels = [lc.normalize(c['label']) for c in creative.get('choices') or []]
    return terms, labels, [label for label in labels if label in terms]


def _edit_errors(job, text, video):
    if video is None:
        return ['Cannot check this edit: its video is no longer an approved library item']
    episode, platform, report = video['episode'], job['platform'], lc.Report()
    terms, labels, answers = _answer_terms(episode)
    if job['kind'] == 'answer':
        # The answer reply is the only text allowed to name the answer.
        if len(text) > lc.COMMENT_LIMITS[platform] or lc.PLACEHOLDER.search(text):
            report.error('text', f'Too long for a {LABELS[platform]} reply, or contains a placeholder', 'length')
    elif platform == 'youtube':
        if '<' in text or '>' in text:
            report.error('text', 'YouTube rejects < and >')
        if lc.PLACEHOLDER.search(text):
            report.error('text', 'No placeholders in YouTube text', 'link')
        if len(text.encode()) > lc.YOUTUBE_DESCRIPTION_BYTES:
            report.error('text', f'Over {lc.YOUTUBE_DESCRIPTION_BYTES} bytes', 'length')
        lc.spoiler_check(report, 'text', text, terms, labels, answers)
    else:
        limit = lc.CAPTION_LIMITS[platform] if job['kind'] == 'post' else lc.COMMENT_LIMITS[platform]
        lc._text_checks(report, 'text', episode, platform, text, limit, terms, labels, answers,
                        platform in lc.LINK_PLATFORMS)
    return [e['message'] for e in report.errors]


def generate(inputs, videos, history, config, base_manifest=None, base_manifest_sha256=None):
    """Draft dict (DESIGN.md "Generator"). `videos` are approved video records, `history` comes
    from ledger_history(), `base_manifest` is the currently approved manifest whose jobs are
    carried unchanged. `base_manifest_sha256` defaults to sha256(canonical(base_manifest)). With
    inputs.carryOnly only the carried jobs are emitted (with inputs.edits applied); no new slots."""
    inputs = _normalize(inputs)
    zone = ZoneInfo(inputs['timezone'])
    videos = sorted(videos, key=_video_key)
    core = _history_core(history)
    channels = config.get('channels') or {}
    warnings, blocking, excluded, ineligible, unfilled = [], [], [], [], []

    def warn(text):
        if text not in warnings:
            warnings.append(text)

    by_id = {(v['episodeId'], v['revision']): v for v in videos}
    by_sha = {v['videoSha256']: v for v in videos}
    carried = _carried_jobs(base_manifest, zone, channels, by_sha)

    active = {}
    thread_ok = x_thread_verified()
    for p in PLATFORM_ORDER:
        if inputs['platforms'][p]['include'] and not inputs['carryOnly']:
            reason = _exclusion(p, channels.get(p))
            if reason:
                excluded.append({'platform': p, 'reason': reason})
            else:
                active[p] = channels[p]
    for p in PLATFORM_ORDER:
        if p not in active and any(j['platform'] == p for j in carried) and _exclusion(p, channels.get(p)):
            warn(f'{LABELS[p]} jobs carried from the approved schedule cannot post: {_exclusion(p, channels.get(p))}')

    occupied = {p: set(core[p]['slots']) for p in PLATFORM_ORDER}
    post_slots = {p: set(core[p]['postSlots']) for p in PLATFORM_ORDER}
    history_used = {p: set(core[p]['used']) for p in PLATFORM_ORDER}
    for j in carried:
        slot = _norm_slot(j['slotUtc'])
        occupied[j['platform']].add(slot)
        history_used[j['platform']].add(j['questionId'])
        if j['kind'] == 'post':
            post_slots[j['platform']].add(slot)
    used = {p: set(values) for p, values in history_used.items()}
    times = {p: sorted(t for t in map(_parse, post_slots[p]) if t) for p in PLATFORM_ORDER}
    day_counts = {p: collections.Counter(t.astimezone(zone).date().isoformat() for t in times[p]) for p in PLATFORM_ORDER}
    buffer_group = [p for p in PLATFORM_ORDER if (channels.get(p) or {}).get('route') == 'buffer']

    order = round_robin(videos)
    static = {}
    for p in active:
        for i, video in enumerate(order):
            reason = _static_reason(video, p)
            if reason:
                static[(p, i)] = reason
            elif video['questionId'] in history_used[p]:
                reason = 'Already posted or scheduled on this account'
            if reason:
                ineligible.append({'platform': p, 'episodeId': video['episodeId'], 'revision': video['revision'],
                                   'questionId': video['questionId'], 'reason': reason})

    def pick(p, day):
        first, unused = None, False
        for i, video in enumerate(order):
            if video['questionId'] in used[p]:
                continue
            unused = True
            reason = static.get((p, i)) or _date_reason(video, day)
            if not reason:
                return video, None
            first = first or reason
        if not unused:
            return None, NO_VIDEO
        return None, f'No unused video is eligible for {LABELS[p]} on {day}: {first}'

    start, end = dt.date.fromisoformat(inputs['startDate']), dt.date.fromisoformat(inputs['endDate'])
    days = [start + dt.timedelta(days=n) for n in range((end - start).days + 1)]
    stagger = collections.Counter()
    posts, requested = [], 0
    for p, channel in active.items():
        spec, gap, cap = inputs['platforms'][p], inputs['minGapHours'][p], PROVIDER_DAILY_CAPS.get(p)
        for day in days:
            if day.weekday() not in spec['weekdays']:
                continue
            candidates = []
            for hhmm in spec['times']:
                value, note = _local_slot(day, hhmm, zone, inputs['timezone'])
                if note:
                    warn(note)
                if value:
                    candidates.append((value.astimezone(UTC), note))
            date = day.isoformat()
            free = sum(iso(base) not in occupied[p] for base, _ in candidates)
            want = max(0, min(free, spec['maxPerDay'] - day_counts[p][date]))
            requested += want
            filled, failures = 0, []
            for base, note in candidates:
                if filled >= want:
                    break

                def fail(reason, when=base, rank=0):
                    failures.append((rank, {'platform': p, 'slotLocal': when.astimezone(zone).isoformat(),
                                            'slotUtc': iso(when), 'reason': reason}))
                if cap and day_counts[p][date] >= cap:
                    fail(f'Daily limit reached on {LABELS[p]} ({cap} posts per day)')
                    continue
                if p in buffer_group and sum(day_counts[b][date] for b in buffer_group) >= BUFFER_DAILY_CAP:
                    fail(f'Buffer daily limit reached ({BUFFER_DAILY_CAP} posts per day shared by Buffer channels)')
                    continue
                video, reason = pick(p, day)
                if not video:
                    fail(reason)
                    continue
                group = (video['questionId'], iso(base))
                when = base + dt.timedelta(minutes=inputs['staggerMinutes'] * stagger[group])
                if iso(when) in occupied[p]:
                    fail(OCCUPIED, when, 1)
                    continue
                if gap and any(abs((when - other).total_seconds()) < gap * 3600 for other in times[p]):
                    fail(f'Too close to another post on this account (minimum gap {gap:g} h)', when)
                    continue
                job = _post_job(p, channel, when, zone, video, inputs, thread_ok, warn)
                if note:
                    job['warnings'].append(note)
                stagger[group] += 1
                occupied[p].add(job['slotUtc'])
                times[p].append(when)
                day_counts[p][date] += 1
                used[p].add(video['questionId'])
                posts.append(job)
                filled += 1
            unfilled += [entry for _, entry in sorted(failures, key=lambda f: f[0])[:want - filled]]

    first_comment, answer_reply = inputs['companions']['firstComment'], inputs['companions']['answerReply']
    threads_ok = THREADS_REPLY_SCOPE in ((channels.get('threads') or {}).get('observedScopes') or [])
    if first_comment or answer_reply:
        for p in active:
            if p == 'threads' and not threads_ok:
                excluded.append({'platform': p, 'companion': 'reply', 'reason': THREADS_SCOPE_MISSING})
            elif first_comment and COMPANIONS[p]['comment'] == 'unavailable':
                excluded.append({'platform': p, 'companion': 'comment', 'reason': COMPANIONS[p]['reason']})

    companions = []
    for parent in posts:
        p, video = parent['platform'], by_id[(parent['episodeId'], parent['revision'])]
        episode, question = video['episode'], video['questionId']
        publication = episode['publication']
        comments = publication.get('firstComment') or {}
        planned = []
        if first_comment and (p in ('instagram', 'bluesky') or (p == 'threads' and threads_ok)):
            if p == 'threads' and publication.get('poll'):
                text = poll_fallback_text(publication['poll'])
                if len(text) > lc.COMMENT_LIMITS['threads']:
                    warn(f"{question}: the Threads poll reply would exceed {lc.COMMENT_LIMITS['threads']} characters; skipped")
                else:
                    poll = {'question': publication['poll']['question'], 'options': list(publication['poll']['options']),
                            'native': False}
                    planned.append(('poll', text, None, COMMENT_DELAY_MINUTES, poll))
            elif comments.get(p):
                raw = comments[p]
                planned.append(('comment', lc.expand(episode, p, raw),
                                 lc.link_for(episode, p) if '{link}' in raw else None, COMMENT_DELAY_MINUTES, None))
        reply = publication.get('answerReply')
        if (answer_reply and reply and p in lc.ANSWER_REPLY_PLATFORMS and COMPANIONS[p]['answer'] != 'unavailable'
                and (p != 'threads' or threads_ok)):
            planned.append(('answer', reply['text'], None, round(reply['delayHours'] * 60), None))
        parent_when = _parse(parent['slotUtc'])
        for kind, text, link, delay, poll in planned:
            target = parent_when + dt.timedelta(minutes=delay)
            when = next((target + dt.timedelta(minutes=s) for s in range(COMPANION_SHIFT_LIMIT)
                         if iso(target + dt.timedelta(minutes=s)) not in occupied[p]), None)
            if when is None:
                warn(f'{LABELS[p]} {kind} for {question} skipped: no free minute near {iso(target)}')
                continue
            occupied[p].add(iso(when))
            minutes = int((when - parent_when).total_seconds() // 60)
            companions.append(_job(p, parent['accountId'], when, zone, kind=kind, episodeKey=f'{question}#{kind}',
                                   parentKey=parent['key'], text=text, link=link, poll=poll,
                                   companion={'parentEpisode': question, 'delayMinutes': minutes},
                                   **_identity(video)))

    new = sorted(posts + companions, key=lambda j: (j['slotUtc'], PLATFORM_ORDER.index(j['platform']),
                                                     KIND_ORDER.index(j['kind']), j['key']))
    jobs = carried + new
    by_key = {j['key']: j for j in jobs}
    sent_keys = set(core['dispatched'])
    sent_slots = {'|'.join(k.split('|', 2)[:2]) for k in sent_keys}

    def sent(job):
        slot = _norm_slot(job['slotUtc'])
        return (f"{job['platform']}|{slot}|{job['episodeKey']}" in sent_keys
                or f"{job['platform']}|{slot}" in sent_slots)

    removed = set()
    for key in sorted(inputs['edits']):
        edit, job = inputs['edits'][key], by_key.get(key)
        if job is None:
            warn(f'An edit names a job that is not in this draft and was not applied: {key}')
            continue
        family = [job] + ([j for j in jobs if j['parentKey'] == key] if 'remove' in edit else [])
        if any(sent(j) for j in family):
            blocking.append(f"{LABELS[job['platform']]} {job['slotLocal']}: {SENT}")
            job['warnings'].append(SENT)
            continue
        if 'remove' in edit:
            removed |= {j['key'] for j in family}
            continue
        p, text = job['platform'], edit['text']
        video = by_id.get((job['episodeId'], job['revision']))
        errors = _edit_errors(job, text, video)
        final = lc.expand(video['episode'], p, text) if video and '{link}' in text and p in lc.LINK_PLATFORMS else text
        if video and '{link}' in text and p in lc.LINK_PLATFORMS:
            job['link'] = lc.link_for(video['episode'], p)
        elif not (job['link'] and job['link'] in final):
            job['link'] = None
        job['text'], job['edited'] = final, True
        if job['youtube']:
            job['youtube'] = {**job['youtube'], 'description': final}
        for message in errors:
            job['warnings'].append(message)
            line = f"{LABELS[p]} {job['slotLocal']}: {message}"
            warn(line)
            blocking.append(line)

    for j in jobs:
        if j['key'] in removed and j['kind'] == 'post' and not j['carried']:
            unfilled.append({'platform': j['platform'], 'slotLocal': j['slotLocal'], 'slotUtc': j['slotUtc'],
                             'reason': 'Removed by edit'})
    jobs = [j for j in jobs if j['key'] not in removed]

    if core['ledgerMissing']:
        warn('No publisher ledger was found, so posting history could not be checked')
    if (history or {}).get('deploymentsLast31d', 0) >= PAGES_DEPLOYMENT_LIMIT:
        warn(f'Pages deployment budget is used up ({PAGES_DEPLOYMENT_LIMIT} in 31 days); approval cannot deploy media yet')
    if (history or {}).get('bufferCallsLast24h', 0) >= BUFFER_CALL_LIMIT:
        warn(f'Buffer call budget is used up for the last 24 hours ({BUFFER_CALL_LIMIT}); Buffer posts due soon will wait')

    if base_manifest is not None and base_manifest_sha256 is None:
        base_manifest_sha256 = hashlib.sha256(lc.canonical(base_manifest)).hexdigest()
    return {
        'version': 1, 'inputs': inputs, 'baseManifestSha256': base_manifest_sha256,
        'libraryHash': hashlib.sha256(lc.canonical(videos)).hexdigest(),
        'historyHash': hashlib.sha256(lc.canonical(core)).hexdigest(),
        'jobs': jobs, 'unfilled': unfilled, 'excluded': excluded, 'ineligible': ineligible,
        'warnings': warnings, 'blocking': blocking,
        'summary': {'requested': requested, 'filled': sum(j['kind'] == 'post' and not j['carried'] for j in jobs),
                    'companions': sum(j['kind'] != 'post' and not j['carried'] for j in jobs),
                    'carried': sum(j['carried'] for j in jobs), 'removed': len(removed)},
    }


def draft_sha256(draft):
    return hashlib.sha256(lc.canonical(draft)).hexdigest()


def manifest_payload(job, video, config, draft_sha):
    """Exact runner payload for one draft job (DESIGN.md "Manifest"). Carried jobs keep their
    approved payload byte-for-byte unless the owner edited them."""
    if job.get('carried'):
        payload = copy.deepcopy(job['basePayload'])
        if job.get('edited'):
            payload['caption'], payload['link'] = job['text'], job['link']
            if (payload.get('metadata') or {}).get('youtube'):
                payload['metadata']['youtube']['description'] = job['text']
            payload['approval'] = {**(payload.get('approval') or {}), 'draftSha256': draft_sha}
        return payload
    if video is None or video['episodeId'] != job['episodeId'] or video['revision'] != job['revision']:
        raise ValueError('Job and video record do not match')
    episode = {'id': job['episodeKey'], 'episodeId': job['episodeId'], 'revision': job['revision'],
               'batchId': job['batchId'], 'game': job['game']}
    approval = {'draftSha256': draft_sha, 'contentApprovalId': video['approvalId'], 'metadataSha256': video['metadataSha256']}
    if job['kind'] != 'post':
        return {'episode': episode, 'kind': job['kind'], 'caption': job['text'], 'link': job['link'], 'media': None,
                'metadata': {}, 'poll': job['poll'], 'companion': dict(job['companion']), 'approval': approval}
    if video['videoSha256'] != job['videoSha256']:
        raise ValueError('Job and video record do not match')
    base = (config.get('media') or {}).get('baseUrl')
    if not base:
        raise ValueError('Media base URL is not configured')
    metadata = {}
    if job['platform'] == 'instagram':
        metadata = {'instagram': {'type': 'reel', 'shouldShareToFeed': True}}
    elif job['platform'] == 'youtube':
        metadata = {'youtube': {'title': job['youtube']['title'], 'description': job['text'], 'categoryId': '27',
                                'privacy': 'public', 'madeForKids': False, 'license': 'youtube',
                                'notifySubscribers': True, 'embeddable': True, 'isAiGenerated': False}}
    return {'episode': episode, 'kind': 'post', 'format': 'self-contained', 'caption': job['text'],
            'link': job['link'], 'previous': None,
            'media': {'url': f"{base.rstrip('/')}/library/{job['videoSha256']}.mp4", 'sha256': job['videoSha256'],
                      'bytes': video['bytes'], 'rightsReviewed': True},
            'metadata': metadata, 'thread': job['thread'], 'approval': approval}
