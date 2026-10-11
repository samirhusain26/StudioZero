"""ui_views: pure shape functions -> publisher/ui/src/api/types.ts. Also provides `fields`/`assert_shape`,
a small reader of the top-level fields of each `export interface` in types.ts, so shape tests compare
against the frontend contract itself rather than a copy of it."""
import datetime as dt
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
import ui_health
import ui_views as v

TYPES = ROOT/'publisher/ui/src/api/types.ts'
NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)
SHA = 'ab' * 32
OTHER = 'cd' * 32
_CACHE = {}


def fields(name):
    """(required, all) top-level field names of `export interface <name>` in types.ts."""
    if name in _CACHE:
        return _CACHE[name]
    text = TYPES.read_text()
    start = re.search(rf'^export interface {name}\b[^{{\n]*{{', text, re.M).end()
    end, depth = start, 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[end], 0)
        end += 1
    body = re.sub(r'/\*.*?\*/', '', text[start:end-1], flags=re.S)
    body = re.sub(r'(^|\s)//[^\n]*', r'\1', body)
    # Members are separated by newlines or `;` outside nested braces (one-line interfaces included).
    members, current, depth = [], '', 0
    for char in body:
        depth += {'{': 1, '}': -1}.get(char, 0)
        if depth == 0 and char in ';\n':
            members.append(current)
            current = ''
        else:
            current += char
    required, every = set(), set()
    for member in members + [current]:
        match = re.match(r'(\w+)(\?)?:', member.strip())
        if match:
            every.add(match.group(1))
            if not match.group(2):
                required.add(match.group(1))
    _CACHE[name] = (required, every)
    return _CACHE[name]


def assert_shape(test, value, name):
    required, every = fields(name)
    test.assertIsInstance(value, dict, name)
    test.assertTrue(required <= set(value), f'{name} missing {sorted(required - set(value))}')
    test.assertTrue(set(value) <= every, f'{name} has extra {sorted(set(value) - every)}')


class ParserTests(unittest.TestCase):
    def test_reads_interfaces(self):
        self.assertEqual(fields('ApiError'), ({'error', 'nextAction'}, {'code', 'error', 'nextAction', 'problems'}))
        required, every = fields('DashboardResponse')
        self.assertIn('statuses', required)
        self.assertNotIn('platforms', every)  # nested, not top level


class HelperTests(unittest.TestCase):
    def test_iso_utc(self):
        self.assertEqual(v.iso_utc('2026-10-05T16:01:00.123+00:00'), '2026-10-05T16:01:00Z')
        self.assertEqual(v.iso_utc('2026-10-05T12:00:00-04:00'), '2026-10-05T16:00:00Z')
        self.assertEqual(v.iso_utc(NOW), '2026-10-07T12:00:00Z')
        self.assertIsNone(v.iso_utc('2026-10-05T16:00:00'))  # naive
        self.assertIsNone(v.iso_utc('nope'))
        self.assertIsNone(v.iso_utc(None))

    def test_systemd_time(self):
        self.assertEqual(v.systemd_time('Tue 2026-10-06 22:00:01 UTC'), '2026-10-06T22:00:01Z')
        self.assertEqual(v.systemd_time('Tue 2026-10-06 18:00:01 EDT', 'America/New_York'), '2026-10-06T22:00:01Z')
        self.assertIsNone(v.systemd_time('Tue 2026-10-06 18:00:01 EDT'))  # abbreviation alone is ambiguous
        self.assertIsNone(v.systemd_time('n/a'))
        self.assertIsNone(v.systemd_time(None))

    def test_problem_from_text(self):
        self.assertEqual(v.problem('publication.captions.x: Names the answer'),
                         {'code': 'invalid', 'path': 'publication.captions.x', 'message': 'Names the answer'})
        self.assertEqual(v.problem('Video must be H.264', 'media', 'video'),
                         {'code': 'media', 'path': 'video', 'message': 'Video must be H.264'})
        self.assertEqual(v.problem({'code': 'spoiler', 'path': 'episodes[0].x', 'message': 'm'}),
                         {'code': 'spoiler', 'path': 'episodes[0].x', 'message': 'm'})

    def test_health(self):
        self.assertEqual(v.health('ui-x', 0, 0), {'ok': True, 'version': 'ui-x',
                                                  'backoff': {'locked': False, 'retryAfterSeconds': None, 'failures': 0}})
        self.assertEqual(v.health('ui-x', 7, 4)['backoff'], {'locked': True, 'retryAfterSeconds': 4, 'failures': 7})
        assert_shape(self, v.health('ui-x', 0, 0), 'HealthResponse')


class ApprovalTests(unittest.TestCase):
    def test_result_lifecycle(self):
        ready = v.approval_result({'status': 'manifest-ready', 'manifestSha256': OTHER, 'draftSha256': SHA, 'scope': ['instagram'],
                                   'jobs': 3, 'cancelled': 0, 'at': '2026-10-07T12:00:00Z',
                                   'deployment': {'deployed': True, 'mediaFiles': 2}, 'verifiedUrls': ['a', 'b']}, NOW)
        self.assertEqual(ready['deployment'], {'id': None, 'url': None, 'verified': 2, 'files': 2})
        self.assertEqual(set(ready), {'status', 'draftSha256', 'manifestSha256', 'jobs', 'deployment', 'at'})
        bound = v.approval_result({'status': 'bound', 'manifestSha256': OTHER, 'draftSha256': SHA, 'jobs': 3,
                                   'at': '2026-10-07T12:00:00Z', 'boundAt': '2026-10-07T12:00:05Z', 'verifiedUrls': []}, NOW)
        self.assertEqual(bound, {'status': 'bound', 'draftSha256': SHA, 'manifestSha256': OTHER, 'jobs': 3,
                                 'at': '2026-10-07T12:00:05Z'})
        staged = v.approval_result({'status': 'validated-no-deploy', 'draftSha256': SHA, 'manifestSha256': OTHER,
                                    'scope': ['instagram'], 'jobs': 3, 'at': '2026-10-07T12:00:00Z'}, NOW)
        self.assertEqual(staged, {'status': 'validated-no-deploy', 'draftSha256': SHA, 'at': '2026-10-07T12:00:00Z'})
        failed = v.approval_result({'status': 'failed', 'category': 'stale_draft', 'message': 'Generate a new draft.',
                                    'draftSha256': None, 'at': '2026-10-07T12:00:00Z'}, NOW)
        self.assertEqual(set(failed), {'status', 'draftSha256', 'category', 'message', 'at'})
        self.assertEqual(v.approval_result({'status': 'unreadable'}, NOW)['category'], 'unreadable')

    def test_processed_request_is_not_pending(self):
        pending = {'draftSha256': SHA, 'requestedAt': '2026-10-07T11:59:00Z'}
        self.assertEqual(v.pending_request(pending, None), pending)
        staged = {'status': 'validated-no-deploy', 'draftSha256': SHA, 'at': '2026-10-07T12:00:00Z'}
        self.assertIsNone(v.pending_request(pending, staged))
        older = {**staged, 'at': '2026-10-07T11:00:00Z'}
        self.assertEqual(v.pending_request(pending, older), pending)
        self.assertEqual(v.pending_request(pending, {**staged, 'draftSha256': OTHER}), pending)

    def test_state(self):
        config = {'approval': {'manifestSha256': OTHER, 'approvedAt': '2026-10-07T12:00:05Z'}}
        manifest = {'scope': ['instagram'], 'approvedAt': '2026-10-07T12:00:00Z', 'jobs': []}
        state = v.approval({'pending': None, 'result': None, 'manifestSha256': OTHER}, config, manifest, NOW)
        assert_shape(self, state, 'ApprovalState')
        self.assertEqual((state['bound'], state['scope'], state['approvedAt']), (True, ['instagram'], '2026-10-07T12:00:00Z'))
        unbound = v.approval({'pending': None, 'result': None, 'manifestSha256': OTHER}, {'approval': None}, manifest, NOW)
        self.assertFalse(unbound['bound'])
        empty = v.approval({'pending': None, 'result': None, 'manifestSha256': None}, {}, None, NOW)
        self.assertEqual((empty['manifestSha256'], empty['scope'], empty['bound']), (None, [], False))


def raw_dashboard(**changes):
    channels = {p: {'enabled': False, 'route': 'disabled', 'identityVerified': False, 'publishingVerified': False}
                for p in v.PLATFORMS}
    channels['instagram'].update(route='instagram', accountId='111', identityVerified=True, publishingVerified=True)
    config = {'timezone': 'America/New_York', 'paused': True, 'channels': channels}
    units = [{'unit': u, 'available': True, 'enabled': 'disabled', 'active': 'inactive', 'result': 'success',
              'exitStatus': '0', 'lastExit': None, 'nextRun': None} for u in ui_health.UNITS]
    raw = {
        'checkedAt': '2026-10-07T12:00:00Z', 'timezone': 'America/New_York', 'platforms': list(v.PLATFORMS),
        'postingTestPassed': {p: {'passed': p == 'instagram', 'permalink': 'https://www.instagram.com/reel/A/' if p == 'instagram' else None,
                                  'publishedAt': '2026-10-05T16:01:00+00:00' if p == 'instagram' else None} for p in v.PLATFORMS},
        'currentlyAuthenticated': {p: {'state': 'not-connected', 'detail': 'Not connected', 'expiresAt': None,
                                       'checkedAt': None, 'renewalFailed': False} for p in v.PLATFORMS},
        'recurringPublishing': {'enabled': False, 'configPaused': True, 'pausedSentinel': True, 'timerEnabled': False,
                                'timerActive': False, 'channels': {}},
        'units': units, 'publisherHealth': {'checkedAt': '2026-10-07T11:50:00+00:00', 'ageSeconds': 600, 'ok': None},
        'monitor': units[3],
        'budgets': {'pagesDeployments': {'used': 7, 'limit': 120, 'window': '31 days'},
                    'bufferCalls': [{'window': '15 minutes', 'used': 0, 'limit': 80}, {'window': '24 hours', 'used': 190, 'limit': 200}]},
        'storage': {'freeBytes': 30_000_000_000, 'totalBytes': 60_000_000_000, 'libraryBytes': 0},
        'jobs': {}, 'issues': [{'code': 'publication_needs_review', 'title': 'Some posts need review', 'nextAction': 'Open the jobs.'}],
        'uncertainJobs': [{'id': 'f' * 24, 'platform': 'threads', 'account': 't-1', 'episode': 'ep04', 'status': 'uncertain',
                           'slot': {'utc': '2026-10-06T16:00:00Z'}, 'dispatchedAt': '2026-10-06T16:00:00+00:00',
                           'lastCheck': '2026-10-06T16:05:00+00:00', 'nextCheck': '2026-10-07T13:00:00Z',
                           'error': ui_health.explain('uncertain_response'), 'ownerActions': ui_health.OWNER_ACTIONS}],
        'approval': None,
    }
    raw.update(changes)
    return raw, config


class DashboardTests(unittest.TestCase):
    def view(self, raw=None, config=None):
        if raw is None:
            raw, config = raw_dashboard()
        state = v.approval({'pending': None, 'result': None, 'manifestSha256': None}, config, None, NOW)
        return v.dashboard(raw, config, state, NOW)

    def test_shape_and_three_separate_statuses(self):
        view = self.view()
        assert_shape(self, view, 'DashboardResponse')
        statuses = view['statuses']
        self.assertEqual(set(statuses), {'postingTestPassed', 'currentlyAuthenticated', 'recurringEnabled'})
        for name, kind in (('postingTestPassed', 'PostingTestStatus'), ('currentlyAuthenticated', 'AuthStatus'),
                           ('recurringEnabled', 'RecurringPlatformStatus')):
            self.assertEqual(list(statuses[name]['platforms']), list(v.PLATFORMS))
            for value in statuses[name]['platforms'].values():
                assert_shape(self, value, kind)
        self.assertEqual(statuses['postingTestPassed']['platforms']['instagram']['state'], 'yes')
        self.assertEqual(statuses['postingTestPassed']['platforms']['instagram']['passedAt'], '2026-10-05T16:01:00Z')
        self.assertEqual(statuses['postingTestPassed']['platforms']['threads']['state'], 'no')
        self.assertEqual(statuses['recurringEnabled']['state'], 'no')
        self.assertTrue(view['paused'])
        for timer in view['timers']:
            assert_shape(self, timer, 'TimerStatus')
        self.assertEqual([t['role'] for t in view['timers']], ['publisher', 'monitor', 'renewal', 'renewal', 'metrics'])
        for item in view['issues']:
            assert_shape(self, item, 'Issue')
        for key, kind in (('pages', 'Budget'), ('buffer', 'Budget')):
            assert_shape(self, view['budgets'][key], kind)
        self.assertTrue(view['budgets']['buffer']['low'])
        assert_shape(self, view['storage'], 'StorageStatus')
        assert_shape(self, view['freshness']['healthJson'], 'Freshness')
        self.assertEqual(view['freshness']['healthJson']['label'], 'Updated 10 min ago')
        self.assertEqual(view['freshness']['monitor']['label'], 'Missing')

    def test_uncertain_job_never_offers_post_again(self):
        job = self.view()['uncertainJobs'][0]
        assert_shape(self, job, 'UncertainJob')
        assert_shape(self, job['reconciliation'], 'Reconciliation')
        self.assertEqual(job['accountId'], 't-1')
        text = json.dumps(job).lower().replace('never post it again', '')
        self.assertNotIn('post again', text)
        self.assertNotIn('retry', text)
        self.assertIn('f' * 24, ' '.join(job['reconciliation']['ownerActions']))
        self.assertNotIn('<job id>', ' '.join(job['reconciliation']['ownerActions']))

    def test_recurring_unknown_only_when_unpaused_and_timer_unreadable(self):
        raw, config = raw_dashboard()
        raw['recurringPublishing'].update(configPaused=False, pausedSentinel=False)
        raw['units'] = [u for u in raw['units'] if u['unit'] != 'scalar-social.timer']
        self.assertEqual(self.view(raw, config)['statuses']['recurringEnabled']['state'], 'unknown')
        raw['recurringPublishing'].update(pausedSentinel=True)
        self.assertEqual(self.view(raw, config)['statuses']['recurringEnabled']['state'], 'no')

    def test_timer_results(self):
        raw, config = raw_dashboard()
        for u in raw['units']:
            if u['unit'] == 'scalar-social-monitor.service':
                u.update(lastExit='Wed 2026-10-07 11:55:00 UTC', result='exit-code', exitStatus='2')
        view = self.view(raw, config)
        monitor = next(t for t in view['timers'] if t['role'] == 'monitor')
        self.assertEqual((monitor['lastResult'], monitor['lastRunAt']), ('failed', '2026-10-07T11:55:00Z'))
        self.assertIn('exit status 2', monitor['lastResultDetail'])
        self.assertEqual(view['freshness']['monitor']['ok'], False)
        publisher = view['timers'][0]
        self.assertEqual(publisher['lastResult'], 'never')


class LibraryTests(unittest.TestCase):
    def raw_episode(self, **changes):
        meta = {'episodeId': 'scalar-clues-001', 'revision': 1}
        raw = {'episodeId': 'scalar-clues-001', 'revision': 1, 'questionId': 'scalar:Q1:clues', 'game': 'scalar',
               'format': 'progressive-clues', 'difficulty': 'approachable', 'status': 'approved', 'expired': False,
               'problems': ['video fps: Measured differs'], 'videoSha256': SHA, 'coverSha256': OTHER, 'metadataSha256': 'ee' * 32,
               'platforms': {p: {'eligible': p != 'bluesky', 'reason': 'Duration must be 0–60 s on bluesky' if p == 'bluesky' else None}
                             for p in v.PLATFORMS},
               'legacy': False, 'inManifest': False, 'variants': ['scalar-clues-009 r2'], 'videoUrl': '/api/media/videos/x',
               'coverUrl': None, 'episode': meta,
               'media': {'bytes': 9, 'durationSeconds': 22.0, 'width': 1080, 'height': 1920, 'fps': '30/1', 'videoCodec': 'h264',
                         'pixFmt': 'yuv420p', 'videoStreams': 1, 'audioStreams': 1, 'audioCodec': 'aac', 'audioSampleRate': 48000,
                         'audioChannels': 2, 'fastStart': True},
               'approvals': [{'id': 4, 'action': 'approve', 'reviewer': 'owner', 'at': '2026-10-07T12:00:00Z', 'video_sha256': SHA,
                              'cover_sha256': OTHER, 'metadata_sha256': 'ee' * 32, 'caption_sha256': 'ff' * 32, 'note': None}]}
        raw.update(changes)
        return raw

    def test_episode_shape(self):
        posted = v.posted_records([('instagram', '111', '2026-10-05T16:00:00+00:00', 'scalar:Q1:clues', 'confirmed'),
                                   ('instagram', '111', '2026-10-05T16:02:00+00:00', 'scalar:Q1:clues#comment', 'confirmed')])
        ep = v.library_episode(self.raw_episode(), 'b1', posted)
        assert_shape(self, ep, 'LibraryEpisode')
        assert_shape(self, ep['media'], 'MeasuredMedia')
        self.assertEqual(ep['variants'], ['scalar-clues-009@2'])
        self.assertEqual(ep['currentApproval']['id'], 4)
        assert_shape(self, ep['currentApproval'], 'ApprovalRecord')
        self.assertEqual(ep['platforms']['bluesky'], {'eligible': False, 'reason': 'Duration must be 0–60 s on bluesky'})
        self.assertEqual(ep['platforms']['x'], {'eligible': True, 'reason': None})
        self.assertEqual(ep['postedOn'], [{'platform': 'instagram', 'accountId': '111', 'status': 'confirmed',
                                           'slotUtc': '2026-10-05T16:00:00Z'}])
        self.assertEqual(ep['problems'], [{'code': 'media', 'path': '', 'message': 'video fps: Measured differs'}])

    def test_missing_video_and_expiry(self):
        ep = v.library_episode(self.raw_episode(platforms=None, media=None, videoUrl=None, expired=True, status='reviewable',
                                                approvals=[]), 'b1', {})
        self.assertEqual((ep['status'], ep['statusLabel'], ep['media'], ep['currentApproval']), ('expired', 'Expired', None, None))
        self.assertFalse(any(p['eligible'] for p in ep['platforms'].values()))
        withdrawn = v.library_episode(self.raw_episode(status='withdrawn'), 'b1', {})
        self.assertIsNone(withdrawn['currentApproval'])
        locked = v.library_episode(self.raw_episode(inManifest=True), 'b1', {})
        self.assertFalse(locked['deletable'])

    def test_batch_and_import(self):
        batch = v.library_batch({'batchId': 'b1', 'origin': 'mac', 'createdAt': '2026-10-06T14:00:00Z',
                                 'importedAt': '2026-10-07T12:00:00Z', 'warnings': ['generator.dirty: uncommitted'],
                                 'episodes': [{'status': 'awaiting_files'}, {'status': 'approved'}], 'batchJsonSha256': SHA,
                                 'generator': {'repoCommit': '7e7deb5', 'dirty': True}})
        assert_shape(self, batch, 'LibraryBatch')
        self.assertEqual((batch['generatorDirty'], batch['awaitingFiles'], batch['episodeCount']), (True, 1, 2))
        result = {'batchId': 'b1', 'status': 'imported', 'problems': [], 'problemItems': [],
                  'warnings': ['dirty'], 'warningItems': [{'code': 'dirty_generator', 'path': 'generator.dirty', 'message': 'dirty'}],
                  'merge': [{'episodeId': 'e', 'revision': 2, 'outcome': 'new-revision', 'message': None}],
                  'expected': [{'file': 'videos/e.mp4', 'kind': 'video', 'episodeId': 'e', 'revision': 2, 'sha256': SHA,
                                'bytes': 5, 'present': False}]}
        view = v.batch_import(result)
        assert_shape(self, view, 'BatchImportResponse')
        assert_shape(self, view['expected'][0], 'ExpectedFile')
        self.assertEqual(view['expected'][0]['name'], 'e.mp4')
        self.assertEqual(view['warnings'], [{'code': 'dirty_generator', 'path': 'generator.dirty', 'message': 'dirty'}])

    def test_file_upload_outcomes(self):
        base = {'file': 'videos/e.mp4', 'kind': 'video', 'episodeId': 'e', 'revision': 1, 'sha256': SHA, 'expectedBytes': 5}
        stored = v.file_upload({**base, 'ok': True, 'alreadyPresent': False, 'status': 'reviewable', 'problems': []}, SHA, 5)
        assert_shape(self, stored, 'FileUploadResult')
        self.assertEqual((stored['outcome'], stored['matched'], stored['message']), ('stored', True, None))
        present = v.file_upload({**base, 'ok': True, 'alreadyPresent': True, 'status': 'reviewable', 'problems': []}, SHA, 5)
        self.assertEqual(present['outcome'], 'already-present')
        mismatch = v.file_upload({**base, 'ok': False, 'problems': ["This file's content doesn't match batch.json"]}, OTHER, 5)
        self.assertEqual((mismatch['outcome'], mismatch['matched'], mismatch['sha256']), ('rejected', False, OTHER))
        short = v.file_upload({**base, 'ok': False, 'problems': ['The file is 4 bytes but batch.json expects 5']}, None, 4)
        self.assertEqual((short['matched'], short['bytes'], short['expectedBytes']), (False, 4, 5))



def draft_body(**changes):
    job = {'key': f'instagram|2026-10-12T13:00:00+00:00|scalar:Q1:clues', 'platform': 'instagram', 'accountId': '111',
           'slotUtc': '2026-10-12T13:00:00+00:00', 'slotLocal': '2026-10-12T09:00:00-04:00', 'zone': 'EDT', 'kind': 'post',
           'episodeKey': 'scalar:Q1:clues', 'parentKey': None, 'episodeId': 'scalar-clues-001', 'revision': 1, 'batchId': 'b',
           'questionId': 'scalar:Q1:clues', 'game': 'scalar', 'videoSha256': SHA, 'coverSha256': OTHER, 'text': 'T',
           'youtube': None, 'thread': None, 'poll': None, 'link': None, 'companion': None, 'carried': False, 'edited': False,
           'basePayload': None, 'warnings': []}
    poll = {**job, 'key': 'threads|x|scalar:Q1:clues#poll', 'platform': 'threads', 'kind': 'poll', 'parentKey': 'p',
            'episodeKey': 'scalar:Q1:clues#poll', 'videoSha256': None,
            'poll': {'question': 'Which?', 'options': ['A', 'B'], 'native': False}, 'companion': {'parentEpisode': 'q'}}
    body = {'version': 1, 'inputs': {'timezone': 'America/New_York', 'carryOnly': False}, 'baseManifestSha256': None,
            'libraryHash': 'aa' * 32, 'historyHash': 'bb' * 32, 'jobs': [job, poll],
            'unfilled': [{'platform': 'x', 'slotLocal': 'l', 'slotUtc': None, 'reason': 'r'}],
            'excluded': [{'platform': 'tiktok', 'reason': 'TikTok is blocked'},
                         {'platform': 'threads', 'companion': 'reply', 'reason': 'Threads replies need a grant'}],
            'ineligible': [], 'warnings': ['w'], 'blocking': [],
            'summary': {'requested': 2, 'filled': 1, 'companions': 1, 'carried': 0, 'removed': 0}}
    body.update(changes)
    return body


class DraftTests(unittest.TestCase):
    def test_projection(self):
        view = v.draft_response(SHA, draft_body(), status='draft', created_at='2026-10-07T12:00:00.5+00:00', blocking=[],
                                cover_urls={OTHER: '/api/media/covers/x.jpg?t=1.a'})
        assert_shape(self, view, 'DraftResponse')
        assert_shape(self, view['draft'], 'Draft')
        for job in view['draft']['jobs']:
            assert_shape(self, job, 'DraftJob')
        self.assertEqual(view['confirmationPhrase'], 'APPROVE abababab')
        self.assertEqual(view['createdAt'], '2026-10-07T12:00:00Z')
        self.assertEqual(view['draft']['jobs'][1]['poll'], {'question': 'Which?', 'options': ['A', 'B']})
        self.assertEqual(view['draft']['excluded'], [{'platform': 'tiktok', 'reason': 'TikTok is blocked'}])
        self.assertIn('Threads replies not scheduled: Threads replies need a grant', view['draft']['warnings'])
        self.assertEqual(view['draft']['summary'], {'requested': 2, 'filled': 1, 'companions': 1})

    def blocking(self, body=None, **kw):
        args = dict(sha=SHA, now=NOW, current_manifest_sha=None, approved_draft_sha=None, pending=None,
                    library_hash='aa' * 32, exclusions={})
        args.update(kw)
        return v.blocking_problems(body or draft_body(), **args)

    def test_blocking_rechecks(self):
        self.assertEqual(self.blocking(), [])
        self.assertTrue(any('library changed' in b for b in self.blocking(library_hash='00' * 32)))
        self.assertTrue(any('different schedule' in b for b in self.blocking(current_manifest_sha=OTHER)))
        self.assertTrue(any('already the approved' in b for b in self.blocking(current_manifest_sha=OTHER, approved_draft_sha=SHA)))
        self.assertTrue(any('Another approval' in b for b in self.blocking(pending={'draftSha256': OTHER})))
        self.assertTrue(any('Instagram:' in b for b in self.blocking(exclusions={'instagram': 'Account identity is not verified'})))
        late = self.blocking(now=dt.datetime(2026, 10, 12, 12, 45, tzinfo=dt.timezone.utc))
        self.assertTrue(any('30 minutes' in b for b in late))
        carried = draft_body()
        for job in carried['jobs']:
            job['carried'] = True
        self.assertEqual(self.blocking(carried, now=dt.datetime(2026, 10, 12, 12, 45, tzinfo=dt.timezone.utc)), [])
        self.assertIn('The draft has no posts to schedule.', self.blocking(draft_body(jobs=[])))
        self.assertIn('kept', self.blocking(draft_body(blocking=['kept'])))

    def test_status(self):
        kw = dict(approved_draft_sha=None, past_draft_shas=set(), pending=None, last_result=None)
        self.assertEqual(v.draft_status('draft', SHA, **kw), 'draft')
        self.assertEqual(v.draft_status('draft', SHA, **{**kw, 'approved_draft_sha': SHA}), 'approved')
        self.assertEqual(v.draft_status('draft', SHA, **{**kw, 'past_draft_shas': {SHA}}), 'superseded')
        self.assertEqual(v.draft_status('draft', SHA, **{**kw, 'pending': {'draftSha256': SHA}}), 'requested')
        self.assertEqual(v.draft_status('requested', SHA, **{**kw, 'last_result': {'status': 'failed', 'draftSha256': SHA}}), 'failed')
        self.assertEqual(v.draft_status('requested', SHA, **{**kw, 'last_result': {'status': 'validated-no-deploy', 'draftSha256': SHA}}),
                         'requested')


class HistoryTests(unittest.TestCase):
    def rows(self):
        base = {'platform': 'instagram', 'account': '111', 'slot': {'utc': '2026-10-05T16:00:00Z'}, 'episode': 'ep03',
                'episodeId': 'scalar-legacy-003', 'game': 'scalar', 'kind': 'post', 'status': 'confirmed', 'attempts': 1,
                'error': None, 'permalink': 'https://www.instagram.com/reel/A/', 'publishedAt': '2026-10-05T16:01:00+00:00',
                'dispatchedAt': '2026-10-05T16:00:01+00:00', 'caption': '=HYPERLINK("x") ' + 'c' * 200}
        uncertain = {**base, 'id': 'b' * 24, 'platform': 'threads', 'episode': 'ep04#comment', 'kind': 'comment',
                     'status': 'uncertain', 'permalink': 'https://threads/x', 'error': ui_health.explain('uncertain_response'),
                     'slot': {'utc': '2026-10-07T03:30:00Z'}, 'game': 'continuum'}
        return [v.history_row(r) for r in ({**base, 'id': 'a' * 24}, uncertain)]

    def test_rows_and_filters(self):
        confirmed, uncertain = self.rows()
        assert_shape(self, confirmed, 'HistoryRow')
        self.assertEqual(len(confirmed['captionPreview']), 140)
        self.assertIsNone(uncertain['permalink'])  # only confirmed posts carry a permalink
        self.assertEqual(uncertain['questionId'], 'ep04')
        q = lambda **k: v.history_query({key: [val] for key, val in k.items()}, 'America/New_York')
        rows = self.rows()
        self.assertEqual(len(v.history(rows, q(), {})['rows']), 2)
        self.assertEqual(v.history(rows, q(question='ep04'), {})['rows'], [uncertain])
        self.assertEqual(v.history(rows, q(platform='threads'), {})['rows'], [uncertain])
        # 03:30 UTC on 7 Oct is 6 Oct in New York.
        self.assertEqual(v.history(rows, q(**{'from': '2026-10-06', 'to': '2026-10-06'}), {})['rows'], [uncertain])
        limited = v.history(rows, q(limit='1'), {'timezone': 'America/New_York'})
        self.assertEqual((limited['total'], limited['truncated'], len(limited['rows'])), (2, True, 1))
        assert_shape(self, limited, 'HistoryResponse')
        for bad in ({'platform': ['myspace']}, {'status': ['gone']}, {'from': ['2026-13-01']}, {'limit': ['0']}, {'format': ['xml']}):
            with self.assertRaises(ValueError):
                v.history_query(bad, 'UTC')

    def test_csv_same_columns_and_no_formula_injection(self):
        text = v.history_csv(self.rows())
        header, first = text.splitlines()[:2]
        self.assertEqual(header.split(','), list(v.CSV_FIELDS))
        self.assertIn(',"\'=HYPERLINK(""x"")', first)
        self.assertIn('uncertain_response', text)

    def test_job_detail(self):
        raw = {'id': 'b' * 24, 'platform': 'threads', 'account': 't-1', 'slot': {'utc': '2026-10-06T16:00:00Z'},
               'episode': 'ep04', 'episodeId': None, 'game': 'continuum', 'kind': 'post', 'status': 'uncertain', 'attempts': 1,
               'error': ui_health.explain('uncertain_response'), 'permalink': None, 'publishedAt': None,
               'dispatchedAt': '2026-10-06T16:00:00+00:00', 'caption': 'Guess along',
               'events': [{'seq': 3, 'kind': 'uncertain', 'at': '2026-10-06T16:00:02+00:00', 'detail': 'uncertain_response'}],
               'reconciliation': {'state': 'uncertain', 'nextCheck': '2026-10-07T13:00:00Z', 'ownerActions': ui_health.OWNER_ACTIONS},
               'payload': {'caption': 'Guess along', 'media': {'url': 'https://m/x.mp4', 'sha256': SHA},
                           'thread': ['A) x'], 'metadata': {}}}
        view = v.job_detail(raw, {'timezone': 'America/New_York'}, None)
        assert_shape(self, view, 'JobDetailResponse')
        assert_shape(self, view['events'][0], 'JobEvent')
        self.assertEqual(view['events'][0]['label'], 'Result unknown; checking')
        self.assertEqual(view['reconciliation']['lastCheckAt'], '2026-10-06T16:00:02Z')
        self.assertEqual(view['payload']['thread'], ['A) x'])
        self.assertNotIn('post again', json.dumps(view).lower().replace('never post it again', ''))


class ActivationTests(unittest.TestCase):
    def test_items(self):
        rows = [('Configuration file is 0640 root:scalar-social', False, 'Found mode 600; run: sudo chmod 0640 /etc/x'),
                ('Approved schedule exists and is bound by hash', True, 'manifest abc, 3 posts')]
        view = v.activation(rows, OTHER, {'scope': ['instagram']}, 'sudo a --apply', 'sudo a --check')
        assert_shape(self, view, 'ActivationResponse')
        for item in view['items']:
            assert_shape(self, item, 'ChecklistItem')
        self.assertFalse(view['ready'])
        self.assertEqual(view['items'][0]['id'], 'configuration-file-is-0640-root-scalar-social')
        self.assertIn('chmod', view['items'][0]['nextAction'])
        self.assertEqual(view['scope'], ['instagram'])


if __name__ == '__main__':
    unittest.main()
