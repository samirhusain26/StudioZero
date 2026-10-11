"""check_sync.py <final.mp4> <reference.wav>: audio offset of the muxed file vs the sample-exact mix, plus spec checks."""
import json, subprocess, sys
import numpy as np, soundfile as sf

R = './node_modules/.bin/remotion'
mp4, ref = sys.argv[1], sys.argv[2]
tmp = '.audio-work/' + mp4.split('/')[-1] + '.chk.wav'
subprocess.run([R, 'ffmpeg', '-v', 'error', '-y', '-i', mp4, '-vn', '-ac', '1', '-ar', '22050', tmp], check=True)
subprocess.run([R, 'ffmpeg', '-v', 'error', '-y', '-i', ref, '-ac', '1', '-ar', '22050', tmp + '.ref.wav'], check=True)
a, sr = sf.read(tmp)
b, _ = sf.read(tmp + '.ref.wav')
lags = []
for t0 in np.linspace(1, len(b) / sr - 4, 3):
    x = b[int(t0 * sr):int((t0 + 3) * sr)]
    best = max((np.dot(x, a[int(t0 * sr) + l:int((t0 + 3) * sr) + l]), l) for l in range(-1500, 1501, 1))
    lags.append(best[1] / sr * 1000)
probe = json.loads(subprocess.run([R, 'ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,width,height,r_frame_rate:format=duration,size', '-of', 'json', mp4], capture_output=True, text=True).stdout)
v = [s for s in probe['streams'] if s.get('width')][0]
size_mb = int(probe['format']['size']) / 1e6
print(f"sync: audio offset {', '.join(f'{l:+.1f}' for l in lags)} ms (want |x| < 5)")
print(f"spec: {v['codec_name']} {v['width']}x{v['height']} {v['r_frame_rate']} · {[s['codec_name'] for s in probe['streams'] if not s.get('width')]} · {float(probe['format']['duration']):.3f}s · {size_mb:.1f} MB")
ok = max(abs(l) for l in lags) < 5 and v['codec_name'] == 'h264' and (v['width'], v['height']) == (1080, 1920) and v['r_frame_rate'] == '30/1' and size_mb < 50
print('PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
