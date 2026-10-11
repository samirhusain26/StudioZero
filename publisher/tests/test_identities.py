"""Pinned identities come only from the Pi config; a missing or malformed pin refuses (fail closed)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
import metrics
from bluesky_adapter import BlueskyAdapter
from buffer_adapter import PublishError
from configure_paused import configure
from facebook_adapter import FacebookAdapter
from first_post import verified_buffer_account
from identities import IdentityMissing, PINS, expected_buffer, pin
from runner import Ledger
from fixture_ids import IDENTITIES


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name)/'ledger.sqlite3')
        self.calls = []

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def remote(self, *args):
        self.calls.append(args)
        return {}

    def test_example_config_carries_every_pin(self):
        self.assertEqual(set(IDENTITIES), set(PINS))
        for name in PINS:
            self.assertEqual(pin({'identities': IDENTITIES}, name), IDENTITIES[name])

    def test_missing_or_malformed_pin_refuses(self):
        for config in ({}, {'identities': None}, {'identities': {}},
                       {'identities': {**IDENTITIES, 'facebookPageId': 'not-a-number'}},
                       {'identities': {**IDENTITIES, 'facebookPageId': 7}}):
            with self.assertRaises(IdentityMissing):
                pin(config, 'facebookPageId')
        with self.assertRaises(IdentityMissing):
            expected_buffer({'identities': {**IDENTITIES, 'bufferX': None}})

    def test_configure_refuses_without_pins_or_media_account(self):
        config = json.loads((ROOT/'publisher/config.example.json').read_text())
        config['media']['cloudflareAccountId'] = 'c'*32
        report = {'organizationId': 'org', 'channels': [
            {'id': account, 'service': service, 'serviceId': provider or 'ig', 'externalLink': config['channels'][p]['profileUrl'],
             'isDisconnected': False, 'isLocked': False} for p, (service, account, provider) in expected_buffer(config).items()]}
        configure(config, report)
        with self.assertRaises(ValueError):
            configure({**config, 'identities': {}}, report)
        with self.assertRaises(ValueError):
            configure({**config, 'media': {**config['media'], 'cloudflareAccountId': None}}, report)

    def test_adapters_refuse_before_any_remote_call(self):
        config = {'channels': {'facebook': {'accountId': IDENTITIES['facebookPageId'], 'profileUrl': IDENTITIES['facebookProfileUrl']},
                               'bluesky': {'accountId': IDENTITIES['blueskyDid'], 'profileUrl': 'https://bsky.app/profile/studiozeroflow.bsky.social'}}}
        facebook = FacebookAdapter(self.ledger, config, self.remote, lambda: 'token', self.remote, lambda p: b'x')
        with self.assertRaises(PublishError) as raised:
            facebook.publish({'id': 'f', 'account': IDENTITIES['facebookPageId']}, {'caption': 'c'})
        self.assertEqual(raised.exception.category, 'authorization')
        bluesky = BlueskyAdapter(self.ledger, config, self.remote, lambda: 'secret', lambda p: b'x')
        with self.assertRaises(PublishError) as raised:
            bluesky.identity({'id': 'b', 'account': IDENTITIES['blueskyDid']})
        self.assertEqual(raised.exception.category, 'authorization')
        self.assertEqual(self.calls, [])

    def test_stats_and_first_post_treat_a_missing_pin_as_not_configured(self):
        with self.assertRaises(PublishError) as raised:
            metrics.fetch({'platform': 'facebook', 'remote_id': '123', 'permalink': None}, {}, self.remote, lambda p: 'token')
        self.assertEqual(raised.exception.category, 'not_configured')
        with self.assertRaises(PublishError) as raised:
            metrics.account_now('youtube', self.remote, lambda p: 'key', {})
        self.assertEqual(raised.exception.category, 'not_configured')
        self.assertEqual(self.calls, [])
        channel = {'accountId': IDENTITIES['bufferX'], 'identityVerified': True, 'route': 'buffer'}
        self.assertTrue(verified_buffer_account({'identities': IDENTITIES, 'channels': {'x': channel}}, 'x'))
        self.assertFalse(verified_buffer_account({'channels': {'x': channel}}, 'x'))


if __name__ == '__main__':
    unittest.main()
