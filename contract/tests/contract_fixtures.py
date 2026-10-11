"""Builders for contract v1 batches. Media bytes are tiny MP4 box skeletons plus a
fake ffprobe, so tests need no encoder. Shared by contract, import and UI tests."""
import copy
import hashlib
import json
from pathlib import Path


def mp4_bytes(tag=b'', faststart=True, size=0):
    def box(kind, body):
        return (8 + len(body)).to_bytes(4, 'big') + kind + body
    ftyp = box(b'ftyp', b'isom\x00\x00\x02\x00isomiso2avc1mp41')
    moov = box(b'moov', b'\x00' * 32 + tag)
    mdat = box(b'mdat', b'\x00' * max(16, size) + tag)
    return ftyp + (moov + mdat if faststart else mdat + moov)


JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 60 + b'\xff\xd9'


def probe_json(duration=22.0, width=1080, height=1920, fps='30/1', vcodec='h264', pix='yuv420p',
               audio=True, rate='48000', channels=2):
    streams = [{'codec_type': 'video', 'codec_name': vcodec, 'pix_fmt': pix, 'width': width, 'height': height,
                'r_frame_rate': fps, 'avg_frame_rate': fps, 'disposition': {'attached_pic': 0}}]
    if audio:
        streams.append({'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': rate, 'channels': channels})
    return {'streams': streams, 'format': {'duration': str(duration)}}


class FakeProbe:
    """Maps file sha256 -> ffprobe JSON (default: valid 22 s H.264/AAC)."""
    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.calls = 0

    def __call__(self, path):
        self.calls += 1
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return self.overrides.get(digest, probe_json())


def episode(n=1, game='scalar', answer='Bolivia', choices=('Bolivia', 'Paraguay', 'Austria'), question_id=None):
    episode_id = f'{game}-clues-{n:03d}'
    labels = list(choices) if choices else []
    listing = ' '.join(f'{k}) {v}' for k, v in zip('ABCD', labels))
    return {
        'episodeId': episode_id,
        'questionId': question_id or f'{game}:Q{n}:clues',
        'revision': 1,
        'game': game,
        'format': 'progressive-clues',
        'language': 'en',
        'difficulty': 'approachable',
        'styleId': f'{game}-paper-1',
        'experimentId': 'baseline-2026-10',
        'variantId': None,
        'creative': {
            'hook': 'Three clues. One country.', 'question': 'Which country?',
            'clues': ['Americas', 'Landlocked', '5 neighbours'],
            'choices': [{'key': k, 'label': v} for k, v in zip('ABCD', labels)] if choices else None,
            'answer': answer, 'answerAliases': ['BOL', 'Plurinational State of Bolivia'] if answer == 'Bolivia' else [],
            'explanation': 'Two landlocked countries in South America; one borders five.',
        },
        'evidence': {'sources': [{'title': 'World Bank', 'url': 'https://data.worldbank.org/', 'retrieved': '2026-10-07'}],
                     'checks': {'uniqueAnswer': True, 'candidateCounts': [41, 2, 1]}, 'reviewer': 'owner'},
        'music': None,
        'video': {'file': f'videos/{episode_id}.mp4', 'sha256': '0' * 64, 'bytes': 1, 'durationSeconds': 22.0,
                  'width': 1080, 'height': 1920, 'fps': '30/1', 'videoCodec': 'h264', 'audioCodec': 'aac'},
        'cover': {'file': f'covers/{episode_id}.jpg', 'sha256': '0' * 64, 'bytes': 1},
        'publication': {
            'deepLink': '/scalar', 'utmCampaign': 'social_library_v1',
            'captions': {
                'instagram': f'Three clues, one country. {listing} — comment your letter. Play at scalargame.com',
                'facebook': f'Three clues, one country. {listing} {{link}}',
                'threads': f'Three clues, one country. {listing} {{link}}',
                'x': f'Three clues, one country. {listing} {{link}}',
                'bluesky': f'Three clues, one country. {listing} {{link}}',
                'tiktok': 'Three clues, one country. Comment your guess.',
            },
            'youtube': {'title': 'Which country? Three clues #shorts', 'description': 'Guess before the reveal.'},
            'altText': 'Animated quiz: three clues about a mystery country, answer revealed at the end.',
            'hashtags': ['#geography', '#quiz'],
            'credits': [],
            'poll': {'question': 'Which country?', 'options': labels} if choices else None,
            'firstComment': {'instagram': f'{listing} — comment your letter', 'threads': None, 'bluesky': None, 'x': None},
            'answerReply': None,
        },
        'eligibility': {'status': 'qa-passed', 'notBefore': None, 'reviewBy': '2027-04-01', 'expiresAt': None},
    }


def document(episodes=None, batch_id='2026-10-fixture'):
    episodes = episodes or [episode(1)]
    games = sorted({e['game'] for e in episodes})
    return {
        'schemaVersion': 1, 'batchId': batch_id, 'createdAt': '2026-10-06T14:00:00Z',
        'generator': {'repoCommit': '7e7deb5', 'dirty': False, 'assetKitVersion': 'kit-1'},
        'sourceSnapshotHash': 'a' * 64,
        'styleRecipes': [{'styleId': f'{g}-paper-1', 'game': g, 'version': 1, 'summary': 'Paper style'} for g in games],
        'episodes': episodes,
    }


def write_batch(root, data=None, files=True, faststart=True):
    """Write a batch folder whose hashes match; returns (folder, data, {relative: bytes})."""
    data = copy.deepcopy(data or document())
    folder = Path(root) / data['batchId']
    (folder / 'videos').mkdir(parents=True, exist_ok=True)
    (folder / 'covers').mkdir(parents=True, exist_ok=True)
    blobs = {}
    for e in data['episodes']:
        video = mp4_bytes(e['episodeId'].encode() + str(e['revision']).encode(), faststart)
        cover = JPEG + e['episodeId'].encode()
        for kind, blob in (('video', video), ('cover', cover)):
            e[kind]['sha256'] = hashlib.sha256(blob).hexdigest()
            e[kind]['bytes'] = len(blob)
            blobs[e[kind]['file']] = blob
            if files:
                (folder / e[kind]['file']).write_bytes(blob)
    (folder / 'batch.json').write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return folder, data, blobs
