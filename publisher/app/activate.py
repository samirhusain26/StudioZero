"""Activation (sudo). --check prints the readiness checklist; --apply --confirm-zero-spend enables exactly the
approved manifest scope, records the evidence flags, unpauses and enables the publisher timer.

--apply is the owner's one-time first activation. After it, --auto (root, from the approve and autopilot units)
keeps the configuration on each newly approved schedule: same checklist, never resumes an owner pause, always exits 0.
Every system call goes through an injectable runner (tests never execute systemctl).
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))  # root runs this with python3 -I, which omits the script folder

import runner
import operations
from configure_paused import save
from ui_approval import (Failure, MANIFEST_CAP, RESULT_CAP, SHA, current_manifest, finished_keys, intended_config,
                         ledger_key, read_capped)

UTC = dt.timezone.utc
MONITOR_MAX_AGE = 30*60
TOKEN_MARGIN = 2*86400
NEEDS_REVIEW = ('uncertain', 'dispatching', 'blocked', 'failed')
TIMER_ROW = 'Publisher timer is currently disabled'
AUTO_IGNORED = ('activatedAt', 'evidence')


class Refused(Exception):
    pass


def system(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout


def show(run, unit, *props):
    args = ['systemctl', 'show', unit]
    for prop in props:
        args += ['-p', prop]
    code, out = run(args)
    values = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
    return code, values


@contextlib.contextmanager
def ledger_owner_preserved(db_path):
    """Reading the WAL ledger as root may create -wal/-shm files; hand them back to the ledger owner."""
    try:
        yield
    finally:
        if os.geteuid() == 0 and db_path.is_file():
            owner = db_path.stat()
            for suffix in ('-wal', '-shm'):
                extra = Path(str(db_path)+suffix)
                with contextlib.suppress(OSError):
                    if extra.lstat().st_uid != owner.st_uid:
                        os.lchown(extra, owner.st_uid, owner.st_gid)


def _expected_owner():
    import grp
    return 0, grp.getgrnam('scalar-social').gr_gid


def checklist(config_path, state, *, run=system, now=None, monotonic=time.monotonic, owner=None):
    """[(label, ok, detail)] plus context {config, manifest, sha} for --apply."""
    state, config_path = Path(state), Path(config_path)
    now = now or dt.datetime.now(UTC)
    rows, ctx = [], {}

    def item(label, check):
        try:
            detail = check()
            rows.append((label, True, detail or ''))
        except Refused as error:
            rows.append((label, False, str(error)))
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            rows.append((label, False, 'Could not be checked: file or service unavailable.'))

    def permissions():
        info = os.stat(config_path)
        uid, gid = owner or _expected_owner()
        if info.st_mode & 0o777 != 0o640 or (info.st_uid, info.st_gid) != (uid, gid):
            raise Refused(f'Found mode {info.st_mode & 0o777:o}; run: sudo chown root:scalar-social {config_path} && '
                          f'sudo chmod 0640 {config_path}')
        ctx['config'] = json.loads(config_path.read_text())
    item('Configuration file is 0640 root:scalar-social', permissions)
    if 'config' not in ctx:
        with contextlib.suppress(OSError, ValueError):
            ctx['config'] = json.loads(config_path.read_text())
    config = ctx.get('config') or {}

    def bound():
        sha, manifest = current_manifest(state)
        if not sha:
            raise Refused('No approved schedule. Approve a draft in the UI first.')
        approval = config.get('approval') or {}
        if approval.get('manifestSha256') != sha or not approval.get('approvedAt'):
            raise Refused('The approved schedule is not bound in the configuration (approval service did not finish).')
        if hashlib.sha256(read_capped(state/'manifests'/f'{sha}.json', MANIFEST_CAP)).hexdigest() != sha:
            raise Refused('The stored manifest copy does not match the approved schedule.')
        if not isinstance(manifest.get('scope'), list) or not manifest['scope'] or not SHA.fullmatch(str(manifest.get('scopeHash'))):
            raise Refused('The approved schedule has no channel scope.')
        if {j['platform'] for j in manifest['jobs']} != set(manifest['scope']):
            raise Refused('The approved schedule scope does not match its posts.')
        ctx.update(sha=sha, manifest=manifest)
        return f'manifest {sha[:12]}, {len(manifest["jobs"])} posts, scope {", ".join(manifest["scope"])}'
    item('Approved schedule exists and is bound by hash', bound)
    manifest = ctx.get('manifest')

    def need_manifest():
        if not manifest or not config:
            raise Refused('Needs the bound approved schedule above.')

    def scope_verified():
        need_manifest()
        try:
            ctx['intended'], ctx['scopeHash'] = intended_config(config, manifest['scope'])
        except Failure as failure:
            raise Refused(failure.message) from None
    item('Every channel in the schedule has verified identity and publishing', scope_verified)

    def scope_hash():
        need_manifest()
        if 'scopeHash' not in ctx:
            raise Refused('Needs verified channels above.')
        if ctx['scopeHash'] != manifest['scopeHash']:
            raise Refused('The configuration changed since this schedule was approved. Approve a new draft.')
    item('Configuration with exactly these channels matches the approved scope hash', scope_hash)

    def media():
        need_manifest()
        sha = ctx['sha']
        try:
            evidence = json.loads(read_capped(state/'manifests'/f'{sha}.verification.json', RESULT_CAP*16))
        except FileNotFoundError:
            raise Refused('No public media verification for this schedule.') from None
        verified = {(u.get('url'), u.get('sha256')) for u in evidence.get('urls', []) if u.get('verified') is True}
        done = set()
        if (state/'ledger.sqlite3').is_file():
            with contextlib.closing(sqlite3.connect((state/'ledger.sqlite3').resolve().as_uri()+'?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                done = finished_keys(db.execute('SELECT id, status FROM jobs'))
        channels = (ctx.get('config') or {}).get('channels') or {}
        # Posts already finished never fetch their media again (their video may have been removed from the Pi).
        wanted = {(j['payload']['media']['url'], j['payload']['media']['sha256'])
                  for j in manifest['jobs'] if j['payload'].get('media')
                  and ledger_key(j['platform'], (channels.get(j['platform']) or {}).get('accountId'), j['slot']) not in done}
        if evidence.get('manifestSha256') != sha or not evidence.get('allVerified') or not wanted <= verified:
            raise Refused('Some public media URLs were not verified by hash.')
        ctx['verificationFile'] = f'manifests/{sha}.verification.json'
        return f'{len(wanted)} URLs verified'
    item('Every public media URL was verified by hash', media)

    def monitor():
        code, values = show(run, 'scalar-social-monitor.service', 'Result', 'ExecMainExitTimestampMonotonic', 'ExecMainStatus')
        exited = int(values.get('ExecMainExitTimestampMonotonic') or 0)
        age = monotonic() - exited/1e6
        if code or values.get('Result') != 'success' or values.get('ExecMainStatus') != '0' or not exited:
            raise Refused('The monitor did not last finish successfully; check the external alert first.')
        if not 0 <= age <= MONITOR_MAX_AGE:
            raise Refused(f'The monitor last succeeded {int(age//60)} minutes ago (needs 30 or fewer).')
        db = state/'ledger.sqlite3'
        with ledger_owner_preserved(db):
            report = operations.inspect(config_path, state, now)
        if not report['healthy']:
            raise Refused('Monitor issues: '+', '.join(report['issues']))
        ctx['monitorEvidence'] = f'scalar-social-monitor.service Result=success {int(age//60)} min before activation; health ok'
        return f'last success {int(age//60)} min ago; health ok'
    item('Monitor succeeded in the last 30 minutes and reports healthy', monitor)

    def ledger():
        db = state/'ledger.sqlite3'
        if not db.is_file():
            return 'no ledger yet'
        with ledger_owner_preserved(db), contextlib.closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True)) as conn:
            counts = dict(conn.execute('SELECT status,count(*) FROM jobs GROUP BY status'))
        bad = {k: counts[k] for k in NEEDS_REVIEW if counts.get(k)}
        if bad:
            raise Refused('Resolve these first: '+', '.join(f'{v} {k}' for k, v in bad.items()))
    item('No uncertain, dispatching, blocked or failed posts', ledger)

    def tokens():
        need_manifest()
        problems = []
        for platform in manifest['scope']:
            channel = config['channels'].get(platform, {})
            if platform not in ('threads', 'instagram') or channel.get('route') != platform:
                continue
            if platform == 'instagram' and (state/'instagram-token-failure.json').exists():
                problems.append('Instagram token renewal failed')
                continue
            try:
                expiry = dt.datetime.fromisoformat(json.loads(read_capped(state/f'{platform}-token-health.json', 4096))['expiresAt'])
                if (expiry-now).total_seconds() < TOKEN_MARGIN:
                    problems.append(f'{platform.title()} token expires within 2 days')
            except (OSError, ValueError, KeyError, TypeError):
                problems.append(f'{platform.title()} token health missing')
        if problems:
            raise Refused('; '.join(problems))
    item('Tokens for scheduled Threads/Instagram are healthy', tokens)

    def service():
        code, values = show(run, 'scalar-social.service', 'ExecStart')
        if code or f'--manifest {state/"manifests"/"approved.json"}' not in values.get('ExecStart', ''):
            raise Refused('scalar-social.service does not read the approved manifest; install the UI release first.')
    item('Publisher service reads the approved manifest', service)

    def timer():
        _, enabled = run(['systemctl', 'is-enabled', 'scalar-social.timer'])
        _, active = run(['systemctl', 'is-active', 'scalar-social.timer'])
        if enabled.strip() != 'disabled' or active.strip() != 'inactive':
            raise Refused(f'Timer is {enabled.strip() or "unknown"}/{active.strip() or "unknown"}; expected disabled/inactive.')
    item(TIMER_ROW, timer)
    return rows, ctx


def report(rows, out=print):
    for n, (label, ok, detail) in enumerate(rows, 1):
        out(f'{n:2}. {"PASS" if ok else "FAIL"}  {label}'+(f' — {detail}' if detail else ''))


def activated_config(ctx, now, zero_spend_note):
    """The checked configuration with exactly the approved scope enabled, unpaused and the evidence recorded."""
    config, manifest = ctx['config'], ctx['manifest']
    new = json.loads(json.dumps(config))
    for platform, channel in new['channels'].items():
        channel['enabled'] = platform in manifest['scope']
    new['paused'] = False
    approval = dict(new.get('approval') or {})
    approval.update(scopeHash=runner.fingerprint(new), deploymentApproved=True, mediaDeliveryVerified=True,
                    monitoringVerified=True, zeroSpendVerified=True,
                    activatedAt=now.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    evidence={'mediaDelivery': ctx['verificationFile'], 'monitoring': ctx['monitorEvidence'],
                              'zeroSpend': zero_spend_note})
    new['approval'] = approval
    if approval['scopeHash'] != manifest['scopeHash']:
        raise Refused('Activation refused: scope hash mismatch. Nothing changed.')
    try:
        runner.validate(new, live=True)
    except ValueError as error:
        raise Refused(f'Activation refused: {error}. Nothing changed.') from None
    return new


def activate(config_path, state, *, run=system, now=None, monotonic=time.monotonic, owner=None, out=print):
    state = Path(state)
    now = now or dt.datetime.now(UTC)
    rows, ctx = checklist(config_path, state, run=run, now=now, monotonic=monotonic, owner=owner)
    report(rows, out)
    if not all(ok for _, ok, _ in rows):
        raise Refused('Activation refused: fix the FAIL items above. Nothing changed.')
    manifest = ctx['manifest']
    save(config_path, activated_config(ctx, now, 'owner confirmed with --confirm-zero-spend'))
    (state/'PAUSED').unlink(missing_ok=True)
    code, _ = run(['systemctl', 'enable', '--now', 'scalar-social.timer'])
    if code:
        raise Refused('Configuration activated but scalar-social.timer could not be enabled, so nothing will publish. '
                      f'To hold everything, run: sudo touch {state/"PAUSED"}')
    _, timers = run(['systemctl', 'list-timers', 'scalar-social.timer', '--no-pager'])
    out(f'Activated: {", ".join(manifest["scope"])} enabled for manifest {ctx["sha"][:12]}. Pause from the UI at any time.')
    out(timers.rstrip())


def _comparable(config):
    approval = {k: v for k, v in (config.get('approval') or {}).items() if k not in AUTO_IGNORED}
    return {**config, 'approval': approval}


def auto_activate(config_path, state, *, run=system, now=None, monotonic=time.monotonic, owner=None, out=print):
    """Keep the configuration on the approved schedule without the owner. Returns a plain message; anything not
    ready (or Refused) waits with nothing changed, and the next run retries. Never removes STATE/PAUSED."""
    state = Path(state)
    now = now or dt.datetime.now(UTC)
    try:
        approval = json.loads(Path(config_path).read_text()).get('approval') or {}
    except (OSError, ValueError, AttributeError):
        return 'Autopilot waits: the configuration could not be read. Nothing changed.'
    if approval.get('zeroSpendVerified') is not True:
        return 'Autopilot waits: the owner\'s first activation (--apply --confirm-zero-spend) has not run. Nothing changed.'
    if approval.get('activatedAt') and (state/'PAUSED').exists():
        return 'Paused in the UI: autopilot changes nothing until publishing is resumed.'
    rows, ctx = checklist(config_path, state, run=run, now=now, monotonic=monotonic, owner=owner)
    failed = [row for row in rows if not row[1] and row[0] != TIMER_ROW]
    if failed:
        report(failed, out)
        return 'Autopilot waits: fix the FAIL items above (the next run retries). Nothing changed.'
    config, sha = ctx['config'], ctx['sha']
    note = (approval.get('evidence') or {}).get('zeroSpend') or 'owner confirmed with --confirm-zero-spend'
    new = activated_config(ctx, now, note)
    changed = _comparable(new) != _comparable(config)
    if changed:
        save(config_path, new)
    _, enabled = run(['systemctl', 'is-enabled', 'scalar-social.timer'])
    _, active = run(['systemctl', 'is-active', 'scalar-social.timer'])
    timer_on = enabled.strip() == 'enabled' and active.strip() == 'active'
    if not timer_on:
        code, _ = run(['systemctl', 'enable', '--now', 'scalar-social.timer'])
        if code:
            return (f'Autopilot: scalar-social.timer could not be enabled{" (configuration updated)" if changed else ""}; '
                    'the next run retries.')
    if not changed and timer_on:
        return f'Autopilot: configuration already matches manifest {sha[:12]} and the publisher timer is on. Nothing changed.'
    return (f'Autopilot activated manifest {sha[:12]}: {", ".join(ctx["manifest"]["scope"])}'
            f'{"" if changed else " (configuration unchanged)"}; publisher timer on. Pause from the UI at any time.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Readiness checklist, owner first activation and autopilot (sudo).')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--auto', action='store_true', help='Autopilot (root): follow the approved schedule; exits 0 so the next run retries')
    parser.add_argument('--confirm-zero-spend', action='store_true')
    parser.add_argument('--config', default='/etc/scalar-social/config.json')
    parser.add_argument('--state', default='/var/lib/scalar-social')
    parser.add_argument('--allow-non-root-for-tests', action='store_true')
    args = parser.parse_args(argv)
    if args.check:
        rows, _ = checklist(args.config, args.state)
        report(rows)
        return 0 if all(ok for _, ok, _ in rows) else 2
    if os.geteuid() != 0 and not args.allow_non_root_for_tests:
        print('Activation must run with sudo.', file=sys.stderr)
        return 1
    if args.auto:
        try:
            print(auto_activate(args.config, args.state))
        except Refused as error:
            print(f'{error} The next run retries.')
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            print('Autopilot waits: configuration or state unavailable. The next run retries.')
        return 0
    if not args.confirm_zero_spend:
        print('Activation needs --confirm-zero-spend: confirm no paid plan, product or add-on is in use.', file=sys.stderr)
        return 1
    try:
        activate(args.config, args.state)
        return 0
    except Refused as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError, KeyError):
        print('Activation stopped: configuration or state unavailable.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
