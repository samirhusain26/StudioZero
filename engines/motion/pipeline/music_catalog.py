"""Measure every candidate music source and write music/catalog.json (docs/AUDIO_CORPUS_PLAN.md).

    .venv/bin/python pipeline/music_catalog.py            (from engines/motion/)

Sources are the downloaded CC0/royalty-free originals under music/sources/<source>/<pack>/ (Mac only, ignored), each
source folder with a LICENSE.txt. Per track: hash, duration, tempo and tempo steadiness (librosa beat track), loudness
(integrated LUFS, short-term spread), crest factor, brightness (median spectral centroid) and busyness (onsets/s).
`calm` ranks the corpus (lower centroid, onset rate and loudness spread are calmer); `cuttable` needs a steady tempo.
Mood: key/mode (Krumhansl-Schmuckler on mean chroma), percussive share (HPSS) and bass share. `quizFit` scores the
brief "curious thinking music" (docs/AUDIO_CORPUS_PLAN.md): major or neutral, 75-110 BPM, steady, calm, not sad;
`flavour` suggests the game whose look it suits best. Both are heuristics for ordering the audition, not decisions.
Owner review sets `status` (candidate/approved/rejected); existing statuses and notes survive a re-run.
"""
import hashlib, json, re, sys
from pathlib import Path
import numpy as np, soundfile as sf, pyloudnorm as pyln, librosa

ROOT = Path(__file__).resolve().parents[1]  # engines/motion/
SOURCES = ROOT / 'music/sources'
OUT = ROOT / 'music/catalog.json'
SR = 22050
# source folder -> licence and page per pack (mirrors music/sources/<source>/LICENSE.txt); a pack may be
# (page, artist, game) where game is the one the research brief matched it to (overrides the heuristic flavour)
SOURCE_META = {
    'holizna': {'artist': 'HoliznaCC0', 'license': 'CC0-1.0', 'pages': {
        'chill_beats': 'https://opengameart.org/content/chill-beats-collection',
        'chills': 'https://opengameart.org/content/chills',
        'happy_lo-fi_lofi_collection': 'https://opengameart.org/content/happy-lo-fi-lofi-collection',
        'lo-fi_and_chill_lofi_collection': 'https://opengameart.org/content/lo-fi-and-chill-collection',
        'lo-fi_and_chill_lofi_collection_2': 'https://opengameart.org/content/lo-fi-and-chill-collection',
        'lo-fi_and_chill_lofi_collection_3': 'https://opengameart.org/content/lo-fi-and-chill-collection',
        'sad_lofi_1': 'https://opengameart.org/content/sad-lo-fi-lofi-collectioni',
        'sad_lofi_2': 'https://opengameart.org/content/sad-lo-fi-lofi-collectioni',
    }, 'retrieved': '2026-10-09'},
    'oga': {'artist': 'various (OpenGameArt)', 'license': 'CC0-1.0', 'retrieved': '2026-10-09', 'pages': {
        'a-small-fire-will-do-calming-loop': ('https://opengameart.org/content/a-small-fire-will-do-calming-loop', 'Trex0n', 'scalar'),
        'ambient-relaxing-loop': ('https://opengameart.org/content/ambient-relaxing-loop', 'isaiah658', 'tectonic'),
        'aquaria': ('https://opengameart.org/content/aquaria', 'cynicmusic', 'tectonic'),
        'atmospheric-puzzles': ('https://opengameart.org/content/atmospheric-puzzles', 'legoluft', 'tectonic'),
        'bossa-town': ('https://opengameart.org/content/bossa-town', 'KarateStudios', 'scalar'),
        'calm-ambient-1-synthwave-4k': ('https://opengameart.org/content/calm-ambient-1-synthwave-4k', 'cynicmusic', 'tectonic'),
        'calm-ambient-2-synthwave-15k': ('https://opengameart.org/content/calm-ambient-2-synthwave-15k', 'cynicmusic', 'tectonic'),
        'calm-ambient-3-lifewave-2k': ('https://opengameart.org/content/calm-ambient-3-lifewave-2k', 'cynicmusic', 'tectonic'),
        'calm-piano-1-vaporware': ('https://opengameart.org/content/calm-piano-1-vaporware', 'cynicmusic', 'whenabouts'),
        'chill-lofi-inspired': ('https://opengameart.org/content/chill-lofi-inspired', 'omfgdude', 'continuum'),
        'chillout-instrumentals-collection': ('https://opengameart.org/content/chillout-instrumentals-collection', 'Holizna', 'continuum'),
        'coffee-house-bump': ('https://opengameart.org/content/coffee-house-bump', 'OatCog', 'whenabouts'),
        'cozy-puzzle-in-game-1': ('https://opengameart.org/content/cozy-puzzle-in-game-1', 'MintoDog', 'scalar'),
        'cozy-puzzle-in-game-2': ('https://opengameart.org/content/cozy-puzzle-in-game-2', 'MintoDog', 'scalar'),
        'cozy-puzzle-in-game-3': ('https://opengameart.org/content/cozy-puzzle-in-game-3', 'MintoDog', 'scalar'),
        'cozy-puzzle-stage-select': ('https://opengameart.org/content/cozy-puzzle-stage-select', 'MintoDog', 'scalar'),
        'cozy-puzzle-title': ('https://opengameart.org/content/cozy-puzzle-title', 'MintoDog', 'scalar'),
        'crystal-cave-song18': ('https://opengameart.org/content/crystal-cave-song18', 'cynicmusic', 'tectonic'),
        'down-the-river': ('https://opengameart.org/content/down-the-river', 'Loyalty Freak Music', 'whenabouts'),
        'elevator-music': ('https://opengameart.org/content/elevator-music', 'Pro Sensory', 'whenabouts'),
        'feel-good-slow-ambient-track-with-a-beat': ('https://opengameart.org/content/feel-good-slow-ambient-track-with-a-beat', 'annandistance', 'continuum'),
        'free-surrealdream-music-pack': ('https://opengameart.org/content/free-surrealdream-music-pack', 'tricksntraps', 'tectonic'),
        'frets': ('https://opengameart.org/content/frets', 'Pro Sensory', 'whenabouts'),
        'happy-lullaby-song17': ('https://opengameart.org/content/happy-lullaby-song17', 'cynicmusic', 'tectonic'),
        'hot-springs-town': ('https://opengameart.org/content/hot-springs-town', 'Kistol', 'scalar'),
        'jazz-slower': ('https://opengameart.org/content/jazz-slower', 'Pro Sensory', 'whenabouts'),
        'jrpg-pack-2-towns': ('https://opengameart.org/content/jrpg-pack-2-towns', 'SubspaceAudio', 'scalar'),
        'jrpg-pack-4-calm': ('https://opengameart.org/content/jrpg-pack-4-calm', 'SubspaceAudio', 'whenabouts'),
        'lofi-compilation': ('https://opengameart.org/content/lofi-compilation', 'TAD', 'continuum'),
        'lofi-hip-hop': ('https://opengameart.org/content/lofi-hip-hop', 'omfgdude', 'continuum'),
        'magic-puzzle-in-game-1': ('https://opengameart.org/content/magic-puzzle-in-game-1', 'MintoDog', 'scalar'),
        'magic-puzzle-in-game-2': ('https://opengameart.org/content/magic-puzzle-in-game-2', 'MintoDog', 'scalar'),
        'magic-puzzle-title': ('https://opengameart.org/content/magic-puzzle-title', 'MintoDog', 'scalar'),
        'menu-chill-music': ('https://opengameart.org/content/menu-chill-music', 'etrock', 'continuum'),
        'mocha-frapp': ('https://opengameart.org/content/mocha-frapp', 'Pro Sensory', 'continuum'),
        'quiet-village-collection': ('https://opengameart.org/content/quiet-village-collection', 'Holizna', 'scalar'),
        'relaxing-instrumentals-collection': ('https://opengameart.org/content/relaxing-instrumentals-collection', 'Holizna', 'continuum'),
        'sci-fi-puzzle-in-game-2': ('https://opengameart.org/content/sci-fi-puzzle-in-game-2', 'MintoDog', 'continuum'),
        'serenade-guitar': ('https://opengameart.org/content/serenade-guitar', 'Pro Sensory', 'whenabouts'),
        'short-kalimba-loop': ('https://opengameart.org/content/short-kalimba-loop', 'extenz', 'scalar'),
        'slow-stride': ('https://opengameart.org/content/slow-stride', 'isaiah658', 'continuum'),
        'title-screens-beginnings-collection': ('https://opengameart.org/content/title-screens-beginnings-collection', 'Holizna', 'whenabouts'),
        'underwater-theme': ('https://opengameart.org/content/underwater-theme', 'CleytonKauffman', 'tectonic'),
        'urban-shop': ('https://opengameart.org/content/urban-shop', 'MintoDog', 'scalar'),
        'vintage-menu': ('https://opengameart.org/content/vintage-menu', 'iamoneabe', 'continuum'),
        'wooden-inn': ('https://opengameart.org/content/wooden-inn', 'Indieteur', 'whenabouts'),
    }},
}
AUDIO = {'.mp3', '.wav', '.flac', '.ogg', '.m4a'}
GAMES = ['scalar', 'continuum', 'whenabouts', 'tectonic']
PICKS = 15  # per game
KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']


def title_of(path):
    t = re.sub(r'(\.mp3)+$|\.(wav|flac|ogg|m4a)$', '', path.name)
    t = re.sub(r'^\d+\s*', '', t).replace('_', ' ')
    t = re.sub(r'\s*bpm\d+$', '', t, flags=re.I)
    return re.sub(r'^(holiznacc0\s*-\s*|HoliznaCC0\s*-\s*)', '', t, flags=re.I).strip() or path.stem


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def measure(path):
    y, sr = sf.read(path, always_2d=True)
    lufs = pyln.Meter(sr).integrated_loudness(y)
    st = [pyln.Meter(sr, block_size=3.0).integrated_loudness(y[i:i + 3 * sr]) for i in range(0, len(y) - 3 * sr, sr)]
    st = [v for v in st if np.isfinite(v) and v > -50]
    mono = librosa.resample(y.mean(1), orig_sr=sr, target_sr=SR)
    tempo, beats = librosa.beat.beat_track(y=mono, sr=SR, units='time')
    ibi = np.diff(beats)
    onsets = librosa.onset.onset_detect(y=mono, sr=SR, units='time')
    cent = librosa.feature.spectral_centroid(y=mono, sr=SR)[0]
    dur = len(y) / sr
    mid = mono[int(len(mono) * 0.25):][:60 * SR]  # a minute from a quarter in: past the intro
    chroma = librosa.feature.chroma_cqt(y=mid, sr=SR).mean(1)
    corr = lambda prof: [np.corrcoef(np.roll(prof, k), chroma)[0, 1] for k in range(12)]
    cmaj, cmin = corr(KS_MAJOR), corr(KS_MINOR)
    major = max(cmaj) >= max(cmin)
    harm, perc = librosa.effects.hpss(mid)
    spec = np.abs(librosa.stft(mid)) ** 2
    bass = spec[librosa.fft_frequencies(sr=SR) < 150].sum() / spec.sum()
    bpm = float(np.atleast_1d(tempo)[0])
    return {
        'durationSeconds': round(dur, 2),
        'bpm': round(bpm, 2),
        'feltBpm': round(bpm / 2 if bpm > 125 else bpm, 1),  # the tracker often reports lo-fi double time
        'key': NOTES[int(np.argmax(cmaj if major else cmin))] + (' major' if major else ' minor'),
        'modeLean': round(float(max(cmaj) - max(cmin)), 3),  # > 0 major, < 0 minor
        'percussive': round(float((perc ** 2).sum() / ((harm ** 2).sum() + (perc ** 2).sum())), 2),
        'bassShare': round(float(bass), 2),
        'beatJitterMs': round(float(np.std(ibi) * 1000), 1) if len(ibi) > 8 else None,
        'lufs': round(float(lufs), 1),
        'loudnessSpreadLu': round(float(np.std(st)), 1) if st else None,
        'crestDb': round(float(20 * np.log10(np.abs(y).max() / max(np.sqrt((y ** 2).mean()), 1e-9))), 1),
        'centroidHz': round(float(np.median(cent))),
        'onsetsPerSecond': round(len(onsets) / dur, 2),
    }


def main():
    old = json.loads(OUT.read_text()) if OUT.exists() else {'tracks': {}}
    tracks = {}
    files = sorted(p for p in SOURCES.glob('*/*/*') if p.suffix.lower() in AUDIO and p.parent.parent.name in SOURCE_META)
    for i, p in enumerate(files, 1):
        src, pack = p.parent.parent.name, p.parent.name
        meta = SOURCE_META[src]
        title = title_of(p)
        page = meta['pages'].get(pack)
        page, artist, game = page if isinstance(page, tuple) else (page, meta['artist'], None)
        tid = f'{src}-{slug(title)}'
        if tid in tracks:
            tid = f'{src}-{slug(pack)}-{slug(title)}'
        print(f'[{i}/{len(files)}] {tid}', file=sys.stderr)
        prev = old['tracks'].get(tid, {})
        tracks[tid] = {
            'id': tid, 'title': title, 'artist': artist, 'source': src, 'pack': pack, 'intendedFor': game,
            'file': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'license': meta['license'], 'page': page, 'retrieved': meta['retrieved'],
            **measure(p),
            'status': prev.get('status', 'candidate'), 'notes': prev.get('notes', ''),
        }
    # calm rank: mean of percentile ranks (lower = calmer) over brightness, busyness and loudness spread
    ids = list(tracks)
    def pct(key):
        v = np.array([tracks[t][key] if tracks[t][key] is not None else np.inf for t in ids])
        return v.argsort().argsort() / max(len(v) - 1, 1)
    score = (pct('centroidHz') + pct('onsetsPerSecond') + pct('loudnessSpreadLu')) / 3
    for t, s in zip(ids, score):
        tr = tracks[t]
        tr['calm'] = round(float(1 - s), 2)
        tr['cuttable'] = tr['beatJitterMs'] is not None and tr['beatJitterMs'] < 25 and tr['durationSeconds'] >= 40
        tempo_fit = float(np.clip(1 - max(75 - tr['feltBpm'], tr['feltBpm'] - 110, 0) / 20, 0, 1))
        bright = float(np.clip((tr['modeLean'] + 0.15) / 0.3, 0, 1)) * (0.5 if 'sad' in tr['pack'] else 1)
        tr['quizFit'] = round((tempo_fit + bright + tr['calm'] + (1.0 if tr['cuttable'] else 0.3)) / 4, 2)
        tr['flavour'] = tr['intendedFor'] or ('tectonic' if tr['percussive'] < 0.22 else 'whenabouts' if tr['centroidHz'] < 650
                         else 'continuum' if tr['centroidHz'] > 1000 else 'scalar')
    # picks: per game, best quizFit first; steady (or beatless ambient, which needs no bar cut), not clearly minor,
    # >= 40 s, and not a near-duplicate upload of an earlier pick (same key, length within 1 s)
    for g in GAMES:
        picked = []
        for tr in sorted((t for t in tracks.values() if t['flavour'] == g), key=lambda t: -t['quizFit']):
            dup = any(abs(tr['durationSeconds'] - o['durationSeconds']) < 1 and tr['key'] == o['key'] for o in picked)
            tr['pick'] = (len(picked) < PICKS and (tr['cuttable'] or tr['percussive'] < 0.25) and tr['modeLean'] > -0.1
                          and tr['durationSeconds'] >= 40 and not dup)
            if tr['pick']:
                picked.append(tr)
    ordered = dict(sorted(tracks.items(), key=lambda kv: -kv[1]['quizFit']))
    OUT.write_text(json.dumps({'version': 1, 'generated': 'pipeline/music_catalog.py', 'tracks': ordered}, indent=2) + '\n')
    print(f'{len(ordered)} tracks -> {OUT.relative_to(ROOT)}', file=sys.stderr)


if __name__ == '__main__':
    main()
