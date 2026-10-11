"""One explicitly approved first-post test, without enabling recurring publishing.

The frozen plan names exact accounts, clip hash and captions. Dispatch uses the
existing ledger and Buffer adapter; every subsequent invocation reconciles rather
than recreating a request. Scheduler eligibility is never asserted in advance.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from buffer_adapter import BufferAdapter, verify_media
from identities import IdentityMissing, expected_buffer
from prepare import caption, eligible
from runner import Ledger, UTC, iso, lock


def digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def verified_buffer_account(config, platform):
    if platform not in ('x', 'instagram', 'youtube', 'tiktok'):
        return False
    c = config['channels'][platform]
    if not c.get('accountId') or not c.get('identityVerified') or c.get('route') != 'buffer':
        return False
    if platform == 'tiktok':
        return (c.get('profileUrl', '').rstrip('/') == 'https://www.tiktok.com/@studiozeroflow'
                and bool(c.get('providerAccountId')))
    try:
        return c['accountId'] == expected_buffer(config)[platform][1]
    except IdentityMissing:
        return False


def valid_platforms(platforms):
    return (1 <= len(platforms) <= 3 and len(set(platforms)) == len(platforms)
            and all(p in ('x', 'instagram', 'youtube', 'tiktok') for p in platforms))


def build_plan(config, catalog, episode_id, now, platforms=('x', 'instagram', 'youtube')):
    if not valid_platforms(platforms):
        raise ValueError('Unexpected Buffer test platform scope')
    if not config['paused'] or any(c['enabled'] for c in config['channels'].values()):
        raise ValueError('First-post test requires paused recurring publishing')
    if config['media']['baseUrl'] != 'https://scalar-social-media.pages.dev':
        raise ValueError('Unexpected media host')
    episodes = [e for e in catalog['episodes'] if e['id'] == episode_id]
    if len(episodes) != 1 or not eligible(episodes[0], now):
        raise ValueError('Episode source verification failed')
    ep = episodes[0]
    clip = catalog['clips'][episode_id+':self']
    if not re.fullmatch(r'clips/[a-zA-Z0-9-]+\.mp4', clip['path']) or not re.fullmatch(r'[a-f0-9]{64}', clip['sha256']) or clip['frames'] != 900:
        raise ValueError('Expected reviewed 30-second self-contained clip')
    jobs = []
    for platform in platforms:
        c = config['channels'][platform]
        if not verified_buffer_account(config, platform):
            raise ValueError('Expected verified Buffer account')
        text, link = caption(ep, platform, 'self-contained')
        metadata = {}
        if platform == 'instagram':
            metadata = {'instagram': {'type': 'reel', 'shouldShareToFeed': True}}
        if platform == 'youtube':
            metadata = {'youtube': {'title': ' '.join(ep['question'])[:87]+' #Shorts', 'categoryId': '27', 'privacy': 'public', 'madeForKids': False, 'license': 'youtube', 'notifySubscribers': True, 'embeddable': True, 'isAiGenerated': False}}
        jobs.append({'platform': platform, 'account': c['accountId'], 'profileUrl': c['profileUrl'],
                     'providerAccountId': c.get('providerAccountId'),
                     'payload': {'episode': ep, 'caption': text, 'link': link, 'format': 'self-contained',
                                 'media': {'url': config['media']['baseUrl']+'/'+clip['path'], 'sha256': clip['sha256'], 'rightsReviewed': True}, 'metadata': metadata}})
    return {'version': 1, 'kind': 'one-time-first-post', 'slot': iso(now), 'jobs': jobs,
            'reviewScope': 'Selected silent SocialEpisode clip only; own text/vector maps/OFL fonts; no legacy audio/photos',
            'recurringPublishing': False}


def execute(ledger, config, plan, approved_hash, adapter, now, reconcile_only=False):
    if digest(plan) != approved_hash or plan.get('kind') != 'one-time-first-post' or plan.get('recurringPublishing') is not False:
        raise ValueError('Exact one-time plan approval required')
    # Recheck identities/content against current paused config without changing it.
    if not config['paused'] or any(c['enabled'] for c in config['channels'].values()):
        raise ValueError('Recurring publisher must remain paused')
    if not valid_platforms([j['platform'] for j in plan['jobs']]):
        raise ValueError('Unexpected platform scope')
    for job in plan['jobs']:
        c = config['channels'][job['platform']]
        if (not verified_buffer_account(config, job['platform']) or job['account'] != c['accountId']
                or job['profileUrl'] != c['profileUrl']
                or 'providerAccountId' in job and job['providerAccountId'] != c.get('providerAccountId')):
            raise ValueError('Account scope changed')
        if not eligible(job['payload']['episode'], now):
            raise ValueError('Source is no longer eligible')
    report = []
    for job in plan['jobs']:
        existing = ledger.db.execute('SELECT * FROM jobs WHERE platform=? AND account=? AND episode=?',
                                     (job['platform'], job['account'], job['payload']['episode']['id'])).fetchone()
        if existing and (existing['slot'] != plan['slot'] or json.loads(existing['payload']) != job['payload']):
            raise ValueError('Episode already reserved with different scope')
        if not existing:
            if reconcile_only:
                report.append({'platform': job['platform'], 'status': 'not-dispatched'})
                continue
            ledger.enqueue(job['platform'], job['account'], plan['slot'], job['payload'])
        row = dict(ledger.db.execute('SELECT * FROM jobs WHERE platform=? AND account=? AND slot=?',
                                    (job['platform'], job['account'], plan['slot'])).fetchone())
        try:
            if row['status'] == 'blocked' and row['error'] == 'media' and not row['remote_id'] and row['attempts'] == 1 and not reconcile_only:
                # BufferAdapter validates media before its first API call. A media
                # failure therefore proves no mutation occurred; reverify bytes
                # before allowing one corrected attempt. Never reset uncertainty.
                verify_media(job['payload'], config)
                ledger.update(row['id'], 'ready', error=None)
                row['status'] = 'ready'
            if row['status'] == 'ready' and not reconcile_only:
                if abs((now-dt.datetime.fromisoformat(plan['slot'])).total_seconds()) > 7200:
                    raise ValueError('First-post plan expired before dispatch')
                ledger.update(row['id'], 'dispatching', attempts=row['attempts']+1, dispatched_at=iso(now))
                receipt = adapter.publish(row, job['payload'])
                ledger.update(row['id'], 'accepted', remote_id=receipt['remoteId'], error=None)
            elif row['status'] in ('dispatching', 'uncertain', 'accepted'):
                receipt = adapter.reconcile(row, job['payload'])
                if receipt['status'] == 'confirmed':
                    ledger.update(row['id'], 'confirmed', remote_id=receipt['remoteId'], permalink=receipt['permalink'], published_at=receipt['publishedAt'], error=None)
                elif receipt['status'] == 'failed':
                    ledger.update(row['id'], 'failed', error='remote_rejected')
        except Exception as error:
            category = getattr(error, 'category', 'uncertain')
            # Never automatically repeat a failed/uncertain first-post mutation.
            status = 'blocked' if category in ('authorization', 'rejected', 'budget', 'media') else 'uncertain'
            ledger.update(row['id'], status, error=category)
        result = dict(ledger.db.execute('SELECT platform,status,remote_id,permalink,error FROM jobs WHERE id=?', (row['id'],)).fetchone())
        report.append(result)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=('plan', 'dispatch', 'reconcile'))
    p.add_argument('--config', default='/etc/scalar-social/config.json')
    p.add_argument('--state', default='/var/lib/scalar-social')
    p.add_argument('--catalog', default='/var/lib/scalar-social/catalog.json')
    p.add_argument('--episode', default='ep01')
    p.add_argument('--platform', action='append', choices=('x', 'instagram', 'youtube', 'tiktok'),
                   help='Limit the frozen test to selected Buffer channels; repeat up to three times')
    p.add_argument('--plan', required=True)
    p.add_argument('--approved-sha256')
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text())
    now = dt.datetime.now(UTC)
    if a.command == 'plan':
        plan = build_plan(config, json.loads(Path(a.catalog).read_text()), a.episode, now,
                          a.platform or ('x', 'instagram', 'youtube'))
        with Path(a.plan).open('x') as f:
            f.write(json.dumps(plan, indent=2)+'\n')
        print(json.dumps({'planSha256': digest(plan), 'plan': plan}, indent=2))
        return
    with lock(Path(a.state)/'runner.lock'):
        ledger = Ledger(Path(a.state)/'ledger.sqlite3')
        try:
            result = execute(ledger, config, json.loads(Path(a.plan).read_text()), a.approved_sha256,
                             BufferAdapter(ledger, config), now, a.command == 'reconcile')
            print(json.dumps({'recurringPublishing': False, 'jobs': result}, indent=2))
        finally:
            ledger.db.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError):
        raise SystemExit('First-post test held: configuration/plan/storage validation failed.')
