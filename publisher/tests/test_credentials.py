from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from credential_entry import store


class CredentialTests(unittest.TestCase):
    def test_instagram_entry_and_renewal_use_private_atomic_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'private'
            store(directory, 'INSTAGRAM_ACCESS_TOKEN', 'instagram-test-fixture')
            path = directory/'INSTAGRAM_ACCESS_TOKEN'
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            store(directory, 'INSTAGRAM_ACCESS_TOKEN', 'renewed-test-fixture')
            self.assertEqual(path.read_text(), 'renewed-test-fixture\n')
            self.assertFalse(list(directory.glob('.credential-*')))

    def test_private_atomic_store_and_reject_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'private'
            store(directory, 'BUFFER_API_KEY', 'test-only-value')
            self.assertEqual(stat.S_IMODE((directory/'BUFFER_API_KEY').stat().st_mode), 0o600)
            store(directory, 'BUFFER_API_KEY', 'replacement')
            self.assertEqual((directory/'BUFFER_API_KEY').read_text(), 'replacement\n')
            with self.assertRaises(ValueError):
                store(directory, 'OTHER', 'x')
            with self.assertRaises(ValueError):
                store(directory, 'BUFFER_API_KEY', 'x\ny')
            with self.assertRaises(ValueError):
                store(directory, 'HEALTHCHECKS_PING_URL', 'http://example.test')

    def test_ui_passcode_minimum_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'private'
            with self.assertRaises(ValueError):
                store(directory, 'UI_PASSCODE', '123')
            store(directory, 'UI_PASSCODE', '4821')
            self.assertEqual(stat.S_IMODE((directory/'UI_PASSCODE').stat().st_mode), 0o600)
