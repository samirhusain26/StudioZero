"""Synthesize the video SFX set into public/sfx/ (44.1 kHz, 16-bit WAV, peak -3 dBFS).

Run (from studio/): .venv/bin/python tools/make_sfx.py
Everything is procedural (no samples), so it is ours to use.
"""
import os
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 44100
OUT = os.path.join(os.path.dirname(__file__), '..', 'public', 'sfx')
rng = np.random.default_rng(7)


def t(d):
    return np.arange(int(d * SR)) / SR


def env(d, a=0.002, r=0.2, curve=4.0):
    x = t(d)
    e = np.minimum(1, x / max(a, 1e-6)) * np.exp(-curve * np.maximum(0, x - a) / r)
    return e


def filt(x, kind, f, order=2):
    f = np.atleast_1d(f) / (SR / 2)
    sos = butter(order, f if len(f) > 1 else f[0], btype=kind, output='sos')
    return sosfilt(sos, x)


def noise(d):
    return rng.standard_normal(int(d * SR))


def sweep(d, f0, f1, shape='exp'):
    x = t(d)
    if shape == 'exp':
        f = f0 * (f1 / f0) ** (x / d)
    else:
        f = f0 + (f1 - f0) * (x / d)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def save(name, x, peak_db=-3.0, stereo_width=0.0):
    x = np.asarray(x, dtype=np.float64)
    fade = int(0.004 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    x *= 10 ** (peak_db / 20) / (np.abs(x).max() + 1e-12)
    if stereo_width:
        d = int(stereo_width * SR)
        x = np.stack([x, np.concatenate([np.zeros(d), x[:-d]])], 1)
    sf.write(os.path.join(OUT, f'{name}.wav'), x, SR, subtype='PCM_16')


def pad(x, d):
    return np.concatenate([x, np.zeros(max(0, int(d * SR) - len(x)))])[: int(d * SR)]


os.makedirs(OUT, exist_ok=True)

# thock: lock-in. Low wooden body + short click.
d = 0.25
body = sum(np.sin(2 * np.pi * f * t(d)) * env(d, 0.001, r, 1) * g
           for f, r, g in [(180, 0.06, 1.0), (330, 0.035, 0.5), (620, 0.02, 0.25)])
body *= 1 + 0.6 * np.exp(-t(d) / 0.01)
click = filt(noise(d), 'bandpass', [1500, 5000]) * env(d, 0.0005, 0.004, 1)
save('thock', body + 0.35 * click)

# key tick: typing / clock.
d = 0.06
save('tick', filt(noise(d), 'bandpass', [2500, 7000]) * env(d, 0.0003, 0.006, 1)
     + 0.4 * np.sin(2 * np.pi * 2200 * t(d)) * env(d, 0.0003, 0.01, 1), peak_db=-6)

# tock: the softer second clock sound for count-ins.
d = 0.08
save('tock', filt(noise(d), 'bandpass', [900, 2600]) * env(d, 0.0003, 0.01, 1)
     + 0.5 * np.sin(2 * np.pi * 1200 * t(d)) * env(d, 0.0003, 0.015, 1), peak_db=-6)

# flip whoosh: card cell flip. Band-passed noise swell with a rising centre.
d = 0.22
x = t(d)
n = noise(d)
lo = filt(n, 'bandpass', [600, 2000])
hi = filt(n, 'bandpass', [2500, 8000])
mix = x / d
w = (lo * (1 - mix) + hi * mix) * np.sin(np.pi * np.clip(x / d, 0, 1)) ** 2
save('flip', w + 0.25 * filt(noise(d), 'highpass', 3000) * env(d, 0.0005, 0.01, 1) * 0, peak_db=-6)

# ding: coin-style. Two bright partials, the second a fourth up after 60 ms.
def bell(f, d, r=0.35):
    return sum(np.sin(2 * np.pi * f * k * t(d)) * env(d, 0.001, r / k ** 0.7, 1) * g
               for k, g in [(1, 1), (2.01, 0.35), (3.02, 0.15), (4.1, 0.08)])
d = 0.7
a = bell(1319, d)          # E6
b = pad(np.concatenate([np.zeros(int(0.06 * SR)), bell(1760, d - 0.06)]), d)  # A6
save('ding', a * 0.8 + b)

# shake sting: rubbery wrong. Detuned square-ish wobble falling in pitch.
d = 0.45
x = t(d)
f = 220 * (1 + 0.12 * np.sin(2 * np.pi * 18 * x)) * (1 - 0.35 * x / d)
ph = 2 * np.pi * np.cumsum(f) / SR
tone = np.tanh(2.5 * np.sin(ph)) + 0.5 * np.tanh(2.5 * np.sin(ph * 1.5 + 0.3))
save('shake', filt(tone, 'lowpass', 2200) * env(d, 0.005, 0.25, 1.6))

# stamp thud: rubber stamp slam. Sub thump + papery slap + tiny rattle.
d = 0.5
sub = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t(d) / 0.08) + 45) / SR) * env(d, 0.001, 0.12, 1)
slap = filt(noise(d), 'bandpass', [300, 3000]) * env(d, 0.0005, 0.03, 1)
rattle = filt(noise(d), 'highpass', 4000) * env(d, 0.002, 0.05, 1) * 0.15
save('stamp', sub * 1.0 + slap * 0.7 + rattle)

# rewind whoosh: tape-style pitch-down sweep with noise, for the year scrubber.
d = 0.6
x = t(d)
tone = sweep(d, 1800, 180) * 0.35
nz = filt(noise(d), 'bandpass', [400, 4000])
shape = np.sin(np.pi * np.clip(x / d, 0, 1)) ** 1.5
save('rewind', (tone + nz * 0.6) * shape)

# forward whip: the opposite direction (scrub forward).
save('whip', (sweep(0.35, 250, 2400) * 0.3 + filt(noise(0.35), 'bandpass', [800, 6000]))
     * np.sin(np.pi * np.clip(t(0.35) / 0.35, 0, 1)) ** 2)

# pop: sticker / card slam-in.
d = 0.12
save('pop', np.sin(2 * np.pi * np.cumsum(900 * np.exp(-t(d) / 0.02) + 200) / SR) * env(d, 0.0005, 0.04, 1)
     + 0.2 * filt(noise(d), 'highpass', 3000) * env(d, 0.0003, 0.005, 1), peak_db=-4)

# swoosh: Venn circle wipe (0.5 s = one beat).
d = 0.5
x = t(d)
nz = noise(d)
cent = 300 * (6000 / 300) ** (x / d)
out = np.zeros_like(nz)
for i in range(0, len(nz), 512):  # stepwise moving band-pass
    seg = slice(i, i + 512)
    c = cent[i]
    out[seg] = filt(nz[max(0, i - 2048):i + 512], 'bandpass', [c * 0.6, min(c * 1.6, 20000)])[-len(nz[seg]):]
save('swoosh', out * np.sin(np.pi * x / d) ** 2, stereo_width=0.012)

# power-off: paper-to-dark cut. Falling tone + low thump, CRT-ish.
d = 0.7
x = t(d)
fall = np.sin(2 * np.pi * np.cumsum(1400 * np.exp(-x / 0.08) + 40) / SR) * env(d, 0.001, 0.25, 1)
thump = np.sin(2 * np.pi * 50 * x) * env(d, 0.002, 0.3, 1)
save('poweroff', fall * 0.5 + thump + 0.2 * filt(noise(d), 'lowpass', 800) * env(d, 0.001, 0.05, 1))

# sparkle: confetti burst. Random high pings.
d = 0.9
out = np.zeros(int(d * SR))
for _ in range(22):
    st = rng.uniform(0, 0.45)
    f = rng.choice([2093, 2349, 2637, 3136, 3520, 4186])
    ping = np.sin(2 * np.pi * f * t(0.25)) * env(0.25, 0.001, 0.07, 1) * rng.uniform(0.3, 1)
    i = int(st * SR)
    out[i:i + len(ping)] += ping[: len(out) - i]
save('sparkle', out, peak_db=-8, stereo_width=0.008)

# hit: big payoff impact (kick + noise burst + low tail).
d = 1.2
kick = np.sin(2 * np.pi * np.cumsum(120 * np.exp(-t(d) / 0.05) + 42) / SR) * env(d, 0.001, 0.35, 1)
burst = filt(noise(d), 'lowpass', 6000) * env(d, 0.001, 0.12, 1)
save('hit', kick + burst * 0.5)

# riser: 2 bars of tension (4 s) for play-along think windows if needed.
d = 4.0
x = t(d)
nz = filt(noise(d), 'bandpass', [500, 9000])
save('riser', (nz * 0.5 + sweep(d, 200, 1600) * 0.25) * (x / d) ** 2.2, peak_db=-6)

# Tectonic ASMR: soft mallet notes on a C major pentatonic, plus a completion chime and an ocean bed.
PENT = [261.63, 293.66, 329.63, 392.00, 440.00, 523.25, 587.33, 659.25, 783.99, 880.00]
for i, f in enumerate(PENT):
    d = 1.2
    x = t(d)
    tone = (np.sin(2 * np.pi * f * x) + 0.25 * np.sin(2 * np.pi * 4 * f * x) * np.exp(-x / 0.05)
            + 0.08 * np.sin(2 * np.pi * 2 * f * x))
    knock = filt(noise(d), 'bandpass', [f * 2, min(f * 6, 18000)]) * env(d, 0.0005, 0.006, 1) * 0.3
    save(f'note{i}', (tone * env(d, 0.002, 0.45, 1.3) + knock), peak_db=-6)

d = 2.5
chord = sum(bell(f, d, 1.4) * g for f, g in [(523.25, 1), (659.25, 0.8), (783.99, 0.7), (1046.5, 0.5)])
save('chime', chord, peak_db=-5, stereo_width=0.01)

d = 30.0
x = t(d)
surf = filt(noise(d), 'lowpass', 900) * 0.6 + filt(noise(d), 'bandpass', [1500, 5000]) * 0.08
swell = 0.55 + 0.45 * np.sin(2 * np.pi * x / 7.5 - np.pi / 2) ** 2
ocean = surf * swell
ocean[: int(SR)] *= np.linspace(0, 1, SR)
# loopable tail: crossfade last 2 s into the first 2 s
L = 2 * SR
ocean[:L] = ocean[:L] * np.linspace(0, 1, L) + ocean[-L:] * np.linspace(1, 0, L)
ocean = ocean[:-L]
save('ocean', ocean, peak_db=-12, stereo_width=0.015)

print('wrote', sorted(os.listdir(OUT)))
