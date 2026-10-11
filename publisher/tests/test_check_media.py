import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'publisher/app'))
from check_media import validate


class CheckMediaTests(unittest.TestCase):
    def test_media_rejects_truncated_or_unexpected_audio(self):
        video={'codec_type':'video','codec_name':'h264','width':1080,'height':1920,'r_frame_rate':'30/1','pix_fmt':'yuv420p'}
        audio={'codec_type':'audio','codec_name':'aac','sample_rate':'48000','channels':2,'duration':'30'}
        probe={'streams':[video,audio],'format':{'duration':'30'}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'clip.mp4';path.write_bytes(b'fixture')
            validate(path,probe)
            for change in ({'duration':'14'},{'codec_name':'mp3'},{'sample_rate':'44100'},{'channels':1}):
                bad=copy.deepcopy(probe);bad['streams'][1].update(change)
                with self.assertRaises(ValueError):validate(path,bad)
            bad=copy.deepcopy(probe);bad['streams'].append(audio)
            with self.assertRaises(ValueError):validate(path,bad)
            validate(path,{'streams':[video],'format':{'duration':'30'}})
