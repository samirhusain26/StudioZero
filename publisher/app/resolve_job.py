"""Owner reconciliation (sudo) for an uncertain/accepted/dispatching job. Never publishes or retries.

--confirmed --permalink URL   the owner found the post on the platform profile
--not-published               the owner verified the post does not exist (recorded as expired, a final state)
Both need --evidence (what was checked, when). Still-waiting companions of the job are expired, never sent.
Runs under runner.lock after dropping from root to the scalar-social user.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import urllib.parse
sys.path.insert(0, str(Path(__file__).resolve().parent))  # root runs this with python3 -I, which omits the script folder

import runner

UNRESOLVED = ('uncertain', 'accepted', 'dispatching')
DOMAINS = {'instagram': ('instagram.com',), 'facebook': ('facebook.com', 'fb.watch'),
           'threads': ('threads.net', 'threads.com'), 'x': ('x.com', 'twitter.com'),
           'youtube': ('youtube.com', 'youtu.be'), 'bluesky': ('bsky.app',), 'tiktok': ('tiktok.com',)}


class Refused(Exception):
    pass


def check_permalink(platform, url):
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or '').lower()
    if (parts.scheme != 'https' or parts.username or parts.password or parts.query or parts.fragment
            or parts.port not in (None, 443) or not parts.path.strip('/')
            or not any(host == d or host.endswith('.'+d) for d in DOMAINS.get(platform, ()))):
        raise Refused(f'The permalink must be a plain https link on {", ".join(DOMAINS.get(platform, ("?",)))} '
                      'without query or credentials.')
    return url


def resolve(state, job_id, *, confirmed, permalink=None, evidence, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    evidence = re.sub(r'[\x00-\x1f\x7f]', ' ', evidence or '').strip()
    if not evidence or len(evidence) > 1000:
        raise Refused('Describe the evidence you checked (1–1000 characters).')
    state = Path(state)
    try:
        with runner.lock(state/'runner.lock'):
            ledger = runner.Ledger(state/'ledger.sqlite3')
            try:
                row = ledger.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
                if row is None:
                    raise Refused('No job with that id.')
                if row['status'] not in UNRESOLVED:
                    raise Refused(f'Job is {row["status"]}; only uncertain, accepted or dispatching jobs can be resolved.')
                at = runner.iso(now)
                detail = {'priorStatus': row['status'], 'resolution': 'confirmed' if confirmed else 'not_published',
                          'evidence': evidence}
                with ledger.db:
                    if confirmed:
                        detail['permalink'] = check_permalink(row['platform'], permalink or '')
                        ledger.db.execute("UPDATE jobs SET status='confirmed', permalink=?, published_at=?, error=NULL "
                                          'WHERE id=? AND status=?', (permalink, at, job_id, row['status']))
                    else:
                        # Final, not "needs review": the owner verified it never appeared.
                        ledger.db.execute("UPDATE jobs SET status='expired', error='owner_verified_absent' "
                                          'WHERE id=? AND status=?', (job_id, row['status']))
                    ledger.db.execute('INSERT INTO events(job,kind,at,detail) VALUES(?,?,?,?)',
                                      (job_id, 'owner_resolved', at, json.dumps(detail, sort_keys=True)))
                    # A resolved parent has no usable remote id for replies: its waiting companions end here.
                    for companion in ledger.db.execute(
                            "SELECT id FROM jobs WHERE platform=? AND account=? AND status='ready' AND dispatched_at IS NULL "
                            "AND substr(episode,1,?)=?", (row['platform'], row['account'], len(row['episode'])+1, row['episode']+'#')).fetchall():
                        ledger.db.execute("UPDATE jobs SET status='expired', error='parent_unavailable' WHERE id=?", (companion['id'],))
                        ledger.db.execute('INSERT INTO events(job,kind,at,detail) VALUES(?,?,?,?)',
                                          (companion['id'], 'expired', at, 'parent_unavailable'))
                return detail
            finally:
                ledger.db.close()
    except BlockingIOError:
        raise Refused('The publisher is running; try again in a minute. Nothing changed.') from None


def drop_to_ledger_owner(state, user='scalar-social'):
    """Root never opens files the unprivileged publisher controls: drop to that user first."""
    if os.geteuid() != 0:
        return
    account = pwd.getpwnam(user)
    for name in ('ledger.sqlite3', 'runner.lock'):
        try:
            info = os.lstat(Path(state)/name)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_uid != account.pw_uid:
            raise Refused(f'{name} is not a regular file owned by {user}; nothing changed.')
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Record the owner-verified outcome of an unresolved post.')
    parser.add_argument('job')
    outcome = parser.add_mutually_exclusive_group(required=True)
    outcome.add_argument('--confirmed', action='store_true')
    outcome.add_argument('--not-published', action='store_true')
    parser.add_argument('--permalink')
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--allow-non-root-for-tests', action='store_true')
    args = parser.parse_args(argv)
    if os.geteuid() != 0 and not args.allow_non_root_for_tests:
        print('Run with sudo.', file=sys.stderr)
        return 1
    if args.confirmed and not args.permalink:
        print('--confirmed needs --permalink.', file=sys.stderr)
        return 1
    try:
        drop_to_ledger_owner(args.state)
        detail = resolve(args.state, args.job, confirmed=args.confirmed, permalink=args.permalink, evidence=args.evidence)
        print(f'Job {args.job} recorded as {detail["resolution"]}. Nothing was published.')
        return 0
    except Refused as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError):
        print('Ledger unavailable; nothing changed.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
