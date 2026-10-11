import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
from first_post import build_plan, digest, execute
from runner import Ledger, UTC


class Adapter:
    def __init__(self, error=False): self.published=[]; self.reconciled=[]; self.error=error
    def publish(self, job, payload):
        self.published.append(job['platform'])
        if self.error: raise TimeoutError()
        return {'remoteId': 'remote-'+job['platform']}
    def reconcile(self, job, payload):
        self.reconciled.append(job['platform'])
        return {'status': 'confirmed', 'remoteId': job['remote_id'], 'permalink': 'https://example.test/post', 'publishedAt': '2026-10-06T03:30:00+00:00'}


class FirstPostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.ledger=Ledger(Path(self.temp.name)/'ledger.sqlite3')
        self.config=json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config['media']['baseUrl']='https://scalar-social-media.pages.dev'
        for name in ('x','instagram','youtube'): self.config['channels'][name]['identityVerified']=True
        self.now=dt.datetime(2026,10,6,3,30,tzinfo=UTC)
        ep=json.loads((ROOT/'publisher/tests/fixtures/social-bank.json').read_text())['episodes'][0]
        self.catalog={'episodes':[ep], 'clips':{ep['id']+':self': {'path':'clips/test.mp4','sha256':'a'*64,'frames':900}}}
        self.plan=build_plan(self.config,self.catalog,ep['id'],self.now)
    def tearDown(self): self.ledger.db.close(); self.temp.cleanup()
    def test_dispatch_then_reconcile_never_republishes_or_enables_scheduler(self):
        original=copy.deepcopy(self.config); a=Adapter()
        execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        result=execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        self.assertEqual(a.published,['x','instagram','youtube']); self.assertEqual(len(a.reconciled),3)
        self.assertTrue(all(j['status']=='confirmed' for j in result)); self.assertEqual(self.config,original)
    def test_uncertain_dispatch_only_reconciles(self):
        a=Adapter(error=True)
        execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        self.assertEqual(len(a.published),3); self.assertEqual(len(a.reconciled),3)
    def test_tampered_plan_makes_no_calls(self):
        approved=digest(self.plan);self.plan['jobs'][0]['payload']['caption']='changed';a=Adapter()
        with self.assertRaises(ValueError):execute(self.ledger,self.config,self.plan,approved,a,self.now)
        self.assertEqual(a.published,[])
    def test_changed_account_makes_no_calls(self):
        self.config['channels']['youtube']['accountId']='wrong';a=Adapter()
        with self.assertRaises(ValueError):execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        self.assertEqual(a.published,[])
    def test_reconcile_does_not_create_jobs(self):
        a=Adapter();execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now,True)
        self.assertEqual(a.published,[]);self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
    def test_unsupported_scope_rejected(self):
        self.plan['jobs'][0]['platform']='tiktok';a=Adapter()
        with self.assertRaises(ValueError):execute(self.ledger,self.config,self.plan,digest(self.plan),a,self.now)
        self.assertEqual(a.published,[])
    def test_short_and_reel_metadata(self):
        self.assertEqual(self.plan['jobs'][1]['payload']['metadata']['instagram']['type'],'reel')
        self.assertTrue(self.plan['jobs'][2]['payload']['metadata']['youtube']['title'].endswith('#Shorts'))
        self.assertFalse(self.config['channels']['youtube']['publishingVerified'])

    def test_tiktok_only_test_never_posts_to_other_channels(self):
        self.config['channels']['tiktok'].update(accountId='new-tiktok-connection', providerAccountId='owned-id',
            identityVerified=True, route='buffer')
        plan = build_plan(self.config, self.catalog, self.catalog['episodes'][0]['id'], self.now, ('tiktok',))
        a = Adapter()
        execute(self.ledger, self.config, plan, digest(plan), a, self.now)
        execute(self.ledger, self.config, plan, digest(plan), a, self.now)
        self.assertEqual(a.published, ['tiktok'])
        self.assertEqual(a.reconciled, ['tiktok'])
        self.assertFalse(self.config['channels']['tiktok']['publishingVerified'])
        self.config['channels']['tiktok']['providerAccountId'] = 'different-id'
        with self.assertRaises(ValueError):
            execute(self.ledger, self.config, plan, digest(plan), a, self.now)

    def test_duplicate_test_platform_is_rejected_before_any_dispatch(self):
        with self.assertRaises(ValueError):
            build_plan(self.config, self.catalog, self.catalog['episodes'][0]['id'], self.now, ('x', 'x'))


if __name__=='__main__': unittest.main()
