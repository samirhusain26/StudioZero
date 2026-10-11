"""Paused-only hosting test. Deploys cached static media, never calls social APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from prepare import deploy_site
from runner import Ledger, lock
from verify_delivery import verify


def probe(config, state, catalog):
    if not config['paused'] or any(c['enabled'] for c in config['channels'].values()):
        raise ValueError('Probe requires all channels disabled and publisher paused')
    state = Path(state)
    site = state/'site'
    manifest = json.loads(Path(catalog).read_text())
    if not manifest['clips']:
        raise ValueError('No clips')
    for clip in manifest['clips'].values():
        if not re.fullmatch(r'clips/[a-zA-Z0-9-]+\.mp4', clip['path']):
            raise ValueError('Invalid clip path')
        path = site/clip['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != clip['sha256']:
            raise ValueError('Cached clip verification failed')
    (site/'catalog.json').write_bytes(Path(catalog).read_bytes())
    (site/'index.html').write_text('<!doctype html><html lang="en"><meta name="robots" content="noindex"><title>Scalar puzzle media</title><h1>Scalar puzzle media</h1><a href="https://www.scalargame.com">Play the daily set</a></html>')
    first = next(iter(manifest['clips'].values()))
    target = site/'published'/(first['sha256']+'.mp4')
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        shutil.copyfile(site/first['path'], target)
    # Reuse the existing full-site retention and conservative deployment budget.
    ledger = Ledger(state/'ledger.sqlite3')
    try:
        deploy_site(ledger, config, site)
        url = config['media']['baseUrl'].rstrip('/')+'/published/'+target.name
        delivery = verify(url, first['sha256'])
        return {'mediaUrl': url, **delivery, 'socialPosts': 0, 'publicationEnabled': False}
    finally:
        ledger.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--catalog', default='/var/lib/scalar-social/catalog.json')
    args = parser.parse_args()
    try:
        with lock(Path(args.state)/'runner.lock'):
            print(json.dumps(probe(json.loads(Path(args.config).read_text()), args.state, args.catalog), indent=2))
    except Exception as error:
        category=getattr(error,'category',type(error).__name__)
        raise SystemExit('Media hosting probe failed; category: '+category+'. No social publication attempted or response body logged.')
