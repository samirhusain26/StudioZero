import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import ui_sessions


class SessionTests(unittest.TestCase):
    def test_persistent_expiring_revocable_and_passcode_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            now = [1000]
            sessions = ui_sessions.Sessions(Path(temp), lambda: now[0])
            token = sessions.create('old-passcode')
            self.assertEqual(len(token), 43)
            self.assertTrue(sessions.valid(token, 'old-passcode'))
            self.assertTrue(ui_sessions.Sessions(Path(temp), lambda: now[0]).valid(token, 'old-passcode'))
            self.assertEqual(Path(temp, 'ui-sessions.sqlite3').stat().st_mode & 0o777, 0o600)
            rotated = sessions.create('old-passcode')
            self.assertFalse(sessions.valid(rotated, 'new-passcode'))
            self.assertFalse(sessions.valid(rotated, 'old-passcode'))
            expiring = sessions.create('old-passcode')
            now[0] += ui_sessions.TTL_SECONDS + 1
            self.assertFalse(sessions.valid(expiring, 'old-passcode'))
            self.assertFalse(sessions.valid(token, 'old-passcode'))
            token2 = sessions.create('old-passcode')
            sessions.revoke(token2)
            self.assertFalse(sessions.valid(token2, 'old-passcode'))

    def test_malformed_tokens_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(ui_sessions.Sessions(Path(temp), lambda: 100).valid('x' * 5000, 'pass'))
            ui_sessions.Sessions(Path(temp), lambda: 100).revoke('x' * 5000)
            self.assertFalse(Path(temp, 'ui-sessions.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
