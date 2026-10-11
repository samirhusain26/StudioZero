import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
import datetime as dt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
import approval_bind
import runner
import ui_approval
from buffer_adapter import PublishError
from library_contract import canonical

BASE = 'https://media.example.test'
SENTINEL = 'sentinel-credential-7f3a91'
NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)


def draft_sha(draft):
    return hashlib.sha256(canonical(draft)).hexdigest()


def build_payload(job, draft, config):
    return {'episode': {'id': job['questionId'], 'episodeId': job['episodeId'], 'revision': 1, 'game': 'scalar'},
            'kind': 'post', 'format': 'self-contained', 'caption': job['text'], 'link': None, 'previous': None,
            'media': {'url': BASE+'/library/'+job['videoSha256']+'.mp4', 'sha256': job['videoSha256'],
                      'bytes': job['bytes'], 'rightsReviewed': True},
            'metadata': {}, 'thread': None, 'approval': {'draftSha256': draft_sha(draft)}}


class Env(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.state = base/'state'
        self.state.mkdir()
        (base/'etc').mkdir()
        self.config_path = base/'etc'/'config.json'
        self.config = json.loads((ROOT/'publisher/config.example.json').read_text())
        self.config['media'].update(baseUrl=BASE, pagesProject='scalar-test', cloudflareAccountId='acct')
        self.config['channels']['x'].update(accountId='x-1', identityVerified=True, publishingVerified=True)
        self.config['channels']['instagram'].update(accountId='ig-1', identityVerified=True, publishingVerified=True)
        self.write_config()
        os.chmod(self.config_path, 0o640)
        creds = base/'creds'
        creds.mkdir()
        (creds/'CLOUDFLARE_API_TOKEN').write_text(SENTINEL)
        patcher = mock.patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(creds)})
        patcher.start()
        self.addCleanup(patcher.stop)
        objects = self.state/'library'/'objects'
        objects.mkdir(parents=True)
        self.videos = {}
        for name in ('a', 'b', 'c'):
            data = b'video-'+name.encode()*100
            sha = hashlib.sha256(data).hexdigest()
            (objects/f'{sha}.mp4').write_bytes(data)
            self.videos[name] = (sha, len(data))
        self.ledger = runner.Ledger(self.state/'ledger.sqlite3')
        self.drafts, self.deploys, self.recorded = {}, [], []
        self.verify_override = None

    def tearDown(self):
        self.ledger.db.close()
        self.temp.cleanup()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config, indent=2)+'\n')

    def job(self, platform, slot, video, q, carried=False, text=None):
        account = {'x': 'x-1', 'instagram': 'ig-1'}.get(platform, 'acct')
        sha, size = self.videos[video]
        return {'key': f'{platform}|{slot}|{q}', 'platform': platform, 'accountId': account, 'slotUtc': slot,
                'kind': 'post', 'episodeKey': q, 'parentKey': None, 'episodeId': 'ep-'+q, 'revision': 1,
                'questionId': q, 'videoSha256': sha, 'bytes': size, 'text': text or 'Guess '+q, 'carried': carried}

    def draft(self, jobs, base=None):
        draft = {'version': 1, 'inputs': {'timezone': 'America/New_York'}, 'baseManifestSha256': base, 'jobs': jobs}
        sha = draft_sha(draft)
        self.drafts[sha] = draft
        return sha

    def deployer(self, ledger, config, site):
        token = (Path(os.environ['CREDENTIALS_DIRECTORY'])/'CLOUDFLARE_API_TOKEN').read_text()
        self.assertEqual(token, SENTINEL)
        self.deploys.append(sorted(p.name for p in (site/'library').iterdir()))

    def verifier(self, url, sha):
        if self.verify_override:
            return self.verify_override(url, sha)
        name = url.rsplit('/', 1)[1]
        data = (self.state/'site'/'library'/name).read_bytes()
        return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'publicDeliveryVerified': True}

    def apply(self, sha, deploy=True, **overrides):
        ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}', now=NOW)
        options = dict(deploy=deploy, deployer=self.deployer, verifier=self.verifier,
                       load_draft=lambda state, s: self.drafts.get(s), revalidate=lambda *a: None,
                       build_payload=build_payload, record_manifest=lambda *a: self.recorded.append(a), now=NOW)
        options.update(overrides)
        return ui_approval.apply(self.state, self.config_path, **options)

    def enqueue_manifest(self):
        _, manifest = ui_approval.current_manifest(self.state)
        keys = {}
        for job in manifest['jobs']:
            account = self.config['channels'][job['platform']]['accountId']
            keys[job['key']] = self.ledger.enqueue(job['platform'], account, job['slot'], job['payload'])
        return keys

    def listing(self):
        out = {}
        for path in sorted(Path(self.temp.name).rglob('*')):
            rel = str(path.relative_to(self.temp.name))
            out[rel] = None if path.is_dir() or rel.endswith(('-wal', '-shm')) else path.read_bytes()
        return out

    def assert_no_secret(self, *texts):
        for path in Path(self.temp.name).rglob('*'):
            if path.is_file() and path.name != 'CLOUDFLARE_API_TOKEN' and not path.name.startswith('ledger'):
                self.assertNotIn(SENTINEL.encode(), path.read_bytes(), path)
        for text in texts:
            self.assertNotIn(SENTINEL, text)


class RequestTests(Env):
    def test_confirmation_must_match_and_request_is_exclusive(self):
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        with self.assertRaises(ValueError):
            ui_approval.request_approval(self.state, sha, 'APPROVE 00000000')
        self.assertFalse((self.state/'approval'/'request.json').exists())
        with self.assertRaises(ValueError):
            ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}', draft_exists=lambda s: False)
        ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}', draft_exists=True, now=NOW)
        path = self.state/'approval'/'request.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text()), {'draftSha256': sha, 'requestedAt': '2026-10-10T12:00:00Z'})
        with self.assertRaises(ui_approval.Conflict):
            ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}')
        self.assertEqual(sorted(p.name for p in (self.state/'approval').iterdir()), ['request.json'])
        self.assertEqual(ui_approval.approval_state(self.state)['pending']['draftSha256'], sha)


class ApplyTests(Env):
    def test_happy_path_writes_exact_manifest_and_archives_request(self):
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1'),
                          self.job('instagram', '2026-10-12T13:00:00+00:00', 'b', 'q2')])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = self.apply(sha)
        self.assertEqual(result['status'], 'manifest-ready', result)
        msha = result['manifestSha256']
        raw = (self.state/'manifests'/f'{msha}.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), msha)
        self.assertEqual((self.state/'manifests'/'approved.json').read_bytes(), raw)
        manifest = json.loads(raw)
        self.assertEqual(manifest['scope'], ['instagram', 'x'])
        intended = json.loads(json.dumps(self.config))
        for p, c in intended['channels'].items():
            c['enabled'] = p in ('instagram', 'x')
        self.assertEqual(manifest['scopeHash'], runner.fingerprint(intended))
        self.assertEqual(manifest['draftSha256'], sha)
        self.assertEqual(manifest['approvedAt'], '2026-10-10T12:00:00Z')
        verification = json.loads((self.state/'manifests'/f'{msha}.verification.json').read_text())
        self.assertTrue(verification['allVerified'])
        self.assertEqual(len(verification['urls']), 2)
        self.assertEqual(len(self.deploys), 1)
        self.assertEqual(self.deploys[0], sorted(f'{self.videos[n][0]}.mp4' for n in 'ab'))
        objects = self.state/'library'/'objects'/f'{self.videos["a"][0]}.mp4'
        self.assertEqual(os.stat(objects).st_ino, os.stat(self.state/'site'/'library'/f'{self.videos["a"][0]}.mp4').st_ino)
        self.assertEqual(json.loads((self.state/'approval'/'result.json').read_text())['status'], 'manifest-ready')
        self.assertEqual(result['scope'], ['instagram', 'x'])
        self.assertEqual(result['jobs'], 2)
        self.assertFalse((self.state/'approval'/'request.json').exists())
        history = sorted(p.name for p in (self.state/'approval'/'history').iterdir())
        self.assertEqual(len(history), 2)
        self.assertTrue(history[0].endswith('-request.json') and history[1].endswith('-result.json'))
        self.assertEqual(self.recorded[0][1], msha)
        self.assertEqual(ui_approval.current_manifest(self.state)[0], msha)
        self.assertEqual(self.config_path.read_text(), json.dumps(self.config, indent=2)+'\n')
        self.assert_no_secret(out.getvalue())

    def test_verifier_hash_mismatch_fails_without_manifest(self):
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        self.verify_override = lambda url, digest: {'sha256': '0'*64, 'bytes': 1}
        result = self.apply(sha)
        self.assertEqual((result['status'], result['category']), ('failed', 'media_delivery'))
        self.assertFalse((self.state/'manifests').exists())
        self.verify_override = lambda url, digest: (_ for _ in ()).throw(PublishError('media'))
        result = self.apply(sha)
        self.assertEqual(result['category'], 'media_delivery')
        self.assertFalse((self.state/'manifests').exists())
        self.assertFalse((self.state/'approval'/'request.json').exists())

    def test_unverified_or_disabled_channel_and_stale_account_fail(self):
        self.config['channels']['x']['publishingVerified'] = False
        self.write_config()
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        result = self.apply(sha)
        self.assertEqual(result['category'], 'scope')
        self.assertIn('X account identity and publishing test', result['message'])
        self.config['channels']['x']['publishingVerified'] = True
        self.write_config()
        stale = self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')
        stale['accountId'] = 'x-previous'
        result = self.apply(self.draft([stale]))
        self.assertEqual(result['category'], 'stale_draft')
        result = self.apply(self.draft([self.job('facebook', '2026-10-12T13:00:00+00:00', 'a', 'q1')]))
        self.assertEqual(result['category'], 'stale_draft')
        result = self.apply(sha, revalidate=lambda *a: (_ for _ in ()).throw(ValueError('changed')))
        self.assertEqual(result['category'], 'stale_draft')
        self.assertFalse((self.state/'manifests').exists())
        self.assertEqual(self.deploys, [])

    def test_draft_must_be_based_on_current_manifest(self):
        first = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        self.assertEqual(self.apply(first)['status'], 'manifest-ready')
        unbased = self.draft([self.job('x', '2026-10-13T13:00:00+00:00', 'b', 'q2')])
        self.assertEqual(self.apply(unbased)['category'], 'stale_draft')

    def test_reapproval_skips_media_of_finished_posts_whose_video_was_removed(self):
        slot1, slot2 = '2026-10-12T13:00:00+00:00', '2026-10-13T13:00:00+00:00'
        self.assertEqual(self.apply(self.draft([self.job('x', slot1, 'a', 'q1')]))['status'], 'manifest-ready')
        base, _ = ui_approval.current_manifest(self.state)
        keys = self.enqueue_manifest()
        self.ledger.update(keys[f'x|{slot1}|q1'], 'confirmed', dispatched_at=runner.iso(NOW), remote_id='r1')
        sha_a = self.videos['a'][0]
        for path in (self.state/'library'/'objects'/f'{sha_a}.mp4', self.state/'site'/'library'/f'{sha_a}.mp4'):
            path.unlink()   # removed after posting (ui_library.archive_videos)
        result = self.apply(self.draft([self.job('x', slot1, 'a', 'q1', carried=True), self.job('x', slot2, 'b', 'q2')], base=base))
        self.assertEqual(result['status'], 'manifest-ready', result)
        self.assertEqual(self.deploys[-1], [f"{self.videos['b'][0]}.mp4"])
        sha, manifest = ui_approval.current_manifest(self.state)
        self.assertEqual(len(manifest['jobs']), 2)
        checks = json.loads((self.state/'manifests'/f'{sha}.verification.json').read_text())['urls']
        self.assertEqual([c['sha256'] for c in checks], [self.videos['b'][0]])

    def test_dispatched_row_change_is_refused_without_side_effects(self):
        slot1, slot2 = '2026-10-12T13:00:00+00:00', '2026-10-13T13:00:00+00:00'
        self.assertEqual(self.apply(self.draft([self.job('x', slot1, 'a', 'q1'), self.job('x', slot2, 'b', 'q2')]))['status'],
                         'manifest-ready')
        base, _ = ui_approval.current_manifest(self.state)
        keys = self.enqueue_manifest()
        self.ledger.update(keys[f'x|{slot1}|q1'], 'accepted', dispatched_at=runner.iso(NOW), remote_id='r1')
        before_rows = [dict(r) for r in self.ledger.db.execute('SELECT * FROM jobs ORDER BY id')]
        before_events = self.ledger.db.execute('SELECT count(*) FROM events').fetchone()[0]
        deploys = len(self.deploys)
        manifests = sorted(p.name for p in (self.state/'manifests').iterdir())
        removed = self.draft([self.job('x', slot2, 'b', 'q2', carried=True)], base=base)
        edited = self.draft([self.job('x', slot1, 'a', 'q1', carried=True, text='Edited'),
                             self.job('x', slot2, 'b', 'q2', carried=True)], base=base)
        for sha in (removed, edited):
            result = self.apply(sha)
            self.assertEqual(result['category'], 'dispatched_job_changed')
        self.assertEqual([dict(r) for r in self.ledger.db.execute('SELECT * FROM jobs ORDER BY id')], before_rows)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM events').fetchone()[0], before_events)
        self.assertEqual(sorted(p.name for p in (self.state/'manifests').iterdir()), manifests)
        self.assertEqual(ui_approval.current_manifest(self.state)[0], base)
        self.assertEqual(len(self.deploys), deploys)

    def test_undispatched_removed_or_edited_rows_are_cancelled_with_full_prior_row(self):
        slot1, slot2 = '2026-10-12T13:00:00+00:00', '2026-10-13T13:00:00+00:00'
        self.apply(self.draft([self.job('x', slot1, 'a', 'q1'), self.job('x', slot2, 'b', 'q2')]))
        base, _ = ui_approval.current_manifest(self.state)
        keys = self.enqueue_manifest()
        removed_row = dict(self.ledger.db.execute('SELECT * FROM jobs WHERE id=?', (keys[f'x|{slot2}|q2'],)).fetchone())
        kept_row = dict(self.ledger.db.execute('SELECT * FROM jobs WHERE id=?', (keys[f'x|{slot1}|q1'],)).fetchone())
        result = self.apply(self.draft([self.job('x', slot1, 'a', 'q1', carried=True)], base=base))
        self.assertEqual(result['status'], 'manifest-ready', result)
        self.assertEqual(result['cancelled'], 1)
        rows = [dict(r) for r in self.ledger.db.execute('SELECT * FROM jobs')]
        self.assertEqual(rows, [kept_row])
        event = self.ledger.db.execute("SELECT * FROM events WHERE kind='cancelled'").fetchone()
        self.assertEqual(event['job'], removed_row['id'])
        self.assertEqual(json.loads(event['detail']), removed_row)
        _, manifest = ui_approval.current_manifest(self.state)
        self.assertEqual(manifest['jobs'][0]['payload'], json.loads(kept_row['payload']))
        base2 = result['manifestSha256']
        result = self.apply(self.draft([self.job('x', slot1, 'a', 'q1', carried=True, text='Edited')], base=base2))
        self.assertEqual(result['cancelled'], 1)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)

    def test_lock_contention_reports_busy_and_archives(self):
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        with runner.lock(self.state/'runner.lock'):
            result = self.apply(sha)
        self.assertEqual((result['status'], result['category']), ('failed', 'publisher_busy'))
        self.assertFalse((self.state/'approval'/'request.json').exists())
        self.assertFalse((self.state/'manifests').exists())
        self.assertEqual(self.deploys, [])

    def test_no_deploy_writes_only_result(self):
        slot = '2026-10-12T13:00:00+00:00'
        undispatched = self.ledger.enqueue('x', 'x-1', '2026-10-01T13:00:00+00:00', {'episode': {'id': 'old'}})
        sha = self.draft([self.job('x', slot, 'a', 'q1')])
        ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}', now=NOW)
        before = self.listing()
        result = ui_approval.apply(self.state, self.config_path, deploy=False, deployer=self.deployer,
                                   verifier=self.verifier, load_draft=lambda s, d: self.drafts.get(d),
                                   revalidate=lambda *a: None, build_payload=build_payload,
                                   record_manifest=lambda *a: self.fail('recorded'), now=NOW)
        self.assertEqual(result['status'], 'validated-no-deploy', result)
        after = self.listing()
        self.assertEqual(set(after) - set(before), {'state/approval/result.json'})
        self.assertEqual({k: v for k, v in after.items() if k != 'state/approval/result.json'}, before)
        self.assertEqual(self.deploys, [])
        self.assertIsNotNone(self.ledger.db.execute('SELECT 1 FROM jobs WHERE id=?', (undispatched,)).fetchone())
        self.assertEqual(result['cancelled'], 1)
        self.assertEqual(result['scope'], ['x'])
        self.assertRegex(result['manifestSha256'], '^[0-9a-f]{64}$')

    def test_credentials_never_leak_from_failing_deployment_or_cli(self):
        def leaking(ledger, config, site):
            token = (Path(os.environ['CREDENTIALS_DIRECTORY'])/'CLOUDFLARE_API_TOKEN').read_text()
            raise RuntimeError(f'wrangler failed with token {token}')
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = self.apply(sha, deployer=leaking)
        self.assertEqual(result['category'], 'deployment')
        result = self.apply(sha, deployer=lambda *a: (_ for _ in ()).throw(PublishError('budget')))
        self.assertEqual(result['category'], 'deployment_budget')
        # CLI path with module defaults: real draft table, patched deploy/verify/generator hooks.
        index = self.state/'library'/'index.sqlite3'
        with contextlib.closing(sqlite3.connect(index)) as db, db:
            db.execute('CREATE TABLE drafts(sha256 TEXT PRIMARY KEY, created_at TEXT, base_manifest_sha256 TEXT, body TEXT, status TEXT)')
            db.execute('INSERT INTO drafts VALUES(?,?,?,?,?)', (sha, 'now', None, canonical(self.drafts[sha]).decode(), 'draft'))
        ui_approval.request_approval(self.state, index, sha, f'APPROVE {sha[:8]}')
        with mock.patch('prepare.deploy_site', leaking), mock.patch.object(ui_approval, 'default_revalidate', lambda *a: None), \
                mock.patch.object(ui_approval, 'default_payload_builder', lambda state, now: build_payload), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = ui_approval.main(['apply', '--state', str(self.state), '--config', str(self.config_path)])
        self.assertEqual(code, 2)
        self.assertIn('deployment', out.getvalue())
        self.assert_no_secret(out.getvalue())

    def test_symlinked_request_is_refused(self):
        folder = self.state/'approval'
        folder.mkdir()
        target = Path(self.temp.name)/'elsewhere.json'
        target.write_text(json.dumps({'draftSha256': 'a'*64}))
        os.symlink(target, folder/'request.json')
        result = ui_approval.apply(self.state, self.config_path, deployer=self.deployer, verifier=self.verifier, now=NOW)
        self.assertEqual(result['category'], 'invalid_request')
        self.assertTrue(target.exists())
        self.assertIsNone(ui_approval.apply(self.state, self.config_path, deployer=self.deployer, verifier=self.verifier))


class GeneratorIntegrationTests(Env):
    """Real ui_schedule drafts and payloads through the default builder/revalidator."""
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(ROOT/'contract/tests'))
        import test_ui_schedule as fixtures
        import ui_schedule
        self.us, self.fixtures = ui_schedule, fixtures
        self.config['channels']['instagram']['route'] = 'instagram'
        self.write_config()
        self.records = []
        for n, name in enumerate('ab', 1):
            record = fixtures.record(n)
            record['videoSha256'], record['bytes'] = self.videos[name]
            self.records.append(record)
        patcher = mock.patch.object(ui_approval, '_schedulable', lambda state, draft, now: self.records)
        patcher.start()
        self.addCleanup(patcher.stop)

    def generate(self, edits=None, base=None):
        inputs = self.fixtures.inputs(platforms=('instagram', 'x'), first=True, edits=edits)
        history = self.us.ledger_history(self.state/'ledger.sqlite3', self.config, NOW)
        draft = self.us.generate(inputs, self.records, history, self.config, base)
        sha = self.us.draft_sha256(draft)
        self.drafts[sha] = draft
        return sha, draft

    def run_apply(self, sha):
        ui_approval.request_approval(self.state, sha, f'APPROVE {sha[:8]}', now=NOW)
        return ui_approval.apply(self.state, self.config_path, deployer=self.deployer, verifier=self.verifier,
                                 load_draft=lambda state, s: self.drafts.get(s),
                                 record_manifest=lambda *a: self.recorded.append(a), now=NOW)

    def test_generated_draft_approves_and_edit_cancels_undispatched_row(self):
        sha, draft = self.generate()
        self.assertGreaterEqual(len(draft['jobs']), 3)
        result = self.run_apply(sha)
        self.assertEqual(result['status'], 'manifest-ready', result)
        self.assertEqual(result['scope'], ['instagram', 'x'])
        base_sha, manifest = ui_approval.current_manifest(self.state)
        comment = next(j for j in manifest['jobs'] if j['payload']['kind'] == 'comment')
        self.assertIsNone(comment['payload']['media'])
        self.enqueue_manifest()
        self.assertEqual(self.run_apply(sha)['category'], 'stale_draft')
        key = next(j['key'] for j in manifest['jobs'] if j['platform'] == 'x')
        sha2, draft2 = self.generate(edits={key: {'text': 'Edited caption'}}, base=manifest)
        self.assertEqual(draft2['baseManifestSha256'], base_sha)
        result = self.run_apply(sha2)
        self.assertEqual(result['status'], 'manifest-ready', result)
        self.assertEqual(result['cancelled'], 1)
        _, manifest2 = ui_approval.current_manifest(self.state)
        unchanged = [j for j in manifest2['jobs'] if j['key'] != key]
        self.assertEqual(unchanged, [j for j in manifest['jobs'] if j['key'] != key])
        self.assertEqual(next(j for j in manifest2['jobs'] if j['key'] == key)['payload']['caption'], 'Edited caption')


class BindTests(Env):
    def ready(self):
        result = self.apply(self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')]))
        self.assertEqual(result['status'], 'manifest-ready')
        return result['manifestSha256']

    def test_binds_only_two_fields_and_preserves_mode(self):
        sha = self.ready()
        before = json.loads(self.config_path.read_text())
        message = approval_bind.bind(self.state, self.config_path, now=NOW)
        self.assertIn('Bound', message)
        after = json.loads(self.config_path.read_text())
        self.assertEqual(after.pop('approval'), {'manifestSha256': sha, 'approvedAt': '2026-10-10T12:00:00Z'})
        before.pop('approval')
        self.assertEqual(after, before)
        self.assertEqual(list(json.loads(self.config_path.read_text())), list(self.config))
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o640)
        result = json.loads((self.state/'approval'/'result.json').read_text())
        self.assertEqual(result['status'], 'bound')
        self.assertEqual((self.state/'approval'/'result.json').stat().st_mode & 0o777, 0o600)
        self.assertIn('Nothing to bind', approval_bind.bind(self.state, self.config_path))

    def test_existing_approval_keys_are_kept(self):
        self.config['approval'] = {'scopeHash': 'keep', 'deploymentApproved': True, 'manifestSha256': 'old'}
        self.write_config()
        sha = self.ready()
        approval_bind.bind(self.state, self.config_path, now=NOW)
        self.assertEqual(json.loads(self.config_path.read_text())['approval'],
                         {'scopeHash': 'keep', 'deploymentApproved': True, 'manifestSha256': sha,
                          'approvedAt': '2026-10-10T12:00:00Z'})

    def assert_refused(self):
        before = self.config_path.read_bytes()
        with self.assertRaises(approval_bind.Refused):
            approval_bind.bind(self.state, self.config_path)
        self.assertEqual(self.config_path.read_bytes(), before)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
            self.assertEqual(approval_bind.main(['--state', str(self.state), '--config', str(self.config_path),
                                                 '--allow-non-root-for-tests']), 1)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertNotIn(SENTINEL, err.getvalue())

    def test_refuses_symlinked_approved_manifest(self):
        sha = self.ready()
        approved = self.state/'manifests'/'approved.json'
        approved.unlink()
        os.symlink(self.state/'manifests'/f'{sha}.json', approved)
        self.assert_refused()

    def test_refuses_symlinked_approval_directory(self):
        self.ready()
        moved = Path(self.temp.name)/'moved'
        os.rename(self.state/'approval', moved)
        os.symlink(moved, self.state/'approval')
        self.assert_refused()

    def test_refuses_mismatched_hash(self):
        self.ready()
        approved = self.state/'manifests'/'approved.json'
        approved.write_bytes(approved.read_bytes()+b' ')
        self.assert_refused()

    def test_refuses_oversize_result(self):
        self.ready()
        result_path = self.state/'approval'/'result.json'
        result = json.loads(result_path.read_text())
        result['padding'] = 'x'*70000
        result_path.write_text(json.dumps(result))
        self.assert_refused()

    def test_nothing_to_bind_for_failed_or_no_deploy(self):
        sha = self.draft([self.job('x', '2026-10-12T13:00:00+00:00', 'a', 'q1')])
        before = self.config_path.read_bytes()
        self.apply(sha, deploy=False)
        self.assertIn('validated-no-deploy', approval_bind.bind(self.state, self.config_path))
        (self.state/'approval'/'request.json').unlink()
        self.verify_override = lambda *a: {'sha256': '0'*64}
        self.apply(sha)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = approval_bind.main(['--state', str(self.state), '--config', str(self.config_path), '--allow-non-root-for-tests'])
        self.assertEqual(code, 0)
        self.assertIn('Nothing to bind', out.getvalue())
        self.assertEqual(self.config_path.read_bytes(), before)

    @unittest.skipIf(os.geteuid() == 0, 'root')
    def test_requires_root_without_test_flag(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(approval_bind.main(['--state', str(self.state), '--config', str(self.config_path)]), 1)


if __name__ == '__main__':
    unittest.main()
