"""One frozen, owner-authorized Bluesky test while recurring publishing is paused."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from bluesky_adapter import BlueskyAdapter, HANDLE
from identities import pin
from prepare import eligible
from runner import Ledger, UTC, iso, lock


def execute(ledger, config, plan, approved_hash, adapter, now):
    if hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest() != approved_hash:
        raise ValueError('Exact test plan mismatch')
    channel = config['channels']['bluesky']
    did = pin(config, 'blueskyDid')
    if (plan.get('kind') != 'one-time-bluesky-test' or plan.get('recurringPublishing') is not False
            or plan['account'] != did or channel['accountId'] != did or not channel['identityVerified']
            or channel['profileUrl'] != 'https://bsky.app/profile/'+HANDLE or channel['route'] != 'bluesky'
            or not config['paused'] or any(c['enabled'] for c in config['channels'].values())
            or not eligible(plan['payload']['episode'], now)):
        raise ValueError('Unexpected test scope')
    payload = plan['payload']
    existing = ledger.db.execute('SELECT * FROM jobs WHERE platform=? AND account=? AND episode=?',
                                 ('bluesky', did, payload['episode']['id'])).fetchone()
    if existing and (existing['slot'] != plan['slot'] or json.loads(existing['payload']) != payload):
        raise ValueError('Episode already reserved')
    if not existing:
        if abs((now-dt.datetime.fromisoformat(plan['slot'])).total_seconds()) > 7200:
            raise ValueError('Undispatched test expired')
        key = ledger.enqueue('bluesky', did, plan['slot'], payload)
    else:
        key = existing['id']
    row = dict(ledger.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())
    try:
        if row['status'] == 'ready':
            ledger.update(key, 'dispatching', attempts=row['attempts']+1, dispatched_at=iso(now))
            row = dict(ledger.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())
            receipt = adapter.publish(row, payload)
            ledger.update(key, 'accepted', remote_id=receipt['remoteId'])
        elif row['status'] in ('dispatching', 'accepted', 'uncertain'):
            result = adapter.reconcile(row, payload)
            if result['status'] == 'confirmed':
                ledger.update(key, 'confirmed', remote_id=result['remoteId'], permalink=result['permalink'],
                              published_at=result['publishedAt'], error=None)
            elif result['status'] == 'failed':
                ledger.update(key, 'blocked', error='processing')
    except Exception as error:
        ledger.update(key, 'uncertain', error=getattr(error, 'category', 'network'))
    row = ledger.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
    return {'status': row['status'], 'permalink': row['permalink'], 'error': row['error']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--approved-sha256', required=True)
    args = parser.parse_args()
    config = json.loads(Path('/etc/scalar-social/config.json').read_text())
    plan = json.loads(Path(args.plan).read_text())
    with lock(Path('/var/lib/scalar-social/runner.lock')):
        ledger = Ledger('/var/lib/scalar-social/ledger.sqlite3')
        print(json.dumps(execute(ledger, config, plan, args.approved_sha256,
                                BlueskyAdapter(ledger, config), dt.datetime.now(UTC))))
