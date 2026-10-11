"""End to end through the HTTP server: batch upload → content approval → generated draft →
typed schedule approval → applier (fake deploy/verify) → root bind → cancel via re-approval.
Never publishes; no network."""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import approval_bind
import ui_approval
from contract_fixtures import document, episode, write_batch
from runner import Ledger, run_jobs
from test_ui_server import SENTINEL, ServerTestCase
from test_ui_views import assert_shape

BASE = 'https://scalar-social-media.pages.dev'


class Adapter:
    def __init__(self):
        self.sent = []

    def publish(self, job, payload):
        self.sent.append((job['episode'], payload.get('parent')))
        return {'remoteId': '9' + str(len(self.sent))}

    def reconcile(self, job, payload):
        return {'status': 'confirmed', 'remoteId': job['remote_id'], 'permalink': 'https://www.instagram.com/reel/X/',
                'publishedAt': '2026-10-08T13:01:00+00:00'}


class IntegrationTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        ig = self.config['channels']['instagram']
        ig.update(route='instagram', accountId='111', identityVerified=True, publishingVerified=True,
                  ownerId='222', ownerIdVerified=True)
        self.config['media'].update(baseUrl=BASE, pagesProject='scalar-social-media', cloudflareAccountId='acct')
        self.config_path.write_text(json.dumps(self.config))
        self.config_path.chmod(0o640)
        self.deployed, self.verified = [], []

    def deployer(self, ledger, config, site):
        self.deployed.append(sorted(p.name for p in (site/'library').iterdir()))

    def verifier(self, url, sha):
        self.verified.append(url)
        if 'credential' in url:
            raise AssertionError(SENTINEL)
        return {'sha256': sha, 'bytes': 1, 'publicDeliveryVerified': True}

    def upload_and_approve(self):
        episodes = [episode(1), episode(2, 'continuum'), episode(3, 'whenabouts')]
        folder, data, blobs = write_batch(Path(self.tmp.name)/'mac', document(episodes))
        status, body = self.json('POST', '/api/library/batches', (folder/'batch.json').read_bytes())
        self.assertEqual(status, 200, body)
        for name, blob in blobs.items():
            kind = 'video/mp4' if name.endswith('.mp4') else 'image/jpeg'
            body = self.json('PUT', f'/api/library/batches/2026-10-fixture/files/{name}', blob, content_type=kind)[1]
            assert_shape(self, body, 'FileUploadResult')
            self.assertIn(body['outcome'], ('stored', 'already-present'), body)
        items = [{'episodeId': e['episodeId'], 'revision': 1} for e in data['episodes']]
        body = self.json('POST', '/api/library/approve', {'items': items, 'reviewer': 'owner'})[1]
        assert_shape(self, body, 'LibraryActionResponse')
        self.assertTrue(all(r['ok'] and r['status'] == 'approved' for r in body['results']), body)

    def inputs(self):
        off = {'include': False}
        return {'timezone': 'America/New_York', 'startDate': '2026-10-08', 'endDate': '2026-10-10',
                'platforms': {'instagram': {'include': True, 'weekdays': [0, 1, 2, 3, 4, 5, 6], 'times': ['09:00'], 'maxPerDay': 1},
                              **{p: off for p in ('facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok')}},
                'minGapHours': {'instagram': 20}, 'staggerMinutes': 0, 'ordering': 'game-round-robin',
                'companions': {'firstComment': True, 'answerReply': False}, 'edits': {}}

    def approve_and_apply(self, sha):
        status, body = self.json('POST', f'/api/schedule/drafts/{sha}/approve', {'confirmation': 'APPROVE wrong'})
        self.assertEqual(status, 422)
        assert_shape(self, body, 'ApiError')
        self.assertEqual(body['problems'][0]['path'], 'confirmation')
        status, body = self.json('POST', f'/api/schedule/drafts/{sha}/approve', {'confirmation': f'APPROVE {sha[:8]}'})
        self.assertEqual(status, 202, body)
        self.assertEqual(body, {'status': 'requested', 'draftSha256': sha, 'requestedAt': '2026-10-07T12:00:00Z'})
        status, body = self.json('POST', f'/api/schedule/drafts/{sha}/approve', {'confirmation': f'APPROVE {sha[:8]}'})
        self.assertEqual(status, 409)
        draft = self.json('GET', f'/api/schedule/drafts/{sha}')[1]
        self.assertEqual(draft['status'], 'requested')
        self.assertIn('This draft is already waiting for approval.', draft['blockingProblems'])
        with contextlib.redirect_stdout(io.StringIO()):
            result = ui_approval.apply(self.state, self.config_path, deployer=self.deployer, verifier=self.verifier,
                                       now=self.now())
        self.assertEqual(result['status'], 'manifest-ready', result)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(approval_bind.main(['--state', str(self.state), '--config', str(self.config_path),
                                                 '--allow-non-root-for-tests']), 0)
        return result

    def now(self):
        import datetime as dt
        return dt.datetime.fromtimestamp(self.clock[0], dt.timezone.utc)

    def test_full_flow_never_publishes_and_binds_only_approval(self):
        self.upload_and_approve()
        before = json.loads(self.config_path.read_text())
        status, body = self.json('POST', '/api/schedule/drafts', self.inputs())
        self.assertEqual(status, 200, body)
        assert_shape(self, body, 'DraftResponse')
        assert_shape(self, body['draft'], 'Draft')
        draft, sha = body['draft'], body['sha256']
        for job in draft['jobs']:
            assert_shape(self, job, 'DraftJob')
        self.assertEqual(body['confirmationPhrase'], f'APPROVE {sha[:8]}')
        self.assertEqual((body['status'], body['blockingProblems']), ('draft', []))
        self.assertEqual(set(body['coverUrls']), {j['coverSha256'] for j in draft['jobs'] if j['coverSha256']})
        self.assertTrue(all('/api/media/covers/' in u for u in body['coverUrls'].values()))
        posts = [j for j in draft['jobs'] if j['kind'] == 'post']
        self.assertEqual(len(posts), 3)
        self.assertEqual([j['game'] for j in posts], ['scalar', 'continuum', 'whenabouts'])
        self.assertEqual(posts[0]['slotLocal'], '2026-10-08T09:00:00-04:00')
        self.assertEqual(posts[0]['zone'], 'EDT')
        self.assertEqual(len([j for j in draft['jobs'] if j['kind'] == 'comment']), 3)
        self.assertNotIn('Bolivia', ' '.join(j['text'] for j in draft['jobs'] if j['kind'] == 'post').replace('A) Bolivia', ''))
        # Same inputs and state → same draft hash.
        self.assertEqual(self.json('POST', '/api/schedule/drafts', self.inputs())[1]['sha256'], sha)

        result = self.approve_and_apply(sha)
        self.assertEqual(result['scope'], ['instagram'])
        self.assertEqual(len(self.deployed), 1)
        self.assertEqual(len(self.verified), 3)
        self.assertTrue(all(u.startswith(BASE + '/library/') for u in self.verified))
        after = json.loads(self.config_path.read_text())
        approval = after.pop('approval')
        before.pop('approval')
        self.assertEqual(after, before)  # paused, channels, everything else untouched
        manifest_bytes = (self.state/'manifests/approved.json').read_bytes()
        import hashlib
        self.assertEqual(approval['manifestSha256'], hashlib.sha256(manifest_bytes).hexdigest())
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest['scopeHash'], ui_approval.intended_config(before, ['instagram'])[1])
        self.assertTrue(after['paused'])
        self.assertFalse(any(c['enabled'] for c in after['channels'].values()))

        schedule = self.json('GET', '/api/schedule')[1]
        assert_shape(self, schedule, 'ScheduleResponse')
        for job in schedule['jobs']:
            assert_shape(self, job, 'QueueJob')
        for channel in schedule['channels']:
            assert_shape(self, channel, 'ChannelSummary')
        self.assertEqual(len(schedule['jobs']), 6)
        self.assertTrue(all(j['status'] == 'not-enqueued' and j['editable'] for j in schedule['jobs']))
        self.assertEqual(schedule['manifest']['bound'], True)
        self.assertEqual(schedule['lastResult']['status'], 'bound')
        self.assertIsNone(schedule['pendingRequest'])
        self.assertEqual(schedule['recentDrafts'][0], {'sha256': sha, 'status': 'approved', 'createdAt': '2026-10-07T12:00:00Z', 'jobs': 6})
        comments = [j for j in schedule['jobs'] if j['kind'] == 'comment']
        self.assertEqual({j['parentKey'] for j in comments}, {j['key'] for j in schedule['jobs'] if j['kind'] == 'post'})
        status, body = self.json('GET', '/api/library')
        self.assertTrue(all(e['inManifest'] and not e['deletable'] for e in body['episodes']))
        status, body = self.json('DELETE', '/api/library/episodes/scalar-clues-001/1')
        self.assertEqual(status, 409)
        assert_shape(self, body, 'ApiError')
        dash = self.json('GET', '/api/dashboard')[1]
        self.assertEqual((dash['approval']['bound'], dash['approval']['scope']), (True, ['instagram']))

        # Runner consumes the manifest: companion waits for its parent's confirmation.
        ledger = Ledger(self.state/'ledger.sqlite3')
        live = {**after, 'paused': False}
        live['channels']['instagram']['enabled'] = True
        live['schedule']['maxLatenessMinutes'] = 10_000
        for job in manifest['jobs']:
            ledger.enqueue(job['platform'], '111', job['slot'], job['payload'])
        import datetime as dt
        adapter = Adapter()
        run_jobs(ledger, live, adapter, dt.datetime(2026, 10, 8, 13, 5, tzinfo=dt.timezone.utc))
        self.assertEqual([e for e, _ in adapter.sent], ['scalar:Q1:clues'])
        run_jobs(ledger, live, adapter, dt.datetime(2026, 10, 8, 13, 10, tzinfo=dt.timezone.utc))
        run_jobs(ledger, live, adapter, dt.datetime(2026, 10, 8, 13, 15, tzinfo=dt.timezone.utc))
        self.assertEqual(adapter.sent[1], ('scalar:Q1:clues#comment', {'remoteId': '91', 'permalink': 'https://www.instagram.com/reel/X/'}))
        ledger.db.close()

        # Cancel the not-yet-dispatched continuum post: new draft → re-approval; the dispatched ones stay.
        schedule = self.json('GET', '/api/schedule')[1]
        sent = [j for j in schedule['jobs'] if j['dispatched']]
        self.assertEqual({j['episodeKey'] for j in sent}, {'scalar:Q1:clues', 'scalar:Q1:clues#comment'})
        self.assertTrue(all(not j['editable'] and j['lockReason'] for j in sent))
        self.assertEqual(next(j for j in sent if j['kind'] == 'post')['permalink'], 'https://www.instagram.com/reel/X/')
        keys = [j['key'] for j in schedule['jobs'] if j['episodeKey'] == 'continuum:Q2:clues']
        status, body = self.json('POST', '/api/schedule/cancel', {'keys': keys})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body['draft']['jobs']), 4)
        self.assertEqual(body['blockingProblems'], [])
        self.approve_and_apply(body['sha256'])
        with sqlite3.connect(self.state/'ledger.sqlite3') as db:
            kinds = [r[0] for r in db.execute("SELECT kind FROM events WHERE kind='cancelled'")]
            remaining = {r[0] for r in db.execute('SELECT episode FROM jobs')}
        self.assertEqual(len(kinds), 2)
        self.assertNotIn('continuum:Q2:clues', remaining)
        # Dispatched posts can't be cancelled or edited; unknown keys are refused.
        sent = [j['key'] for j in self.json('GET', '/api/schedule')[1]['jobs'] if j['episodeKey'] == 'scalar:Q1:clues']
        self.assertEqual(self.json('POST', '/api/schedule/cancel', {'keys': sent})[0], 409)
        self.assertEqual(self.json('POST', '/api/schedule/edit', {'key': sent[0], 'text': 'new'})[0], 409)
        self.assertEqual(self.json('POST', '/api/schedule/cancel', {'keys': ['nope']})[0], 422)

        # History: cancelled rows come back from their event; filters and CSV use the same rows.
        history = self.json('GET', '/api/history')[1]
        assert_shape(self, history, 'HistoryResponse')
        for row in history['rows']:
            assert_shape(self, row, 'HistoryRow')
        cancelled = self.json('GET', '/api/history?status=cancelled')[1]['rows']
        self.assertEqual({r['questionId'] for r in cancelled}, {'continuum:Q2:clues'})
        self.assertEqual(len(self.json('GET', '/api/history?question=scalar:Q1:clues')[1]['rows']), 2)
        self.assertEqual(self.json('GET', '/api/history?game=whenabouts&status=ready')[1]['total'], 2)
        self.assertEqual(self.json('GET', '/api/history?platform=myspace')[0], 422)
        status, headers, data = self.request('GET', '/api/history?format=csv&status=confirmed')
        self.assertEqual(headers['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(len(data.decode().splitlines()), 3)
        job = self.json('GET', f"/api/jobs/{cancelled[0]['jobId']}")[1]
        assert_shape(self, job, 'JobDetailResponse')
        self.assertEqual((job['job']['status'], job['events'][-1]['kind']), ('cancelled', 'cancelled'))
        confirmed = next(r for r in history['rows'] if r['status'] == 'confirmed' and r['kind'] == 'post')
        job = self.json('GET', f"/api/jobs/{confirmed['jobId']}")[1]
        self.assertEqual(job['manifestSha256'], self.json('GET', '/api/schedule')[1]['manifest']['sha256'])
        self.assertTrue(job['payload']['mediaUrl'].startswith(BASE + '/library/'))
        self.assertIsNone(job['reconciliation'])

        # Activity: one timeline of the whole flow, every entry in the types.ts shape.
        activity = self.json('GET', '/api/activity?limit=500')[1]
        assert_shape(self, activity, 'ActivityResponse')
        for item in activity['entries']:
            assert_shape(self, item, 'ActivityEntry')
        events = {e['event'] for e in activity['entries']}
        for name in ('library.batch-imported', 'library.video-stored', 'library.approved', 'approval.draft',
                     'approval.requested', 'approval.manifest-ready', 'approval.bound', 'job.confirmed', 'job.cancelled'):
            self.assertIn(name, events)
        cancelled = [e for e in activity['entries'] if e['event'] == 'job.cancelled']
        self.assertTrue(all(e['detail'].startswith('Removed by a re-approved schedule') for e in cancelled))
        self.assertTrue(all(e['jobId'] for e in cancelled))

    def test_dashboard_activation_history_backup_no_secrets(self):
        self.upload_and_approve()
        for path in ('/api/dashboard', '/api/activation', '/api/history', '/api/history?format=csv', '/api/schedule',
                     '/api/library', '/api/backup'):
            status, headers, data = self.request('GET', path)
            self.assertEqual(status, 200, (path, data[:300]))
            self.assertNotIn(SENTINEL.encode(), data)
            self.assertNotIn(b'correct-horse-battery', data)
        activation = self.json('GET', '/api/activation')[1]
        assert_shape(self, activation, 'ActivationResponse')
        self.assertFalse(activation['ready'])
        self.assertIn('activate.py --apply --confirm-zero-spend', activation['command'])
        dash = self.json('GET', '/api/dashboard')[1]
        assert_shape(self, dash, 'DashboardResponse')
        self.assertEqual(set(dash['statuses']), {'postingTestPassed', 'currentlyAuthenticated', 'recurringEnabled'})
        self.assertEqual(dash['displayTimezone'], 'America/New_York')
        self.assertEqual(dash['statuses']['recurringEnabled']['state'], 'no')
        library = self.json('GET', '/api/library')[1]
        assert_shape(self, library, 'LibraryResponse')
        for batch in library['batches']:
            assert_shape(self, batch, 'LibraryBatch')
        for episode in library['episodes']:
            assert_shape(self, episode, 'LibraryEpisode')
        self.assertEqual([e['episodeId'] for e in library['episodes']],
                         ['continuum-clues-002', 'scalar-clues-001', 'whenabouts-clues-003'])

    def test_staging_approval_then_new_request_and_lead_time(self):
        self.upload_and_approve()
        sha = self.json('POST', '/api/schedule/drafts', self.inputs())[1]['sha256']
        self.assertEqual(self.json('POST', f'/api/schedule/drafts/{sha}/approve', {'confirmation': f'APPROVE {sha[:8]}'})[0], 202)
        self.assertEqual(self.json('GET', '/api/schedule')[1]['pendingRequest']['draftSha256'], sha)
        with contextlib.redirect_stdout(io.StringIO()):
            result = ui_approval.apply(self.state, self.config_path, deploy=False, now=self.now())
        self.assertEqual(result['status'], 'validated-no-deploy')
        self.assertTrue((self.state/'approval/request.json').exists())  # staging leaves it in place
        schedule = self.json('GET', '/api/schedule')[1]
        self.assertIsNone(schedule['pendingRequest'])
        self.assertEqual(schedule['lastResult'], {'status': 'validated-no-deploy', 'draftSha256': sha, 'at': '2026-10-07T12:00:00Z'})
        self.assertIsNone(schedule['manifest'])
        self.assertFalse((self.state/'manifests/approved.json').exists())
        # The processed staging request is archived when the owner requests again.
        self.clock[0] += 60
        self.assertEqual(self.json('POST', f'/api/schedule/drafts/{sha}/approve', {'confirmation': f'APPROVE {sha[:8]}'})[0], 202)
        self.assertEqual(len(list((self.state/'approval/history').glob('*-request.json'))), 1)
        (self.state/'approval/request.json').unlink()
        # Every read re-checks the 30-minute lead time (2026-10-08 09:00 EDT = 13:00Z).
        self.clock[0] = dt.datetime(2026, 10, 8, 12, 45, tzinfo=dt.timezone.utc).timestamp()
        body = self.json('GET', f'/api/schedule/drafts/{sha}')[1]
        self.assertTrue(any('30 minutes' in b for b in body['blockingProblems']), body['blockingProblems'])
        status, body = self.json('POST', f'/api/schedule/drafts/{sha}/approve', {'confirmation': f'APPROVE {sha[:8]}'})
        self.assertEqual(status, 409)
        self.assertEqual(body['problems'][0]['code'], 'blocking')


if __name__ == '__main__':
    unittest.main()
