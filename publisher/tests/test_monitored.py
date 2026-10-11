import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from monitored import alert_text, ping


class HeartbeatTests(unittest.TestCase):
    def test_missing_credential_is_visible_false(self):
        with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': '/nonexistent'}):
            self.assertFalse(ping(0))

    def test_signal_is_categorical_and_acknowledged(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'HEALTHCHECKS_PING_URL').write_text('https://hc-ping.com/00000000-0000-0000-0000-000000000000')
            with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': tmp}), patch('monitored.urllib.request.urlopen', return_value=io.BytesIO(b'ok')) as network:
                self.assertTrue(ping(2))
                request = network.call_args.args[0]
                self.assertTrue(request.full_url.endswith('/fail'))
                self.assertEqual(request.data, b'scalar-social: failure\nsee the Pi UI Health page')

    def test_alert_text_names_issues_and_platforms(self):
        self.assertEqual(alert_text(0), 'scalar-social: healthy')
        self.assertEqual(alert_text(2, ['publication_missed', 'content_exhausted'], {'threads': ['uncertain'], 'bluesky': ['blocked', 'failed']}, 1),
                         'scalar-social: failure\nissues: content_exhausted, publication_missed\nbluesky: blocked, failed\n'
                         'threads: uncertain\nmissed slots in the last 24 h: 1')
