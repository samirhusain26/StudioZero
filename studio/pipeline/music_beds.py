"""Cut the library music beds on bar lines so each reveal lands on a downbeat.

    .venv/bin/python pipeline/music_beds.py [bed ...]   (from studio/)

Same method as the launch beds (.audio-work/build_music.py, see music/TRACKS.md): 120.00 BPM, bar = 2.000 s,
splices PRE before a downbeat with an XF equal-power crossfade, -14 LUFS integrated, lookahead limiter (true peak
<= -1 dBTP). Sources are the owner-supplied Gemini tracks music/sources/<n>.mp4 decoded to .audio-work/<n>.wav.
Writes public/episodes/music/<bed>.m4a and public/episodes/music/beds.json (source/output hashes, segments, loudness).

    .venv/bin/python pipeline/music_beds.py --picks     (calm library beds, docs/AUDIO_CORPUS_PLAN.md)

Builds <game>-<duration>-<trackId> beds for every `pick` in music/catalog.json, for each (duration, reveal) its game's
formats use. One contiguous window per bed (no splicing): the steadiest full-arrangement stretch whose downbeat lands
exactly on the reveal (beatless ambient: free placement), with a slight preference for a gentle lift after the reveal.
Mastered at LIB_TARGET (-20 LUFS) so calm beds sit ~6 dB under the SFX; true peak <= -1 dBTP.
"""
import hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np, soundfile as sf, pyloudnorm as pyln, librosa
from scipy.ndimage import minimum_filter1d, uniform_filter1d

ROOT = Path(__file__).resolve().parents[1]  # studio/
OUT = ROOT / 'public/episodes/music'
SR = 44100
PRE, XF = 0.005, 0.010
TARGET, CEIL_DB, FADE_OUT = -14.0, -1.5, 1.5
# Downbeat = attack start of bar 0 (track 2 measured 6 Oct 2026: beat-tracker phase 0.102 s minus the usual ~22 ms lag).
DOWNBEAT = {'2': 1.080, '3': 1.546, '5': 0.088, '6': 0.593}
TITLES = {'2': 'Midday Market Rush', '3': 'The Pocket Heist', '5': 'Golden Question', '6': 'Skipping Downstairs'}
# bed: (track, [(start_bar, end_bar)], reveal_s, duration_s). Owner mapping, Checkpoint 1 (6 Oct 2026).
BEDS = {
    'scalar-24': ('6', [(0, 3), (0, 3), (3, 4), (4, 9)], 14, 24),        # pluck intro x2 · build · kick in at the reveal
    'continuum-20': ('2', [(0, 3), (1, 3), (3, 8)], 10, 20),             # hits + stab break · stab break · groove at the reveal
    'continuum-22': ('2', [(0, 3), (1, 3), (2, 3), (3, 8)], 12, 22),
    'whenabouts-22': ('5', [(0, 1), (0, 5), (5, 10)], 12, 22),           # ticks · ticks/stabs/riser · drop at the reveal
    'tectonic-22': ('3', [(0, 2), (11, 15), (15, 20)], 12, 22),          # intro · breakdown + riser · drop at the reveal
    'tectonic-24': ('3', [(0, 3), (11, 15), (15, 20)], 14, 24),
}


def limit(x, ceil):
    look = int(0.003 * SR)
    need = np.minimum(1.0, ceil / np.maximum(np.abs(x).max(1), 1e-9))
    g = uniform_filter1d(minimum_filter1d(need, size=2 * look + 1), size=look)
    rel = np.exp(-1 / (0.08 * SR)); out = np.empty_like(g); cur = 1.0
    for n in range(len(g)):
        cur = g[n] if g[n] < cur else g[n] + (cur - g[n]) * rel
        out[n] = cur
    return x * out[:, None]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_wav(track):
    wav = ROOT / f'.audio-work/{track}.wav'
    if not wav.exists():
        subprocess.run([str(ROOT / 'node_modules/.bin/remotion'), 'ffmpeg', '-v', 'error', '-y', '-i', str(ROOT / f'music/sources/{track}.mp4'),
                        '-vn', '-ac', '2', '-ar', str(SR), str(wav)], check=True)
    return wav


def build(name):
    track, bars, reveal, duration = BEDS[name]
    if sum(b - a for a, b in bars) * 2 != duration: raise ValueError(f'{name}: bars do not add up to {duration}s')
    y, _ = sf.read(source_wav(track))
    t0 = DOWNBEAT[track]
    s = lambda sec: int(round(sec * SR)); n = s(XF); out = None
    for a, b in bars:
        A, B = t0 + 2 * a, t0 + 2 * b
        if out is None:
            out = y[s(A):s(B - PRE)].copy()
        else:
            seg = y[s(A - PRE) - n:s(B - PRE)]
            w = np.linspace(0, np.pi / 2, n)[:, None]
            out = np.concatenate([out[:-n], out[-n:] * np.cos(w) + seg[:n] * np.sin(w), seg[n:]])
    out = np.concatenate([out, y[s(t0 + 2 * bars[-1][1] - PRE):s(t0 + 2 * bars[-1][1])]])
    out = out[:s(duration)]
    if len(out) != s(duration): raise ValueError(f'{name}: {len(out) / SR:.3f}s')
    fi, fo = s(0.002), s(FADE_OUT)
    out[:fi] *= np.linspace(0, 1, fi)[:, None]
    out[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    return dict(**master(out, name), trackId=f'owner-gemini-{track}', title=TITLES[track],
                source=f'music/sources/{track}.mp4', sourceSha256=sha(ROOT / f'music/sources/{track}.mp4'),
                segments_s=[[round(t0 + 2 * a, 3), round(t0 + 2 * b, 3)] for a, b in bars], revealSeconds=reveal, durationSeconds=duration,
                license='owner-supplied',
                rights='Owner statement: AI-generated with Gemini, reuse authorized 2026-09-28, reaffirmed 2026-10-05; no attribution required. Not an independent licence verification.')


def master(out, name, target=TARGET):
    """Normalise to `target` LUFS through the lookahead limiter (true peak <= -1 dBTP), encode <name>.m4a."""
    meter = pyln.Meter(SR); raw = out; ceil_db = CEIL_DB
    while True:  # lower the sample-peak ceiling until the 4x-oversampled true peak is <= -1 dBTP
        out = raw
        for _ in range(4):
            L = meter.integrated_loudness(out)
            out = limit(out * 10 ** ((target - L) / 20), 10 ** (ceil_db / 20))
        L = meter.integrated_loudness(out)
        tp = 20 * np.log10(np.abs(librosa.resample(out.T, orig_sr=SR, target_sr=SR * 4)).max())
        if tp <= -1.0 or ceil_db <= -6: break
        ceil_db -= 0.5
    OUT.mkdir(parents=True, exist_ok=True)
    wav = ROOT / f'.audio-work/library-{name}.wav'
    sf.write(wav, out, SR, subtype='PCM_24')
    m4a = OUT / f'{name}.m4a'
    subprocess.run([str(ROOT / 'node_modules/.bin/remotion'), 'ffmpeg', '-v', 'error', '-y', '-i', str(wav), '-c:a', 'libfdk_aac', '-b:a', '256k',
                    '-ar', '48000', '-movflags', '+faststart', '-f', 'mp4', str(m4a)], check=True)
    return dict(bed=name, file=f'episodes/music/{name}.m4a', sha256=sha(m4a), lufs=round(L, 1), truePeakDbtp=round(tp, 1), limiterCeilingDb=ceil_db)


LIB_TARGET = -20.0
LIB_FADE_IN = 0.25
# (duration, reveal) per game, from the formats each game uses (src/episodes/timing.ts)
GAME_BEDS = {'scalar': [(24, 14)], 'continuum': [(20, 10), (22, 12)], 'whenabouts': [(22, 12)], 'tectonic': [(22, 12), (24, 14)]}


def downbeats(mono, beatless):
    """Downbeat times (s) of the felt 4/4 bar, or None for beatless material. Phase = the beat-of-4 with the most kick."""
    if beatless:
        return None
    tempo, beats = librosa.beat.beat_track(y=mono, sr=SR, units='time')
    if float(np.atleast_1d(tempo)[0]) > 125:  # tracker double time: keep the stronger half of the beats
        kick = librosa.onset.onset_strength(y=mono, sr=SR, n_mels=32, fmax=250)
        at = lambda ts: kick[np.minimum(librosa.time_to_frames(ts, sr=SR), len(kick) - 1)].sum()
        beats = max((beats[0::2], beats[1::2]), key=at)
    kick = librosa.onset.onset_strength(y=mono, sr=SR, n_mels=32, fmax=250)
    strength = lambda ts: kick[np.minimum(librosa.time_to_frames(ts, sr=SR), len(kick) - 1)].mean() if len(ts) else 0
    return beats[max(range(4), key=lambda p: strength(beats[p::4]))::4]


def library_bed(tr, duration, reveal):
    name = f"{tr['flavour']}-{duration}-{tr['id']}"
    y, sr = sf.read(ROOT / tr['file'], always_2d=True)
    y = y[:, :2] if y.shape[1] > 1 else np.repeat(y, 2, 1)
    if sr != SR:
        y = librosa.resample(y.T, orig_sr=sr, target_sr=SR).T
    mono = y.mean(1)
    total = len(y) / SR
    beatless = not tr['cuttable'] and tr['percussive'] < 0.25
    db = 20 * np.log10(np.maximum(librosa.feature.rms(y=mono, frame_length=SR // 2, hop_length=SR // 4)[0], 1e-6))
    med = np.median(db)
    seg = lambda a, b: db[int(a * 4):max(int(b * 4), int(a * 4) + 1)]
    starts = (np.arange(0, total, 0.5) if beatless else downbeats(mono, beatless) - reveal)
    lo = min(max(4.0, 0.08 * total), total - duration - 0.5)  # skip the intro, but keep at least one window
    best = None
    for s0 in starts:
        if s0 < lo or s0 + duration > total - 0.5:
            continue
        w = seg(s0, s0 + duration)
        lift = np.clip(seg(s0 + reveal, s0 + duration).mean() - seg(s0, s0 + reveal).mean(), 0, 3)
        score = -w.std() - 0.5 * max(0.0, med - w.mean()) + 0.3 * lift
        if best is None or score > best[0]:
            best = (score, float(s0))
    if best is None:
        raise ValueError(f'{name}: no {duration}s window with a downbeat at {reveal}s')
    s0 = best[1]
    out = y[int(round(s0 * SR)):int(round(s0 * SR)) + int(round(duration * SR))].copy()
    fi, fo = int(LIB_FADE_IN * SR), int(FADE_OUT * SR)
    out[:fi] *= np.sin(np.linspace(0, np.pi / 2, fi))[:, None]
    out[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    return dict(**master(out, name, LIB_TARGET), trackId=tr['id'], title=tr['title'], artist=tr['artist'], game=tr['flavour'],
                source=tr['file'], sourceSha256=tr['sha256'], page=tr['page'], segments_s=[[round(s0, 3), round(s0 + duration, 3)]],
                alignment='free' if beatless else 'downbeat', feltBpm=tr['feltBpm'], key=tr['key'],
                revealSeconds=reveal, durationSeconds=duration, license=tr['license'],
                rights=f"{tr['license']} ({tr['artist']}, {tr['page']}, retrieved {tr['retrieved']}); no attribution required.")


if __name__ == '__main__':
    manifest_path = OUT / 'beds.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if sys.argv[1:] == ['--picks']:
        catalog = json.loads((ROOT / 'music/catalog.json').read_text())['tracks']
        jobs = [(tr, d, r) for tr in catalog.values() if tr.get('pick') for d, r in GAME_BEDS[tr['flavour']]]
        for i, (tr, d, r) in enumerate(jobs, 1):
            e = library_bed(tr, d, r)
            manifest[e['bed']] = e
            print(f"[{i}/{len(jobs)}] {e['bed']} start {e['segments_s'][0][0]}s {e['alignment']} {e['lufs']} LUFS {e['truePeakDbtp']} dBTP", flush=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    for name in ([] if sys.argv[1:] == ['--picks'] else sys.argv[1:] or BEDS):
        manifest[name] = build(name)
        print(json.dumps({k: manifest[name][k] for k in ('bed', 'durationSeconds', 'revealSeconds', 'lufs', 'truePeakDbtp')}))
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
