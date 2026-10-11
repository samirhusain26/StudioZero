"""Schedule approval: UI request file -> applier (scalar-social user) -> approved manifest. Never publishes.

The applier re-validates the draft, deploys the referenced media once, verifies every public URL by
hash, writes the exact manifest bytes and replaces manifests/approved.json. Binding that hash into
/etc/scalar-social/config.json is approval_bind.py (root); enabling channels/timer is activate.py (owner).

Busy publisher: the request is archived with a failed/publisher_busy result and the owner approves
again. Keeping it would make the path unit retrigger in a tight loop while the runner holds its lock.
--no-deploy (staging demo, L10) validates and hashes the manifest in memory and writes result.json
only: no site files, manifests, approved.json, ledger or config change; the request is left in place.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import time

import runner
# In the repo the shared contract lives in <repo>/contract; on the Pi the installer copies it next to this file.
_CONTRACT = Path(__file__).resolve().parents[2] / 'contract'
if _CONTRACT.is_dir() and str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))
from library_contract import canonical  # noqa: E402

UTC = dt.timezone.utc
SHA = re.compile(r'[0-9a-f]{64}')
REQUEST_CAP = 4096
RESULT_CAP = 64*1024
MANIFEST_CAP = 8*1024*1024
PLATFORM_ORDER = ('instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok')
LABELS = {'instagram': 'Instagram', 'facebook': 'Facebook', 'threads': 'Threads', 'x': 'X',
          'youtube': 'YouTube', 'bluesky': 'Bluesky', 'tiktok': 'TikTok'}
NOTHING = ' Nothing was scheduled or published.'
MESSAGES = {
    'invalid_request': 'The approval request could not be read. Approve the draft again.',
    'publisher_busy': 'The publisher was busy, so nothing changed. Approve the draft again in a minute.',
    'configuration': 'The publishing configuration could not be read.'+NOTHING,
    'draft_missing': 'That draft no longer exists or has changed. Generate a new draft and approve it.',
    'stale_draft': 'The library, posting history, accounts or a newer approval changed after this draft was made. '
                   'Generate a new draft and approve it.',
    'invalid_draft': 'The draft contains an entry that cannot be published as written. Generate a new draft.',
    'dispatched_job_changed': 'This schedule would change or remove a post that has already been sent. Nothing changed.',
    'episode_conflict': 'A question in this schedule already has a post reserved on that account. Generate a new draft.',
    'media': 'A video for this schedule is missing or does not match its recorded hash.'+NOTHING,
    'deployment': 'Publishing the videos to the media site failed.'+NOTHING,
    'deployment_budget': 'The monthly media-site deployment allowance is used up.'+NOTHING,
    'media_delivery': 'A published video could not be downloaded with the expected contents.'+NOTHING,
    'storage': 'The approved schedule could not be saved.'+NOTHING,
    'internal': 'Approval stopped unexpectedly.'+NOTHING,
}


class Conflict(Exception):
    """An approval request is already pending."""


class Failure(Exception):
    def __init__(self, category, message=None):
        super().__init__(category)
        self.category = category
        self.message = message or MESSAGES[category]


def stamp(now):
    return now.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_capped(path, cap):
    """Bytes of a regular, non-symlink file no larger than cap. FileNotFoundError when absent."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise
    except OSError:
        raise ValueError('Refusing a symlinked or unreadable file') from None
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Refusing a non-regular file')
        data = handle.read(cap+1)
    if len(data) > cap:
        raise ValueError('File exceeds its size limit')
    return data


def write_atomic(path, data, mode=0o600):
    path = Path(path)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name+'-')
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def _index_draft(index, draft_sha):
    if isinstance(index, sqlite3.Connection):
        return index.execute('SELECT body FROM drafts WHERE sha256=?', (draft_sha,)).fetchone()
    path = Path(index)
    if not path.is_file():
        return None
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        return db.execute('SELECT body FROM drafts WHERE sha256=?', (draft_sha,)).fetchone()


def request_approval(state, *args, draft_exists=None, now=None):
    """request_approval(state, draft_sha, confirmation) or (state, index, draft_sha, confirmation).

    Publishes the request with an exclusive hard link, so the path unit never sees a partial file.
    """
    if len(args) == 3:
        index, draft_sha, confirmation = args
        if draft_exists is None:
            draft_exists = lambda sha: _index_draft(index, sha) is not None
    elif len(args) == 2:
        draft_sha, confirmation = args
    else:
        raise TypeError('request_approval(state, [index,] draft_sha, confirmation)')
    if not isinstance(draft_sha, str) or not SHA.fullmatch(draft_sha):
        raise ValueError('Unknown draft.')
    if confirmation != f'APPROVE {draft_sha[:8]}':
        raise ValueError(f'Type APPROVE {draft_sha[:8]} exactly to approve this draft.')
    if draft_exists is not None and not (draft_exists(draft_sha) if callable(draft_exists) else draft_exists):
        raise ValueError(MESSAGES['draft_missing'])
    folder = Path(state)/'approval'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    request = {'draftSha256': draft_sha, 'requestedAt': stamp(now or dt.datetime.now(UTC))}
    fd, name = tempfile.mkstemp(dir=folder, prefix='.request-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(canonical(request))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(name, folder/'request.json')
        except FileExistsError:
            raise Conflict('An approval is already being processed. Wait for its result.') from None
    finally:
        Path(name).unlink(missing_ok=True)
    return request


def current_manifest(state):
    """(sha256, parsed) of manifests/approved.json, or (None, None)."""
    try:
        raw = read_capped(Path(state)/'manifests'/'approved.json', MANIFEST_CAP)
    except FileNotFoundError:
        return None, None
    return hashlib.sha256(raw).hexdigest(), json.loads(raw)


def approval_state(state):
    folder = Path(state)/'approval'
    out = {'pending': None, 'result': None, 'manifestSha256': None}
    for name, key, cap in (('request.json', 'pending', REQUEST_CAP), ('result.json', 'result', RESULT_CAP)):
        try:
            out[key] = json.loads(read_capped(folder/name, cap))
        except FileNotFoundError:
            pass
        except ValueError:
            out[key] = {'status': 'unreadable'}
    with contextlib.suppress(ValueError):
        out['manifestSha256'] = current_manifest(state)[0]
    return out


def intended_config(config, scope):
    """Config with exactly scope enabled + its fingerprint. Raises Failure('scope') with plain text."""
    problems = []
    for platform in scope:
        channel = config['channels'].get(platform)
        label = LABELS.get(platform, platform)
        if not channel:
            problems.append(f'{label} is not configured.')
        elif channel.get('route') == 'disabled':
            problems.append(f'{label} has no publishing route.')
        elif not (channel.get('identityVerified') and channel.get('publishingVerified')):
            problems.append(f'{label} account identity and publishing test are not both verified.')
        elif not channel.get('accountId'):
            problems.append(f'{label} has no account identifier.')
    if problems:
        raise Failure('scope', ' '.join(problems)+' Remove it from the schedule or finish its verification.')
    intended = json.loads(json.dumps(config))
    for platform, channel in intended['channels'].items():
        channel['enabled'] = platform in scope
    try:
        runner.validate(intended)
    except ValueError as error:
        # runner.validate messages are fixed plain-language strings.
        raise Failure('scope', f'These platforms cannot be enabled together: {error}.') from None
    except (KeyError, TypeError):
        raise Failure('scope', 'The publishing configuration is incomplete for these platforms.') from None
    return intended, runner.fingerprint(intended)


def ledger_key(platform, account, slot):
    return hashlib.sha256(f'{platform}|{account}|{slot}'.encode()).hexdigest()[:24]


# The runner never dispatches or reconciles these again, so their media is never fetched again: a posted video
# may be removed from the Pi (ui_library.archive_videos) without blocking later approvals or activation.
FINISHED = ('confirmed', 'failed', 'expired')


def finished_keys(rows):
    return {row['id'] for row in rows if row['status'] in FINISHED}


def plan_ledger(rows, jobs, config, old_jobs):
    """Rows to cancel (undispatched, absent/changed) and whether a dispatched row would change."""
    wanted = {}
    for job in jobs:
        account = config['channels'][job['platform']]['accountId']
        wanted[ledger_key(job['platform'], account, job['slot'])] = (job, account)
    old_ids = set()
    for job in old_jobs or []:
        account = (config['channels'].get(job.get('platform')) or {}).get('accountId')
        old_ids.add(ledger_key(job.get('platform'), account, job.get('slot')))
    cancel, refused = [], []
    for row in rows:
        dispatched = row['dispatched_at'] is not None or row['status'] != 'ready'
        if row['id'] in wanted:
            payload = wanted[row['id']][0]['payload']
            if json.loads(row['payload']) == payload and row['episode'] == payload['episode']['id']:
                continue
            (refused if dispatched else cancel).append(row)
        elif not dispatched:
            cancel.append(row)
        elif row['id'] in old_ids:
            refused.append(row)
    cancelled = {row['id'] for row in cancel}
    kept = [row for row in rows if row['id'] not in cancelled]
    conflict = any(row['platform'] == job['platform'] and row['account'] == account
                   and row['episode'] == job['payload']['episode']['id'] and row['id'] != key
                   for key, (job, account) in wanted.items() for row in kept)
    return cancel, refused, conflict


def _ledger_rows(state, deploy):
    path = Path(state)/'ledger.sqlite3'
    if deploy:
        ledger = runner.Ledger(path)
        return ledger, [dict(r) for r in ledger.db.execute('SELECT * FROM jobs ORDER BY slot,id')]
    if not path.is_file():
        return None, []
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        return None, [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY slot,id')]


def _check_payload(job, payload, base_url):
    episode = payload.get('episode') if isinstance(payload, dict) else None
    if not isinstance(episode, dict) or not isinstance(episode.get('id'), str) or not episode['id']:
        raise Failure('invalid_draft')
    media = payload.get('media')
    if media is None:
        return None
    if (not isinstance(media, dict) or not isinstance(media.get('sha256'), str) or not SHA.fullmatch(media['sha256'])
            or not isinstance(media.get('bytes'), int) or not base_url or not base_url.startswith('https://')
            or media.get('url') != base_url.rstrip('/')+'/library/'+media['sha256']+'.mp4'):
        raise Failure('invalid_draft')
    return media


def _parse_slot(value):
    try:
        slot = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise Failure('invalid_draft') from None
    if slot.tzinfo is None:
        raise Failure('invalid_draft')
    return value


def _sha_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while chunk := handle.read(1 << 16):
            digest.update(chunk)
    return digest.hexdigest()


def default_locate(state, sha):
    state = Path(state)
    path = state/'library'/'objects'/f'{sha}.mp4'
    if path.is_file():
        return path
    index = state/'library'/'index.sqlite3'
    if index.is_file():
        with contextlib.closing(sqlite3.connect(index.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            row = db.execute('SELECT path FROM videos WHERE sha256=?', (sha,)).fetchone()
        if row:
            candidate = (state/row[0]).resolve()
            if candidate.is_relative_to(state.resolve()) and candidate.is_file():
                return candidate
    return None


def link_media(state, sha, locate):
    """Hard-link (fallback copy) a verified object into site/library/<sha>.mp4."""
    target_dir = Path(state)/'site'/'library'
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = target_dir/f'{sha}.mp4'
    if target.is_file() and not target.is_symlink() and _sha_file(target) == sha:
        return target
    source = locate(state, sha)
    if not source or not Path(source).is_file() or _sha_file(source) != sha:
        raise Failure('media')
    temp = target_dir/f'.{sha}.{os.getpid()}.tmp'
    temp.unlink(missing_ok=True)
    try:
        try:
            os.link(source, temp)
        except OSError:
            shutil.copyfile(source, temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def default_load_draft(state, draft_sha):
    row = _index_draft(Path(state)/'library'/'index.sqlite3', draft_sha)
    return json.loads(row[0]) if row else None


def ledger_history(state, config):
    """{platform: {used: questionIds on current/previous accounts, slots: slots on the current account}}."""
    path = Path(state)/'ledger.sqlite3'
    rows = []
    if path.is_file():
        with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            rows = db.execute('SELECT platform, account, slot, episode FROM jobs').fetchall()
    history = {}
    for platform, channel in config['channels'].items():
        accounts = {channel.get('accountId'), *channel.get('previousAccountIds', [])} - {None}
        history[platform] = {
            'used': {episode.split('#')[0] for p, account, _, episode in rows if p == platform and account in accounts},
            'slots': {slot for p, account, slot, _ in rows if p == platform and account == channel.get('accountId')}}
    return history


def _schedulable(state, draft, now):
    import ui_library
    from zoneinfo import ZoneInfo
    today = now.astimezone(ZoneInfo(draft['inputs']['timezone'])).date()
    index = Path(state)/'library'/'index.sqlite3'
    if not index.is_file():
        raise ValueError('library index missing')
    with contextlib.closing(sqlite3.connect(index.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        return ui_library.schedulable_videos(db, today)


def default_revalidate(state, config, draft, base_manifest, now):
    """New (non-carried) posts must still use approved, eligible, unused videos at free future slots.

    Not a full regeneration: ledger status changes while live would make every draft stale."""
    videos = {(v['episodeId'], v['revision'], v['videoSha256']): v for v in _schedulable(state, draft, now)}
    history = ledger_history(state, config)
    for job in draft['jobs']:
        if job.get('carried') or job.get('parentKey'):
            continue
        video = videos.get((job.get('episodeId'), job.get('revision'), job.get('videoSha256')))
        if not video or not (video['platforms'].get(job['platform']) or {}).get('eligible'):
            raise ValueError('video no longer approved or eligible')
        used = history.get(job['platform'], {'used': set(), 'slots': set()})
        if str(job.get('questionId')).split('#')[0] in used['used'] or job.get('slotUtc') in used['slots']:
            raise ValueError('question or slot already used')
        if dt.datetime.fromisoformat(job['slotUtc']) <= now:
            raise ValueError('slot already passed')


def default_payload_builder(state, now):
    """ui_schedule.manifest_payload with the approved video record of each new job."""
    cache = {}

    def build(job, draft, config):
        import ui_schedule
        sha = hashlib.sha256(canonical(draft)).hexdigest()
        if job.get('carried'):
            return ui_schedule.manifest_payload(job, None, config, sha)
        if 'videos' not in cache:
            cache['videos'] = {(v['episodeId'], v['revision']): v for v in _schedulable(state, draft, now)}
        return ui_schedule.manifest_payload(job, cache['videos'].get((job.get('episodeId'), job.get('revision'))),
                                            config, sha)
    return build


def default_record(state, manifest_sha, manifest):
    import ui_library
    hashes = sorted({j['payload']['media']['sha256'] for j in manifest['jobs'] if j['payload'].get('media')})
    with contextlib.closing(ui_library.open_index(state)) as db:
        ui_library.record_manifest(db, manifest_sha, manifest['draftSha256'], hashes, manifest['approvedAt'])


def _same_post(old, new):
    strip = lambda payload: {k: v for k, v in payload.items() if k != 'approval'} if isinstance(payload, dict) else payload
    return strip(old) == strip(new)


def _apply_locked(state, config_path, draft_sha, deploy, deployer, verifier, load_draft, revalidate,
                  build_payload, locate, record, now):
    try:
        config = json.loads(Path(config_path).read_text())
        base_url = config['media']['baseUrl']
        channels = config['channels']
    except (OSError, ValueError, KeyError, TypeError):
        raise Failure('configuration') from None
    try:
        draft = load_draft(state, draft_sha)
    except (OSError, ValueError, sqlite3.Error):
        draft = None
    if not isinstance(draft, dict) or hashlib.sha256(canonical(draft)).hexdigest() != draft_sha:
        raise Failure('draft_missing')
    try:
        current_sha, current = current_manifest(state)
    except ValueError:
        raise Failure('storage') from None
    if (draft.get('baseManifestSha256') or None) != current_sha:
        raise Failure('stale_draft')
    try:
        revalidate(state, config, draft, current, now)
    except (ValueError, KeyError, TypeError):
        raise Failure('stale_draft') from None
    if draft.get('blocking'):
        raise Failure('invalid_draft', 'This draft has problems that block approval. Fix or remove them, then approve the new draft.')
    if not isinstance(draft.get('jobs'), list) or not draft['jobs']:
        raise Failure('invalid_draft', 'The draft has no posts to schedule.')
    old_payloads = {j.get('key'): j.get('payload') for j in (current or {}).get('jobs', [])}
    jobs, job_media = [], []
    for job in draft['jobs']:
        if not isinstance(job, dict) or job.get('platform') not in channels:
            raise Failure('invalid_draft')
        if job.get('accountId') != channels[job['platform']].get('accountId'):
            raise Failure('stale_draft')
        try:
            payload = build_payload(job, draft, config)
        except (ValueError, KeyError, TypeError):
            raise Failure('stale_draft') from None
        if job.get('carried') and _same_post(old_payloads.get(job.get('key')), payload):
            # Unedited carried job: keep the exact approved payload (its approval provenance included).
            payload = old_payloads[job['key']]
        item = _check_payload(job, payload, base_url)
        slot = _parse_slot(job.get('slotUtc'))
        if item:
            job_media.append((ledger_key(job['platform'], channels[job['platform']].get('accountId'), slot), item))
        jobs.append({'platform': job['platform'], 'slot': slot, 'key': job.get('key'), 'payload': payload})
    if (len({(j['platform'], j['slot']) for j in jobs}) != len(jobs)
            or len({(j['platform'], j['payload']['episode']['id']) for j in jobs}) != len(jobs)
            or len({j['key'] for j in jobs}) != len(jobs)):
        raise Failure('invalid_draft')
    scope = [p for p in PLATFORM_ORDER if any(j['platform'] == p for j in jobs)]
    scope += sorted({j['platform'] for j in jobs} - set(scope))
    _, scope_hash = intended_config(config, scope)
    manifest = {'version': 1, 'draftSha256': draft_sha, 'scopeHash': scope_hash, 'scope': scope,
                'approvedAt': stamp(now), 'jobs': jobs}
    data = canonical(manifest)
    if len(data) > MANIFEST_CAP:
        raise Failure('invalid_draft', 'This schedule is too large to approve at once. Shorten the date range.')
    sha = hashlib.sha256(data).hexdigest()
    ledger, rows = _ledger_rows(state, deploy)
    done = finished_keys(rows)
    # Only media for posts that can still be sent is linked, deployed and verified; finished posts keep their payload.
    media = {item['sha256']: item for key, item in job_media if key not in done}
    try:
        cancel, refused, conflict = plan_ledger(rows, jobs, config, (current or {}).get('jobs'))
        if refused:
            raise Failure('dispatched_job_changed')
        if conflict:
            raise Failure('episode_conflict')
        summary = {'manifestSha256': sha, 'draftSha256': draft_sha, 'scope': scope, 'jobs': len(jobs),
                   'cancelled': len(cancel), 'at': stamp(now)}
        if not deploy:
            return {'status': 'validated-no-deploy', **summary}
        for digest in media:
            link_media(state, digest, locate)
        if media:
            try:
                deployer(ledger, config, Path(state)/'site')
            except Exception as error:
                raise Failure('deployment_budget' if getattr(error, 'category', None) == 'budget' else 'deployment') from None
        checks = []
        for digest, item in sorted(media.items()):
            try:
                receipt = verifier(item['url'], digest)
            except Exception:
                print(f"Public media check failed: {item['url']}", file=sys.stderr)
                raise Failure('media_delivery') from None
            if not isinstance(receipt, dict) or receipt.get('sha256') != digest:
                print(f"Public media check failed: {item['url']}", file=sys.stderr)
                raise Failure('media_delivery')
            checks.append({'url': item['url'], 'sha256': digest, 'bytes': receipt.get('bytes'), 'verified': True})
        verification = {'version': 1, 'manifestSha256': sha, 'checkedAt': stamp(now), 'allVerified': True,
                        'urls': checks}
        folder = Path(state)/'manifests'
        try:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_atomic(folder/f'{sha}.json', data)
            write_atomic(folder/f'{sha}.verification.json', canonical(verification))
        except OSError:
            raise Failure('storage') from None
        try:
            record(state, sha, manifest)
        except Exception:
            raise Failure('storage') from None
        try:
            with ledger.db:
                for row in cancel:
                    deleted = ledger.db.execute(
                        "DELETE FROM jobs WHERE id=? AND status='ready' AND dispatched_at IS NULL", (row['id'],)).rowcount
                    if deleted != 1:
                        raise sqlite3.IntegrityError('row changed')
                    ledger.db.execute('INSERT INTO events(job,kind,at,detail) VALUES(?,?,?,?)',
                                      (row['id'], 'cancelled', runner.iso(now), json.dumps(row, sort_keys=True)))
            write_atomic(folder/'approved.json', data)
        except (OSError, sqlite3.Error):
            raise Failure('storage') from None
        return {'status': 'manifest-ready', **summary,
                'deployment': {'deployed': bool(media), 'mediaFiles': len(media)},
                'verifiedUrls': [c['url'] for c in checks]}
    finally:
        if ledger:
            ledger.db.close()


def _archive(state, raw_name, result, now):
    folder = Path(state)/'approval'
    history = folder/'history'
    history.mkdir(parents=True, exist_ok=True, mode=0o700)
    prefix = now.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')+'-'+(result.get('draftSha256') or 'unknown')[:8]
    with contextlib.suppress(FileNotFoundError):
        os.replace(folder/raw_name, history/f'{prefix}-request.json')
    write_atomic(history/f'{prefix}-result.json', canonical(result))


def patient(verify, attempts=6, delay=10, sleep=time.sleep):
    """Retry a public media check: a new Pages deployment can take a little while to serve every file."""
    def check(url, digest):
        for attempt in range(attempts):
            try:
                return verify(url, digest)
            except Exception:
                if attempt == attempts - 1:
                    raise
                sleep(delay)
    return check


def apply(state, config_path, *, deploy=True, deployer=None, verifier=None, load_draft=None, revalidate=None,
          build_payload=None, locate=None, record_manifest=None, now=None):
    """Process STATE/approval/request.json. Returns the result dict, or None when nothing is pending."""
    state = Path(state)
    now = now or dt.datetime.now(UTC)
    if deployer is None:
        from prepare import deploy_site as deployer
    if verifier is None:
        from verify_delivery import verify
        verifier = patient(verify)
    folder = state/'approval'
    draft_sha = None
    try:
        try:
            request = json.loads(read_capped(folder/'request.json', REQUEST_CAP))
        except FileNotFoundError:
            return None
        except ValueError:
            raise Failure('invalid_request') from None
        draft_sha = request.get('draftSha256') if isinstance(request, dict) else None
        if not isinstance(draft_sha, str) or not SHA.fullmatch(draft_sha):
            draft_sha = None
            raise Failure('invalid_request')
        with contextlib.ExitStack() as stack:
            if deploy:
                try:
                    stack.enter_context(runner.lock(state/'runner.lock'))
                except BlockingIOError:
                    raise Failure('publisher_busy') from None
            result = _apply_locked(state, config_path, draft_sha, deploy, deployer, verifier,
                                   load_draft or default_load_draft, revalidate or default_revalidate,
                                   build_payload or default_payload_builder(state, now), locate or default_locate,
                                   record_manifest or default_record, now)
    except Failure as failure:
        result = {'status': 'failed', 'category': failure.category, 'message': failure.message,
                  'draftSha256': draft_sha, 'at': stamp(now)}
    except Exception:
        # Never echo exception text: it may carry paths, vendor output or credentials.
        result = {'status': 'failed', 'category': 'internal', 'message': MESSAGES['internal'],
                  'draftSha256': draft_sha, 'at': stamp(now)}
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_atomic(folder/'result.json', canonical(result))
    if deploy:
        _archive(state, 'request.json', result, now)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Apply a pending schedule approval. Never publishes.')
    parser.add_argument('command', choices=('apply',))
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--no-deploy', action='store_true', help='Staging: validate only; write result.json only')
    args = parser.parse_args(argv)
    result = apply(args.state, args.config, deploy=not args.no_deploy)
    if result is None:
        print('No approval request is waiting.')
        return 0
    print(json.dumps({k: result[k] for k in ('status', 'category', 'message', 'manifestSha256', 'scope', 'jobs')
                      if k in result}))
    return 0 if result['status'] in ('manifest-ready', 'validated-no-deploy') else 2


if __name__ == '__main__':
    sys.exit(main())
