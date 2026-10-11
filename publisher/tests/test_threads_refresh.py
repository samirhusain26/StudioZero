import io
import json
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from credential_entry import clear_superseded_failure
from refresh_threads import refresh


class RefreshTests(unittest.TestCase):
    def config(self):
        return {'channels': {'threads': {'identityVerified': True, 'accountId': '42', 'profileUrl': 'https://www.threads.com/@studiozeroflow'}}}

    def test_refresh_requires_matching_identity_and_valid_expiry(self):
        opener = lambda *a, **k: io.BytesIO(json.dumps({'access_token': 'test-only', 'expires_in': 5184000}).encode())
        profile = lambda *a: {'id': '42', 'username': 'studiozeroflow'}
        self.assertEqual(refresh(self.config(), 'fixture', opener, profile), ('test-only', 5184000))
        with self.assertRaises(ValueError):
            refresh(self.config(), 'fixture', opener, lambda *a: {'id': 'wrong', 'username': 'studiozeroflow'})

    def test_disabled_identity_cannot_refresh(self):
        config = self.config()
        config['channels']['threads']['identityVerified'] = False
        with self.assertRaises(ValueError):
            refresh(config, 'fixture')


class SupersededFailureTests(unittest.TestCase):
    def test_failure_before_a_replaced_token_is_cleared_and_a_newer_one_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            failure, source = Path(tmp)/'failure.json', Path(tmp)/'TOKEN'
            failure.write_text('{}')
            source.write_text('t')
            os.utime(failure, (1000, 1000))
            os.utime(source, (2000, 2000))
            self.assertTrue(clear_superseded_failure(failure, source))
            self.assertFalse(failure.exists())
            failure.write_text('{}')
            os.utime(failure, (3000, 3000))
            self.assertFalse(clear_superseded_failure(failure, source))
            self.assertTrue(failure.exists())
            failure.unlink()
            self.assertFalse(clear_superseded_failure(failure, source))
