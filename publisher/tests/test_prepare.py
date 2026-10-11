import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'publisher/app'))
from prepare import BatchPreparer, caption, eligible
from runner import Ledger, UTC, run_jobs
from buffer_adapter import PublishError


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=Path(self.tmp.name)
        self.db=Ledger(self.state/'ledger.sqlite')
        self.config=json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config.update(paused=False,format='chained')
        self.config['channels']['x'].update(enabled=True,accountId='x-1')
        self.now=dt.datetime(2026,10,5,12,tzinfo=UTC)
        self.bank=json.loads((ROOT/'publisher/tests/fixtures/social-bank.json').read_text())['episodes'][:8]
        self.catalog={'rightsReviewed':True,'episodes':self.bank,'clips':{}}
        for e in self.bank:
            for kind in ('self','hook','challenge','reminder'):
                self.catalog['clips'][e['id']+':'+kind]={'path':'unused.mp4','sha256':'fixture'}
        self.catalog['clips']['intro']={'path':'intro.mp4','sha256':'fixture'}
        path=self.state/'catalog.json';path.write_text(json.dumps(self.catalog))
        self.config['approval']={'catalogSha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        self.parts=[]
        def assemble(parts):
            self.parts.append(parts)
            return {'url':'https://media.example.test/video.mp4','sha256':'fixture','rightsReviewed':True}
        self.preparer=BatchPreparer(self.db,self.config,self.state,path,assemble,lambda:self.now)

    def tearDown(self):self.db.db.close();self.tmp.cleanup()

    def test_first_episode_has_intro_not_invented_previous(self):
        self.preparer.fill(self.now)
        row=dict(self.db.db.execute('SELECT * FROM jobs ORDER BY slot LIMIT 1').fetchone())
        result=self.preparer.prepare(row,json.loads(row['payload']))
        self.assertEqual(self.parts[0][1],'intro')
        self.assertIsNone(result['previous'])

    def test_chain_uses_last_confirmed_after_missed_day(self):
        self.preparer.fill(self.now)
        rows=self.db.db.execute('SELECT * FROM jobs ORDER BY slot').fetchall()
        self.db.update(rows[0]['id'],'confirmed',remote_id='remote-1',permalink='https://x.com/test/status/1',published_at=self.now.isoformat())
        self.db.update(rows[1]['id'],'expired')
        self.now+=dt.timedelta(days=2)
        row=dict(rows[2]);result=self.preparer.prepare(row,json.loads(row['payload']))
        self.assertEqual(result['previous']['remoteId'],'remote-1')
        self.assertEqual(self.parts[-1][1],rows[0]['episode']+':reminder')

    def test_wrong_platform_never_used_as_previous(self):
        self.db.enqueue('instagram','ig-1',(self.now-dt.timedelta(days=1)).isoformat(),{'episode':self.bank[0]})
        other=self.db.db.execute("SELECT id FROM jobs WHERE platform='instagram'").fetchone()[0]
        self.db.update(other,'confirmed',remote_id='ig-r',permalink='https://instagram.com/p/1',published_at=(self.now-dt.timedelta(days=1)).isoformat())
        self.preparer.fill(self.now)
        row=dict(self.db.db.execute("SELECT * FROM jobs WHERE platform='x' ORDER BY slot LIMIT 1").fetchone())
        self.assertIsNone(self.preparer.prepare(row,json.loads(row['payload']))['previous'])

    def test_batch_tampering_rejected(self):
        path=self.state/'catalog.json';path.write_text('{}')
        with self.assertRaises(ValueError):BatchPreparer(self.db,self.config,self.state,path)

    def test_route_migration_does_not_reuse_episodes_or_foreign_predecessors(self):
        c = self.config['channels']['x']
        c['previousAccountIds'] = ['old-buffer-connection']
        key = self.db.enqueue('x', 'old-buffer-connection', (self.now-dt.timedelta(days=1)).isoformat(),
            {'episode': self.bank[0]})
        self.db.update(key, 'confirmed', remote_id='old-buffer-post', permalink='https://x.com/test/status/1',
            published_at=(self.now-dt.timedelta(days=1)).isoformat())
        self.preparer.fill(self.now)
        rows = self.db.db.execute("SELECT * FROM jobs WHERE account='x-1' ORDER BY slot").fetchall()
        self.assertNotIn(self.bank[0]['id'], [r['episode'] for r in rows])
        self.assertIsNone(self.preparer.prepare(dict(rows[0]), json.loads(rows[0]['payload']))['previous'])

    def test_exhaustion_final_episode_reveals(self):
        self.config['queueDays']=7
        self.preparer.fill(self.now)
        self.now+=dt.timedelta(days=6)
        self.preparer.fill(self.now)
        rows=self.db.db.execute('SELECT * FROM jobs ORDER BY slot').fetchall()
        self.assertEqual(len(rows),8)
        self.assertEqual(json.loads(rows[-1]['payload'])['format'],'self-contained')

    def test_cutoff_and_malformed_dates_on_pi(self):
        ep=dict(self.bank[4]);ep['event']={**ep['event'],'playDate':'2026-10-01'};ep['provenance']={**ep['provenance'],'playDate':'2026-10-01'}
        self.assertTrue(eligible(ep,self.now))
        ep['provenance']['playDate']='2026-10-02';self.assertFalse(eligible(ep,self.now))
        ep['provenance']['playDate']='2026-02-30';self.assertFalse(eligible(ep,self.now))

    def test_exact_payload_persists_before_network(self):
        self.preparer.fill(self.now)
        class Adapter:
            def publish(inner,job,payload):
                actual=json.loads(self.db.db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
                self.assertEqual(actual,payload)
                raise TimeoutError()
        run_jobs(self.db,self.config,Adapter(),self.now,prepare=self.preparer.prepare)
        row=self.db.db.execute('SELECT * FROM jobs ORDER BY slot LIMIT 1').fetchone()
        self.assertEqual(row['status'],'uncertain')
        self.assertIn('caption',json.loads(row['payload']))

    def test_rate_limit_during_reconcile_cannot_recreate_post(self):
        self.preparer.fill(self.now)
        row=self.db.db.execute('SELECT * FROM jobs ORDER BY slot LIMIT 1').fetchone()
        self.db.update(row['id'],'accepted',remote_id='remote-1')
        class Adapter:
            def reconcile(inner,job,payload):raise PublishError('rate_limit',300)
            def publish(inner,job,payload):self.fail('Must not republish an accepted request')
        run_jobs(self.db,self.config,Adapter(),self.now)
        run_jobs(self.db,self.config,Adapter(),self.now+dt.timedelta(minutes=6))
        self.assertEqual(self.db.db.execute('SELECT status FROM jobs WHERE id=?',(row['id'],)).fetchone()[0],'uncertain')



class DeploySiteTests(unittest.TestCase):
    def setUp(self):
        import os
        from unittest import mock
        self.tmp=tempfile.TemporaryDirectory()
        base=Path(self.tmp.name)
        (base/'creds').mkdir()
        (base/'creds'/'CLOUDFLARE_API_TOKEN').write_text('tok-'+'s'*40)
        (base/'site').mkdir()
        (base/'site'/'a.mp4').write_bytes(b'x')
        self.site=base/'site'
        self.db=Ledger(base/'ledger.sqlite')
        self.config={'media':{'cloudflareAccountId':'acct','pagesProject':'scalar-social-media'}}
        patcher=mock.patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(base/'creds')})
        patcher.start();self.addCleanup(patcher.stop)

    def tearDown(self):self.db.db.close();self.tmp.cleanup()

    def deploy(self,stdout,code=0):
        import contextlib,io,subprocess
        from unittest import mock
        import prepare
        done=subprocess.CompletedProcess([],code,stdout,'')
        out=io.StringIO()
        with mock.patch.object(prepare.subprocess,'run',return_value=done),contextlib.redirect_stdout(out):
            try:
                prepare.deploy_site(self.db,self.config,self.site)
                return None,out.getvalue()
            except PublishError as error:
                return error,out.getvalue()

    def test_success_needs_the_deployment_url(self):
        error,out=self.deploy('Uploaded 1 files\n✨ Deployment complete! Take a peek over at https://1a2b3c4d.scalar-social-media.pages.dev\n')
        self.assertIsNone(error)
        self.assertIn('https://1a2b3c4d.scalar-social-media.pages.dev',out)

    def test_exit_zero_without_a_deployment_fails_with_a_redacted_tail(self):
        error,out=self.deploy('Uploading... tok-'+'s'*40+'\nSomething odd happened\n')
        self.assertIsInstance(error,PublishError)
        self.assertIn('staticDeploymentUnconfirmed',out)
        self.assertIn('Something odd happened',out)
        self.assertNotIn('s'*40,out)

    def test_new_files_upload_in_small_stages_then_the_whole_site(self):
        import contextlib,io,subprocess
        from unittest import mock
        import prepare
        for n in range(12):
            (self.site/'library').mkdir(exist_ok=True)
            (self.site/'library'/f'{n:02}.mp4').write_bytes(b'v'*(n+1))
        self.config['media']['baseUrl']='https://media.example.test'
        old={'https://media.example.test/a.mp4','https://media.example.test/library/00.mp4'}
        seen=[]
        def run(args,**kw):
            folder=Path(args[3])
            seen.append((folder,sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file())))
            return subprocess.CompletedProcess(args,0,'Deployment complete https://1a2b3c4d.scalar-social-media.pages.dev','')
        with mock.patch.object(prepare.subprocess,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
            prepare.deploy_site(self.db,self.config,self.site,served=lambda url,size:url in old)
        self.assertEqual([len(files) for _,files in seen],[8,13])
        self.assertNotEqual(seen[0][0],self.site)
        self.assertEqual(seen[-1][0],self.site)
        self.assertIn('a.mp4',seen[0][1])
        self.assertFalse((self.site.parent/'site-stage').exists())
        self.assertEqual(self.db.db.execute('SELECT count(*) FROM deployments').fetchone()[0],2)

    def test_served_check_reads_type_and_optional_length(self):
        import email.message
        from unittest import mock
        import prepare
        def answer(content_type,length=None):
            headers=email.message.Message()
            headers['Content-Type']=content_type
            if length is not None:headers['Content-Length']=length
            response=mock.MagicMock();response.__enter__.return_value.headers=headers
            return response
        cases=[(answer('video/mp4'),True),(answer('video/mp4','5'),True),(answer('video/mp4','4'),False),
               (answer('text/html; charset=utf-8'),False)]
        for response,expected in cases:
            with mock.patch.object(prepare.urllib.request,'urlopen',return_value=response):
                self.assertIs(prepare.publicly_served('https://media.example.test/a.mp4',5),expected)
        with mock.patch.object(prepare.urllib.request,'urlopen',side_effect=OSError):
            self.assertFalse(prepare.publicly_served('https://media.example.test/a.mp4',5))


if __name__=='__main__':unittest.main()
