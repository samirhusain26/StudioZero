"""Offline end-to-end queue simulation. Never opens network or loads credentials."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
from runner import Ledger, UTC, run_jobs
from prepare import BatchPreparer
from buffer_adapter import PublishError

ROOT=Path(__file__).resolve().parents[2]

class SimulatedPlatforms:
    def __init__(self):self.calls=[]
    def publish(self,job,payload):
        self.calls.append({'operation':'publish','platform':job['platform'],'episode':payload['episode']['id']})
        if job['platform']=='instagram':raise PublishError('authorization')
        if job['platform']=='youtube':raise TimeoutError()
        return {'remoteId':'simulated-'+job['episode']}
    def reconcile(self,job,payload):
        self.calls.append({'operation':'reconcile','platform':job['platform'],'episode':payload['episode']['id']})
        if job['platform']=='youtube':raise PublishError('rate_limit',3600)
        return {'status':'confirmed','remoteId':'simulated-'+job['episode'],
                'permalink':'https://example.invalid/simulated/'+job['episode'],
                'publishedAt':job['slot']}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        state=Path(tmp);ledger=Ledger(state/'ledger.sqlite3')
        config=json.loads((ROOT/'publisher/config.example.json').read_text())
        config.update(paused=False,format='chained')
        for platform in ('x','instagram','youtube'):
            config['channels'][platform].update(enabled=True,accountId='simulated-'+platform)
        catalog=json.loads((ROOT/'engines/motion/out/social-site/catalog.json').read_text())
        catalog['rightsReviewed']=True # Simulation fixture only; never changes reviewed live catalogue.
        path=state/'catalog.json';path.write_text(json.dumps(catalog))
        config['approval']={'catalogSha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        now=dt.datetime(2026,10,6,12,tzinfo=UTC)
        parts=[]
        def assembler(keys):
            parts.append(keys)
            return {'url':'https://example.invalid/simulated.mp4','sha256':'simulated','rightsReviewed':True}
        preparer=BatchPreparer(ledger,config,state,path,assembler,lambda:now)
        adapter=SimulatedPlatforms();preparer.fill(now)
        run_jobs(ledger,config,adapter,now,prepare=preparer.prepare)
        first={r['platform']:r['status'] for r in ledger.db.execute('SELECT * FROM jobs WHERE slot=?',(now.isoformat(),))}
        assert first=={'x':'accepted','instagram':'blocked','youtube':'uncertain'},first
        run_jobs(ledger,config,adapter,now+dt.timedelta(hours=1),prepare=preparer.prepare)
        assert ledger.db.execute("SELECT status FROM jobs WHERE platform='youtube' AND slot=?",(now.isoformat(),)).fetchone()[0]=='uncertain'
        # Miss the next day: expire its ready X job, then publish the following day.
        now+=dt.timedelta(days=2)
        run_jobs(ledger,config,adapter,now,prepare=preparer.prepare)
        xrow=ledger.db.execute("SELECT * FROM jobs WHERE platform='x' AND slot=?",(now.isoformat(),)).fetchone()
        payload=json.loads(xrow['payload'])
        assert payload['previous']['episode']['id']==catalog['episodes'][0]['id']
        assert sum(c['operation']=='publish' and c['platform']=='youtube' for c in adapter.calls)==1
        count=len(adapter.calls);run_jobs(ledger,config,adapter,now,pause=lambda:True,prepare=preparer.prepare)
        assert len(adapter.calls)==count
        report={'simulationOnly':True,'networkCalls':0,'publicPosts':0,'firstDispatch':first,
                'missedDayChainPredecessor':payload['previous']['episode']['id'],
                'uncertainYouTubePublishAttempts':1,'pausePreventedCalls':True,
                'jobs':[dict(r) for r in ledger.db.execute('SELECT platform,episode,slot,status FROM jobs ORDER BY slot,platform')],
                'simulatedAdapterOperations':adapter.calls}
        out=ROOT/'engines/motion/out/social-qa/dry-run.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('jobs','simulatedAdapterOperations')}))
        ledger.db.close()

if __name__=='__main__':main()
