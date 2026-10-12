"""Pi self-update (updater.py + /api/system/update/*) against REAL git: a bare origin seeded from a small
synthetic repo and a partial (blob:none) + sparse (publisher/, contract/) "Pi" clone, as on the device."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater
from test_ui_server import ServerTestCase

QUICK = ('test_quick',)
CONTRACT_FIELDS = {'runningCommit', 'installKind', 'repoHead', 'restartNeeded', 'unitsChanged', 'piPackageChanged',
                   'applyUnitsCommand', 'unitsApply', 'status'}
STATUS_FIELDS = {'phase', 'requestId', 'startedAt', 'updatedAt', 'fromCommit', 'toCommit', 'error', 'log', 'check'}
CHECK_FIELDS = {'checkedAt', 'fetchOk', 'head', 'origin', 'behind', 'ahead', 'dirty', 'diverged', 'branchOk', 'originOk',
                'originUrl', 'incoming', 'changes', 'error'}


def git(cwd, *args):
    proc = subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com', '-c', 'commit.gpgsign=false',
                           '-c', 'init.defaultBranch=main', '-c', 'protocol.file.allow=always', *args],
                          cwd=cwd, capture_output=True, text=True,
                          # The test's own git (playing the Mac and GitHub) never reads HOME, which HardeningTests plants.
                          env={**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'})
    if proc.returncode:
        raise AssertionError(f'git {args}: {proc.stderr}')
    return proc.stdout.strip()


def static_files(index='<!doctype html><title>Scalar</title>'):
    files = {'index.html': index, 'assets/app.js': 'console.log(1)'}
    manifest = {'files': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()}, 'sourceHash': '0'*64}
    out = {f'publisher/app/static/{k}': v for k, v in files.items()}
    out['publisher/app/static/MANIFEST.json'] = json.dumps(manifest)
    return out


SEED = {
    'publisher/app/mod_a.py': 'VALUE = 1\n',
    'publisher/tests/test_quick.py': 'import unittest\n\nclass Quick(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n',
    'publisher/deploy/scalar-social-ui.service': '[Service]\nExecStart=/bin/true\n',
    'publisher/pi-package.json': '{}\n',
    'contract/library_contract.py': 'OK = True\n',
    'contract/tests/test_contract.py': 'import unittest\n\nclass C(unittest.TestCase):\n    def test_ok(self):\n        pass\n',
    'studio/big.txt': 'Mac only\n',
    '.gitignore': '**/__pycache__/\n',
    **static_files(),
}


class Repos:
    """src (the Mac) -> origin.git (GitHub) -> pi (partial + sparse checkout). On the Pi two users share two
    folders: `home` plays /var/lib/scalar-social (scalar-social's state and passwd home; runner.lock), `state`
    plays /var/lib/scalar-social-update (the update user's status.json, units-applied.json, and inbox/ that the
    UI writes). On the Mac one user plays both; the cross-user parts are checked with GIT_TEST_ASSUME_DIFFERENT_OWNER."""
    def __init__(self, root):
        self.root, self.src, self.origin, self.pi = root, root/'src', root/'origin.git', root/'pi'
        self.home = root/'scalar-social'
        self.home.mkdir(parents=True)
        self.state = root/'scalar-social-update'
        (self.state/'inbox').mkdir(parents=True)
        self.src.mkdir()
        git(self.src, 'init', '-q')
        self.write(SEED)
        git(self.src, 'add', '-A')
        git(self.src, 'commit', '-qm', 'seed')
        git(root, 'clone', '-q', '--bare', str(self.src), str(self.origin))
        git(self.origin, 'config', 'uploadpack.allowFilter', 'true')
        git(self.src, 'remote', 'add', 'origin', str(self.origin))
        self.url = f'file://{self.origin}'
        git(root, 'clone', '-q', '--filter=blob:none', '--no-checkout', self.url, str(self.pi))
        git(self.pi, 'sparse-checkout', 'set', '--cone', 'publisher', 'contract')
        git(self.pi, 'checkout', '-q', 'main')

    def write(self, files, base=None):
        for name, text in files.items():
            path = (base or self.src)/name
            if text is None:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def push(self, files, message='change'):
        self.write(files)
        git(self.src, 'add', '-A')
        git(self.src, 'commit', '-qm', message)
        git(self.src, 'push', '-q', 'origin', 'main')
        return git(self.src, 'rev-parse', 'HEAD')

    def head(self):
        return git(self.pi, 'rev-parse', 'HEAD')


class UpdaterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repos = Repos(Path(self.tmp.name).resolve())
        self.state, self.home, self.pi = self.repos.state, self.repos.home, self.repos.pi
        env = mock.patch.dict(os.environ, {updater.ORIGINS_ENV: self.repos.url})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)
        err = mock.patch('sys.stderr', new_callable=io.StringIO)
        err.start()
        self.addCleanup(err.stop)

    def run_request(self, **kwargs):
        kwargs.setdefault('quick_tests', QUICK)
        kwargs.setdefault('restart_wait', 0)  # no UI here: the switch stays 'switched' (RollbackTests covers the rest)
        kwargs.setdefault('lock_path', self.home/'runner.lock')
        self.assertEqual(updater.run_request(self.state, self.pi, **kwargs), 0)
        self.assertFalse((self.state/'inbox/request.json').exists())
        self.assertFalse((self.state/'inbox/request.taken.json').exists())
        return updater.read_status(self.state)

    def check(self):
        updater.queue_request(self.state, 'check')
        return self.run_request()

    def apply(self, sha, **kwargs):
        self.check()
        updater.start(self.state, self.pi, self.repos.head(), f'UPDATE TO {sha}')
        return self.run_request(**kwargs)

    def assert_no_stage(self):
        self.assertEqual(list(updater.stage_base(self.pi).glob('stage-*')), [])
        self.assertEqual(list(self.state.glob('**/stage-*')), [])
        self.assertEqual(len(git(self.pi, 'worktree', 'list').splitlines()), 1)


class CheckTests(UpdaterCase):
    def test_behind_with_change_flags(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/deploy/scalar-social-ui.service': '[Service]\nExecStart=/bin/false\n',
                               'publisher/pi-package.json': '{"x": 1}\n', 'contract/library_contract.py': 'OK = 2\n',
                               'publisher/app/static/index.html': 'x', 'studio/big.txt': 'ignored by the Pi\n'}, 'Second commit')
        status = self.check()
        self.assertEqual(status['phase'], 'checked')
        check = status['check']
        self.assertEqual(set(check), CHECK_FIELDS)
        self.assertEqual((check['head'], check['origin'], check['behind'], check['ahead']), (old, new, 1, 0))
        self.assertTrue(check['fetchOk'] and check['branchOk'] and check['originOk'])
        self.assertFalse(check['dirty'] or check['diverged'] or check['error'])
        self.assertEqual([c['sha'] for c in check['incoming']], [new])
        self.assertEqual(check['incoming'][0]['subject'], 'Second commit')
        self.assertRegex(check['incoming'][0]['date'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual(check['changes'], {'units': True, 'piPackage': True, 'contract': True, 'ui': True, 'files': [
            'contract/library_contract.py', 'publisher/app/static/index.html', 'publisher/deploy/scalar-social-ui.service',
            'publisher/pi-package.json']})
        self.assertEqual((status['fromCommit'], status['toCommit']), (old, new))
        self.assertEqual(self.repos.head(), old)  # a check never moves the checkout
        self.assertFalse((self.pi/'studio').exists())

    def test_up_to_date_ahead_diverged_dirty(self):
        check = self.check()['check']
        self.assertEqual((check['behind'], check['ahead'], check['diverged'], check['changes']['files']), (0, 0, False, []))
        self.repos.write({'publisher/app/local.py': 'X = 1\n'}, self.pi)
        self.assertTrue(self.check()['check']['dirty'])  # untracked counts
        git(self.pi, 'add', '-A')
        git(self.pi, 'commit', '-qm', 'local only')
        check = self.check()['check']
        self.assertEqual((check['ahead'], check['diverged'], check['dirty']), (1, True, False))
        self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        check = self.check()['check']
        self.assertEqual((check['ahead'], check['behind'], check['diverged']), (1, 1, True))
        self.repos.write({'publisher/app/mod_a.py': 'VALUE = 9\n'}, self.pi)
        self.assertTrue(self.check()['check']['dirty'])

    def test_origin_and_branch_mismatch(self):
        with mock.patch.dict(os.environ, {updater.ORIGINS_ENV: ''}):
            check = self.check()['check']
        self.assertFalse(check['originOk'])
        self.assertEqual(check['originUrl'], self.repos.url)
        git(self.pi, 'checkout', '-q', '-b', 'other')
        self.assertFalse(self.check()['check']['branchOk'])
        self.assertIn('git@github.com-scalar:samirhusain26/scalargame-marketing.git', updater.ORIGINS)
        self.assertIn('git@github.com-scalar:samirhusain26/scalargame-marketing-plan.git', updater.ORIGINS)
        self.assertIn('git@github.com-scalar:samirhusain26/StudioZero.git', updater.ORIGINS)
        self.assertIn('git@github.com-scalar:samirhusain26/StudioZero', updater.ORIGINS)

    def test_lookalike_origins_are_refused(self):
        for url in ('git@github.com-scalar:samirhusain26/StudioZero.git.evil', 'git@github.com-scalar:samirhusain26/StudioZero-fork.git',
                    'git@github.com-scalar:other/StudioZero.git', 'git@github.com:samirhusain26/StudioZero.git',
                    'https://github.com/samirhusain26/StudioZero.git', 'git@github.com-scalar:samirhusain26/studiozero.git'):
            git(self.pi, 'remote', 'set-url', 'origin', url)
            with mock.patch.dict(os.environ, {updater.ORIGINS_ENV: ''}):
                self.assertFalse(self.check()['check']['originOk'], url)

    def test_unrelated_history_is_diverged_and_refused(self):
        # The StudioZero move: same publisher/ + contract/ bytes, unrelated history. An in-place re-point is refused,
        # which is why publisher/deploy/migrate-origin.sh replaces the checkout instead.
        other = self.repos.root/'unrelated'
        other.mkdir()
        git(other, 'init', '-q')
        self.repos.write(SEED, other)
        git(other, 'add', '-A')
        git(other, 'commit', '-qm', 'import')
        self.repos.write({'publisher/app/mod_a.py': 'VALUE = 2\n'}, other)
        git(other, 'commit', '-qam', 'next')
        bare = self.repos.root/'unrelated.git'
        git(self.repos.root, 'clone', '-q', '--bare', str(other), str(bare))
        url = f'file://{bare}'
        before = self.repos.head()
        git(self.pi, 'remote', 'set-url', 'origin', url)
        with mock.patch.dict(os.environ, {updater.ORIGINS_ENV: url}):
            check = self.check()['check']
            self.assertTrue(check['originOk'])
            self.assertTrue(check['diverged'])
            self.assertGreater(check['behind'], 0)
            with self.assertRaises(updater.Refused) as caught:
                updater.check_start(self.state, self.pi, before, f"UPDATE TO {check['origin']}")
        self.assertEqual(caught.exception.code, 'diverged')
        self.assertEqual(self.repos.head(), before)

    def test_fetch_failure_is_reported(self):
        missing = f'file://{self.repos.root}/missing.git'
        git(self.pi, 'remote', 'set-url', 'origin', missing)
        with mock.patch.dict(os.environ, {updater.ORIGINS_ENV: missing}):
            status = self.check()
        self.assertEqual(status['phase'], 'checked')
        self.assertFalse(status['check']['fetchOk'])
        self.assertIn('git fetch failed', status['check']['error'])

    def test_unreadable_request(self):
        (self.state/'inbox/request.json').write_text('{nope')
        status = self.run_request()
        self.assertEqual((status['phase'], status['error']), ('failed', 'Unreadable update request.'))
        self.assertEqual(updater.run_request(self.state, self.pi), 0)  # nothing to take


class ApplyTests(UpdaterCase):
    def test_happy_path_switch_restart_reconcile(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n', 'publisher/app/mod_b.py': 'import mod_a\n'})
        status = self.apply(new)
        self.assertEqual(status['phase'], 'switched', status['error'])
        self.assertEqual((status['fromCommit'], status['toCommit'], self.repos.head()), (old, new, new))
        self.assertEqual(status['check']['behind'], 0)
        self.assertEqual((self.pi/'publisher/app/mod_b.py').read_text(), 'import mod_a\n')
        self.assertFalse((self.pi/'studio').exists())
        self.assertTrue(any('Staged check: publisher tests' in line for line in status['log']))
        self.assert_no_stage()
        self.assertEqual(git(self.pi, 'status', '--porcelain'), '')
        # The UI still runs `old`: its watcher marks the run restarting and exits 86.
        exits = []
        self.assertTrue(updater.watch_once(self.state, self.pi, old, exit=exits.append, pause=0))
        self.assertEqual(exits, [86])
        self.assertEqual(updater.current_status(self.state)['phase'], 'restarting')
        self.assertEqual(updater.read_status(self.state)['phase'], 'switched')  # the UI reports via inbox/ui.json
        self.assertTrue(updater.busy(self.state))
        status = updater.reconcile(self.state, new)
        self.assertEqual((status['phase'], status['error']), ('complete', None))
        self.assertFalse(updater.busy(self.state))

    def test_failing_staged_checks_leave_head_unchanged(self):
        cases = {
            'compile': {'publisher/app/mod_a.py': 'def broken(:\n'},
            'import every module': {'publisher/app/mod_c.py': 'raise RuntimeError("boom")\n'},
            'publisher tests': {'publisher/tests/test_quick.py': 'import unittest\n\nclass Q(unittest.TestCase):\n    def test_no(self):\n        self.fail("no")\n'},
            'contract tests': {'contract/tests/test_contract.py': 'import unittest\n\nclass C(unittest.TestCase):\n    def test_no(self):\n        self.fail("no")\n'},
            'MANIFEST.json': {'publisher/app/static/index.html': 'tampered'},
        }
        old = self.repos.head()
        for name, files in cases.items():
            with self.subTest(name):
                bad = self.repos.push(files, f'bad {name}')
                status = self.apply(bad)
                self.assertEqual(status['phase'], 'failed')
                self.assertIn(name, status['error'])
                self.assertEqual(self.repos.head(), old)
                self.assert_no_stage()
                self.assertEqual(git(self.pi, 'status', '--porcelain'), '')
                git(self.src_reset(old), 'push', '-q', '-f', 'origin', 'main')

    def src_reset(self, sha):
        git(self.repos.src, 'reset', '-q', '--hard', sha)
        return self.repos.src

    def test_failure_after_merge_resets_to_old(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 3\n'})
        with mock.patch.object(updater, 'verify_switched', side_effect=updater.UpdateError('post-merge check failed')):
            status = self.apply(new)
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('post-merge check failed (rolled back to', status['error'])
        self.assertEqual(self.repos.head(), old)
        self.assertEqual((self.pi/'publisher/app/mod_a.py').read_text(), 'VALUE = 1\n')
        self.assert_no_stage()

    def test_dirty_or_diverged_at_apply_time(self):
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 4\n'})
        self.check()
        updater.start(self.state, self.pi, self.repos.head(), f'UPDATE TO {new}')
        self.repos.write({'publisher/app/mod_a.py': 'local edit\n'}, self.pi)
        status = self.run_request()
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('local changes; nothing was changed', status['error'])
        git(self.pi, 'checkout', '-q', '--', '.')
        git(self.pi, 'commit', '-q', '--allow-empty', '-m', 'local')
        updater.queue_request(self.state, 'apply', new)
        status = self.run_request()
        self.assertIn('diverged', status['error'])
        self.assertNotEqual(self.repos.head(), new)

    def test_runner_lock_held_times_out(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 5\n'})
        with open(self.home/'runner.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            started = time.monotonic()
            status = self.apply(new, lock_timeout=0.3)
        self.assertLess(time.monotonic() - started, 60)
        self.assertEqual((status['phase'], status['error']), ('failed', updater.BUSY_MESSAGE))
        self.assertEqual(self.repos.head(), old)
        self.assert_no_stage()

    def test_origin_moved_after_confirmation(self):
        first = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 6\n'})
        self.check()
        updater.start(self.state, self.pi, self.repos.head(), f'UPDATE TO {first}')
        self.repos.push({'publisher/app/mod_a.py': 'VALUE = 7\n'})
        old = self.repos.head()
        status = self.run_request()
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('origin changed after confirmation', status['error'])
        self.assertEqual(self.repos.head(), old)

    def test_leftover_stage_from_killed_run_is_removed(self):
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 8\n'})
        leftover = updater.stage_base(self.pi)/'stage-deadbeef'
        git(self.pi, 'worktree', 'add', '-q', '--detach', str(leftover), 'HEAD')
        self.assertEqual(self.apply(new)['phase'], 'switched')
        self.assert_no_stage()


class SparseTests(UpdaterCase):
    """publisher/deploy/sparse-paths in the applied commit sets the checkout's cone (the Studio's motion assets)."""
    def sparse(self):
        return git(self.pi, 'sparse-checkout', 'list').split()

    def switch(self, sha):
        status = self.apply(sha)
        self.assertEqual(status['phase'], 'switched', status['error'])
        updater.reconcile(self.state, sha)  # the new UI reports serving
        return status

    def test_the_applied_commit_widens_and_narrows_the_cone(self):
        new = self.repos.push({updater.SPARSE_FILE: '# cone\npublisher\ncontract\nstudio\n', 'studio/big.txt': 'assets\n'})
        status = self.switch(new)
        self.assertEqual(sorted(self.sparse()), ['contract', 'publisher', 'studio'])
        self.assertEqual((self.pi/'studio/big.txt').read_text(), 'assets\n')
        self.assertTrue(any('Sparse checkout: contract, publisher, studio' in line for line in status['log']))
        self.assertEqual(git(self.pi, 'status', '--porcelain'), '')
        # Unchanged cone: no sparse step.
        same = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 5\n'})
        status = self.switch(same)
        self.assertFalse(any('Sparse checkout' in line for line in status['log'][-12:]))
        # No file: back to publisher/ + contract/.
        narrow = self.repos.push({updater.SPARSE_FILE: None})
        self.switch(narrow)
        self.assertEqual(sorted(self.sparse()), ['contract', 'publisher'])
        self.assertFalse((self.pi/'studio').exists())

    def test_an_invalid_list_changes_nothing(self):
        old = self.repos.head()
        for text in ('publisher\nstudio\n', 'publisher\ncontract\n../etc\n', 'publisher\ncontract\n/abs\n', 'publisher\ncontract\nStudio\n',
                     'publisher\ncontract\n' + ''.join(f'd{i}\n' for i in range(9)), 'publisher\ncontract\n' + '#' * 3000 + '\n'):
            with self.subTest(text=text[:30]):
                bad = self.repos.push({updater.SPARSE_FILE: text})
                status = self.apply(bad)
                self.assertEqual(status['phase'], 'failed')
                self.assertIn(updater.SPARSE_FILE, status['error'])
                self.assertEqual((self.repos.head(), sorted(self.sparse())), (old, ['contract', 'publisher']))
                self.assert_no_stage()
                git(self.repos.src, 'reset', '-q', '--hard', old)
                git(self.repos.src, 'push', '-q', '-f', 'origin', 'main')

    def test_a_failed_sparse_set_restores_the_cone_and_switches_nothing(self):
        old = self.repos.head()
        new = self.repos.push({updater.SPARSE_FILE: 'publisher\ncontract\nstudio\n'})
        real = updater.git

        def failing(repo, *args, **kwargs):
            if args[:3] == ('sparse-checkout', 'set', '--cone') and 'studio' in args:
                return subprocess.CompletedProcess(args, 128, '', 'fatal: could not fetch blobs')
            return real(repo, *args, **kwargs)
        with mock.patch.object(updater, 'git', side_effect=failing):
            status = self.apply(new)
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('sparse-checkout set failed', status['error'])
        self.assertEqual((self.repos.head(), sorted(self.sparse())), (old, ['contract', 'publisher']))


class StartValidationTests(UpdaterCase):
    def refused(self, confirm, **kwargs):
        with self.assertRaises(updater.Refused) as caught:
            updater.check_start(self.state, self.pi, kwargs.pop('running', self.repos.head()), confirm, **kwargs)
        return caught.exception.status, caught.exception.code

    def test_codes(self):
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        phrase = f'UPDATE TO {new}'
        self.assertEqual(self.refused(phrase, running=None), (409, 'not_git'))
        for bad in ('', 'update to ' + new, f'UPDATE TO {new[:12]}', f'UPDATE TO {new} ', None, 42):
            self.assertEqual(self.refused(bad), (400, 'bad_confirm'), bad)
        self.assertEqual(self.refused(phrase), (409, 'stale_check'))  # never checked
        self.check()
        self.assertEqual(updater.check_start(self.state, self.pi, self.repos.head(), phrase), new)
        self.assertEqual(self.refused(f'UPDATE TO {"a"*40}'), (400, 'bad_confirm'))  # not the checked commit
        self.assertEqual(self.refused(phrase, now=time.time() + 16*60), (409, 'stale_check'))
        status = updater.read_status(self.state)
        for key, value, code in (('fetchOk', False, 'stale_check'), ('head', 'b'*40, 'stale_check'), ('dirty', True, 'dirty'),
                                 ('diverged', True, 'diverged'), ('originOk', False, 'origin'), ('branchOk', False, 'branch'),
                                 ('behind', 0, 'up_to_date')):
            updater.write_status(self.state, {**status, 'check': {**status['check'], key: value}})
            self.assertEqual(self.refused(phrase), (409 if code != 'bad_confirm' else 400, code), key)
        updater.write_status(self.state, status)
        updater.queue_request(self.state, 'check')
        self.assertEqual(self.refused(phrase), (409, 'busy'))

    def test_single_flight_and_staleness(self):
        updater.queue_request(self.state, 'check')
        with self.assertRaises(updater.Busy):
            updater.queue_request(self.state, 'check')
        old = time.time() - updater.STALE_SECONDS - 5
        os.utime(self.state/'inbox/request.json', (old, old))
        updater.queue_request(self.state, 'check')  # a request nobody took for 40 minutes no longer blocks
        (self.state/'inbox/request.json').unlink()
        for phase in updater.BUSY:
            updater.write_status(self.state, {'phase': phase})
            self.assertTrue(updater.busy(self.state), phase)
            self.assertFalse(updater.busy(self.state, time.time() + updater.STALE_SECONDS + 5), phase)
        for phase in ('idle', 'checked', 'complete', 'failed'):
            updater.write_status(self.state, {'phase': phase})
            self.assertFalse(updater.busy(self.state), phase)


class RestartTests(UpdaterCase):
    def test_reconcile_reports_serving_and_status_follows(self):
        a, b = 'a'*40, 'b'*40
        for phase in ('checked', 'failed', 'complete'):
            updater.write_status(self.state, {'phase': phase, 'requestId': 'r1', 'toCommit': b})
            self.assertEqual(updater.reconcile(self.state, b)['phase'], phase)
            self.assertFalse((self.state/'inbox/ui.json').exists())
        updater.write_status(self.state, {'phase': 'switched', 'requestId': 'r1', 'fromCommit': a, 'toCommit': b})
        status = updater.reconcile(self.state, b)
        self.assertEqual((status['phase'], status['error']), ('complete', None))
        self.assertEqual(updater.read_status(self.state)['phase'], 'switched')  # the UI never writes status.json
        self.assertEqual(oct((self.state/'inbox/ui.json').stat().st_mode & 0o777), '0o644')
        self.assertEqual(updater.reconcile(self.state, a)['phase'], 'failed')
        self.assertIn('not bbbbbbbbbbbb', updater.current_status(self.state)['error'])
        updater.write_ui(self.state, 'r1', 'restarting', a)
        self.assertEqual(updater.current_status(self.state)['phase'], 'restarting')
        updater.write_ui(self.state, 'other-request', 'serving', b)  # another request's report changes nothing
        self.assertEqual(updater.current_status(self.state)['phase'], 'switched')

    def test_watcher(self):
        head = self.repos.head()
        exits = []
        updater.write_status(self.state, {'phase': 'switched', 'requestId': 'r1', 'toCommit': head})
        self.assertFalse(updater.watch_once(self.state, self.pi, head, exit=exits.append, pause=0))  # already on it
        self.assertFalse(updater.watch_once(self.state, self.pi, None, exit=exits.append, pause=0))  # copy install
        updater.write_status(self.state, {'phase': 'checked'})
        self.assertFalse(updater.watch_once(self.state, self.pi, 'c'*40, exit=exits.append, pause=0))
        self.assertEqual(exits, [])
        # The thread form: os._exit is mocked; it fires once status.json shows the switch.
        fired = []
        updater.start_watcher(self.state, self.pi, 'c'*40, interval=0.01, exit=fired.append)
        updater.write_status(self.state, {'phase': 'switched', 'requestId': 'r2', 'toCommit': head})
        deadline = time.time() + 10
        while not fired and time.time() < deadline:
            time.sleep(0.02)
        self.assertEqual(fired[:1], [86])
        self.assertEqual(updater.current_status(self.state)['phase'], 'restarting')
        self.assertEqual(updater.read_status(self.state)['phase'], 'switched')

    def test_running_commit_reads_files_without_git(self):
        head = self.repos.head()
        self.assertEqual(updater.running_commit(self.pi), head)
        git(self.pi, 'pack-refs', '--all')
        self.assertFalse((self.pi/'.git/refs/heads/main').exists())
        self.assertEqual(updater.running_commit(self.pi), head)  # from packed-refs
        git(self.pi, 'checkout', '-q', '--detach')
        self.assertEqual(updater.running_commit(self.pi), head)  # detached HEAD holds the sha itself
        (self.pi/'.git/HEAD').write_text('ref: refs/heads/../../../etc\n')
        self.assertIsNone(updater.running_commit(self.pi))
        self.assertIsNone(updater.running_commit(self.repos.root/'not-a-repo'))

    def test_ui_reads_the_update_users_checkout(self):
        """The UI (scalar-social) runs git on the checkout scalar-social-update owns: git refuses a repository owned by
        someone else unless that one path is trusted on the command line (safe.directory)."""
        head = self.repos.head()
        (self.state/'units-applied.json').write_text(json.dumps({'commit': head}))
        new = self.repos.push({'publisher/deploy/scalar-social-ui.service': 'changed\n'})
        git(self.pi, 'fetch', '-q', 'origin')
        git(self.pi, 'merge', '-q', '--ff-only', new)
        with mock.patch.dict(os.environ, {'GIT_TEST_ASSUME_DIFFERENT_OWNER': '1'}):
            plain = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.pi, capture_output=True, text=True,
                                   env={**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'})
            self.assertIn('dubious ownership', plain.stderr)
            info = updater.info(self.state, self.pi, head)
        self.assertEqual((info['repoHead'], info['unitsChanged'], info['piPackageChanged']), (new, True, False))

    def test_info(self):
        head = self.repos.head()
        info = updater.info(self.state, self.pi, head)
        self.assertEqual(set(info), CONTRACT_FIELDS)
        self.assertEqual(set(info['status']), STATUS_FIELDS)
        self.assertEqual((info['installKind'], info['runningCommit'], info['repoHead'], info['restartNeeded']), ('git', head, head, False))
        self.assertEqual((info['unitsChanged'], info['piPackageChanged'], info['applyUnitsCommand']),
                         (True, True, updater.APPLY_UNITS_COMMAND))  # never applied
        (self.state/'units-applied.json').write_text(json.dumps({'commit': head}))
        info = updater.info(self.state, self.pi, head)
        self.assertEqual((info['unitsChanged'], info['piPackageChanged'], info['applyUnitsCommand']), (False, False, None))
        new = self.repos.push({'publisher/deploy/scalar-social-ui.service': 'changed\n'})
        self.assertEqual(self.apply(new)['phase'], 'switched')
        info = updater.info(self.state, self.pi, head)
        self.assertEqual((info['repoHead'], info['restartNeeded'], info['unitsChanged'], info['piPackageChanged']), (new, True, True, False))
        copy = updater.info(self.state, self.repos.root/'not-a-repo', None)
        self.assertEqual((copy['installKind'], copy['runningCommit'], copy['repoHead'], copy['unitsChanged']), ('copy', None, None, False))
        self.assertIsNone(updater.running_commit(self.repos.root/'not-a-repo'))
        updater.write_status(self.state, {'phase': 'staging', 'updatedAt': None})
        status = json.loads((self.state/'status.json').read_text())
        status['updatedAt'] = '2026-01-01T00:00:00Z'
        (self.state/'status.json').write_text(json.dumps(status))
        self.assertEqual(updater.info(self.state, self.pi, head)['status']['phase'], 'failed')  # killed mid-run


class HardeningTests(UpdaterCase):
    """M1: everything a scalar-social process can write (its home, the state folder, XDG config) is never read by
    git or ssh in the update unit. The planted config is proved live first, so the negative check means something."""

    def plant(self):
        home = self.home  # /var/lib/scalar-social on the Pi: scalar-social's passwd home, writable by the UI
        self.marker = self.repos.root/'PLANTED-CONFIG-RAN'
        script = home/'evil.sh'
        script.write_text(f'#!/bin/sh\ntouch {self.marker}\nexit 1\n')
        script.chmod(0o755)
        hooks = home/'hooks'
        hooks.mkdir()
        for name in ('post-checkout', 'post-merge', 'reference-transaction', 'pre-auto-gc', 'post-index-change'):
            (hooks/name).write_text(f'#!/bin/sh\ntouch {self.marker}\n')
            (hooks/name).chmod(0o755)
        config = (f'[core]\n\tfsmonitor = {script}\n\thooksPath = {hooks}\n\tsshCommand = {script}\n'
                  f'[url "file:///nonexistent/"]\n\tinsteadOf = file://\n')
        (home/'.gitconfig').write_text(config)
        (home/'.config/git').mkdir(parents=True)
        (home/'.config/git/config').write_text(config)
        (home/'.ssh').mkdir()
        (home/'.ssh/config').write_text(f'Host *\n  ProxyCommand {script}\n')
        env = mock.patch.dict(os.environ, {'HOME': str(home), 'XDG_CONFIG_HOME': str(home/'.config')})
        env.start()
        self.addCleanup(env.stop)

    def test_planted_home_config_never_runs_during_check_or_apply(self):
        self.plant()
        # Control: a plain git in that environment does run the planted fsmonitor command.
        subprocess.run(['git', 'status', '--porcelain'], cwd=self.pi, capture_output=True)
        self.assertTrue(self.marker.exists(), 'the planted config should be live for an unhardened git')
        self.marker.unlink()
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        status = self.apply(new)
        self.assertEqual(status['phase'], 'switched', status['error'])
        self.assertEqual(self.repos.head(), new)
        self.assertNotEqual(old, new)
        self.assertFalse(self.marker.exists(), 'planted config ran inside the update unit')
        self.assertEqual(updater.fetch(self.pi).returncode, 0)  # the planted url.insteadOf was not applied either
        self.assertFalse(self.marker.exists())

    def test_git_environment(self):
        env = updater.git_env()
        self.assertEqual((env['GIT_CONFIG_GLOBAL'], env['GIT_CONFIG_NOSYSTEM'], env['GIT_TERMINAL_PROMPT']), ('/dev/null', '1', '0'))
        self.assertEqual(env['GIT_SSH_COMMAND'], f'ssh -F {updater.SSH_CONFIG}')
        self.assertEqual(updater.SSH_CONFIG, '/etc/scalar-social-update/ssh_config')
        for flag in ('core.hooksPath=/dev/null', 'core.fsmonitor=false', 'protocol.file.allow=user'):
            self.assertIn(flag, updater.hardened())  # file:// only because the test lists a file:// origin
        with mock.patch.dict(os.environ, {updater.ORIGINS_ENV: ''}):
            self.assertIn('protocol.file.allow=never', updater.hardened())  # the Pi
        with mock.patch.dict(os.environ, {'HOME': '/attacker'}):
            proc = updater.run([sys.executable, '-c', 'import os, sys; print(os.environ["HOME"], sys.flags.dont_write_bytecode)'], self.pi)
        self.assertEqual(proc.stdout.split(), [updater.UPDATE_HOME, '1'])

    def test_studiozero_origin_is_accepted_over_the_pinned_alias(self):
        self.plant()
        trusted = self.repos.root/'trusted-sz'
        trusted.mkdir()
        (trusted/'ssh_config').write_text('Host github.com-scalar\n  ProxyCommand sh -c "exit 1"\n  BatchMode yes\n')
        git(self.pi, 'remote', 'set-url', 'origin', 'git@github.com-scalar:samirhusain26/StudioZero.git')
        with mock.patch.object(updater, 'SSH_CONFIG', str(trusted/'ssh_config')), mock.patch.dict(os.environ, {updater.ORIGINS_ENV: ''}):
            status = self.check()
        self.assertFalse(status['check']['fetchOk'])
        self.assertTrue(status['check']['originOk'])

    def test_ssh_uses_only_the_root_owned_config(self):
        self.plant()
        trusted = self.repos.root/'trusted'
        trusted.mkdir()
        used = self.repos.root/'TRUSTED-SSH-CONFIG-USED'
        (trusted/'ssh_config').write_text(f'Host github.com-scalar\n  ProxyCommand sh -c "touch {used}; exit 1"\n  BatchMode yes\n')
        origin = 'git@github.com-scalar:samirhusain26/scalargame-marketing-plan.git'
        git(self.pi, 'remote', 'set-url', 'origin', origin)
        with mock.patch.object(updater, 'SSH_CONFIG', str(trusted/'ssh_config')):
            status = self.check()
        self.assertFalse(status['check']['fetchOk'])
        self.assertTrue(status['check']['originOk'])
        self.assertTrue(used.exists(), 'ssh did not read the -F config')
        self.assertFalse(self.marker.exists(), 'ssh or git read the planted ~/.ssh/config or core.sshCommand')

    def test_ignored_bytecode_counts_as_dirty(self):
        cache = self.pi/'publisher/app/__pycache__'
        cache.mkdir()
        (cache/'mod_a.cpython-313.pyc').write_bytes(b'\x00')
        self.assertEqual(git(self.pi, 'status', '--porcelain'), '')  # ignored by .gitignore ...
        self.assertTrue(self.check()['check']['dirty'])               # ... but it would run, so it is a change
        (cache/'mod_a.cpython-313.pyc').unlink()
        cache.rmdir()
        self.assertFalse(self.check()['check']['dirty'])

    def test_runner_lock_is_opened_read_only(self):
        (self.home/'runner.lock').touch()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 3\n'})
        self.check()
        updater.start(self.state, self.pi, self.repos.head(), f'UPDATE TO {new}')
        (self.home/'runner.lock').chmod(0o444)
        self.home.chmod(0o511)  # the update user cannot write the publisher's state folder
        try:
            status = self.run_request()
        finally:
            self.home.chmod(0o700)
        self.assertEqual(status['phase'], 'switched', status['error'])
        missing = self.repos.root/'readonly'
        missing.mkdir(mode=0o500)
        try:
            with self.assertRaises(updater.UpdateError) as caught:  # missing and not creatable: never switch unlocked
                with updater.runner_lock(missing/'runner.lock', 1):
                    pass
            self.assertIn('runner.lock is missing', str(caught.exception))
        finally:
            missing.chmod(0o700)
        (self.home/'other').symlink_to(self.home/'runner.lock')
        with self.assertRaises(updater.UpdateError):
            with updater.runner_lock(self.home/'other', 1):
                pass
        os.mkfifo(self.home/'fifo')  # a FIFO planted as runner.lock must not hang the update unit
        with self.assertRaises(updater.UpdateError):
            with updater.runner_lock(self.home/'fifo', 1):
                pass

    def test_no_switch_without_runner_lock(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 4\n'})
        self.home.chmod(0o500)  # runner.lock missing and the update user cannot create it
        try:
            status = self.apply(new)
        finally:
            self.home.chmod(0o700)
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('runner.lock is missing', status['error'])
        self.assertEqual(self.repos.head(), old)
        self.assert_no_stage()

    def test_symlinked_inbox_is_refused(self):
        elsewhere = self.repos.root/'elsewhere'
        elsewhere.mkdir()
        (self.state/'inbox').rmdir()
        (self.state/'inbox').symlink_to(elsewhere)
        updater._write_request(self.state, 'check')
        self.assertEqual(updater.run_request(self.state, self.pi, quick_tests=QUICK, restart_wait=0), 1)
        self.assertTrue((elsewhere/'request.json').exists())
        self.assertFalse((self.state/'status.json').exists())

    def test_planted_files_are_not_followed_or_blocking(self):
        (self.state/'inbox/request.json').symlink_to(self.pi/'publisher/app/mod_a.py')
        self.assertEqual(self.run_request()['error'], 'Unreadable update request.')
        self.assertEqual((self.pi/'publisher/app/mod_a.py').read_text(), 'VALUE = 1\n')
        os.mkfifo(self.state/'inbox/ui.json')
        updater.write_status(self.state, {'phase': 'switched', 'requestId': 'r1'})
        self.assertEqual(updater.current_status(self.state)['phase'], 'switched')  # FIFO ignored, no hang
        (self.state/'inbox/ui.json').unlink()
        (self.state/'inbox/ui.json').write_text('x' * (updater.SMALL_JSON_MAX + 1))
        self.assertIsNone(updater.read_ui(self.state, 'r1'))

    def test_files_the_other_user_reads_are_0644(self):
        updater.queue_request(self.state, 'check')
        self.assertEqual((self.state/'inbox/request.json').stat().st_mode & 0o777, 0o644)
        self.run_request()
        self.assertEqual((self.state/'status.json').stat().st_mode & 0o777, 0o644)


class RequestAgeAndDeadlineTests(UpdaterCase):
    def test_expired_request_is_ignored(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        self.check()
        updater.start(self.state, self.pi, old, f'UPDATE TO {new}')
        status = self.run_request(now=time.time() + updater.REQUEST_MAX_AGE + 5)
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('older than 15 minutes', status['error'])
        self.assertEqual(self.repos.head(), old)
        request = {'action': 'check', 'requestId': 'a'*32}  # undated
        (self.state/'inbox/request.json').write_text(json.dumps(request))
        self.assertIn('older than 15 minutes', self.run_request()['error'])

    def test_no_switch_without_enough_time_left(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        status = self.apply(new, deadline=time.monotonic() + updater.SWITCH_MARGIN - 1)
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('not enough time left', status['error'])
        self.assertEqual(self.repos.head(), old)
        self.assert_no_stage()

    def test_sigterm_during_switch_rolls_back(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        with mock.patch.object(updater, 'verify_switched', side_effect=updater.Stopped('stopped by systemd')):
            status = self.apply(new)
        self.assertEqual(status['phase'], 'failed')
        self.assertIn('stopped by systemd (rolled back to', status['error'])
        self.assertEqual(self.repos.head(), old)
        self.assert_no_stage()

    def test_sigterm_handler_raises_once(self):
        previous = updater.signal.getsignal(updater.signal.SIGTERM)
        self.addCleanup(updater.signal.signal, updater.signal.SIGTERM, previous)
        updater.install_sigterm()
        with self.assertRaises(updater.Stopped):
            os.kill(os.getpid(), updater.signal.SIGTERM)
            time.sleep(1)
        self.assertEqual(updater.signal.getsignal(updater.signal.SIGTERM), updater.signal.SIG_IGN)

    def test_rollback_ignores_sigterm(self):
        seen = []
        real = updater.git

        def spy(repo, *args, **kwargs):
            if args[:1] == ('reset',):
                seen.append(updater.signal.getsignal(updater.signal.SIGTERM))
            return real(repo, *args, **kwargs)
        previous = updater.signal.getsignal(updater.signal.SIGTERM)
        with mock.patch.object(updater, 'git', spy):
            updater.roll_back(self.pi, self.repos.head(), time.time())
        self.assertEqual(seen, [updater.signal.SIG_IGN])
        self.assertEqual(updater.signal.getsignal(updater.signal.SIGTERM), previous)

    def test_request_queued_during_a_run_is_handled_in_the_same_run(self):
        real = updater.do_check
        calls = []

        def check_then_queue(state, repo, status):
            calls.append(status['requestId'])
            real(state, repo, status)
            if len(calls) == 1:
                updater._write_request(state, 'check')  # the path unit would miss this one: the service is still active
        updater.queue_request(self.state, 'check')
        with mock.patch.object(updater, 'do_check', check_then_queue):
            self.run_request()
        self.assertEqual(len(calls), 2)

    def test_stale_index_lock_is_removed(self):
        lock = self.pi/'.git/index.lock'
        lock.touch()
        stale = time.time() - updater.STALE_SECONDS - 60
        os.utime(lock, (stale, stale))
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        status = self.apply(new)
        self.assertEqual(status['phase'], 'switched', status['error'])
        self.assertFalse(lock.exists())
        self.assertTrue(any('stale .git/index.lock' in line for line in status['log']))


class RollbackTests(UpdaterCase):
    """S4: the update unit watches the restart after a switch and resets the checkout when the new UI never serves."""

    def ui(self, old, serves, fired):
        """Plays the old UI's watcher (exit 86 -> 'restarting'), then, if `serves`, the new UI's reconcile()."""
        def loop():
            deadline = time.time() + 30
            while time.time() < deadline and not fired:
                updater.watch_once(self.state, self.pi, old, exit=fired.append, pause=0)
                time.sleep(0.05)
            if serves and fired:
                updater.reconcile(self.state, self.repos.head())
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        return thread

    def test_new_ui_serves_complete(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        fired = []
        thread = self.ui(old, True, fired)
        status = self.apply(new, restart_wait=20, verify_wait=20)
        thread.join(5)
        self.assertEqual(fired, [86])
        self.assertEqual((status['phase'], status['error'], self.repos.head()), ('complete', None, new))

    def test_completed_update_with_unit_changes_queues_the_automatic_apply(self):
        old = self.repos.head()
        (self.state/'units-applied.json').write_text(json.dumps({'commit': old}))
        new = self.repos.push({'publisher/deploy/scalar-social-ui.service': 'changed\n'})
        fired = []
        thread = self.ui(old, True, fired)
        status = self.apply(new, restart_wait=20, verify_wait=20)
        thread.join(5)
        self.assertEqual(status['phase'], 'complete')
        self.assertEqual(json.loads((self.state/'units-pending.json').read_text())['commit'], new)
        info = updater.info(self.state, self.pi, new)
        self.assertEqual((info['unitsChanged'], info['unitsApply']['phase'], info['unitsApply']['commit']), (True, 'queued', new))
        self.assertTrue(any('applies them automatically' in line for line in status['log']))

    def test_completed_update_without_unit_changes_queues_nothing(self):
        old = self.repos.head()
        (self.state/'units-applied.json').write_text(json.dumps({'commit': old}))
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        fired = []
        thread = self.ui(old, True, fired)
        self.assertEqual(self.apply(new, restart_wait=20, verify_wait=20)['phase'], 'complete')
        thread.join(5)
        self.assertFalse((self.state/'units-pending.json').exists())
        self.assertIsNone(updater.info(self.state, self.pi, new)['unitsApply'])

    def test_units_apply_reads_typed_fields_only(self):
        sha = self.repos.head()
        (self.state/'units-apply.json').write_text(json.dumps({'phase': 'failed', 'commit': sha, 'at': '2026-10-09T06:00:00Z',
                                                                'error': 'npm ci failed', 'log': ['a', 7, 'b'], 'extra': 'x'}))
        self.assertEqual(updater.units_apply(self.state), {'phase': 'failed', 'commit': sha, 'at': '2026-10-09T06:00:00Z',
                                                            'error': 'npm ci failed', 'log': ['a', 'b']})
        for bad in ('{', json.dumps({'phase': 'done'}), json.dumps([1])):
            (self.state/'units-apply.json').write_text(bad)
            self.assertIsNone(updater.units_apply(self.state))

    def test_crash_loop_is_rolled_back(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        fired = []
        thread = self.ui(old, False, fired)
        started = time.monotonic()
        status = self.apply(new, restart_wait=20, verify_wait=1)
        thread.join(5)
        self.assertLess(time.monotonic() - started, 60)
        self.assertEqual(fired, [86])
        self.assertEqual(status['phase'], 'failed')
        self.assertIn(f'did not come back on {new[:12]}', status['error'])
        self.assertIn(f'rolled back to {old[:12]}', status['error'])
        self.assertEqual(self.repos.head(), old)
        self.assertEqual(git(self.pi, 'status', '--porcelain'), '')
        self.assertEqual(status['check']['head'], old)
        # The old code starts: nothing more to do. A late UI that did come up on the new commit restarts itself.
        self.assertEqual(updater.reconcile(self.state, old)['phase'], 'failed')
        self.assertEqual(updater.read_status(self.state)['phase'], 'failed')
        exits = []
        self.assertFalse(updater.watch_once(self.state, self.pi, old, exit=exits.append, pause=0))
        self.assertTrue(updater.watch_once(self.state, self.pi, new, exit=exits.append, pause=0))
        self.assertEqual(exits, [86])
        self.assertEqual(updater.read_status(self.state)['phase'], 'failed')

    def test_ui_not_running_leaves_the_switch(self):
        old = self.repos.head()
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        status = self.apply(new, restart_wait=0.5, verify_wait=0.5)
        self.assertEqual((status['phase'], self.repos.head()), ('switched', new))
        self.assertIn('has not restarted yet', status['log'][-1])
        self.assertEqual(updater.reconcile(self.state, new)['phase'], 'complete')
        self.assertNotEqual(old, new)


class UpdateApiTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.repos = Repos(Path(self.tmp.name).resolve()/'git')
        self.app.repo, self.app.running = self.repos.pi, self.repos.head()
        self.app.update_state = self.repos.state
        env = mock.patch.dict(os.environ, {updater.ORIGINS_ENV: self.repos.url})
        env.start()
        self.addCleanup(env.stop)

    def test_status_check_start(self):
        status, body = self.json('GET', '/api/system/update/status')
        self.assertEqual(status, 200)
        self.assertEqual(set(body), CONTRACT_FIELDS)
        self.assertEqual((body['installKind'], body['status']['phase']), ('git', 'idle'))
        self.assertEqual(self.json('GET', '/api/system/update/status', auth=False)[0], 401)
        self.assertEqual(self.json('POST', '/api/system/update/check', mutate=False)[0], 403)  # CSRF header + origin
        self.assertEqual(self.json('POST', '/api/system/update/check', {}), (202, {'queued': True}))
        status, body = self.json('POST', '/api/system/update/check', {})
        self.assertEqual((status, body['code']), (409, 'busy'))
        self.assertEqual(set(body), {'error', 'nextAction', 'code'})
        head = self.repos.head()
        status, body = self.json('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {head}'})
        self.assertEqual((status, body['code']), (409, 'busy'))
        updater.run_request(self.repos.state, self.repos.pi, quick_tests=QUICK, restart_wait=0, lock_path=self.repos.home/'runner.lock')  # what the unit does
        status, body = self.json('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {head}'})
        self.assertEqual((status, body['code']), (409, 'up_to_date'))
        new = self.repos.push({'publisher/app/mod_a.py': 'VALUE = 2\n'})
        self.assertEqual(self.json('POST', '/api/system/update/check')[0], 202)
        updater.run_request(self.repos.state, self.repos.pi, quick_tests=QUICK, restart_wait=0, lock_path=self.repos.home/'runner.lock')
        status, body = self.json('GET', '/api/system/update/status')
        self.assertEqual((body['status']['phase'], body['status']['check']['origin']), ('checked', new))
        status, body = self.json('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {new[:7]}'})
        self.assertEqual((status, body['code']), (400, 'bad_confirm'))
        self.assertEqual(self.json('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {new}'}), (202, {'queued': True}))
        request = json.loads((self.repos.state/'inbox/request.json').read_text())
        self.assertEqual((request['action'], request['sha']), ('apply', new))
        self.assertEqual(self.json('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {new}'})[1]['code'], 'busy')
        updater.run_request(self.repos.state, self.repos.pi, quick_tests=QUICK, restart_wait=0, lock_path=self.repos.home/'runner.lock')
        status, body = self.json('GET', '/api/system/update/status')
        self.assertEqual((body['status']['phase'], body['repoHead'], body['restartNeeded']), ('switched', new, True))

    def test_copy_install(self):
        self.app.running = None
        self.assertEqual(self.json('POST', '/api/system/update/check', {})[1]['code'], 'not_git')
        status, body = self.json('POST', '/api/system/update/start', {'confirm': 'UPDATE TO ' + 'a'*40})
        self.assertEqual((status, body['code']), (409, 'not_git'))
        self.assertEqual(self.json('GET', '/api/system/update/status')[1]['installKind'], 'copy')

    def test_manifest_not_served(self):
        (self.static/'MANIFEST.json').write_text('{}')
        for path in ('/MANIFEST.json', '/./MANIFEST.json', '//MANIFEST.json', '/assets/../MANIFEST.json', '/x/%2e%2e/MANIFEST.json'):
            self.assertEqual(self.request('GET', path, auth=False)[0], 404, path)

    def test_sd_notify_ready(self):
        import socket
        import ui_server
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        path = os.path.join(folder, 'notify')
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.bind(path)
            sock.settimeout(5)
            with mock.patch.dict(os.environ, {'NOTIFY_SOCKET': path}):
                self.assertTrue(ui_server.sd_notify('READY=1'))
            self.assertEqual(sock.recv(64), b'READY=1')
        with mock.patch.dict(os.environ, {'NOTIFY_SOCKET': ''}):
            self.assertFalse(ui_server.sd_notify('READY=1'))  # outside systemd: a no-op

    def test_bad_content_length_is_400(self):
        status, _, _ = self.request('POST', '/api/system/update/check', b'{}', headers={'Content-Length': 'x'})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
