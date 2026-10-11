"""Apply verified Buffer identities and public host metadata; never enables publishing."""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from identities import expected_buffer



def configure(config, report):
    config = json.loads(json.dumps(config))
    if not report.get('organizationId') or len(report.get('channels', [])) != 3:
        raise ValueError('Exactly three expected Buffer connections required')
    normalize = lambda v: (v or '').rstrip('/').lower().replace('https://www.', 'https://')
    services = {c['service'] for c in report['channels']}
    expected = expected_buffer(config)
    if services == {'twitter', 'instagram', 'youtube'}:
        selected = expected
    elif services == {'twitter', 'youtube', 'tiktok'}:
        if config['channels']['instagram']['route'] != 'instagram' or not all(
                config['channels']['instagram'].get(k) for k in ('identityVerified', 'publishingVerified')):
            raise ValueError('Verify direct Instagram before reallocating its Buffer slot')
        selected = {p: expected[p] for p in ('x', 'youtube')}
        selected['tiktok'] = ('tiktok', None, None)
    else:
        raise ValueError('Unexpected Buffer channel allocation')
    for platform, (service, account, provider) in selected.items():
        matches = [c for c in report['channels'] if (not account or c['id'] == account) and c['service'] == service]
        if len(matches) != 1:
            raise ValueError('Expected account missing')
        actual = matches[0]
        target = config['channels'][platform]
        if actual['isDisconnected'] or actual['isLocked'] or not actual.get('id') or not actual.get('serviceId'):
            raise ValueError('Connection blocked')
        if platform == 'tiktok' and normalize(target['profileUrl']) != 'https://tiktok.com/@studiozeroflow':
            raise ValueError('Unexpected TikTok profile')
        if provider:
            if actual['serviceId'] != provider:
                raise ValueError('Provider identity mismatch')
        elif normalize(actual['externalLink']) != normalize(target['profileUrl']):
            raise ValueError('Profile identity mismatch')
        # A channel already proven on this exact connection keeps its posting test (X and YouTube when
        # TikTok takes Instagram's Buffer slot); a new or changed connection must be tested again.
        kept = bool(target.get('publishingVerified') and target.get('route') == 'buffer'
                    and target.get('accountId') == actual['id'] and target.get('providerAccountId') == actual['serviceId'])
        target.update(accountId=actual['id'], providerAccountId=actual['serviceId'], route='buffer', identityVerified=True,
                      publishingVerified=kept, enabled=False, observedScopes=actual.get('scopes', []),
                      observedAllowedActions=actual.get('allowedActions', []),
                      reason=target.get('reason') if kept else
                      'API identity verified; permissions/automatic public publishing test still required')
    for channel in config['channels'].values():
        channel['enabled'] = False
    config.update(paused=True, approval=None, bufferOrganizationId=report['organizationId'])
    if not re.fullmatch(r'[0-9a-f]{32}', str(config['media'].get('cloudflareAccountId') or '')):
        raise ValueError('media.cloudflareAccountId missing in the Pi config')
    config['media'].update(baseUrl='https://scalar-social-media.pages.dev', pagesProject='scalar-social-media')
    return config


def confirm_publishing(config, ledger, platform, permalink):
    """Mark a Buffer channel's posting test passed after the owner saw the post publicly.

    The ledger must hold a confirmed post with exactly this permalink on the channel's current account.
    Never enables the channel."""
    config = json.loads(json.dumps(config))
    c = config['channels'][platform]
    if c.get('route') != 'buffer' or not c.get('identityVerified') or not c.get('accountId'):
        raise ValueError('Verify the Buffer identity first')
    if c.get('enabled'):
        raise ValueError('Channel must be disabled')
    row = ledger.execute("SELECT 1 FROM jobs WHERE platform=? AND account=? AND status='confirmed' AND permalink=?",
                         (platform, c['accountId'], permalink)).fetchone()
    if not row:
        raise ValueError('No confirmed post with that permalink on this account')
    c.update(publishingVerified=True, reason='Automatic Buffer post confirmed and checked publicly: '+permalink)
    return config


def save(path, value):
    path = Path(path)
    metadata = path.stat()
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.config-')
    try:
        os.fchmod(fd, metadata.st_mode & 0o777)
        os.fchown(fd, metadata.st_uid, metadata.st_gid)
        with os.fdopen(fd, 'w') as handle:
            handle.write(json.dumps(value, indent=2)+'\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report')
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-publishing', choices=('x', 'youtube', 'tiktok'),
                        help='Instead of --report: mark this channel publishing-verified from its confirmed first post')
    parser.add_argument('--permalink', help='Public post URL, with --confirm-publishing')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    args = parser.parse_args()
    try:
        current = json.loads(Path(args.config).read_text())
        if args.confirm_publishing:
            ledger = sqlite3.connect(f"file:{Path(args.state)/'ledger.sqlite3'}?mode=ro", uri=True)
            try:
                config = confirm_publishing(current, ledger, args.confirm_publishing, args.permalink or '')
            finally:
                ledger.close()
        else:
            config = configure(current, json.loads(Path(args.report).read_text()))
        if args.apply:
            if os.geteuid() != 0:
                raise ValueError('Apply with sudo on Pi')
            save(args.config, config)
            print('Publishing test recorded. The channel stays disabled until it is scheduled and activated.' if args.confirm_publishing
                  else 'Verified identities and media host configured. All six platforms remain disabled; approval cleared.')
        else:
            print(json.dumps(config, indent=2))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        raise SystemExit('Configuration held; expected account identity or private file validation failed.')
