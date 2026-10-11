"""Mac end-to-end demo of the Pi self-update (not a unittest; run by hand):

    python3 publisher/tests/selfupdate_demo.py [--keep] [--scratch DIR]

Builds "GitHub" (a bare origin) from a temp clone of THIS repo plus the current working tree's publisher/ and
contract/, clones a partial + sparse "Pi" checkout over file://, starts the real ui_server.py from that checkout
(--insecure-dev, loopback) and drives the API with urllib. Where systemd would start
scalar-social-update.service, the demo runs `updater.py run-request` itself (in the background, as the unit
does); where systemd would restart the UI after exit 86 (or after a crash), the demo restarts it. Two folders play the two
users' state (/var/lib/scalar-social and /var/lib/scalar-social-update with its inbox/). Every process
gets HOME = the scalar-social state folder with a planted ~/.gitconfig (core.fsmonitor, hooksPath) and ~/.ssh/config, as
an attacker with scalar-social's rights could plant on the Pi (M1); the demo shows that it is live for a plain
git and never runs inside the updater or the UI. Prints a transcript. Touches nothing outside the scratch folder.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[2]
SKIP = ('node_modules/', '/dist/', 'test-results/', 'playwright-report/', '__pycache__/', '.DS_Store')


def say(text=''):
    print(text, flush=True)


def git(cwd, *args, check=True):
    proc = subprocess.run(['git', '-c', 'user.name=Demo', '-c', 'user.email=demo@example.com', '-c', 'commit.gpgsign=false',
                           '-c', 'protocol.file.allow=always', *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode:
        raise SystemExit(f'git {" ".join(args)} failed: {proc.stderr.strip()}')
    return proc.stdout.strip()


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Demo:
    def __init__(self, scratch):
        self.scratch = scratch
        self.src, self.origin, self.pi = scratch/'src', scratch/'origin.git', scratch/'pi'
        self.state = scratch/'scalar-social'           # /var/lib/scalar-social: the UI's state and HOME, runner.lock
        self.ustate = scratch/'scalar-social-update'   # /var/lib/scalar-social-update: status.json, inbox/
        self.url = f'file://{self.origin}'
        self.marker = scratch/'PLANTED-CONFIG-RAN'
        # As on the Pi: HOME is the scalar-social state folder (attacker-writable); /opt is read-only for the UI,
        # so it never writes bytecode into the checkout.
        self.env = {**os.environ, 'SCALAR_UPDATE_ORIGINS': self.url, 'HOME': str(self.state),
                    'XDG_CONFIG_HOME': str(self.state/'.config'), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.env.pop('CREDENTIALS_DIRECTORY', None)
        self.unit_proc = None
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        self.server = None

    # --- repos ------------------------------------------------------------------
    def build(self):
        say(f'# Setup in {self.scratch}')
        git(self.scratch, 'clone', '-q', '--no-local', str(REPO), str(self.src))
        git(self.src, 'checkout', '-q', '-B', 'main')  # REPO may be on a worktree branch
        # Overlay the working tree (uncommitted self-update work included) for publisher/ and contract/.
        listed = git(REPO, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', 'publisher', 'contract').split('\0')
        for shutil_dir in ('publisher', 'contract'):
            shutil.rmtree(self.src/shutil_dir)
        for name in filter(None, listed):
            source = REPO/name
            if source.is_file() and not any(part in name for part in SKIP):
                target = self.src/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        git(self.src, 'add', '-A')
        git(self.src, 'commit', '-q', '--allow-empty', '-m', 'demo: baseline = current working tree')
        git(self.scratch, 'clone', '-q', '--bare', str(self.src), str(self.origin))
        git(self.origin, 'config', 'uploadpack.allowFilter', 'true')
        git(self.src, 'remote', 'set-url', 'origin', str(self.origin))
        git(self.scratch, 'clone', '-q', '--filter=blob:none', '--no-checkout', self.url, str(self.pi))
        git(self.pi, 'sparse-checkout', 'set', '--cone', 'publisher', 'contract')
        git(self.pi, 'checkout', '-q', 'main')
        self.state.mkdir()
        (self.state/'PAUSED').touch()
        (self.ustate/'inbox').mkdir(parents=True)
        self.plant()
        shutil.copy(REPO/'publisher/config.example.json', self.scratch/'config.json')
        top = sorted(p.name for p in self.pi.iterdir() if p.name != '.git')
        say(f'origin = bare repo, Pi = partial (blob:none) + sparse clone; Pi top level: {top}')
        say(f'Pi HEAD {self.head()}')

    def head(self):
        return git(self.pi, 'rev-parse', 'HEAD')

    def plant(self):
        script = self.state/'evil.sh'
        script.write_text(f'#!/bin/sh\ntouch {self.marker}\nexit 1\n')
        script.chmod(0o755)
        hooks = self.state/'hooks'
        hooks.mkdir()
        for name in ('post-checkout', 'post-merge', 'reference-transaction'):
            (hooks/name).write_text(f'#!/bin/sh\ntouch {self.marker}\n')
            (hooks/name).chmod(0o755)
        (self.state/'.gitconfig').write_text(f'[core]\n\tfsmonitor = {script}\n\thooksPath = {hooks}\n\tsshCommand = {script}\n')
        (self.state/'.ssh').mkdir()
        (self.state/'.ssh/config').write_text(f'Host *\n  ProxyCommand {script}\n')
        subprocess.run(['git', 'status', '--porcelain'], cwd=self.pi, env=self.env, capture_output=True)
        live = self.marker.exists()
        self.marker.unlink(missing_ok=True)
        say(f'M1 plant: HOME={self.state} has .gitconfig (core.fsmonitor, core.hooksPath, core.sshCommand) and .ssh/config '
            f'(ProxyCommand); a plain `git status` there runs it: {live}')
        assert live

    def planted_ran(self):
        return self.marker.exists()

    def push(self, files, message):
        for name, text in files.items():
            path = self.src/name
            if text is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        git(self.src, 'add', '-A')
        git(self.src, 'commit', '-q', '-m', message)
        git(self.src, 'push', '-q', 'origin', 'main')
        sha = git(self.src, 'rev-parse', 'HEAD')
        say(f'GitHub main <- {sha[:12]} "{message}"')
        return sha

    # --- server and unit -------------------------------------------------------------
    def start_server(self, quiet=False, seconds=20):
        log = open(self.scratch/'ui-server.log', 'a')
        # The UI plays scalar-social reading a checkout another user owns: git refuses it unless safe.directory.
        self.server = subprocess.Popen(
            [sys.executable, str(self.pi/'publisher/app/ui_server.py'), '--state', str(self.state),
             '--update-state', str(self.ustate), '--config', str(self.scratch/'config.json'),
             '--static', str(self.pi/'publisher/app/static'), '--port', str(self.port), '--insecure-dev', '--no-legacy',
             '--allowed-origin', self.base], cwd=self.pi, env={**self.env, 'GIT_TEST_ASSUME_DIFFERENT_OWNER': '1'},
            stdout=log, stderr=log)
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.server.poll() is not None:
                break
            try:
                with urllib.request.urlopen(self.base + '/api/health', timeout=2):
                    if not quiet:
                        say(f'UI server started from the Pi checkout (pid {self.server.pid}, port {self.port})')
                    return
            except OSError:
                time.sleep(0.2)
        if quiet:
            if self.server.poll() is None:
                self.server.terminate()
                self.server.wait(10)
            raise RuntimeError('UI did not start')
        raise SystemExit('UI server did not start; see ui-server.log')

    def api(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': 'application/json'} if data else {}
        if method != 'GET':
            headers.update({'X-Scalar-Request': '1', 'Origin': self.base})
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b'null')
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b'null')

    def call(self, method, path, body=None):
        status, reply = self.api(method, path, body)
        shown = {k: reply[k] for k in ('queued', 'code', 'error') if isinstance(reply, dict) and k in reply}
        say(f'{method} {path}{" " + json.dumps(body) if body else ""} -> {status} {json.dumps(shown)}')
        return status, reply

    def unit(self, lock_timeout=None, verify_wait=None, background=False):
        command = [sys.executable, '-I', '-B', str(self.pi/'publisher/app/updater.py'), 'run-request', '--state', str(self.ustate),
                   '--runner-lock', str(self.state/'runner.lock'), '--repo', str(self.pi)]
        if lock_timeout is not None:
            command += ['--lock-timeout', str(lock_timeout)]
        if verify_wait is not None:
            command += ['--verify-wait', str(verify_wait)]
        self.unit_started = time.time()
        self.unit_proc = subprocess.Popen(command, cwd=self.pi, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not background:
            self.unit_wait()

    def unit_wait(self, seconds=900):
        code = self.unit_proc.wait(seconds)
        say(f'[scalar-social-update.service] updater.py run-request -> exit {code} in {time.time()-self.unit_started:.1f}s')

    def status(self, label='status'):
        _, info = self.api('GET', '/api/system/update/status')
        status, check = info['status'], info['status']['check'] or {}
        say(f'GET /api/system/update/status ({label}): phase={status["phase"]} running={str(info["runningCommit"])[:12]} '
            f'repoHead={str(info["repoHead"])[:12]} restartNeeded={info["restartNeeded"]} installKind={info["installKind"]}')
        if check:
            say(f'    check: behind={check["behind"]} ahead={check["ahead"]} dirty={check["dirty"]} diverged={check["diverged"]} '
                f'originOk={check["originOk"]} branchOk={check["branchOk"]} origin={str(check["origin"])[:12]} '
                f'incoming={[c["subject"] for c in check["incoming"]]} changes={ {k: v for k, v in check["changes"].items() if k != "files"} }')
        if status['error']:
            say(f'    error: {status["error"]}')
        return info

    def check(self):
        self.call('POST', '/api/system/update/check', {})
        self.unit()
        return self.status('after check')

    def wait_for_exit(self, seconds=900):
        try:
            code = self.server.wait(seconds)
        except subprocess.TimeoutExpired:
            raise SystemExit('UI server did not exit after the switch') from None
        say(f'UI server exited with code {code} (systemd Restart=on-failure would restart it)')
        return code

    def systemd_restarts(self):
        """Restart=on-failure, RestartSec shortened to 1 s: restart the UI until it serves or the unit finishes."""
        attempts = 0
        while True:
            attempts += 1
            try:
                self.start_server(quiet=True, seconds=6)
                say(f'[systemd] UI start attempt {attempts}: serving on {self.head()[:12]}')
                return attempts
            except RuntimeError:
                say(f'[systemd] UI start attempt {attempts}: exited with {self.server.poll()} (crash); restarting in 1 s')
                time.sleep(1)

    def stop(self):
        if self.server and self.server.poll() is None:
            self.server.terminate()
            self.server.wait(10)

    # --- scenarios ----------------------------------------------------------------
    def happy(self):
        say('\n## 1. Happy path: check -> confirm -> staged checks -> switch -> exit 86 -> restart -> complete')
        self.start_server()
        before = self.status('fresh install')
        assert before['installKind'] == 'git' and before['status']['phase'] == 'idle'
        self.check()
        target = self.push({'publisher/docs/SELF_UPDATE_DEMO.md': 'Delivered by the self-update demo.\n'}, 'demo: harmless docs change')
        info = self.check()
        assert info['status']['check']['behind'] == 1
        status, _ = self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {target[:12]}'})
        assert status == 400
        status, _ = self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {target}'})
        assert status == 202
        self.unit(background=True)
        code = self.wait_for_exit()
        assert code == 86
        say('    status.json: ' + ' | '.join(json.loads((self.ustate/'status.json').read_text())['log'][-4:]))
        say(f'Pi HEAD is now {self.head()[:12]}; restarting the UI')
        self.start_server()
        self.unit_wait()  # the unit saw the new UI serving (phase complete) and exits
        info = self.status('after restart')
        assert info['status']['phase'] == 'complete' and info['runningCommit'] == target, info
        say('    log: ' + ' | '.join(info['status']['log'][-6:]))
        return target

    def failing_check(self, good):
        say('\n## 2. Failing staged check: nothing switches, the UI keeps running the old commit')
        bad = self.push({'publisher/app/demo_broken.py': 'def broken(:\n'}, 'demo: broken module')
        self.check()
        self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {bad}'})
        self.unit()
        time.sleep(2.5)
        assert self.server.poll() is None, 'UI exited after a failed update'
        info = self.status('after failed apply')
        assert info['status']['phase'] == 'failed' and info['repoHead'] == good and info['runningCommit'] == good
        stages = list((self.pi/'.git/scalar-update-stage').glob('stage-*'))
        say(f'Pi HEAD still {self.head()[:12]}; stage worktrees left: {len(stages)}; UI still up: {self.server.poll() is None}')
        return self.push({'publisher/app/demo_broken.py': None}, 'demo: remove the broken module')

    def dirty(self):
        say('\n## 3. Dirty checkout: start refused with 409 dirty')
        stray = self.pi/'publisher/app/stray_local_edit.py'
        stray.write_text('X = 1\n')
        info = self.check()
        status, reply = self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {info["status"]["check"]["origin"]}'})
        assert (status, reply['code']) == (409, 'dirty')
        stray.unlink()

    def diverged(self):
        say('\n## 4. Diverged history: start refused with 409 diverged')
        before = self.head()
        git(self.pi, 'commit', '-q', '--allow-empty', '-m', 'local commit made on the Pi')
        info = self.check()
        status, reply = self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {info["status"]["check"]["origin"]}'})
        assert (status, reply['code']) == (409, 'diverged')
        git(self.pi, 'reset', '-q', '--hard', before)
        say(f'(demo cleanup: Pi reset to {before[:12]})')

    def lock_held(self):
        say('\n## 5. Publisher holds runner.lock: apply waits, then fails with the busy message')
        info = self.check()
        target = info['status']['check']['origin']
        self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {target}'})
        with open(self.state/'runner.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            say('(demo holds runner.lock like a running post; unit lock timeout 3 s)')
            self.unit(lock_timeout=3)
        info = self.status('after lock timeout')
        assert info['status']['phase'] == 'failed' and 'Publisher is running a post' in info['status']['error']
        say(f'Pi HEAD still {self.head()[:12]}')
        say('\n## 6. Lock free again: the same update now applies')
        self.check()
        self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {target}'})
        self.unit(background=True)
        self.wait_for_exit()
        self.start_server()
        self.unit_wait()
        info = self.status('after restart')
        assert info['status']['phase'] == 'complete' and info['runningCommit'] == target
        return target

    def crash_rollback(self, good):
        say('\n## 7. New code passes the staged checks but the UI crashes at start: automatic rollback')
        source = (self.src/'publisher/app/ui_server.py').read_text()
        broken = source.replace("    parser = argparse.ArgumentParser(description='Scalar social Pi UI (loopback only).')",
                                "    raise SystemExit('demo: crash at start')\n"
                                "    parser = argparse.ArgumentParser(description='Scalar social Pi UI (loopback only).')", 1)
        assert broken != source
        bad = self.push({'publisher/app/ui_server.py': broken}, 'demo: UI crashes at start')
        self.check()
        self.call('POST', '/api/system/update/start', {'confirm': f'UPDATE TO {bad}'})
        say('(unit verify window shortened to 8 s for the demo; the Pi waits 120 s)')
        self.unit(background=True, verify_wait=8)
        assert self.wait_for_exit() == 86
        say(f'Pi HEAD is now {self.head()[:12]} (the crashing commit)')
        attempts = self.systemd_restarts()
        self.unit_wait()
        info = self.status('after automatic rollback')
        assert info['status']['phase'] == 'failed' and 'rolled back' in info['status']['error'], info
        assert info['runningCommit'] == good and info['repoHead'] == good, info
        say(f'UI back on {good[:12]} after {attempts} start attempt(s); nobody had to SSH in')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scratch', help='folder to build in (default: a new temp folder)')
    parser.add_argument('--keep', action='store_true', help='keep the scratch folder')
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix='selfupdate-demo-', dir=args.scratch)).resolve()
    demo = Demo(scratch)
    try:
        demo.build()
        good = demo.happy()
        demo.failing_check(good)
        demo.dirty()
        demo.diverged()
        good = demo.lock_held()
        demo.crash_rollback(good)
        assert not demo.planted_ran(), 'planted HOME config ran'
        say(f'\nM1: planted HOME config ran inside the updater or the UI: {demo.planted_ran()}')
        say('All scenarios behaved as specified.')
    finally:
        demo.stop()
        if args.keep:
            say(f'Kept {scratch}')
        else:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == '__main__':
    main()
