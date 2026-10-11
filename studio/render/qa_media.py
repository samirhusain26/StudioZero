"""Audio/visual QA of a delivered MP4 (remotion's ffmpeg has no ebur128/null output, so measure here).

    .venv/bin/python render/qa_media.py <video.mp4>   -> JSON on stdout

Loudness: integrated LUFS (pyloudnorm) and 4x-oversampled true peak of the decoded AAC.
Silence: gaps >= 1 s below -50 dBFS RMS (50 ms windows), ignoring the final 2 s fade.
Black frames: frames sampled at 10 fps (tiny greyscale PNGs); a run >= 0.2 s with mean luma < 5% is a black segment.
"""
import json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, soundfile as sf, pyloudnorm as pyln, librosa

R = str(Path(__file__).resolve().parents[1] / 'node_modules/.bin/remotion')


def main(mp4):
    out = {}
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / 'a.wav'
        subprocess.run([R, 'ffmpeg', '-v', 'error', '-y', '-i', mp4, '-vn', '-c:a', 'pcm_s16le', str(wav)], check=True)
        y, sr = sf.read(wav)
        y = y if y.ndim == 2 else y[:, None]
        out['loudnessLufs'] = round(float(pyln.Meter(sr).integrated_loudness(y)), 1)
        out['truePeakDbtp'] = round(float(20 * np.log10(np.abs(librosa.resample(y.T, orig_sr=sr, target_sr=sr * 4)).max() + 1e-12)), 1)
        mono = y.mean(1); win = int(0.05 * sr)
        rms = np.sqrt(np.convolve(mono ** 2, np.ones(win) / win, 'valid')[::win]) + 1e-12
        quiet = 20 * np.log10(rms) < -50
        dur = len(mono) / sr; starts, run = [], 0
        for i, q in enumerate(quiet):
            run = run + 1 if q else 0
            if run == 20 and i * 0.05 < dur - 2: starts.append(round((i - 19) * 0.05, 2))
        out['silenceStarts'] = starts
        # Bundled ffmpeg lacks fps/rawvideo; sample at 10 fps via -r and tiny greyscale PNGs.
        subprocess.run([R, 'ffmpeg', '-v', 'error', '-y', '-i', mp4, '-an', '-vf', 'scale=54:96,format=gray', '-r', '10', '-f', 'image2', '-c:v', 'png', str(Path(d) / 'f%05d.png')], check=True)
        from PIL import Image
        dark = np.array([np.asarray(Image.open(p)).mean() < 0.05 * 255 for p in sorted(Path(d).glob('f*.png'))])
        segs, run = 0, 0
        for x in dark:
            run = run + 1 if x else 0
            if run == 2: segs += 1
        out['blackSegments'] = segs
    print(json.dumps(out))


if __name__ == '__main__':
    main(sys.argv[1])
