"""Pi library index: streaming uploads, batch import, legacy registration, content approval.

Stdlib only (Python 3.13 on the Pi). Contract rules live in library_contract.py and are
never duplicated here. Every problem string is plain language for the owner's phone:
no stack traces and no paths outside STATE-relative names.

Index: STATE/library/index.sqlite3 (WAL, synchronous FULL, 0600; library dirs 0700).
Schema = DESIGN.md plus these additions:
  batch_documents(sha256, batch_id, origin, raw, imported_at)  every batch.json version ever
      imported (batches.batch_json holds the latest). Older manual-* (phone upload) batches stay readable.
  videos.cover_sha256       frame extracted from this video (legacy media).
  covers.registered_at      when the cover object was registered.
  indexes on episodes(batch_id), episodes(video_sha256), episodes(question_id),
      approvals(episode_id, revision).
  feedback(episode_id, revision, tags, note, status open|used, updated_at)  owner feedback for the next batch.
  batch_notes(batch_id, kind brief|retro, text, sha256, bytes, uploaded_at)  batch brief/retro markdown.
  Feedback and notes may name answers: they are owner-only planning text, never read by scheduling,
  approval or publishing, and never part of captions.

Contract v1 and v2 batches share the index: episodes.question_id holds the duplicate key (v2 contentId, v1
questionId; the namespaces are the same, so nothing is migrated) and episodes.game the scheduling group (v1 game;
v2 projectData.game, else the project). metadata is the episode exactly as imported; lc.episode_view() reads
both versions for the views.

Statuses: awaiting_files -> reviewable | invalid; reviewable -> approved -> withdrawn.
A withdrawn revision may be approved again (a fresh, recorded decision). "Expired" is
computed from eligibility.expiresAt when a date is given, never written.

Legacy mapping (batch legacy-2026-10-05): episodeId <game>-legacy-<nnn> from epNN,
format scalar=progressive-clues, continuum=head-to-head, whenabouts=guess-the-year,
tectonic=missing-country; difficulty approachable; when the catalogue answer is not a
choice label (tectonic "Mongolia · Eastern Asia"), the longest choice label contained in
it becomes the answer and the catalogue answer an alias.
"""
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time

# In the repo the shared contract lives in <repo>/contract; on the Pi the installer copies it next to this file.
_CONTRACT = Path(__file__).resolve().parents[2] / 'contract'
if _CONTRACT.is_dir() and str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))
import library_contract as lc  # noqa: E402

UTC = dt.timezone.utc
FREE_SPACE_RESERVE = 2_000_000_000
CHUNK = 65536
CAPS = {'video': lc.MAX_VIDEO_BYTES, 'cover': lc.MAX_COVER_BYTES, 'batch': lc.MAX_BATCH_JSON_BYTES}
LEGACY_BATCH = 'legacy-2026-10-05'
LEGACY_FORMATS = {'scalar': 'progressive-clues', 'continuum': 'head-to-head',
                  'whenabouts': 'guess-the-year', 'tectonic': 'missing-country'}
FILE_NAME = re.compile(r'(videos|covers)/([a-z0-9-]{1,120})\.(mp4|jpg)')
OPEN_STATUSES = ('awaiting_files', 'reviewable', 'invalid')

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches(batch_id TEXT PRIMARY KEY, origin TEXT NOT NULL,
  batch_json TEXT NOT NULL, batch_json_sha256 TEXT NOT NULL, created_at TEXT, imported_at TEXT NOT NULL,
  warnings TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS batch_documents(sha256 TEXT PRIMARY KEY, batch_id TEXT NOT NULL, origin TEXT NOT NULL,
  raw TEXT NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS episodes(episode_id TEXT NOT NULL, revision INTEGER NOT NULL, batch_id TEXT NOT NULL,
  question_id TEXT NOT NULL, game TEXT NOT NULL, format TEXT, difficulty TEXT,
  metadata TEXT NOT NULL, metadata_sha256 TEXT NOT NULL, video_sha256 TEXT NOT NULL, cover_sha256 TEXT,
  status TEXT NOT NULL, problems TEXT NOT NULL DEFAULT '[]', imported_at TEXT NOT NULL,
  PRIMARY KEY(episode_id, revision));
CREATE INDEX IF NOT EXISTS episodes_batch ON episodes(batch_id);
CREATE INDEX IF NOT EXISTS episodes_video ON episodes(video_sha256);
CREATE INDEX IF NOT EXISTS episodes_question ON episodes(question_id);
CREATE TABLE IF NOT EXISTS videos(sha256 TEXT PRIMARY KEY, path TEXT NOT NULL, bytes INTEGER NOT NULL,
  measured TEXT NOT NULL, platforms TEXT NOT NULL, legacy INTEGER NOT NULL DEFAULT 0, registered_at TEXT NOT NULL,
  cover_sha256 TEXT);
CREATE TABLE IF NOT EXISTS covers(sha256 TEXT PRIMARY KEY, path TEXT NOT NULL, bytes INTEGER NOT NULL,
  extracted INTEGER NOT NULL DEFAULT 0, registered_at TEXT);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, episode_id TEXT, revision INTEGER, action TEXT,
  reviewer TEXT, at TEXT, video_sha256 TEXT, cover_sha256 TEXT, metadata_sha256 TEXT, caption_sha256 TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS approvals_episode ON approvals(episode_id, revision);
CREATE TABLE IF NOT EXISTS drafts(sha256 TEXT PRIMARY KEY, created_at TEXT NOT NULL, base_manifest_sha256 TEXT,
  body TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manifests(sha256 TEXT PRIMARY KEY, draft_sha256 TEXT, approved_at TEXT, video_hashes TEXT);
CREATE TABLE IF NOT EXISTS deletions(id INTEGER PRIMARY KEY, episode_id TEXT NOT NULL, revision INTEGER NOT NULL,
  batch_id TEXT, question_id TEXT, game TEXT, at TEXT NOT NULL, bytes_freed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS archives(video_sha256 TEXT PRIMARY KEY, at TEXT NOT NULL, bytes_freed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS feedback(episode_id TEXT NOT NULL, revision INTEGER NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
  note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL CHECK(status IN ('open','used')), updated_at TEXT NOT NULL,
  PRIMARY KEY(episode_id, revision));
CREATE TABLE IF NOT EXISTS batch_notes(batch_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('brief','retro')),
  text TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, uploaded_at TEXT NOT NULL,
  PRIMARY KEY(batch_id, kind));
"""


class UploadError(ValueError):
    """Upload refused or interrupted; the message is shown to the owner as is."""


def stamp(now):
    return now.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def _dirs(state):
    library = Path(state)/'library'
    for d in (library, library/'objects', library/'covers', library/'.incoming'):
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(d, 0o700)
    return library


def open_index(state):
    library = _dirs(state)
    path = library/'index.sqlite3'
    if not path.exists():
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    os.chmod(path, 0o600)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.executescript(SCHEMA)
    return db


# ---------- streaming upload core ----------

def receive(stream, length, state, *, cap, expected_sha256=None, expected_bytes=None, reserve=None):
    """Stream exactly `length` bytes to library/.incoming/<random>.part; returns (sha256, part)."""
    if not isinstance(length, int) or isinstance(length, bool):
        raise UploadError('The upload had no size (Content-Length); try again.')
    if length <= 0:
        raise UploadError('The file is empty.')
    if length > cap:
        raise UploadError(f'The file is too large: {length:,} bytes, the limit is {cap:,}.')
    if expected_bytes is not None and length != expected_bytes:
        raise UploadError(f'The file is {length:,} bytes but batch.json expects {expected_bytes:,}; choose the file from the same batch folder.')
    incoming = Path(state)/'library'/'.incoming'
    incoming.mkdir(parents=True, exist_ok=True, mode=0o700)
    reserve = FREE_SPACE_RESERVE if reserve is None else reserve
    if shutil.disk_usage(incoming).free < length + reserve:
        raise UploadError('The Pi is low on storage; free some space before uploading.')
    part = incoming/(secrets.token_hex(16)+'.part')
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    digest, remaining = hashlib.sha256(), length
    try:
        with os.fdopen(fd, 'wb') as out:
            while remaining:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    raise UploadError('The upload stopped before the whole file arrived; choose the file again.')
                if len(chunk) > remaining:
                    raise UploadError('The upload sent more data than announced.')
                digest.update(chunk)
                out.write(chunk)
                remaining -= len(chunk)
            out.flush()
            os.fsync(out.fileno())
        sha = digest.hexdigest()
        if expected_sha256 is not None and sha != expected_sha256:
            raise UploadError("This file's content doesn't match batch.json; choose the file from the same batch folder.")
        return sha, part
    except UploadError:
        part.unlink(missing_ok=True)
        raise
    except (OSError, ValueError):
        part.unlink(missing_ok=True)
        raise UploadError('The upload was interrupted; choose the file again.') from None
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def cleanup_incoming(state, max_age_hours=6, all_files=False):
    incoming = Path(state)/'library'/'.incoming'
    if not incoming.is_dir():
        return 0
    cutoff = time.time() - max_age_hours*3600
    removed = 0
    for part in incoming.glob('*.part'):
        try:
            if all_files or part.stat().st_mtime < cutoff:
                part.unlink()
                removed += 1
        except FileNotFoundError:
            pass
    return removed


# ---------- helpers ----------

def frame_grab(video_path, out_path):
    """One-frame cover grab (no rendering). Single-threaded to fit the UI unit's MemoryMax on a Pi Zero."""
    result = subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-threads', '1', '-ss', '1', '-i', str(video_path),
                             '-frames:v', '1', '-filter_threads', '1', '-vf', 'scale=540:-2', '-q:v', '4',
                             # Explicit format: the temporary output name ends in .part.
                             '-c:v', 'mjpeg', '-f', 'image2', '-update', '1', str(out_path)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    if result.returncode or not Path(out_path).is_file():
        raise ValueError('ffmpeg could not extract a frame')


def probe(path):
    return lc.run_ffprobe(path)


def _plain(items, episodes=()):
    out = []
    for item in items:
        path = item['path']
        m = re.match(r'episodes\[(\d+)\]\.?(.*)', path)
        if m:
            i = int(m.group(1))
            name = episodes[i].get('episodeId') if i < len(episodes) and isinstance(episodes[i], dict) else None
            path = f"{name or f'episode {i+1}'}" + (f' · {m.group(2)}' if m.group(2) else '')
        elif path.startswith('episode.'):
            path = path[len('episode.'):]
        elif path.startswith('batch.'):
            path = path[len('batch.'):]
        out.append(f"{path}: {item['message']}")
    return out


def _platforms_json(eligibility):
    return {p: {'eligible': ok, 'reason': reason} for p, (ok, reason) in eligibility.items()}


def _video(index, sha):
    return index.execute('SELECT * FROM videos WHERE sha256=?', (sha,)).fetchone() if sha else None


def _cover(index, sha):
    return index.execute('SELECT * FROM covers WHERE sha256=?', (sha,)).fetchone() if sha else None


def _present(state, row):
    return row is not None and (Path(state)/row['path']).is_file()


def _origin(index, batch_id):
    row = index.execute('SELECT origin FROM batches WHERE batch_id=?', (batch_id,)).fetchone()
    return row['origin'] if row else 'mac'


def _media_problems(meta, video_row, cover_row, origin):
    m = json.loads(video_row['measured'])
    problems = list(lc.media_errors(m, legacy=origin == 'legacy'))
    if origin == 'mac':
        report = lc.Report()
        lc.compare_measured(report, 'video', meta['video'], m)
        problems += [f"video {e['path'].split('.')[-1]}: {e['message']}" for e in report.errors]
        if video_row['bytes'] != meta['video']['bytes']:
            problems.append('video: file size differs from batch.json')
        if cover_row['bytes'] != meta['cover']['bytes']:
            problems.append('cover: file size differs from batch.json')
    return problems


def _refresh(index, state, episode_id, revision):
    """Recompute an open episode's status from the objects on the Pi."""
    row = index.execute('SELECT * FROM episodes WHERE episode_id=? AND revision=?', (episode_id, revision)).fetchone()
    if row is None or row['status'] != 'awaiting_files':
        return row['status'] if row else None
    v, c = _video(index, row['video_sha256']), _cover(index, row['cover_sha256'])
    if not (_present(state, v) and _present(state, c)):
        return 'awaiting_files'
    problems = _media_problems(json.loads(row['metadata']), v, c, _origin(index, row['batch_id']))
    status = 'invalid' if problems else 'reviewable'
    index.execute('UPDATE episodes SET status=?, problems=? WHERE episode_id=? AND revision=?',
                  (status, json.dumps(problems), episode_id, revision))
    return status


def _insert_episode(index, batch_id, meta, status, problems, now, cover_sha=None):
    view = lc.episode_view(meta)
    index.execute('INSERT OR REPLACE INTO episodes(episode_id,revision,batch_id,question_id,game,format,difficulty,metadata,'
                  'metadata_sha256,video_sha256,cover_sha256,status,problems,imported_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (meta['episodeId'], meta['revision'], batch_id, view['contentId'], view['group'], meta.get('format'),
                   view['difficulty'], json.dumps(meta, ensure_ascii=False, sort_keys=True), lc.episode_metadata_hash(meta),
                   meta['video']['sha256'], cover_sha if cover_sha is not None else meta['cover']['sha256'],
                   status, json.dumps(problems), stamp(now)))


def _record_batch(index, batch_id, origin, raw_text, created_at, warnings, now):
    digest = hashlib.sha256(raw_text.encode()).hexdigest()
    index.execute('INSERT OR IGNORE INTO batch_documents(sha256,batch_id,origin,raw,imported_at) VALUES(?,?,?,?,?)',
                  (digest, batch_id, origin, raw_text, stamp(now)))
    index.execute('INSERT INTO batches(batch_id,origin,batch_json,batch_json_sha256,created_at,imported_at,warnings) '
                  'VALUES(?,?,?,?,?,?,?) ON CONFLICT(batch_id) DO UPDATE SET batch_json=excluded.batch_json,'
                  'batch_json_sha256=excluded.batch_json_sha256,created_at=excluded.created_at,warnings=excluded.warnings',
                  (batch_id, origin, raw_text, digest, created_at, stamp(now), json.dumps(warnings)))


def _store(part, target):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        part.unlink(missing_ok=True)
    else:
        os.replace(part, target)


# ---------- batch import ----------

def import_batch_json(index, state, raw_bytes, now):
    """`problems`/`warnings` are plain strings; `problemItems`/`warningItems` carry the same items as
    {code, path, message} with batch.json paths, and `merge` the per-episode outcome."""
    result = {'batchId': None, 'status': 'rejected', 'expected': [], 'problems': [], 'warnings': [], 'alreadyImported': [],
              'merge': [], 'problemItems': [], 'warningItems': []}

    def refuse(code, path, message):
        result['problems'].append(message)
        result['problemItems'].append({'code': code, 'path': path, 'message': message})
        return result
    if len(raw_bytes) > lc.MAX_BATCH_JSON_BYTES:
        return refuse('size', 'batch.json', 'batch.json is larger than 1 MB.')
    try:
        raw_text = raw_bytes.decode('utf-8')
        data = json.loads(raw_text)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return refuse('json', 'batch.json', "This isn't a readable batch.json (invalid JSON).")
    report = lc.validate_document(data, now=now, origin='mac')
    episodes = data.get('episodes') if isinstance(data, dict) and isinstance(data.get('episodes'), list) else []
    result['warnings'] = [e['message'] for e in report.warnings]
    result['warningItems'] = list(report.warnings)
    if isinstance(data, dict) and isinstance(data.get('batchId'), str):
        result['batchId'] = data['batchId']
    if not report.ok:
        result['problems'] = _plain(report.errors, episodes)
        result['problemItems'] = list(report.errors)
        return result
    batch_id = data['batchId']
    existing = index.execute('SELECT origin FROM batches WHERE batch_id=?', (batch_id,)).fetchone()
    if existing and existing['origin'] != 'mac':
        return refuse('reserved', 'batchId', f'{batch_id} is reserved for a Pi-created batch; choose another batchId.')
    new, problems = [], []
    for i, e in enumerate(episodes):
        eid, rev = e['episodeId'], e['revision']
        rows = index.execute('SELECT revision, video_sha256, cover_sha256, metadata_sha256 FROM episodes WHERE episode_id=?',
                             (eid,)).fetchall()
        same = next((r for r in rows if r['revision'] == rev), None)
        latest = max((r['revision'] for r in rows), default=0)
        merge = {'episodeId': eid, 'revision': rev, 'outcome': None, 'message': None}
        result['merge'].append(merge)
        if same and (same['video_sha256'], same['cover_sha256'], same['metadata_sha256']) == (
                e['video']['sha256'], e['cover']['sha256'], lc.episode_metadata_hash(e)):
            result['alreadyImported'].append(eid)
            merge['outcome'] = 'already-imported'
        elif same or rev < latest:
            message = (f'{eid}: revision {rev} differs from what is already on the Pi (latest revision {latest}). '
                       f'Bump the revision to {latest+1} on the Mac and finalize again.')
            problems.append(message)
            result['problemItems'].append({'code': 'revision', 'path': f'episodes[{i}].revision', 'message': message})
            merge.update(outcome='rejected', message=message)
        else:
            new.append(e)
            merge['outcome'] = 'new-revision' if rows else 'added'
    if problems:
        result['problems'] = problems
        for merge in result['merge']:
            if merge['outcome'] != 'rejected':
                merge.update(outcome='rejected', message='Not imported: another episode in this batch.json was refused.')
        return result
    with index:
        if new or not existing:
            _record_batch(index, batch_id, 'mac', raw_text, data['createdAt'], result['warnings'], now)
        for e in new:
            _insert_episode(index, batch_id, e, 'awaiting_files', [], now)
        for e in new:
            _refresh(index, state, e['episodeId'], e['revision'])
    result['status'] = 'imported' if new else 'already imported'
    for e in episodes:
        for kind, table in (('video', _video), ('cover', _cover)):
            result['expected'].append({'file': e[kind]['file'], 'kind': kind, 'episodeId': e['episodeId'],
                                       'revision': e['revision'], 'sha256': e[kind]['sha256'], 'bytes': e[kind]['bytes'],
                                       'present': _present(state, table(index, e[kind]['sha256']))})
    return result


def accept_batch_file(index, state, batch_id, relative_name, stream, length, probe, frame_grabber, now):
    """One videos/<episodeId>.mp4 or covers/<episodeId>.jpg of an imported batch."""
    state = Path(state)
    result = {'file': relative_name if isinstance(relative_name, str) else None, 'ok': False, 'problems': []}
    m = FILE_NAME.fullmatch(relative_name) if isinstance(relative_name, str) else None
    if not m or (m.group(1) == 'videos') != (m.group(3) == 'mp4'):
        result['problems'] = ['Only videos/<episodeId>.mp4 and covers/<episodeId>.jpg from the batch folder can be uploaded.']
        return result
    kind = 'video' if m.group(1) == 'videos' else 'cover'
    row = index.execute('SELECT * FROM episodes WHERE batch_id=? AND episode_id=? ORDER BY revision DESC LIMIT 1',
                        (batch_id, m.group(2))).fetchone()
    if row is None or _origin(index, batch_id) != 'mac':
        result['problems'] = [f'{relative_name} is not part of batch {batch_id}; add its batch.json first.']
        return result
    meta = json.loads(row['metadata'])
    expected = meta[kind]
    result.update(episodeId=row['episode_id'], revision=row['revision'], kind=kind, sha256=expected['sha256'],
                  expectedBytes=expected['bytes'])
    existing = (_video if kind == 'video' else _cover)(index, expected['sha256'])
    try:
        sha, part = receive(stream, length, state, cap=CAPS[kind], expected_sha256=expected['sha256'],
                            expected_bytes=expected['bytes'])
    except UploadError as error:
        result['problems'] = [str(error)]
        return result
    target = state/'library'/('objects' if kind == 'video' else 'covers')/(sha+('.mp4' if kind == 'video' else '.jpg'))
    if _present(state, existing):
        part.unlink(missing_ok=True)
        result['alreadyPresent'] = True
    else:
        problems = []
        if kind == 'video':
            try:
                measured = lc.measure(probe(part), part)
            except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
                measured = None
                problems.append("The video couldn't be read (ffprobe failed).")
            if measured:
                problems += lc.media_errors(measured)
                report = lc.Report()
                lc.compare_measured(report, 'video', expected, measured)
                problems += [f"video {e['path'].split('.')[-1]}: {e['message']}" for e in report.errors]
        elif not lc.is_jpeg(part):
            problems.append('The cover must be a JPEG image.')
        if problems:
            part.unlink(missing_ok=True)
            with index:
                index.execute("UPDATE episodes SET status='invalid', problems=? WHERE episode_id=? AND revision=? AND status IN (?,?,?)",
                              (json.dumps(problems), row['episode_id'], row['revision'], *OPEN_STATUSES))
            result.update(problems=problems, status='invalid')
            return result
        _store(part, target)
        rel = str(target.relative_to(state))
        with index:
            if kind == 'video':
                index.execute('INSERT OR REPLACE INTO videos(sha256,path,bytes,measured,platforms,legacy,registered_at,cover_sha256) '
                              'VALUES(?,?,?,?,?,0,?,(SELECT cover_sha256 FROM videos WHERE sha256=?))',
                              (sha, rel, length, json.dumps(measured), json.dumps(_platforms_json(lc.platform_eligibility(measured))),
                               stamp(now), sha))
                index.execute('DELETE FROM archives WHERE video_sha256=?', (sha,))   # re-uploaded after removal
            else:
                index.execute('INSERT OR REPLACE INTO covers(sha256,path,bytes,extracted,registered_at) VALUES(?,?,?,0,?)',
                              (sha, rel, length, stamp(now)))
        result['alreadyPresent'] = False
    with index:
        for other in index.execute("SELECT episode_id, revision FROM episodes WHERE status='awaiting_files' AND "
                                   '(video_sha256=? OR cover_sha256=?)', (sha, sha)).fetchall():
            _refresh(index, state, other['episode_id'], other['revision'])
    current = index.execute('SELECT status, problems FROM episodes WHERE episode_id=? AND revision=?',
                            (row['episode_id'], row['revision'])).fetchone()
    result.update(ok=True, status=current['status'], problems=json.loads(current['problems']))
    return result


# ---------- covers from frames ----------

def _extract_cover(index, state, video_sha, video_path, frame_grabber, now):
    """Returns (cover_sha, problem). Reuses an earlier extraction for the same video."""
    state = Path(state)
    v = _video(index, video_sha)
    if v is not None and v['cover_sha256'] and _present(state, _cover(index, v['cover_sha256'])):
        return v['cover_sha256'], None
    covers = state/'library'/'covers'
    covers.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = state/'library'/'.incoming'/(secrets.token_hex(16)+'.jpg.part')
    temp.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        frame_grabber(video_path, temp)
        if not temp.is_file() or not lc.is_jpeg(temp):
            raise ValueError('not a JPEG')
        sha, size = lc.file_digest(temp)
        if size > lc.MAX_COVER_BYTES:
            raise ValueError('cover too large')
        os.chmod(temp, 0o600)
        target = covers/f'{sha}.jpg'
        _store(temp, target)
    except (ValueError, OSError, subprocess.SubprocessError):
        temp.unlink(missing_ok=True)
        return None, "A cover frame couldn't be extracted from the video."
    with index:
        index.execute('INSERT OR IGNORE INTO covers(sha256,path,bytes,extracted,registered_at) VALUES(?,?,?,1,?)',
                      (sha, str(target.relative_to(state)), size, stamp(now)))
        index.execute('UPDATE videos SET cover_sha256=? WHERE sha256=?', (sha, video_sha))
    return sha, None


# ---------- legacy registration ----------

def _legacy_answer(ep, labels):
    answer = ep.get('answer') or ''
    norm = lc.normalize(answer)
    if not labels or norm in {lc.normalize(x) for x in labels}:
        return answer, []
    padded = f' {norm} '
    inside = [x for x in labels if lc.normalize(x) and f' {lc.normalize(x)} ' in padded]
    if not inside:
        return answer, []
    best = max(inside, key=lambda x: len(lc.normalize(x)))
    return best, [answer]


def legacy_episode(ep, video_sha, measured, video_bytes, cover_sha, cover_bytes):
    """Contract-shaped episode for one legacy catalogue entry (captions from prepare.caption)."""
    from prepare import caption
    n = int(re.fullmatch(r'ep(\d+)', ep['id']).group(1))
    game = ep['game']
    episode_id = f'{game}-legacy-{n:03d}'
    question = [str(q) for q in ep.get('question') or []]
    hook = question[0] if question else 'Guess along.'
    labels = [str(c) for c in ep.get('choices') or []]
    answer, aliases = _legacy_answer(ep, labels)
    if ep.get('answerId') and ep['answerId'] not in aliases:
        aliases.append(ep['answerId'])
    choices = [{'key': k, 'label': v} for k, v in zip('ABCD', labels)] if 2 <= len(labels) <= 4 else None
    captions = {p: caption(ep, p, 'self-contained')[0] for p in lc.CAPTION_PLATFORMS}
    url = caption(ep, 'bluesky', 'self-contained')[1]
    if len(captions['bluesky']) > lc.CAPTION_LIMITS['bluesky']:
        # Same short form the legacy preparer publishes on Bluesky.
        captions['bluesky'] = '\n'.join([' '.join(question), 'Archive challenge. Guess along; reveal in this video.', url])
    poll = ({'question': hook, 'options': labels}
            if choices and all(1 <= len(x) <= lc.POLL_OPTION_LIMIT for x in labels) else None)
    verification = ep.get('verification') or {}
    retrieved = (verification.get('verifiedAt') or '')[:10]
    m = measured or {}
    return {
        'episodeId': episode_id, 'questionId': ep['id'], 'revision': 1, 'game': game,
        'format': LEGACY_FORMATS.get(game, 'progressive-clues'), 'language': 'en', 'difficulty': 'approachable',
        'styleId': LEGACY_BATCH, 'experimentId': None, 'variantId': None,
        'creative': {'hook': hook, 'question': hook, 'clues': question[1:], 'choices': choices, 'answer': answer,
                     'answerAliases': aliases, 'explanation': str(ep.get('reveal') or '')},
        'evidence': {'sources': [{'title': 'Scalar game data (' + str((ep.get('provenance') or {}).get('source') or 'catalogue') + ')',
                                  'url': lc.SITE + ep.get('deepLink', '/'),
                                  'retrieved': retrieved if lc.DATE.fullmatch(retrieved) else '2026-10-05'}],
                     'checks': {'uniqueAnswer': verification.get('status') == 'verified',
                                'sourceHash': verification.get('sourceHash')},
                     'reviewer': 'legacy-catalogue'},
        'music': None,
        'video': {'file': f'videos/{episode_id}.mp4', 'sha256': video_sha, 'bytes': video_bytes or 1,
                  'durationSeconds': m.get('durationSeconds') or 1, 'width': m.get('width') or 1080,
                  'height': m.get('height') or 1920, 'fps': m.get('fps') or '30/1',
                  'videoCodec': m.get('videoCodec') or 'h264', 'audioCodec': m.get('audioCodec')},
        'cover': {'file': f'covers/{episode_id}.jpg', 'sha256': cover_sha or '0'*64, 'bytes': cover_bytes or 1},
        'publication': {'deepLink': ep.get('deepLink', '/'), 'utmCampaign': 'social_puzzles_v1', 'captions': captions,
                        'youtube': {'title': ' '.join(question)[:95], 'description': caption(ep, 'youtube', 'self-contained')[0]},
                        'altText': f'Animated quiz: {hook} The answer is revealed at the end.',
                        'hashtags': ['#geography', '#puzzles', '#scalargame'], 'credits': [], 'poll': poll,
                        'firstComment': None, 'answerReply': None},
        'eligibility': {'status': 'qa-passed', 'notBefore': None, 'reviewBy': None, 'expiresAt': None},
    }


def register_legacy(index, state, probe, frame_grabber, now):
    """Register STATE/catalog.json + site/clips in place as batch legacy-2026-10-05. Idempotent."""
    state = Path(state)
    result = {'batchId': LEGACY_BATCH, 'registered': [], 'already': [], 'invalid': [], 'problems': []}
    catalog_path = state/'catalog.json'
    if not catalog_path.is_file() or catalog_path.is_symlink():
        result['problems'].append('No legacy catalogue (catalog.json) on the Pi.')
        return result
    raw = catalog_path.read_bytes()
    try:
        catalog = json.loads(raw)
        episodes, clips = catalog['episodes'], catalog['clips']
    except (ValueError, KeyError, TypeError):
        result['problems'].append("catalog.json couldn't be read.")
        return result
    site = (state/'site').resolve()
    built = []
    for ep in sorted(episodes, key=lambda e: str(e.get('id'))):
        if not isinstance(ep, dict) or not re.fullmatch(r'ep\d+', str(ep.get('id'))) or ep.get('game') not in lc.GAMES:
            result['problems'].append(f"Catalogue entry {ep.get('id') if isinstance(ep, dict) else '?'} isn't a recognised episode; skipped.")
            continue
        episode_id = f"{ep['game']}-legacy-{int(ep['id'][2:]):03d}"
        row = index.execute('SELECT status FROM episodes WHERE episode_id=? AND revision=1', (episode_id,)).fetchone()
        if row is not None and row['status'] != 'invalid':
            result['already'].append(episode_id)
            built.append(json.loads(index.execute('SELECT metadata FROM episodes WHERE episode_id=? AND revision=1',
                                                  (episode_id,)).fetchone()['metadata']))
            continue
        clip = clips.get(ep['id']+':self') if isinstance(clips, dict) else None
        declared = clip.get('sha256') if isinstance(clip, dict) else None
        rel = clip.get('path') if isinstance(clip, dict) else None
        problems, measured, size, cover_sha, cover_bytes = [], None, None, None, None
        if not isinstance(declared, str) or not lc.SHA256.fullmatch(declared):
            problems.append('The catalogue has no valid hash for this clip.')
            declared = declared if isinstance(declared, str) else ''
        if not isinstance(rel, str) or not re.fullmatch(r'clips/[A-Za-z0-9._-]+\.mp4', rel):
            problems.append('The catalogue clip path is not under site/clips.')
        if not problems:
            path = state/'site'/rel
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(site):
                problems.append(f'site/{rel} is missing.')
            else:
                digest, size = lc.file_digest(path)
                if digest != declared:
                    problems.append(f"site/{rel} doesn't match the catalogue hash; it was changed after the catalogue was approved.")
        if not problems:
            v = _video(index, declared)
            if v is not None:
                measured = json.loads(v['measured'])
            else:
                try:
                    measured = lc.measure(probe(path), path)
                except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
                    problems.append(f"site/{rel} couldn't be read (ffprobe failed).")
            if measured is not None:
                hard = lc.media_errors(measured, legacy=True)
                problems += hard
                if not hard and v is None:
                    with index:
                        index.execute('INSERT OR IGNORE INTO videos(sha256,path,bytes,measured,platforms,legacy,registered_at) '
                                      'VALUES(?,?,?,?,?,1,?)',
                                      (declared, f'site/{rel}', size, json.dumps(measured),
                                       json.dumps(_platforms_json(lc.platform_eligibility(measured, legacy=True))), stamp(now)))
        if not problems:
            cover_sha, problem = _extract_cover(index, state, declared, path, frame_grabber, now)
            if problem:
                problems.append(problem)
            else:
                cover_bytes = _cover(index, cover_sha)['bytes']
        meta = legacy_episode(ep, declared, measured, size, cover_sha, cover_bytes)
        if not problems:
            report = lc.Report()
            lc.validate_episode(meta, 'episode', {}, now.astimezone(UTC).date(), report, origin='pi')
            problems += _plain(report.errors)
        with index:
            _insert_episode(index, LEGACY_BATCH, meta, 'invalid' if problems else 'reviewable', problems, now, cover_sha)
        built.append(meta)
        (result['invalid'] if problems else result['registered']).append(
            {'episodeId': episode_id, 'problems': problems} if problems else episode_id)
    document = {'schemaVersion': lc.SCHEMA_VERSION, 'batchId': LEGACY_BATCH, 'origin': 'legacy',
                'catalogSha256': hashlib.sha256(raw).hexdigest(), 'createdAt': catalog.get('generatedAt'),
                'episodes': built}
    created = catalog.get('generatedAt') if isinstance(catalog.get('generatedAt'), str) else None
    with index:
        _record_batch(index, LEGACY_BATCH, 'legacy', json.dumps(document, ensure_ascii=False, sort_keys=True), created,
                      ['Already published on 2026-10-05; questions posted then stay excluded on those accounts.'], now)
    return result


# ---------- content approval ----------

def _item(item):
    if not isinstance(item, dict) or not isinstance(item.get('episodeId'), str):
        return None, None
    rev = item.get('revision')
    return item['episodeId'], rev if isinstance(rev, int) and not isinstance(rev, bool) else None


def _hashes(index, state, row):
    """Current (video, cover, metadata, caption) hashes; None and a problem when files changed."""
    meta = json.loads(row['metadata'])
    if lc.episode_metadata_hash(meta) != row['metadata_sha256']:
        return None, 'Its details changed since import; re-import it as a new revision.'
    v, c = _video(index, row['video_sha256']), _cover(index, row['cover_sha256'])
    if not (_present(state, v) and _present(state, c)):
        return None, 'Its video or cover file is missing on the Pi.'
    if lc.file_digest(Path(state)/v['path'])[0] != row['video_sha256'] or lc.file_digest(Path(state)/c['path'])[0] != row['cover_sha256']:
        return None, 'Its video or cover file changed on disk; it cannot be approved.'
    return (row['video_sha256'], row['cover_sha256'], row['metadata_sha256'], lc.caption_hash(meta)), None


def _decide(index, state, items, reviewer, now, note, action):
    results = []
    reviewer = reviewer.strip()[:64] if isinstance(reviewer, str) and reviewer.strip() else None
    allowed = ('reviewable', 'withdrawn') if action == 'approve' else ('approved', 'reviewable')
    for item in items if isinstance(items, list) else []:
        eid, rev = _item(item)
        entry = {'episodeId': eid, 'revision': rev, 'ok': False, 'problem': None}
        results.append(entry)
        if reviewer is None:
            entry['problem'] = 'Say who is reviewing.'
            continue
        row = index.execute('SELECT * FROM episodes WHERE episode_id=? AND revision=?', (eid, rev)).fetchone() if eid and rev else None
        if row is None:
            entry['problem'] = 'No such video revision in the library.'
            continue
        if row['status'] not in allowed:
            entry['problem'] = {'approved': 'Already approved.', 'withdrawn': 'Already withdrawn.',
                                'awaiting_files': 'Its video or cover has not been uploaded yet.',
                                'invalid': 'It failed checks; fix it on the Mac and import a new revision.'}.get(
                                    row['status'], f"It is {row['status']} and can't be {action}d.")
            continue
        hashes, problem = _hashes(index, state, row) if action == 'approve' else (
            (row['video_sha256'], row['cover_sha256'], row['metadata_sha256'], lc.caption_hash(json.loads(row['metadata']))), None)
        if problem:
            entry['problem'] = problem
            continue
        with index:
            cursor = index.execute('INSERT INTO approvals(episode_id,revision,action,reviewer,at,video_sha256,cover_sha256,'
                                   'metadata_sha256,caption_sha256,note) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                   (eid, rev, action, reviewer, stamp(now), *hashes, note))
            index.execute('UPDATE episodes SET status=? WHERE episode_id=? AND revision=?',
                          ('approved' if action == 'approve' else 'withdrawn', eid, rev))
        entry.update(ok=True, approvalId=cursor.lastrowid)
    return {'results': results, 'count': sum(r['ok'] for r in results)}


def approve(index, items, reviewer, now, state=None, note=None):
    """Approve reviewable revisions [{episodeId, revision}]. `state` locates objects (default: the index's STATE)."""
    return _decide(index, state or _state_of(index), items, reviewer, now, note, 'approve')


def withdraw(index, items, reviewer, now, note=None):
    return _decide(index, _state_of(index), items, reviewer, now, note, 'withdraw')


def _state_of(index):
    path = index.execute('PRAGMA database_list').fetchone()['file']
    return Path(path).parent.parent


# ---------- manifests and deletion ----------

def record_manifest(index, sha, draft_sha, video_hashes, approved_at):
    with index:
        index.execute('INSERT OR IGNORE INTO manifests(sha256,draft_sha256,approved_at,video_hashes) VALUES(?,?,?,?)',
                      (sha, draft_sha, approved_at, json.dumps(sorted(set(video_hashes)))))


def in_manifest(index, video_sha):
    return any(video_sha in json.loads(r['video_hashes'] or '[]') for r in index.execute('SELECT video_hashes FROM manifests'))


def _manifest_file_hashes(state):
    found = set()
    folder = Path(state)/'manifests'
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        if path.name.endswith('.verification.json') or path.is_symlink():
            continue
        try:
            jobs = json.loads(path.read_bytes()).get('jobs') or []
        except (OSError, ValueError, AttributeError):
            continue
        for job in jobs:
            media = ((job or {}).get('payload') or {}).get('media') if isinstance(job, dict) else None
            if isinstance(media, dict) and isinstance(media.get('sha256'), str):
                found.add(media['sha256'])
    return found


def delete_episode(index, state, episode_id, revision, now=None):
    """Delete a never-scheduled revision; the deletion itself is recorded (deletions) for the activity feed."""
    state = Path(state)
    row = index.execute('SELECT * FROM episodes WHERE episode_id=? AND revision=?', (episode_id, revision)).fetchone()
    if row is None:
        return {'ok': False, 'problem': 'No such video revision in the library.'}
    if in_manifest(index, row['video_sha256']) or row['video_sha256'] in _manifest_file_hashes(state):
        return {'ok': False, 'problem': 'This video is part of an approved schedule, so it is kept as a permanent record. '
                                        'Withdraw it instead to stop future use.'}
    removed = []
    with index:
        index.execute('DELETE FROM episodes WHERE episode_id=? AND revision=?', (episode_id, revision))
        for table, column, sha in (('videos', 'video_sha256', row['video_sha256']), ('covers', 'cover_sha256', row['cover_sha256'])):
            if not sha or index.execute(f'SELECT 1 FROM episodes WHERE {column}=?', (sha,)).fetchone():
                continue
            if table == 'covers' and index.execute('SELECT 1 FROM videos WHERE cover_sha256=?', (sha,)).fetchone():
                continue
            obj = index.execute(f'SELECT path FROM {table} WHERE sha256=?', (sha,)).fetchone()
            if obj is None:
                continue
            index.execute(f'DELETE FROM {table} WHERE sha256=?', (sha,))
            if obj['path'].startswith('library/'):
                removed.append(obj['path'])
        if not index.execute('SELECT 1 FROM episodes WHERE batch_id=?', (row['batch_id'],)).fetchone():
            index.execute('DELETE FROM batches WHERE batch_id=?', (row['batch_id'],))
        sizes = 0
        for rel in removed:
            with contextlib.suppress(OSError):
                sizes += (state/rel).stat().st_size
        index.execute('INSERT INTO deletions(episode_id,revision,batch_id,question_id,game,at,bytes_freed) VALUES(?,?,?,?,?,?,?)',
                      (episode_id, revision, row['batch_id'], row['question_id'], row['game'],
                       stamp(now or dt.datetime.now(UTC)), sizes))
    for rel in removed:
        (state/rel).unlink(missing_ok=True)
    return {'ok': True, 'removedFiles': removed}


# ---------- removing posted videos (covers and records are kept) ----------

def archived(index, sha):
    return index.execute('SELECT * FROM archives WHERE video_sha256=?', (sha,)).fetchone() if sha else None


def _video_files(state, sha, video):
    """The Pi's copies of a library video: the object and its hard link (or copy) in the public site folder."""
    paths = [Path(state)/video['path']] if str(video['path']).startswith('library/') else []
    return paths + [Path(state)/'site'/'library'/f'{sha}.mp4']


def _freed(paths):
    """Bytes freed by unlinking all of `paths` (hard links share their data, so count each inode once)."""
    seen, total = set(), 0
    for path in paths:
        with contextlib.suppress(OSError):
            info = path.stat()
            if (info.st_dev, info.st_ino) not in seen:
                seen.add((info.st_dev, info.st_ino))
                total += info.st_size
    return total


def cleanup_candidates(index, state, ledger_rows, manifest, accounts):
    """Videos that can be removed from the Pi: posted (confirmed) at least once, every post that used them has
    finished (confirmed, failed or expired; nothing ready, sending, uncertain or blocked), and no job in the approved
    schedule still needs them. Legacy clips are never removed. `accounts` maps platform to its configured account id."""
    import ui_approval
    status = {row['id']: row['status'] for row in ledger_rows}
    used = {}
    for row in ledger_rows:
        try:
            sha = ((json.loads(row['payload']) or {}).get('media') or {}).get('sha256')
        except (ValueError, TypeError, AttributeError):
            continue
        if isinstance(sha, str):
            used.setdefault(sha, []).append(row)
    pending = set()
    for job in (manifest or {}).get('jobs') or []:
        sha = (((job or {}).get('payload') or {}).get('media') or {}).get('sha256')
        key = ui_approval.ledger_key(job.get('platform'), accounts.get(job.get('platform')), job.get('slot'))
        if sha and status.get(key) not in ui_approval.FINISHED:
            pending.add(sha)
    out = []
    for sha, rows in sorted(used.items()):
        if (sha in pending or any(r['status'] not in ui_approval.FINISHED for r in rows)
                or not any(r['status'] == 'confirmed' for r in rows)):
            continue
        video = _video(index, sha)
        if video is None or video['legacy'] or archived(index, sha):
            continue
        files = [p for p in _video_files(state, sha, video) if p.is_file()]
        if not files:
            continue
        episodes = [{'episodeId': e['episode_id'], 'revision': e['revision'], 'batchId': e['batch_id'], 'game': e['game']}
                    for e in index.execute('SELECT episode_id, revision, batch_id, game FROM episodes WHERE video_sha256=? '
                                           'ORDER BY episode_id, revision', (sha,))]
        out.append({'videoSha256': sha, 'bytes': _freed(files), 'episodes': episodes,
                    'postedOn': sorted({r['platform'] for r in rows if r['status'] == 'confirmed'})})
    return out


def archive_videos(index, state, shas, ledger_rows, manifest, accounts, now=None):
    """Remove the Pi's copies of posted videos; episodes, video records and covers stay. The removal is recorded
    first, so a removed video is never offered to the schedule generator again. Re-uploading the same file restores it."""
    state = Path(state)
    allowed = {c['videoSha256']: c for c in cleanup_candidates(index, state, ledger_rows, manifest, accounts)}
    removed, refused, freed = [], [], 0
    for sha in dict.fromkeys(shas):
        if sha not in allowed:
            refused.append(sha)
            continue
        files = [p for p in _video_files(state, sha, _video(index, sha)) if p.is_file()]
        size = _freed(files)
        with index:
            index.execute('INSERT OR REPLACE INTO archives(video_sha256,at,bytes_freed) VALUES(?,?,?)',
                          (sha, stamp(now or dt.datetime.now(UTC)), size))
        for path in files:
            path.unlink(missing_ok=True)
        removed.append(sha)
        freed += size
    return {'removed': removed, 'refused': refused, 'bytesFreed': freed}


# ---------- views ----------

def _date(value):
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _expired(meta, today):
    expires = (meta.get('eligibility') or {}).get('expiresAt')
    return bool(today and expires and _date(expires) < today)


def library_view(index, state, media_url, today=None):
    state = Path(state)
    today = _date(today) if today else None
    manifest_hashes = {h for r in index.execute('SELECT video_hashes FROM manifests') for h in json.loads(r['video_hashes'] or '[]')}
    manifest_hashes |= _manifest_file_hashes(state)
    groups = {}
    for r in index.execute('SELECT question_id, episode_id, revision FROM episodes ORDER BY episode_id, revision'):
        groups.setdefault(r['question_id'], []).append(f"{r['episode_id']} r{r['revision']}")
    batches = []
    for b in index.execute('SELECT * FROM batches ORDER BY imported_at DESC, batch_id'):
        episodes = []
        for row in index.execute('SELECT * FROM episodes WHERE batch_id=? ORDER BY episode_id, revision DESC', (b['batch_id'],)):
            meta = json.loads(row['metadata'])
            v, c = _video(index, row['video_sha256']), _cover(index, row['cover_sha256'])
            v_ok, c_ok = _present(state, v), _present(state, c)
            removed = archived(index, row['video_sha256'])
            m = json.loads(v['measured']) if v else {}
            approvals = [dict(a) for a in index.execute('SELECT id,action,reviewer,at,video_sha256,cover_sha256,metadata_sha256,'
                                                        'caption_sha256,note FROM approvals WHERE episode_id=? AND revision=? ORDER BY id',
                                                        (row['episode_id'], row['revision']))]
            publication = meta.get('publication') or {}
            view = lc.episode_view(meta)
            episodes.append({
                'episodeId': row['episode_id'], 'revision': row['revision'], 'questionId': row['question_id'],
                'game': row['game'], 'format': row['format'], 'difficulty': row['difficulty'],
                'schemaVersion': view['schemaVersion'], 'project': view['project'], 'engine': view['engine'],
                'route': view['route'], 'renderer': view['renderer'], 'models': view['models'], 'costUsd': view['costUsd'],
                'credits': view['credits'], 'disclosure': view['disclosure'], 'tags': view['tags'],
                'status': row['status'], 'expired': _expired(meta, today), 'problems': json.loads(row['problems']),
                'missing': [k for k, ok in (('video', v_ok or removed is not None), ('cover', c_ok)) if not ok],
                'videoRemovedAt': removed['at'] if removed else None,
                'measured': {'durationSeconds': m.get('durationSeconds'), 'bytes': v['bytes'] if v else None,
                             'width': m.get('width'), 'height': m.get('height'), 'fps': m.get('fps'),
                             'pixFmt': m.get('pixFmt'), 'audio': m.get('audioCodec'), 'fastStart': m.get('fastStart')} if v else None,
                'platforms': json.loads(v['platforms']) if v else None,
                'legacy': bool(v['legacy']) if v else False,
                'creative': view['creative'],
                'captions': publication.get('captions'), 'youtube': publication.get('youtube'),
                'poll': publication.get('poll'), 'firstComment': publication.get('firstComment'),
                'answerReply': publication.get('answerReply'), 'altText': publication.get('altText'),
                'hashtags': publication.get('hashtags'), 'eligibility': meta.get('eligibility'),
                'links': {p: lc.link_for(meta, p) for p in lc.LINK_PLATFORMS} if view['link'] else {},
                'videoSha256': row['video_sha256'], 'coverSha256': row['cover_sha256'],
                'metadataSha256': row['metadata_sha256'],
                'approvals': approvals, 'approval': approvals[-1] if approvals else None,
                'inManifest': row['video_sha256'] in manifest_hashes,
                'variants': [x for x in groups.get(row['question_id'], []) if x != f"{row['episode_id']} r{row['revision']}"],
                'videoUrl': media_url('videos', row['video_sha256']) if v_ok else None,
                'coverUrl': media_url('covers', row['cover_sha256']) if c_ok else None,
                'episode': meta, 'media': {**m, 'bytes': v['bytes']} if v else None,
            })
        try:
            generator = json.loads(b['batch_json']).get('generator')
        except (ValueError, AttributeError):
            generator = None
        batches.append({'batchId': b['batch_id'], 'origin': b['origin'], 'createdAt': b['created_at'],
                        'importedAt': b['imported_at'], 'warnings': json.loads(b['warnings']), 'episodes': episodes,
                        'batchJsonSha256': b['batch_json_sha256'], 'generator': generator if isinstance(generator, dict) else None})
    return batches


def content_labels(index, content_ids):
    """{contentId: {project, engine, route, format, renderer, group}} from the newest imported revision of each
    content id (Learn groups the per-video funnel by these). Ids the library does not hold are left out."""
    out = {}
    for content in sorted(set(content_ids)):
        row = index.execute('SELECT metadata FROM episodes WHERE question_id=? ORDER BY imported_at DESC, revision DESC LIMIT 1',
                            (content,)).fetchone()
        if row is None:
            continue
        view = lc.episode_view(json.loads(row['metadata']))
        out[content] = {k: view[k] for k in ('project', 'engine', 'route', 'format', 'renderer', 'group')}
    return out


def schedulable_videos(index, today):
    """Approved video records for the generator (DESIGN.md "Approved video record")."""
    today = _date(today)
    records = []
    for row in index.execute("SELECT * FROM episodes WHERE status='approved' ORDER BY batch_id, episode_id, revision"):
        approval = index.execute('SELECT * FROM approvals WHERE episode_id=? AND revision=? ORDER BY id DESC LIMIT 1',
                                 (row['episode_id'], row['revision'])).fetchone()
        meta = json.loads(row['metadata'])
        v = _video(index, row['video_sha256'])
        if (approval is None or approval['action'] != 'approve' or v is None or archived(index, row['video_sha256'])
                or lc.episode_metadata_hash(meta) != row['metadata_sha256']
                or (approval['video_sha256'], approval['cover_sha256'], approval['metadata_sha256'])
                != (row['video_sha256'], row['cover_sha256'], row['metadata_sha256'])
                or approval['caption_sha256'] != lc.caption_hash(meta) or _expired(meta, today)):
            continue
        measured = json.loads(v['measured'])
        episode = {**meta, 'eligibility': {**meta['eligibility'], 'status': 'approved'}}
        records.append({
            'episodeId': row['episode_id'], 'revision': row['revision'], 'batchId': row['batch_id'],
            'questionId': row['question_id'], 'game': row['game'], 'difficulty': row['difficulty'],
            'videoSha256': row['video_sha256'], 'coverSha256': row['cover_sha256'], 'bytes': v['bytes'],
            'durationSeconds': measured.get('durationSeconds'), 'platforms': json.loads(v['platforms']),
            'eligibility': {k: meta['eligibility'].get(k) for k in ('notBefore', 'reviewBy', 'expiresAt')},
            'approvalId': approval['id'], 'metadataSha256': row['metadata_sha256'], 'episode': episode,
        })
    records.sort(key=lambda r: (r['batchId'], r['episodeId'], r['revision']))
    return records


# ---------- feedback and batch notes (owner planning text: never scheduled, approved or published) ----------

NUMBERED_BATCH = re.compile(r'\d{4}-(0[1-9]|1[0-2])-b([0-9]+)')


def episode_row(index, episode_id, revision):
    return index.execute('SELECT * FROM episodes WHERE episode_id=? AND revision=?', (episode_id, revision)).fetchone()


def batch_known(index, batch_id):
    return index.execute('SELECT 1 FROM batches WHERE batch_id=? UNION SELECT 1 FROM batch_documents WHERE batch_id=?',
                         (batch_id, batch_id)).fetchone() is not None


def stored_episode(index, batch_id, episode_id, revision, fallback=None):
    """The episode object exactly as imported, from the newest stored batch.json that lists this revision."""
    for doc in index.execute('SELECT raw FROM batch_documents WHERE batch_id=? ORDER BY imported_at DESC, sha256', (batch_id,)):
        try:
            episodes = json.loads(doc['raw']).get('episodes')
        except (ValueError, AttributeError):
            continue
        for e in episodes if isinstance(episodes, list) else []:
            if isinstance(e, dict) and e.get('episodeId') == episode_id and e.get('revision') == revision:
                return e
    return fallback


def _feedback(row):
    return None if row is None else {'episodeId': row['episode_id'], 'revision': row['revision'], 'tags': json.loads(row['tags']),
                                     'note': row['note'], 'status': row['status'], 'updatedAt': row['updated_at']}


def get_feedback(index, episode_id, revision):
    return _feedback(index.execute('SELECT * FROM feedback WHERE episode_id=? AND revision=?', (episode_id, revision)).fetchone())


def set_feedback(index, episode_id, revision, tags, note, now):
    """Upsert one revision's feedback; saving always reopens it."""
    with index:
        index.execute('INSERT INTO feedback(episode_id,revision,tags,note,status,updated_at) VALUES(?,?,?,?,?,?) '
                      'ON CONFLICT(episode_id, revision) DO UPDATE SET tags=excluded.tags, note=excluded.note, '
                      "status='open', updated_at=excluded.updated_at",
                      (episode_id, revision, json.dumps(list(tags)), note, 'open', stamp(now)))
    return get_feedback(index, episode_id, revision)


def clear_feedback(index, episode_id, revision):
    with index:
        return index.execute('DELETE FROM feedback WHERE episode_id=? AND revision=?', (episode_id, revision)).rowcount


def mark_feedback_used(index, items):
    """Mark open feedback for [(episodeId, revision)] used; returns how many rows changed."""
    updated = 0
    with index:
        for episode_id, revision in sorted(set(items)):
            updated += index.execute("UPDATE feedback SET status='used' WHERE episode_id=? AND revision=? AND status='open'",
                                     (episode_id, revision)).rowcount
    return updated


def open_feedback(index):
    """Open feedback with its episode's batch and metadata (also for revisions deleted since)."""
    out = []
    for f in index.execute("SELECT * FROM feedback WHERE status='open' ORDER BY updated_at, episode_id, revision").fetchall():
        row = episode_row(index, f['episode_id'], f['revision'])
        if row is not None:
            batch_id, meta = row['batch_id'], json.loads(row['metadata'])
        else:
            gone = index.execute('SELECT batch_id FROM deletions WHERE episode_id=? AND revision=? ORDER BY id DESC LIMIT 1',
                                 (f['episode_id'], f['revision'])).fetchone()
            batch_id = gone['batch_id'] if gone else None
            meta = stored_episode(index, batch_id, f['episode_id'], f['revision']) if batch_id else None
        if not isinstance(meta, dict):
            continue
        view = lc.episode_view(meta)
        out.append({**_feedback(f), 'batchId': batch_id, 'questionId': view['contentId'], 'game': view['group'],
                    'format': meta.get('format'), 'styleId': view['styleId'], 'project': view['project']})
    return out


def _note(row):
    return None if row is None else {'batchId': row['batch_id'], 'kind': row['kind'], 'text': row['text'],
                                     'sha256': row['sha256'], 'bytes': row['bytes'], 'uploadedAt': row['uploaded_at']}


def batch_notes(index, batch_id):
    rows = {r['kind']: r for r in index.execute('SELECT * FROM batch_notes WHERE batch_id=?', (batch_id,))}
    return {'batchId': batch_id, 'brief': _note(rows.get('brief')), 'retro': _note(rows.get('retro'))}


def set_batch_note(index, batch_id, kind, text, now):
    data = text.encode('utf-8')
    with index:
        index.execute('INSERT INTO batch_notes(batch_id,kind,text,sha256,bytes,uploaded_at) VALUES(?,?,?,?,?,?) '
                      'ON CONFLICT(batch_id, kind) DO UPDATE SET text=excluded.text, sha256=excluded.sha256, '
                      'bytes=excluded.bytes, uploaded_at=excluded.uploaded_at',
                      (batch_id, kind, text, hashlib.sha256(data).hexdigest(), len(data), stamp(now)))
    return _note(index.execute('SELECT * FROM batch_notes WHERE batch_id=? AND kind=?', (batch_id, kind)).fetchone())


def last_note(index, kind):
    """The non-empty note of this kind from the most recently imported batch that has one."""
    return _note(index.execute(
        'SELECT n.*, COALESCE((SELECT imported_at FROM batches b WHERE b.batch_id=n.batch_id), '
        '(SELECT MAX(imported_at) FROM batch_documents d WHERE d.batch_id=n.batch_id)) AS imported '
        'FROM batch_notes n WHERE n.kind=? AND n.bytes>0 ORDER BY imported DESC, n.batch_id DESC LIMIT 1', (kind,)).fetchone())


def next_batch_id(index, now):
    """YYYY-MM-bNN: the current UTC month; NN = 1 + the highest bNN of any batch ever imported (any month)."""
    ids = [r[0] for r in index.execute('SELECT batch_id FROM batches UNION SELECT batch_id FROM batch_documents')]
    highest = max((int(m.group(2)) for m in map(NUMBERED_BATCH.fullmatch, ids) if m), default=0)
    return f"{now.astimezone(UTC).strftime('%Y-%m')}-b{highest+1:02d}"


def standing(index, today=None):
    """Library half of the dashboard standing (next posts come from the approved manifest)."""
    today = _date(today) if today else None
    last = index.execute("SELECT batch_id, imported_at FROM batches WHERE batch_id NOT LIKE 'legacy-%' "
                         "AND batch_id NOT LIKE 'manual-%' ORDER BY imported_at DESC, batch_id DESC LIMIT 1").fetchone()
    awaiting = sum(not _expired(json.loads(r['metadata']), today)
                   for r in index.execute("SELECT metadata FROM episodes WHERE status='reviewable'"))
    count = 'SELECT count(*) FROM episodes WHERE batch_id=?'
    return {'lastBatch': {'batchId': last['batch_id'], 'importedAt': last['imported_at'],
                          'episodeCount': index.execute(count, (last['batch_id'],)).fetchone()[0],
                          'awaitingFiles': index.execute(count + " AND status='awaiting_files'",
                                                         (last['batch_id'],)).fetchone()[0]} if last else None,
            'awaitingReview': awaiting, 'openFeedback': len(open_feedback(index))}
