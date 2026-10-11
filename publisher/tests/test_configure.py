import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
from configure_paused import configure, confirm_publishing
from identities import expected_buffer

EXPECTED = expected_buffer(json.loads((ROOT/'publisher/config.example.json').read_text()))


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config['media']['cloudflareAccountId'] = 'c'*32   # set on the Pi before configure runs
        self.report = {'organizationId': 'org', 'channels': []}
        for p, (service, account, provider) in EXPECTED.items():
            self.report['channels'].append({'id': account, 'service': service, 'serviceId': provider or 'ig-provider',
                'externalLink': self.config['channels'][p]['profileUrl'], 'isDisconnected': False, 'isLocked': False, 'scopes': []})

    def test_configure_never_enables_or_claims_publication(self):
        value = configure(self.config, self.report)
        self.assertTrue(value['paused'])
        self.assertIsNone(value['approval'])
        self.assertTrue(value['channels']['x']['identityVerified'])
        self.assertFalse(any(c['enabled'] or c['publishingVerified'] for c in value['channels'].values()))
        self.assertIsNone(self.config['bufferOrganizationId'])

    def test_wrong_provider_or_disconnected_rejected(self):
        self.report['channels'][0]['serviceId'] = 'wrong'
        with self.assertRaises(ValueError):
            configure(self.config, self.report)

    def test_tiktok_reallocation_requires_verified_direct_instagram(self):
        self.report['channels'] = [c for c in self.report['channels'] if c['service'] != 'instagram']
        self.report['channels'].append({'id': 'new-tiktok-connection', 'service': 'tiktok',
            'serviceId': 'owned-tiktok-id', 'externalLink': 'https://www.tiktok.com/@studiozeroflow',
            'isDisconnected': False, 'isLocked': False})
        with self.assertRaises(ValueError):
            configure(self.config, self.report)
        self.config['channels']['instagram'].update(route='instagram', accountId='123456',
            identityVerified=True, publishingVerified=True)
        value = configure(self.config, self.report)
        self.assertEqual(value['channels']['tiktok']['accountId'], 'new-tiktok-connection')
        self.assertEqual(value['channels']['tiktok']['route'], 'buffer')
        self.assertFalse(value['channels']['tiktok']['publishingVerified'])
        self.assertTrue(value['channels']['instagram']['publishingVerified'])
        self.assertFalse(any(c['enabled'] for c in value['channels'].values()))
        self.assertEqual(value['channels']['instagram']['route'], 'instagram')
        self.report['channels'][-1]['externalLink'] = 'https://www.tiktok.com/@other'
        with self.assertRaises(ValueError):
            configure(self.config, self.report)

    def test_tiktok_reallocation_keeps_proven_x_and_youtube(self):
        self.config['channels']['instagram'].update(route='instagram', accountId='123456',
            identityVerified=True, publishingVerified=True)
        for p in ('x', 'youtube'):
            self.config['channels'][p].update(route='buffer', accountId=EXPECTED[p][1], providerAccountId=EXPECTED[p][2],
                identityVerified=True, publishingVerified=True, reason='Public post verified')
        self.config['channels']['youtube']['providerAccountId'] = 'old-provider'
        self.report['channels'] = [c for c in self.report['channels'] if c['service'] != 'instagram']
        self.report['channels'].append({'id': 'new-tiktok-connection', 'service': 'tiktok',
            'serviceId': 'owned-tiktok-id', 'externalLink': 'https://www.tiktok.com/@studiozeroflow',
            'isDisconnected': False, 'isLocked': False})
        value = configure(self.config, self.report)
        self.assertTrue(value['channels']['x']['publishingVerified'])
        self.assertEqual(value['channels']['x']['reason'], 'Public post verified')
        self.assertFalse(value['channels']['youtube']['publishingVerified'])   # provider changed: test again
        self.assertFalse(value['channels']['tiktok']['publishingVerified'])
        self.assertFalse(any(c['enabled'] for c in value['channels'].values()))

    def test_confirm_publishing_needs_confirmed_post_on_current_account(self):
        self.config['channels']['tiktok'].update(route='buffer', accountId='tt', providerAccountId='owned',
            identityVerified=True)
        ledger = sqlite3.connect(':memory:')
        ledger.execute('CREATE TABLE jobs(platform, account, status, permalink)')
        link = 'https://www.tiktok.com/@studiozeroflow/video/1234567890'
        with self.assertRaises(ValueError):
            confirm_publishing(self.config, ledger, 'tiktok', link)
        ledger.execute("INSERT INTO jobs VALUES('tiktok','old-tt','confirmed',?)", (link,))
        ledger.execute("INSERT INTO jobs VALUES('tiktok','tt','uncertain',?)", (link,))
        with self.assertRaises(ValueError):
            confirm_publishing(self.config, ledger, 'tiktok', link)
        ledger.execute("INSERT INTO jobs VALUES('tiktok','tt','confirmed',?)", (link,))
        value = confirm_publishing(self.config, ledger, 'tiktok', link)
        self.assertTrue(value['channels']['tiktok']['publishingVerified'])
        self.assertFalse(value['channels']['tiktok']['enabled'])
        self.assertFalse(self.config['channels']['tiktok']['publishingVerified'])
        self.config['channels']['tiktok']['enabled'] = True
        with self.assertRaises(ValueError):
            confirm_publishing(self.config, ledger, 'tiktok', link)
