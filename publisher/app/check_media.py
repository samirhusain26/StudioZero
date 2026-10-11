import json
from pathlib import Path
import sys


def validate(path, probe):
    streams=probe['streams']
    video=[s for s in streams if s['codec_type']=='video']
    if len(video)!=1:
        raise ValueError('Social output must have one video stream')
    audio=[s for s in streams if s['codec_type']=='audio']
    if len(audio)>1 or any(s['codec_name']!='aac' or s.get('sample_rate')!='48000' or s.get('channels')!=2 for s in audio):
        raise ValueError('Unexpected social audio encoding')
    if audio and abs(float(audio[0].get('duration',0))-float(probe['format']['duration']))>0.1:
        raise ValueError('Incomplete social audio')
    s=video[0]
    if (s['codec_name'],s['width'],s['height'],s['r_frame_rate'])!=('h264',1080,1920,'30/1') or s['pix_fmt'] not in ('yuv420p','yuvj420p'):
        raise ValueError('Unexpected codec, resolution, frame rate or pixel format')
    if not 0<Path(path).stat().st_size<=24_000_000:
        raise ValueError('Exceeded media host free file limit')
    if not 0<float(probe['format']['duration'])<=30.1:
        raise ValueError('Unexpected duration')


if __name__=='__main__':
    validate(sys.argv[1],json.loads(Path(sys.argv[2]).read_text()))
    print('Media verified: H.264 with optional AAC, 1080×1920, 30fps, ≤24 MB')
