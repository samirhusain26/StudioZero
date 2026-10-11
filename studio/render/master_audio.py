"""Master a rendered episode mix: gain to -14 LUFS integrated, lookahead limiter so true peak <= -1 dBTP.

    .venv/bin/python render/master_audio.py in.wav out.wav   (from studio/)

Same limiter as the music beds (studio/pipeline/music_beds.py). Sample-aligned: output length == input length,
so the sync check against the mastered WAV stays exact. Prints the measured result as JSON.
"""
import json, sys
import numpy as np, soundfile as sf, pyloudnorm as pyln, librosa
from scipy.ndimage import minimum_filter1d, uniform_filter1d

TARGET, TP_MAX = -14.0, -1.0


def limit(x, ceil, sr):
    look = int(0.003 * sr)
    need = np.minimum(1.0, ceil / np.maximum(np.abs(x).max(1), 1e-9))
    g = uniform_filter1d(minimum_filter1d(need, size=2 * look + 1), size=look)
    rel = np.exp(-1 / (0.08 * sr)); out = np.empty_like(g); cur = 1.0
    for n in range(len(g)):
        cur = g[n] if g[n] < cur else g[n] + (cur - g[n]) * rel
        out[n] = cur
    return x * out[:, None]


def main(src, dst):
    y, sr = sf.read(src, always_2d=True)
    meter = pyln.Meter(sr); ceil_db = -1.5
    while True:
        out = y
        for _ in range(4):
            L = meter.integrated_loudness(out)
            out = limit(out * 10 ** ((TARGET - L) / 20), 10 ** (ceil_db / 20), sr)
        L = meter.integrated_loudness(out)
        tp = 20 * np.log10(np.abs(librosa.resample(out.T, orig_sr=sr, target_sr=sr * 4)).max() + 1e-12)
        if tp <= TP_MAX or ceil_db <= -6: break
        ceil_db -= 0.5
    sf.write(dst, out, sr, subtype='PCM_24')
    print(json.dumps({'lufs': round(float(L), 2), 'truePeakDbtp': round(float(tp), 2), 'ceilingDb': ceil_db, 'sampleRate': sr}))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
