import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
import activate
import resolve_job
import runner
from library_contract import canonical
from ui_approval import intended_config

SENTINEL = 'sentinel-credential-c0ffee'
NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)
MONO = 500000.0


class FakeSystem:
    def __init__(self, state, monitor_age=120, result='success', timer=('disabled', 'inactive'), manifest_mode=True,
                 enable_code=0):
        self.state, self.calls = state, []
        self.monitor_age, self.result, self.timer = monitor_age, result, timer
        self.manifest_mode, self.enable_code = manifest_mode, enable_code

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:3] == ['systemctl', 'show', 'scalar-social-monitor.service']:
            return 0, (f'Result={self.result}\nExecMainExitTimestampMonotonic={int((MONO-self.monitor_age)*1e6)}\n'
                       'ExecMainStatus=0\n')
        if args[:3] == ['systemctl', 'show', 'scalar-social.service']:
            source = f'--manifest {self.state}/manifests/approved.json' if self.manifest_mode else '--catalog x'
            return 0, f'ExecStart={{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 monitored.py tick {source} ; }}\n'
        if args[:2] == ['systemctl', 'is-enabled']:
            return (0 if self.timer[0] == 'enabled' else 1), self.timer[0]+'\n'
        if args[:2] == ['systemctl', 'is-active']:
            return (0 if self.timer[1] == 'active' else 3), self.timer[1]+'\n'
        if args[:3] == ['systemctl', 'enable', '--now']:
            return self.enable_code, ''
        if args[:2] == ['systemctl', 'list-timers']:
            return 0, 'NEXT  LEFT  LAST  PASSED  UNIT  ACTIVATES\nSat 2026-10-10 12:15:00 UTC 14min - - scalar-social.timer scalar-social.service\n'
        raise AssertionError(f'unexpected command {args}')


class ActivationEnv(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.state = base/'state'
        (self.state/'manifests').mkdir(parents=True)
        (base/'etc').mkdir()
        self.config_path = base/'etc'/'config.json'
        creds = base/'creds'
        creds.mkdir()
        (creds/'CLOUDFLARE_API_TOKEN').write_text(SENTINEL)
        patcher = mock.patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(creds)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config['media'].update(baseUrl='https://media.example.test', pagesProject='scalar-test', cloudflareAccountId='acct')
        self.config['channels']['x'].update(accountId='x-1', identityVerified=True, publishingVerified=True)
        self.ledger = runner.Ledger(self.state/'ledger.sqlite3')
        (self.state/'PAUSED').touch()
        self.bind(['x'])

    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()

    def bind(self, scope):
        _, scope_hash = intended_config(self.config, scope)
        jobs = []
        for n, platform in enumerate(scope):
            sha = hashlib.sha256(platform.encode()).hexdigest()
            jobs.append({'platform': platform, 'slot': f'2026-10-1{n+2}T13:00:00+00:00', 'key': f'{platform}|k',
                         'payload': {'episode': {'id': f'q{n}'}, 'kind': 'post', 'caption': 'c',
                                     'media': {'url': f'https://media.example.test/library/{sha}.mp4', 'sha256': sha,
                                               'bytes': 10, 'rightsReviewed': True}}})
        data = canonical({'version': 1, 'draftSha256': 'd'*64, 'scopeHash': scope_hash, 'scope': scope,
                          'approvedAt': '2026-10-10T11:00:00Z', 'jobs': jobs})
        self.sha = hashlib.sha256(data).hexdigest()
        for name in (f'{self.sha}.json', 'approved.json'):
            (self.state/'manifests'/name).write_bytes(data)
        urls = [{'url': j['payload']['media']['url'], 'sha256': j['payload']['media']['sha256'], 'bytes': 10, 'verified': True}
                for j in jobs]
        (self.state/'manifests'/f'{self.sha}.verification.json').write_text(json.dumps(
            {'version': 1, 'manifestSha256': self.sha, 'allVerified': True, 'urls': urls}))
        self.config['approval'] = {'manifestSha256': self.sha, 'approvedAt': '2026-10-10T11:05:00Z'}
        self.write_config()

    def write_config(self, mode=0o640):
        self.config_path.write_text(json.dumps(self.config, indent=2)+'\n')
        os.chmod(self.config_path, mode)

    def check(self, system=None):
        system = system or FakeSystem(self.state)
        rows, _ = activate.checklist(self.config_path, self.state, run=system, now=NOW, monotonic=lambda: MONO,
                                     owner=(os.getuid(), os.getgid()))
        return {label: (ok, detail) for label, ok, detail in rows}

    def failing(self, system=None):
        return [label for label, (ok, _) in self.check(system).items() if not ok]

    def activate(self, system):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                activate.activate(self.config_path, self.state, run=system, now=NOW, monotonic=lambda: MONO,
                                  owner=(os.getuid(), os.getgid()))
                refused = None
            except activate.Refused as error:
                refused = str(error)
        self.assertNotIn(SENTINEL, out.getvalue()+(refused or ''))
        return out.getvalue(), refused


class CheckTests(ActivationEnv):
    def test_all_items_pass_when_ready(self):
        results = self.check()
        self.assertEqual(len(results), 10)
        self.assertEqual(self.failing(), [], results)

    def test_individual_failures(self):
        self.write_config(0o600)
        self.assertEqual(self.failing(), ['Configuration file is 0640 root:scalar-social'])
        self.write_config()
        self.assertIn('Monitor succeeded in the last 30 minutes and reports healthy',
                      self.failing(FakeSystem(self.state, monitor_age=31*60)))
        self.assertIn('Monitor succeeded in the last 30 minutes and reports healthy',
                      self.failing(FakeSystem(self.state, result='exit-code')))
        self.assertEqual(self.failing(FakeSystem(self.state, timer=('enabled', 'active'))),
                         ['Publisher timer is currently disabled'])
        self.assertEqual(self.failing(FakeSystem(self.state, manifest_mode=False)),
                         ['Publisher service reads the approved manifest'])
        key = self.ledger.enqueue('x', 'x-1', '2026-10-01T13:00:00+00:00', {'episode': {'id': 'old'}})
        self.ledger.update(key, 'uncertain')
        failing = self.failing()
        self.assertIn('No uncertain, dispatching, blocked or failed posts', failing)

    def test_unbound_or_changed_scope_fails(self):
        self.config['approval']['manifestSha256'] = 'e'*64
        self.write_config()
        self.assertIn('Approved schedule exists and is bound by hash', self.failing())
        self.config['approval']['manifestSha256'] = self.sha
        self.config['schedule']['time'] = '09:00'
        self.write_config()
        self.assertEqual(self.failing(), ['Configuration with exactly these channels matches the approved scope hash'])
        self.config['schedule']['time'] = '08:00'
        self.config['channels']['x']['publishingVerified'] = False
        self.write_config()
        self.assertIn('Every channel in the schedule has verified identity and publishing', self.failing())

    def test_unverified_media_fails(self):
        path = self.state/'manifests'/f'{self.sha}.verification.json'
        evidence = json.loads(path.read_text())
        evidence['urls'] = []
        path.write_text(json.dumps(evidence))
        self.assertEqual(self.failing(), ['Every public media URL was verified by hash'])

    def test_finished_posts_need_no_media_verification(self):
        path = self.state/'manifests'/f'{self.sha}.verification.json'
        evidence = json.loads(path.read_text())
        evidence['urls'] = []
        path.write_text(json.dumps(evidence))
        key = self.ledger.enqueue('x', 'x-1', '2026-10-12T13:00:00+00:00', {'episode': {'id': 'q0'}})
        self.ledger.update(key, 'confirmed', remote_id='r1')
        self.assertNotIn('Every public media URL was verified by hash', self.failing())

    def test_scoped_threads_token_must_not_be_expiring(self):
        self.config['channels']['threads'].update(accountId='th-1', identityVerified=True, publishingVerified=True)
        self.bind(['threads', 'x'])
        health = self.state/'threads-token-health.json'
        health.write_text(json.dumps({'expiresAt': (NOW+dt.timedelta(hours=3)).isoformat()}))
        self.assertIn('Tokens for scheduled Threads/Instagram are healthy', self.failing())
        health.write_text(json.dumps({'expiresAt': (NOW+dt.timedelta(days=40)).isoformat()}))
        self.assertEqual(self.failing(), [])


class ApplyTests(ActivationEnv):
    def test_refuses_on_any_fail_without_changes(self):
        before = self.config_path.read_bytes()
        system = FakeSystem(self.state, monitor_age=3600)
        out, refused = self.activate(system)
        self.assertIn('Activation refused', refused)
        self.assertIn('FAIL', out)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertTrue((self.state/'PAUSED').exists())
        self.assertFalse(any(c[:2] == ['systemctl', 'enable'] for c in system.calls))

    def test_success_enables_exact_scope_and_timer(self):
        system = FakeSystem(self.state)
        out, refused = self.activate(system)
        self.assertIsNone(refused, out)
        config = json.loads(self.config_path.read_text())
        self.assertEqual([p for p, c in config['channels'].items() if c['enabled']], ['x'])
        self.assertFalse(config['paused'])
        manifest = json.loads((self.state/'manifests'/'approved.json').read_text())
        self.assertEqual(config['approval']['scopeHash'], runner.fingerprint(config))
        self.assertEqual(config['approval']['scopeHash'], manifest['scopeHash'])
        self.assertEqual(config['approval']['manifestSha256'], self.sha)
        for flag in ('deploymentApproved', 'mediaDeliveryVerified', 'monitoringVerified', 'zeroSpendVerified'):
            self.assertIs(config['approval'][flag], True)
        runner.validate(config, live=True)
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o640)
        self.assertFalse((self.state/'PAUSED').exists())
        self.assertIn(['systemctl', 'enable', '--now', 'scalar-social.timer'], system.calls)
        self.assertEqual(system.calls[-1], ['systemctl', 'list-timers', 'scalar-social.timer', '--no-pager'])
        self.assertIn('scalar-social.timer', out)

    def test_cli_requires_zero_spend_flag_and_root(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = activate.main(['--apply', '--config', str(self.config_path), '--state', str(self.state),
                                  '--allow-non-root-for-tests'])
        self.assertEqual(code, 1)
        self.assertIn('--confirm-zero-spend', err.getvalue())
        if os.geteuid() != 0:
            with contextlib.redirect_stderr(err):
                self.assertEqual(activate.main(['--apply', '--confirm-zero-spend', '--config', str(self.config_path),
                                                '--state', str(self.state)]), 1)
        self.assertTrue((self.state/'PAUSED').exists())


class AutoTests(ActivationEnv):
    def setUp(self):
        super().setUp()
        (self.state/'PAUSED').unlink()
        self.config['approval'].update(zeroSpendVerified=True, activatedAt='2026-10-09T20:00:00Z',
                                       evidence={'zeroSpend': 'owner confirmed with --confirm-zero-spend'})
        self.write_config()
        # Once live, the monitor expects the publisher's health file.
        (self.state/'health.json').write_text(json.dumps({'checkedAt': (NOW-dt.timedelta(minutes=10)).isoformat()}))

    def auto(self, system):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            message = activate.auto_activate(self.config_path, self.state, run=system, now=NOW, monotonic=lambda: MONO,
                                             owner=(os.getuid(), os.getgid()), out=print)
        self.assertNotIn(SENTINEL, out.getvalue()+message)
        return out.getvalue(), message

    def enables(self, system):
        return [c for c in system.calls if c[:2] == ['systemctl', 'enable']]

    def test_waits_for_the_owners_first_activation(self):
        del self.config['approval']['zeroSpendVerified']
        self.write_config()
        before = self.config_path.read_bytes()
        system = FakeSystem(self.state)
        _, message = self.auto(system)
        self.assertIn('first activation', message)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(system.calls, [])

    def test_owner_pause_is_never_resumed(self):
        (self.state/'PAUSED').touch()
        before = self.config_path.read_bytes()
        system = FakeSystem(self.state)
        _, message = self.auto(system)
        self.assertIn('Paused in the UI', message)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(system.calls, [])
        self.assertTrue((self.state/'PAUSED').exists())

    def test_any_failure_other_than_the_timer_waits(self):
        before = self.config_path.read_bytes()
        system = FakeSystem(self.state, monitor_age=3600, timer=('enabled', 'active'))
        out, message = self.auto(system)
        self.assertIn('waits', message)
        self.assertIn('FAIL', out)
        self.assertNotIn(activate.TIMER_ROW, out)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(self.enables(system), [])

    def test_activates_the_bound_schedule_and_enables_the_timer(self):
        system = FakeSystem(self.state)
        _, message = self.auto(system)
        self.assertIn('Autopilot activated', message)
        config = json.loads(self.config_path.read_text())
        self.assertEqual([p for p, c in config['channels'].items() if c['enabled']], ['x'])
        self.assertFalse(config['paused'])
        self.assertEqual(config['approval']['scopeHash'], runner.fingerprint(config))
        self.assertEqual(config['approval']['evidence']['zeroSpend'], 'owner confirmed with --confirm-zero-spend')
        runner.validate(config, live=True)
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.enables(system), [['systemctl', 'enable', '--now', 'scalar-social.timer']])

    def test_nothing_changes_when_already_live(self):
        self.auto(FakeSystem(self.state))
        before = self.config_path.read_bytes()
        system = FakeSystem(self.state, timer=('enabled', 'active'))
        _, message = self.auto(system)
        self.assertIn('already matches', message)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(self.enables(system), [])

    def test_new_scope_is_saved_while_the_timer_runs(self):
        self.auto(FakeSystem(self.state))
        self.config = json.loads(self.config_path.read_text())
        self.config['channels']['threads'].update(accountId='th-1', identityVerified=True, publishingVerified=True)
        (self.state/'threads-token-health.json').write_text(json.dumps({'expiresAt': (NOW+dt.timedelta(days=40)).isoformat()}))
        self.bind(['threads', 'x'])
        self.config['approval'].update(zeroSpendVerified=True, activatedAt='2026-10-09T20:00:00Z')
        self.write_config()
        system = FakeSystem(self.state, timer=('enabled', 'active'))
        _, message = self.auto(system)
        self.assertIn('Autopilot activated', message)
        config = json.loads(self.config_path.read_text())
        self.assertEqual(sorted(p for p, c in config['channels'].items() if c['enabled']), ['threads', 'x'])
        self.assertEqual(config['approval']['manifestSha256'], self.sha)
        self.assertEqual(self.enables(system), [])

    def test_cli_auto_exits_zero_when_waiting(self):
        (self.state/'PAUSED').touch()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = activate.main(['--auto', '--config', str(self.config_path), '--state', str(self.state),
                                  '--allow-non-root-for-tests'])
        self.assertEqual(code, 0)
        self.assertIn('Paused in the UI', out.getvalue())


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.ledger = runner.Ledger(self.state/'ledger.sqlite3')
        self.key = self.ledger.enqueue('x', 'x-1', '2026-10-05T12:00:00+00:00', {'episode': {'id': 'q1'}})
        self.ledger.update(self.key, 'uncertain', dispatched_at='2026-10-05T12:00:00+00:00', error='remote_confirmation_pending')

    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()

    def row(self):
        return self.ledger.db.execute('SELECT * FROM jobs WHERE id=?', (self.key,)).fetchone()

    def test_confirmed_with_platform_permalink(self):
        detail = resolve_job.resolve(self.state, self.key, confirmed=True, permalink='https://x.com/StudioZeroFlow/status/1',
                                     evidence='Seen on profile 10 Oct 12:05', now=NOW)
        row = self.row()
        self.assertEqual((row['status'], row['permalink'], row['published_at'], row['error']),
                         ('confirmed', 'https://x.com/StudioZeroFlow/status/1', NOW.isoformat(), None))
        event = self.ledger.db.execute("SELECT * FROM events WHERE kind='owner_resolved'").fetchone()
        self.assertEqual(json.loads(event['detail']), detail)
        self.assertEqual(detail['priorStatus'], 'uncertain')

    def test_rejects_foreign_or_unsafe_permalinks(self):
        for url in ('https://evil.com/x.com/1', 'https://x.com.evil.com/a', 'http://x.com/a/status/1',
                    'https://x.com/a/status/1?ref=1', 'https://user:pw@x.com/a', 'https://instagram.com/p/1'):
            with self.assertRaises(resolve_job.Refused, msg=url):
                resolve_job.resolve(self.state, self.key, confirmed=True, permalink=url, evidence='checked')
        self.assertEqual(self.row()['status'], 'uncertain')
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM events WHERE kind='owner_resolved'").fetchone()[0], 0)

    def test_not_published_is_final_and_expires_waiting_companions(self):
        companion = self.ledger.enqueue('x', 'x-1', '2026-10-05T12:02:00+00:00', {'episode': {'id': 'q1#comment'}})
        other = self.ledger.enqueue('x', 'x-1', '2026-10-05T12:03:00+00:00', {'episode': {'id': 'q10#comment'}})
        resolve_job.resolve(self.state, self.key, confirmed=False, evidence='Profile checked, no post', now=NOW)
        row = self.row()
        # Expired is final, so it no longer counts as "needs review" for activation or the monitor.
        self.assertEqual((row['status'], row['error']), ('expired', 'owner_verified_absent'))
        status = lambda key: self.ledger.db.execute('SELECT status, error FROM jobs WHERE id=?', (key,)).fetchone()
        self.assertEqual(tuple(status(companion)), ('expired', 'parent_unavailable'))
        self.assertEqual(tuple(status(other)), ('ready', None))

    def test_root_refuses_planted_links(self):
        target = self.state/'elsewhere'
        target.write_text('x')
        (self.state/'runner.lock').unlink(missing_ok=True)
        (self.state/'runner.lock').symlink_to(target)
        with mock.patch.object(resolve_job.os, 'geteuid', return_value=0), \
                mock.patch.object(resolve_job.pwd, 'getpwnam', return_value=mock.Mock(pw_uid=os.getuid(), pw_gid=os.getgid())), \
                mock.patch.object(resolve_job.os, 'setuid') as setuid:
            with self.assertRaises(resolve_job.Refused):
                resolve_job.drop_to_ledger_owner(self.state)
            setuid.assert_not_called()

    def test_refuses_other_statuses_missing_evidence_and_busy_lock(self):
        with self.assertRaises(resolve_job.Refused):
            resolve_job.resolve(self.state, self.key, confirmed=False, evidence='  ')
        ready = self.ledger.enqueue('x', 'x-1', '2026-10-06T12:00:00+00:00', {'episode': {'id': 'q2'}})
        with self.assertRaises(resolve_job.Refused):
            resolve_job.resolve(self.state, ready, confirmed=False, evidence='checked')
        with runner.lock(self.state/'runner.lock'):
            with self.assertRaises(resolve_job.Refused):
                resolve_job.resolve(self.state, self.key, confirmed=False, evidence='checked')
        self.assertEqual(self.row()['status'], 'uncertain')

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = resolve_job.main([self.key, '--not-published', '--evidence', 'checked', '--state', str(self.state),
                                     '--allow-non-root-for-tests'])
        self.assertEqual(code, 0)
        self.assertIn('not_published', out.getvalue())


if __name__ == '__main__':
    unittest.main()
