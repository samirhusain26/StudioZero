"""Synthesize the calm SFX candidates into sfx/sources/procedural/ (44.1 kHz, 16-bit stereo WAV, peak -6 dBFS).

Run (from engines/motion/): .venv/bin/python tools/make_calm_sfx.py
Everything is procedural (no samples), so it is ours to use. Candidates only (docs/AUDIO_CORPUS_PLAN.md): approved
sounds get promoted to public/sfx later. Softer than tools/make_sfx.py: modal marimba/wood/kalimba bars, FM glass
bells, filtered-noise paper and air, all through a short stereo room. Notes stay in C major pentatonic so any two
sounds (and a lo-fi bed in a related key) sit together.
"""
import os
import zlib
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
OUT = os.path.join(os.path.dirname(__file__), '..', 'sfx', 'sources', 'procedural')
rng = np.random.default_rng(11)
PENTA = {'C5': 523.25, 'D5': 587.33, 'E5': 659.26, 'G5': 783.99, 'A5': 880.0,
         'C6': 1046.5, 'D6': 1174.66, 'E6': 1318.51, 'G4': 392.0, 'A4': 440.0, 'C4': 261.63}


def t(d):
    return np.arange(int(d * SR)) / SR


def filt(x, kind, f, order=2):
    f = np.atleast_1d(f) / (SR / 2)
    sos = butter(order, f if len(f) > 1 else f[0], btype=kind, output='sos')
    return sosfilt(sos, x)


def noise(d):
    return rng.standard_normal(int(d * SR))


def pad(x, d):
    n = int(d * SR)
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def at(x, s, d):
    """x delayed by s seconds inside a d-second buffer."""
    return pad(np.concatenate([np.zeros(int(s * SR)), x]), d)


def modal(f, d, ratios, decays, gains, strike=0.002):
    """Struck bar: decaying partials at f*ratio (decay in s) plus a soft felt-mallet transient."""
    x = t(d)
    out = sum(g * np.sin(2 * np.pi * f * r * x) * np.exp(-x / dc) for r, dc, g in zip(ratios, decays, gains))
    att = np.minimum(1, x / strike)
    thump = filt(noise(d), 'bandpass', [f * 0.8, min(f * 4, 18000)]) * np.exp(-x / 0.004) * 0.08
    return (out + thump) * att


def marimba(f, d=1.2):
    return modal(f, d, [1, 3.93, 9.24], [0.45, 0.08, 0.02], [1, 0.25, 0.06], 0.003)


def wood(f, d=0.35):
    return modal(f, d, [1, 2.57, 4.2], [0.06, 0.025, 0.012], [1, 0.4, 0.15], 0.0008)


def kalimba(f, d=1.4):
    return modal(f, d, [1, 5.4, 11.1], [0.7, 0.05, 0.015], [1, 0.18, 0.05], 0.0015)


def glass(f, d=2.0, idx=1.6, ratio=1.41):
    """FM bell: modulation index decays faster than the carrier, so the strike is bright and the tail pure."""
    x = t(d)
    i = idx * np.exp(-x / 0.25)
    y = np.sin(2 * np.pi * f * x + i * np.sin(2 * np.pi * f * ratio * x)) * np.exp(-x / (d * 0.35))
    return y * np.minimum(1, x / 0.002)


def room(x, size=0.6, mix=0.22, seed=0):
    """Stereo room: two decorrelated exponentially decaying noise IRs, darkened."""
    r = np.random.default_rng(seed)
    n = int(size * SR)
    e = np.exp(-np.arange(n) / (size * SR / 6))
    irs = [filt(r.standard_normal(n), 'lowpass', 5000) * e for _ in range(2)]
    irs = [ir / np.sqrt((ir ** 2).sum()) for ir in irs]
    wet = np.stack([fftconvolve(x, ir)[:len(x) + n] for ir in irs], 1)
    dry = np.stack([np.pad(x, (0, n - 1))] * 2, 1)
    return dry * (1 - mix) + wet * mix


def save(name, x, peak_db=-6.0, rev=0.22, size=0.6):
    y = room(x, size, rev, seed=zlib.crc32(name.encode())) if rev else np.stack([x, x], 1)
    tail = int(0.01 * SR)
    y[-tail:] *= np.linspace(1, 0, tail)[:, None]
    y = y / max(np.abs(y).max(), 1e-9) * 10 ** (peak_db / 20)
    sf.write(os.path.join(OUT, f'{name}.wav'), y, SR, subtype='PCM_16')


os.makedirs(OUT, exist_ok=True)

# item-in: single soft mallet notes (marimba, wood, kalimba) across the pentatonic set
for k in ['G4', 'A4', 'C5', 'D5', 'E5', 'G5', 'A5', 'C6']:
    save(f'marimba-{k}', marimba(PENTA[k]))
for k in ['C5', 'E5', 'G5', 'C6']:
    save(f'wood-{k}', wood(PENTA[k] * 1.5), rev=0.15, size=0.35)
for k in ['C5', 'D5', 'E5', 'G5', 'A5']:
    save(f'kalimba-{k}', kalimba(PENTA[k]))

# choices-in: soft pops and two-note marimba "ta-da" pickups
for i, f0 in enumerate([300, 380, 460]):
    d = 0.18
    x = t(d)
    ph = 2 * np.pi * np.cumsum(f0 * (1 + 1.2 * np.exp(-x / 0.012))) / SR
    save(f'softpop-{i + 1}', filt(np.sin(ph) * np.exp(-x / 0.035) * np.minimum(1, x / 0.001), 'lowpass', 2500), rev=0.12, size=0.3)
for name, (a, b) in {'pickup-up': ('C5', 'G5'), 'pickup-up2': ('E5', 'A5'), 'pickup-down': ('G5', 'C5')}.items():
    d = 1.3
    save(name, marimba(PENTA[a], d) * 0.7 + at(marimba(PENTA[b], d - 0.11), 0.11, d))

# think: clock tick/tock pairs and a slow breathing pad
for i, (hi, lo) in enumerate([(2400, 1700), (3000, 2100), (1900, 1400)]):
    save(f'clock-tick-{i + 1}', wood(hi, 0.12), rev=0.08, size=0.25, peak_db=-9)
    save(f'clock-tock-{i + 1}', wood(lo, 0.12), rev=0.08, size=0.25, peak_db=-9)
for i, chord in enumerate([('C4', 'G4', 'E5'), ('A4', 'C5', 'E5'), ('G4', 'D5', 'A5')]):
    d = 3.0
    x = t(d)
    y = sum(np.sin(2 * np.pi * PENTA[n] * dt * x + rng.uniform(0, 6)) for n in chord for dt in (0.997, 1.003))
    shape = np.sin(np.pi * x / d) ** 2
    save(f'think-pad-{i + 1}', filt(y, 'lowpass', 1800) * shape, rev=0.35, size=1.2, peak_db=-12)

# reveal: glass bells, rising pentatonic glass/marimba arpeggios, shimmer
for k in ['E5', 'G5', 'C6', 'E6']:
    save(f'glass-{k}', glass(PENTA[k]), rev=0.3, size=1.0)
for name, notes in {'reveal-arp-1': ['C5', 'E5', 'G5', 'C6'], 'reveal-arp-2': ['D5', 'G5', 'A5', 'D6'],
                    'reveal-arp-3': ['G4', 'C5', 'E5', 'G5'], 'reveal-arp-4': ['E5', 'G5', 'C6', 'E6']}.items():
    d = 2.4
    y = sum(at(glass(PENTA[n], d - 0.07 * i, idx=1.2) * (0.6 + 0.13 * i), 0.07 * i, d) for i, n in enumerate(notes))
    save(name, y, rev=0.3, size=1.2)
for name, notes in {'reveal-marimba-1': ['C5', 'E5', 'G5', 'C6'], 'reveal-marimba-2': ['G4', 'A4', 'C5', 'E5']}.items():
    d = 1.8
    save(name, sum(at(marimba(PENTA[n], d - 0.09 * i), 0.09 * i, d) for i, n in enumerate(notes)))
for i in range(3):
    d = 2.2
    x = t(d)
    sh = sum(glass(rng.choice([PENTA['C6'], PENTA['D6'], PENTA['E6']]) * 2, d, idx=0.8) for _ in range(1))
    grains = np.zeros(int(d * SR))
    for s in np.sort(rng.uniform(0, 1.2, 14)):
        g = glass(rng.choice(list(PENTA.values())[:8]) * 2, 0.6, idx=0.6) * rng.uniform(0.2, 0.5)
        grains += at(g, s, d)
    save(f'shimmer-{i + 1}', (grains + 0.3 * sh) * np.minimum(1, x / 0.02), rev=0.4, size=1.4, peak_db=-8)

# explain: paper flips, pencil scribbles, soft page turn
for i in range(4):
    d = 0.35
    x = t(d)
    flutter = 1 + 0.6 * np.sin(2 * np.pi * rng.uniform(25, 45) * x)
    shape = np.sin(np.pi * np.clip(x / d, 0, 1)) ** 2
    save(f'paper-flip-{i + 1}', filt(noise(d), 'bandpass', [rng.uniform(800, 1500), 7000]) * flutter * shape,
         rev=0.12, size=0.3, peak_db=-9)
for i in range(3):
    d = 0.9
    x = t(d)
    strokes = np.clip(np.sin(2 * np.pi * rng.uniform(4, 7) * x + rng.uniform(0, 3)), 0, 1) ** 0.6
    grit = filt(noise(d), 'bandpass', [2500, 9000]) * (0.6 + 0.4 * rng.random(len(x)))
    save(f'pencil-{i + 1}', grit * strokes * np.sin(np.pi * x / d), rev=0.1, size=0.3, peak_db=-12)

# cta: gentle whooshes and resolving success stingers
for i, (f0, f1) in enumerate([(300, 2400), (500, 3500), (2400, 400)]):
    d = 0.8
    x = t(d)
    fc = f0 * (f1 / f0) ** (x / d)
    nz = noise(d)
    out = np.zeros_like(nz)
    for j in range(0, len(nz), 512):  # piecewise band-pass sweep
        c = fc[j]
        out[j:j + 512] = filt(nz[max(0, j - 2048):j + 512], 'bandpass', [c * 0.7, min(c * 1.4, 20000)])[-len(out[j:j + 512]):]
    save(f'air-whoosh-{i + 1}', out * np.sin(np.pi * x / d) ** 2, rev=0.25, size=0.8, peak_db=-10)
for name, seq in {'stinger-1': [('C5', 0), ('E5', 0.12), ('G5', 0.24), ('C6', 0.36)],
                  'stinger-2': [('G4', 0), ('C5', 0.15), ('D5', 0.3), ('G5', 0.45)],
                  'stinger-3': [('A4', 0), ('C5', 0.12), ('E5', 0.24), ('A5', 0.5)]}.items():
    d = 2.0
    y = sum(at(kalimba(PENTA[n], d - s), s, d) for n, s in seq) + at(glass(PENTA[seq[-1][0]] * 2, d - seq[-1][1], idx=0.8) * 0.3, seq[-1][1], d)
    save(name, y, rev=0.28, size=1.0)

print(f'{len(os.listdir(OUT))} files -> {os.path.normpath(OUT)}')
