from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from inspect_buffer import inspect
from runner import Ledger


class InspectorTests(unittest.TestCase):
    def test_unique_org_resolves_and_every_call_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp)/'ledger.sqlite3')
            def transport(query, variables, token):
                if not variables:
                    return {'account': {'organizations': [{'id': 'org', 'name': 'test'}]}}
                return {'channels': [{'id': 'c', 'scopes': []}]}
            result = inspect({}, ledger, 'fixture', transport)
            self.assertEqual(result['organizationId'], 'org')
            self.assertEqual(ledger.db.execute('SELECT count(*) FROM calls').fetchone()[0], 2)
            self.assertFalse(result['publicationEnabled'])
            ledger.db.close()

    def test_multiple_orgs_requires_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp)/'ledger.sqlite3')
            result = inspect({}, ledger, 'fixture', lambda *args: {'account': {'organizations': [{'id': 'a'}, {'id': 'b'}]}})
            self.assertTrue(result['requiresOrganizationChoice'])
            self.assertNotIn('channels', result)
            ledger.db.close()
