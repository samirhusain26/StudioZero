"""Throwaway Pi UI state for the end-to-end browser run against the real backend. Never publishes.

Builds, under --out DIR:
  DIR/state/          ledger (two confirmed historical posts, one uncertain), PAUSED, library imported
                      through ui_library from a real H.264 batch (ffprobe-measured), most of it approved
  DIR/config.json     publisher/config.example.json, all channels disabled, paused, Instagram direct route
                      verified (accountId 111, ownerId 222), media baseUrl set
  DIR/credentials/UI_PASSCODE   a random fixture passcode (not a real credential)
  DIR/work/           batch copies; work/2026-10-second/ is left un-imported for the "add batch" flow

Prints JSON {state, config, credentials, passcode}. The --source batch folder (a finalized batch with a real
H.264 yuv420p video) is only read.
"""
import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
import library_contract as lc  # noqa: E402
import ui_library  # noqa: E402
from runner import Ledger  # noqa: E402

BASE_URL = 'https://scalar-social-media.pages.dev'
REMOTION = ROOT/'studio/node_modules/.bin/remotion'
EXTRA = (  # game, n, difficulty, question, choices, answer
    ('continuum', 2, 'moderate', 'Which is larger by area?', ['Chad', 'Peru', 'Mongolia'], 'Mongolia'),
    ('whenabouts', 3, 'challenging', 'Which year?', ['1961', '1969', '1972'], '1969'),
    ('tectonic', 4, 'approachable', 'Which country is missing?', ['Laos', 'Nepal', 'Bhutan'], 'Nepal'),
)


def frame_grab(video, out):
    """One cover frame (no rendering); the Pi uses /usr/bin/ffmpeg, the Mac Remotion's bundled ffmpeg."""
    subprocess.run([str(REMOTION), 'ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', str(video), '-frames:v', '1',
                    '-vf', 'scale=540:-2', '-q:v', '4', str(out)], cwd=ROOT, check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    if not lc.is_jpeg(out):
        raise ValueError('frame grab did not produce a JPEG')


def config(out):
    data = json.loads((ROOT/'publisher/config.example.json').read_text())
    data['paused'] = True
    data['approval'] = None
    data['media'].update(baseUrl=BASE_URL, pagesProject='scalar-social-media', cloudflareAccountId='fixture-account')
    for channel in data['channels'].values():
        channel['enabled'] = False
    data['channels']['instagram'].update(route='instagram', accountId='111', ownerId='222', identityVerified=True,
                                         ownerIdVerified=True, publishingVerified=True,
                                         reason='Fixture: direct Instagram route verified')
    path = out/'config.json'
    path.write_text(json.dumps(data, indent=2) + '\n')
    path.chmod(0o640)
    return path


def ledger(state):
    db = Ledger(state/'ledger.sqlite3')
    def post(platform, account, slot, question, episode_id, game, caption):
        return db.enqueue(platform, account, slot, {
            'episode': {'id': question, 'episodeId': episode_id, 'game': game}, 'kind': 'post', 'format': 'self-contained',
            'caption': caption, 'link': None, 'previous': None,
            'media': {'url': f'{BASE_URL}/clips/{episode_id}.mp4', 'sha256': '0' * 64, 'bytes': 1, 'rightsReviewed': True},
            'metadata': {}, 'thread': None})
    one = post('instagram', '111', '2026-10-05T16:00:00+00:00', 'ep01', 'scalar-legacy-001', 'scalar',
               'Archive challenge: three clues, one country. Comment your letter.')
    db.update(one, 'dispatching', attempts=1, dispatched_at='2026-10-05T16:00:02+00:00')
    db.update(one, 'confirmed', permalink='https://www.instagram.com/reel/FIXTURE1/', published_at='2026-10-05T16:01:10+00:00')
    two = post('bluesky', 'did:plc:fixture', '2026-10-05T17:00:00+00:00', 'ep02', 'continuum-legacy-002', 'continuum',
               'Archive challenge: which is larger? scalargame.com')
    db.update(two, 'dispatching', attempts=1, dispatched_at='2026-10-05T17:00:01+00:00')
    db.update(two, 'confirmed', permalink='https://bsky.app/profile/fixture/post/2', published_at='2026-10-05T17:00:20+00:00')
    three = post('instagram', '111', '2026-10-06T16:00:00+00:00', 'ep03', 'whenabouts-legacy-003', 'whenabouts',
                 'Archive challenge: which year? Comment your letter.')
    db.update(three, 'dispatching', attempts=1, dispatched_at='2026-10-06T16:00:03+00:00')
    db.update(three, 'uncertain', retry_at=time.time() + 3600, error='uncertain_response')
    # Ledger.update stamps events with the real clock; date them like the history they stand for.
    stamps = {one: ('2026-10-05T16:00:02+00:00', '2026-10-05T16:01:10+00:00'),
              two: ('2026-10-05T17:00:01+00:00', '2026-10-05T17:00:20+00:00'),
              three: ('2026-10-06T16:00:03+00:00', '2026-10-06T16:00:33+00:00')}
    with db.db:
        for job, times in stamps.items():
            for (seq,), at in zip(db.db.execute('SELECT seq FROM events WHERE job=? ORDER BY seq', (job,)).fetchall(), times):
                db.db.execute('UPDATE events SET at=? WHERE seq=?', (at, seq))
    db.db.close()


def variant(base, game, n, difficulty, question, labels, answer):
    episode = copy.deepcopy(base)
    episode_id = f'{game}-clues-{n:03d}'
    listing = ' '.join(f'{k}) {v}' for k, v in zip('ABCD', labels))
    episode.update(episodeId=episode_id, questionId=f'{game}:Q{n}:clues', game=game, difficulty=difficulty,
                   styleId=f'{game}-paper-1')
    episode['creative'].update(hook=f'{question} Three clues.', question=question,
                               choices=[{'key': k, 'label': v} for k, v in zip('ABCD', labels)], answer=answer,
                               answerAliases=[], explanation='Fixture explanation.')
    episode['video']['file'] = f'videos/{episode_id}.mp4'
    episode['cover']['file'] = f'covers/{episode_id}.jpg'
    publication = episode['publication']
    publication['deepLink'] = f'/{game}'
    publication['captions'] = {
        'instagram': f'{question} {listing} — comment your letter. Play at scalargame.com',
        'facebook': f'{question} {listing} {{link}}', 'threads': f'{question} {listing} {{link}}',
        'x': f'{question} {listing} {{link}}', 'bluesky': f'{question} {listing} {{link}}',
        'tiktok': f'{question} Comment your guess.'}
    publication['youtube'] = {'title': f'{question} Three clues #shorts', 'description': 'Guess before the reveal.'}
    publication['altText'] = f'Animated quiz: {question} The answer is revealed at the end.'
    publication['poll'] = {'question': question, 'options': list(labels)}
    publication['firstComment'] = {'instagram': f'{listing} — comment your letter', 'threads': None, 'bluesky': None, 'x': None}
    return episode


def write_batch(folder, data, video, cover):
    (folder/'videos').mkdir(parents=True, exist_ok=True)
    (folder/'covers').mkdir(parents=True, exist_ok=True)
    for episode in data['episodes']:
        shutil.copyfile(video, folder/episode['video']['file'])
        shutil.copyfile(cover, folder/episode['cover']['file'])
    (folder/'batch.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    return folder


def library(state, work, now, source_dir):
    source = json.loads((source_dir/'batch.json').read_text())  # read only; the original is never written
    base = source['episodes'][0]
    video = work/'source.mp4'
    shutil.copyfile(source_dir/base['video']['file'], video)
    cover = work/'cover.jpg'
    frame_grab(video, cover)
    video_sha, video_bytes = lc.file_digest(video)
    cover_sha, cover_bytes = lc.file_digest(cover)
    if video_sha != base['video']['sha256']:
        raise SystemExit('The source video does not match its batch.json hash.')
    base['cover'].update(sha256=cover_sha, bytes=cover_bytes)
    batch = copy.deepcopy(source)
    batch['styleRecipes'] = [{'styleId': f'{g}-paper-1', 'game': g, 'version': 1, 'summary': 'Paper style'} for g in lc.GAMES]
    base['styleId'] = f"{base['game']}-paper-1"  # match the fixture's replacement style recipes
    batch['episodes'] = [base] + [variant(base, *spec) for spec in EXTRA]
    folder = write_batch(work/batch['batchId'], batch, video, cover)

    second = copy.deepcopy(batch)
    second.update(batchId='2026-10-second', createdAt=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    second['episodes'] = [variant(base, 'scalar', 5, 'moderate', 'Which capital?', ['Lima', 'La Paz', 'Quito'], 'La Paz'),
                          variant(base, 'tectonic', 6, 'moderate', 'Which country borders both?', ['Peru', 'Chile', 'Brazil'], 'Peru')]
    write_batch(work/'2026-10-second', second, video, cover)

    index = ui_library.open_index(state)
    try:
        result = ui_library.import_batch_json(index, state, (folder/'batch.json').read_bytes(), now)
        if result['problems']:
            raise SystemExit('Fixture batch rejected: ' + '; '.join(result['problems']))
        for expected in result['expected']:
            path = folder/expected['file']
            with open(path, 'rb') as stream:
                upload = ui_library.accept_batch_file(index, state, batch['batchId'], expected['file'], stream,
                                                      path.stat().st_size, lc.run_ffprobe, frame_grab, now)
            if not upload['ok'] or upload['problems']:
                raise SystemExit(f"Fixture upload refused: {expected['file']}: {upload['problems']}")
        approve = [{'episodeId': e['episodeId'], 'revision': e['revision']} for e in batch['episodes'][:3]]
        decided = ui_library.approve(index, approve, 'owner', now, state=state)
        if decided['count'] != len(approve):
            raise SystemExit(f"Fixture approval refused: {decided['results']}")
    finally:
        index.close()
    return {'videoSha256': video_sha, 'videoBytes': video_bytes, 'coverSha256': cover_sha}


def build(out, source, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty; choose a new folder.')
    state, work, creds = out/'state', out/'work', out/'credentials'
    for folder in (state, work, creds):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = config(out)
    (state/'PAUSED').touch()
    ledger(state)
    media = library(state, work, now, Path(source))
    passcode = 'fixture-' + secrets.token_urlsafe(12)
    (creds/'UI_PASSCODE').write_text(passcode + '\n')
    os.chmod(creds/'UI_PASSCODE', 0o600)
    return {'state': str(state), 'config': str(config_path), 'credentials': str(creds), 'passcode': passcode,
            'secondBatch': str(work/'2026-10-second'), 'media': media}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build throwaway Pi UI fixture state (never publishes).')
    parser.add_argument('--out', required=True)
    parser.add_argument('--source', required=True,
                        help='A finalized contract batch folder with one real H.264 yuv420p video (read only)')
    args = parser.parse_args(argv)
    print(json.dumps(build(args.out, args.source), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
