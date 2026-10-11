"""One approved Threads video test; recurring configuration remains paused."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from prepare import eligible
from runner import Ledger, UTC, iso, lock
from threads_adapter import ThreadsAdapter
from identities import pin


def execute(ledger, config, plan, approved_hash, adapter, now):
    if hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()!=approved_hash:
        raise ValueError('Plan approval mismatch')
    channel=config['channels']['threads']
    if (plan.get('kind')!='one-time-threads-test' or plan.get('recurringPublishing') is not False
        or plan['account']!=pin(config,'threadsUserId') or channel['accountId']!=plan['account']
        or not channel['identityVerified'] or channel['threadsFormat']!='video'
        or not config['paused'] or any(c['enabled'] for c in config['channels'].values())
        or not eligible(plan['payload']['episode'],now)):
        raise ValueError('Unexpected test scope')
    payload=plan['payload']
    existing=ledger.db.execute('SELECT * FROM jobs WHERE platform=? AND account=? AND episode=?',('threads',plan['account'],payload['episode']['id'])).fetchone()
    if existing and (existing['slot']!=plan['slot'] or json.loads(existing['payload'])!=payload):raise ValueError('Episode already reserved')
    if not existing:
        if now-dt.datetime.fromisoformat(plan['slot'])>dt.timedelta(hours=24):raise ValueError('Expired undispatched test')
        key=ledger.enqueue('threads',plan['account'],plan['slot'],payload)
    else:key=existing['id']
    row=dict(ledger.db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())
    if row['status']=='ready':
        ledger.update(key,'dispatching',attempts=row['attempts']+1,dispatched_at=iso(now))
        row=dict(ledger.db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())
        try:
            receipt=adapter.publish(row,payload)
            ledger.update(key,'accepted',remote_id=receipt['remoteId'])
        except Exception as error:
            ledger.update(key,'uncertain',error=getattr(error,'category','network'))
    elif row['status'] in ('dispatching','accepted','uncertain'):
        try:
            result=adapter.reconcile(row,payload)
            if result['status']=='confirmed':
                ledger.update(key,'confirmed',remote_id=result['remoteId'],permalink=result['permalink'],published_at=result['publishedAt'],error=None)
            elif result['status']=='failed':ledger.update(key,'blocked',error='processing')
        except Exception as error:ledger.update(key,'uncertain',error=getattr(error,'category','network'))
    row=ledger.db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
    return {'status':row['status'],'remoteId':row['remote_id'],'permalink':row['permalink'],'error':row['error']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--approved-sha256',required=True);args=parser.parse_args()
    config=json.loads(Path('/etc/scalar-social/config.json').read_text());plan=json.loads(Path(args.plan).read_text())
    with lock(Path('/var/lib/scalar-social/runner.lock')):
        ledger=Ledger('/var/lib/scalar-social/ledger.sqlite3')
        print(json.dumps(execute(ledger,config,plan,args.approved_sha256,ThreadsAdapter(ledger,config),dt.datetime.now(UTC))))
