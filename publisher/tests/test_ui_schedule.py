import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'publisher/app'))
sys.path.insert(0, str(ROOT / 'contract'))
sys.path.insert(0, str(ROOT / 'contract/tests'))
import buffer_adapter
import library_contract as lc
from contract_fixtures import episode
from runner import Ledger
import ui_schedule as us

ALL = us.PLATFORM_ORDER


def record(n=1, game='scalar', difficulty='approachable', batch='2026-10-fixture', qid=None, revision=1):
    ep = episode(n, game, question_id=qid)
    ep['difficulty'], ep['revision'] = difficulty, revision
    sha = hashlib.sha256(f'{game}{n}{revision}{qid}'.encode()).hexdigest()
    ep['video']['sha256'] = sha
    ep['cover']['sha256'] = hashlib.sha256(sha.encode()).hexdigest()
    ep['eligibility']['status'] = 'approved'
    return {'episodeId': ep['episodeId'], 'revision': revision, 'batchId': batch, 'questionId': ep['questionId'],
            'game': game, 'difficulty': difficulty, 'videoSha256': sha, 'coverSha256': ep['cover']['sha256'],
            'bytes': 9123456, 'durationSeconds': 22.0,
            'platforms': {p: {'eligible': True, 'reason': None} for p in ALL},
            'eligibility': {'notBefore': None, 'reviewBy': '2027-04-01', 'expiresAt': None},
            'approvalId': n, 'metadataSha256': lc.episode_metadata_hash(ep), 'episode': ep}


def channel(account, route, **extra):
    return {'profileUrl': 'https://example.test/' + account, 'accountId': account, 'enabled': False, 'route': route,
            'identityVerified': True, 'publishingVerified': True, 'reason': None, **extra}


def config():
    data = json.loads((ROOT / 'publisher/config.example.json').read_text())
    data['media']['baseUrl'] = 'https://media.example.test'
    data['channels'] = {
        'instagram': channel('ig-1', 'instagram', previousAccountIds=['ig-old']),
        'facebook': channel('fb-1', 'facebook'),
        'threads': channel('th-1', 'threads', threadsFormat='video', observedScopes=['threads_basic']),
        'x': channel('x-1', 'buffer'),
        'youtube': channel('yt-1', 'buffer'),
        'bluesky': channel('bs-1', 'bluesky'),
        'tiktok': channel('tt-1', 'buffer'),
    }
    return data


def inputs(platforms=('instagram',), start='2026-10-12', end='2026-10-12', times=('09:00',), per_day=1, gap=0,
           stagger=15, first=False, answer=False, edits=None, weekdays=range(7)):
    return {'timezone': 'America/New_York', 'startDate': start, 'endDate': end,
            'platforms': {p: {'include': True, 'weekdays': list(weekdays), 'times': list(times), 'maxPerDay': per_day}
                          for p in platforms},
            'minGapHours': {p: gap for p in platforms}, 'staggerMinutes': stagger, 'ordering': 'game-round-robin',
            'companions': {'firstComment': first, 'answerReply': answer}, 'edits': edits or {}}


def posts(draft, platform=None):
    return [j for j in draft['jobs'] if j['kind'] == 'post' and (platform is None or j['platform'] == platform)]


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = config()
        self.videos = [record(1), record(2), record(3)]

    def gen(self, inp, videos=None, history=None, base=None, cfg=None):
        return us.generate(inp, self.videos if videos is None else videos, history or {}, cfg or self.config, base)

    def test_deterministic_and_order_independent(self):
        videos = [record(n, g, d) for n, (g, d) in enumerate(
            [(g, d) for g in lc.GAMES for d in lc.DIFFICULTIES], 1)]
        inp = inputs(platforms=('instagram', 'threads', 'x'), end='2026-10-20', times=('09:00', '18:30'), per_day=2,
                     first=True)
        a = us.generate(inp, videos, {}, self.config)
        shuffled = videos[:]
        random.Random(7).shuffle(shuffled)
        b = us.generate(copy.deepcopy(inp), shuffled, {}, self.config)
        self.assertEqual(lc.canonical(a), lc.canonical(b))
        self.assertEqual(us.draft_sha256(a), us.draft_sha256(b))
        self.assertEqual(us.draft_sha256(a), hashlib.sha256(lc.canonical(a)).hexdigest())

    def test_game_round_robin_with_interleaved_difficulty(self):
        videos = [record(n, g, d) for n, (g, d) in enumerate(
            [(g, d) for g in ('tectonic', 'scalar', 'continuum') for d in ('challenging', 'approachable', 'moderate')], 1)]
        draft = self.gen(inputs(end='2026-10-20'), videos)
        picked = [(j['game'], next(v['difficulty'] for v in videos if v['episodeId'] == j['episodeId'])) for j in posts(draft)]
        self.assertEqual(picked, [('scalar', 'approachable'), ('continuum', 'approachable'), ('tectonic', 'approachable'),
                                  ('scalar', 'moderate'), ('continuum', 'moderate'), ('tectonic', 'moderate'),
                                  ('scalar', 'challenging'), ('continuum', 'challenging'), ('tectonic', 'challenging')])

    def test_spring_forward_nonexistent_time_skipped(self):
        draft = self.gen(inputs(start='2027-03-13', end='2027-03-15', times=('02:30',)))
        self.assertEqual([j['slotLocal'][:10] for j in posts(draft)], ['2027-03-13', '2027-03-15'])
        self.assertEqual(draft['summary']['requested'], 2)
        self.assertTrue(any('2027-03-14 02:30' in w and 'does not exist' in w for w in draft['warnings']))

    def test_fall_back_ambiguous_time_uses_first_occurrence(self):
        draft = self.gen(inputs(start='2026-11-01', end='2026-11-01', times=('01:30',)))
        [job] = posts(draft)
        self.assertEqual(job['slotUtc'], '2026-11-01T05:30:00+00:00')
        self.assertEqual(job['slotLocal'], '2026-11-01T01:30:00-04:00')
        self.assertEqual(job['zone'], 'EDT')
        self.assertTrue(any('2026-11-01 01:30' in w and 'twice' in w for w in draft['warnings']))
        self.assertTrue(job['warnings'])

    def test_slot_display(self):
        self.assertEqual(us.slot_display('2026-10-12T13:00:00+00:00', 'America/New_York'),
                         {'local': '2026-10-12T09:00:00-04:00', 'utc': '2026-10-12T13:00:00+00:00', 'zone': 'EDT'})
        self.assertEqual(us.slot_display(dt.datetime(2027, 1, 5, 14, tzinfo=dt.timezone.utc), 'America/New_York')['zone'], 'EST')
        draft = self.gen(inputs())
        self.assertEqual((posts(draft)[0]['slotUtc'], posts(draft)[0]['slotLocal']),
                         ('2026-10-12T13:00:00+00:00', '2026-10-12T09:00:00-04:00'))

    def test_exhaustion_counts(self):
        draft = self.gen(inputs(end='2026-10-16'), self.videos[:2])
        self.assertEqual(draft['summary']['requested'], 5)
        self.assertEqual(draft['summary']['filled'], 2)
        self.assertEqual(len(draft['unfilled']), 3)
        self.assertTrue(all(u['reason'] == us.NO_VIDEO for u in draft['unfilled']))

    def test_media_and_caption_ineligibility(self):
        videos = copy.deepcopy(self.videos)
        videos[0]['platforms']['instagram'] = {'eligible': False, 'reason': 'Duration must be 3–900 s on instagram'}
        videos[0]['episode']['publication']['captions']['threads'] = None
        videos[1]['episode']['publication']['youtube'] = None
        draft = self.gen(inputs(platforms=('instagram', 'threads', 'youtube')), videos)
        firsts = {j['platform']: j['episodeId'] for j in posts(draft)}
        self.assertEqual(firsts, {'instagram': 'scalar-clues-002', 'threads': 'scalar-clues-002',
                                  'youtube': 'scalar-clues-001'})
        reasons = {(i['platform'], i['episodeId']): i['reason'] for i in draft['ineligible']}
        self.assertIn('Duration', reasons[('instagram', 'scalar-clues-001')])
        self.assertEqual(reasons[('threads', 'scalar-clues-001')], 'No Threads caption')
        self.assertEqual(reasons[('youtube', 'scalar-clues-002')], 'No YouTube title and description')
        yt = posts(draft, 'youtube')[0]
        self.assertEqual(yt['youtube'], {'title': 'Which country? Three clues #shorts', 'description': 'Guess before the reveal.'})

    def test_eligibility_dates(self):
        video = record(1)
        video['eligibility']['notBefore'] = '2026-10-14'
        draft = self.gen(inputs(end='2026-10-14'), [video])
        self.assertEqual([j['slotLocal'][:10] for j in posts(draft)], ['2026-10-14'])
        self.assertTrue(all('Not before 2026-10-14' in u['reason'] for u in draft['unfilled']))
        expiring = [record(1), record(2)]
        expiring[0]['eligibility']['expiresAt'] = '2026-10-12'
        expiring[1]['eligibility']['reviewBy'] = '2026-10-12'
        draft = self.gen(inputs(end='2026-10-13'), expiring)
        self.assertEqual(len(posts(draft)), 1)
        self.assertIn('Review was due by 2026-10-12', draft['unfilled'][0]['reason'])
        expired = record(1)
        expired['eligibility']['expiresAt'] = '2026-10-11'
        draft = self.gen(inputs(), [expired])
        self.assertIn('Expired on 2026-10-11', draft['unfilled'][0]['reason'])

    def test_provider_caps(self):
        busy = [f'2026-10-12T{14 + i // 60:02d}:{i % 60:02d}:00+00:00' for i in range(25)]
        draft = self.gen(inputs(end='2026-10-13', per_day=30), history={'instagram': {'used': [], 'slots': busy, 'postSlots': busy}})
        self.assertEqual([j['slotLocal'][:10] for j in posts(draft)], ['2026-10-13'])
        self.assertIn('Daily limit reached on Instagram (25', draft['unfilled'][0]['reason'])
        x_busy = [f'2026-10-12T{15 + i // 60:02d}:{i % 60:02d}:00+00:00' for i in range(20)]
        yt_busy = [f'2026-10-12T{16 + i // 60:02d}:{i % 60:02d}:00+00:00' for i in range(20)]
        history = {'x': {'used': [], 'slots': x_busy}, 'youtube': {'used': [], 'slots': yt_busy}}
        draft = self.gen(inputs(platforms=('x',), per_day=30), history=history)
        self.assertEqual(posts(draft), [])
        self.assertIn('Buffer daily limit', draft['unfilled'][0]['reason'])

    def test_tiktok_on_buffer(self):
        videos = copy.deepcopy(self.videos)
        videos[0]['episode']['publication']['captions']['tiktok'] = 'Guess. #a #b #c #d #e #f'
        draft = self.gen(inputs(platforms=('tiktok',), end='2026-10-13'), videos)
        self.assertEqual([j['episodeId'] for j in posts(draft)], ['scalar-clues-002', 'scalar-clues-003'])
        reasons = {i['episodeId']: i['reason'] for i in draft['ineligible']}
        self.assertEqual(reasons['scalar-clues-001'], 'TikTok caption has more than 5 hashtags (Buffer limit)')
        job = posts(draft)[0]
        payload = us.manifest_payload(job, videos[1], self.config, 'd' * 64)
        self.assertEqual((payload['caption'], payload['metadata'], payload['link']), (job['text'], {}, None))
        busy = [f'2026-10-12T{14 + i // 60:02d}:{i % 60:02d}:00+00:00' for i in range(25)]
        draft = self.gen(inputs(platforms=('tiktok',), per_day=30), history={'tiktok': {'used': [], 'slots': busy, 'postSlots': busy}})
        self.assertIn('Daily limit reached on TikTok (25', draft['unfilled'][0]['reason'])

    def test_min_gap(self):
        draft = self.gen(inputs(times=('09:00', '10:00'), per_day=2, gap=2))
        self.assertEqual(len(posts(draft)), 1)
        self.assertIn('minimum gap 2 h', draft['unfilled'][0]['reason'])
        draft = self.gen(inputs(end='2026-10-14', gap=30))
        self.assertEqual([j['slotLocal'][:10] for j in posts(draft)], ['2026-10-12', '2026-10-14'])
        self.assertEqual(draft['summary'], {'requested': 3, 'filled': 2, 'companions': 0, 'carried': 0, 'removed': 0})

    def test_ledger_occupied_slot_and_max_per_day(self):
        history = {'instagram': {'used': [], 'slots': ['2026-10-12T13:00:00+00:00'], 'postSlots': ['2026-10-12T13:00:00+00:00']}}
        draft = self.gen(inputs(times=('09:00', '18:30'), per_day=2), history=history)
        self.assertEqual([j['slotLocal'] for j in posts(draft)], ['2026-10-12T18:30:00-04:00'])
        self.assertEqual(draft['summary']['requested'], 1)
        draft = self.gen(inputs(), history=history)
        self.assertEqual((posts(draft), draft['summary']['requested']), ([], 0))

    def test_stagger(self):
        draft = self.gen(inputs(platforms=('instagram', 'threads', 'x'), stagger=15))
        self.assertEqual([(j['platform'], j['slotUtc'][11:16]) for j in posts(draft)],
                         [('instagram', '13:00'), ('threads', '13:15'), ('x', '13:30')])
        self.assertEqual(len({j['questionId'] for j in posts(draft)}), 1)
        draft = self.gen(inputs(platforms=('instagram', 'threads'), stagger=0))
        self.assertEqual({j['slotUtc'] for j in posts(draft)}, {'2026-10-12T13:00:00+00:00'})

    def test_exclusions(self):
        cfg = config()
        cfg['channels']['facebook']['route'] = 'disabled'
        cfg['channels']['facebook']['reason'] = 'Page route pending'
        cfg['channels']['bluesky']['identityVerified'] = False
        cfg['channels']['youtube']['publishingVerified'] = False
        cfg['channels']['tiktok']['accountId'] = None
        draft = self.gen(inputs(platforms=('instagram', 'facebook', 'youtube', 'bluesky', 'tiktok')), cfg=cfg)
        reasons = {e['platform']: e['reason'] for e in draft['excluded']}
        self.assertEqual(reasons['tiktok'], 'No account identifier is configured')
        self.assertEqual(reasons['facebook'], 'Channel route is disabled: Page route pending')
        self.assertEqual(reasons['bluesky'], 'Account identity is not verified')
        self.assertIn('Publishing is not verified', reasons['youtube'])
        self.assertEqual({j['platform'] for j in draft['jobs']}, {'instagram'})
        self.assertEqual(draft['summary']['requested'], 1)

    def test_companions_per_capability(self):
        videos = copy.deepcopy(self.videos)
        for v in videos:
            v['episode']['publication']['firstComment'].update(bluesky='A) Bolivia B) Paraguay C) Austria {link}',
                                                               x='A) Bolivia B) Paraguay C) Austria')
        everything = ('instagram', 'facebook', 'threads', 'x', 'bluesky')
        draft = self.gen(inputs(platforms=everything, stagger=0, first=True), videos)
        self.assertIn({'platform': 'threads', 'companion': 'reply', 'reason': us.THREADS_SCOPE_MISSING}, draft['excluded'])
        self.assertTrue(any(e['platform'] == 'facebook' and e.get('companion') for e in draft['excluded']))
        companions = {(j['platform'], j['kind']): j for j in draft['jobs'] if j['kind'] != 'post'}
        self.assertEqual(set(companions), {('instagram', 'comment'), ('bluesky', 'comment')})
        ig = companions[('instagram', 'comment')]
        parent = posts(draft, 'instagram')[0]
        self.assertEqual(ig['parentKey'], parent['key'])
        self.assertEqual(ig['episodeKey'], parent['questionId'] + '#comment')
        self.assertEqual(ig['key'], f"instagram|2026-10-12T13:02:00+00:00|{parent['questionId']}#comment")
        self.assertEqual(ig['text'], 'A) Bolivia B) Paraguay C) Austria — comment your letter')
        self.assertEqual(ig['companion'], {'parentEpisode': parent['questionId'], 'delayMinutes': 2})
        self.assertTrue(companions[('bluesky', 'comment')]['text'].endswith(companions[('bluesky', 'comment')]['link']))
        self.assertEqual(draft['summary']['companions'], 2)

        cfg = config()
        cfg['channels']['threads']['observedScopes'] = ['threads_basic', us.THREADS_REPLY_SCOPE]
        draft = self.gen(inputs(platforms=('threads',), first=True), videos, cfg=cfg)
        [poll] = [j for j in draft['jobs'] if j['kind'] == 'poll']
        self.assertEqual(poll['text'], 'Which country?\nA) Bolivia\nB) Paraguay\nC) Austria\nReply with your letter.')
        self.assertEqual(poll['poll']['native'], False)
        self.assertFalse(any(e['platform'] == 'threads' for e in draft['excluded']))
        no_poll = copy.deepcopy(videos)
        for v in no_poll:
            v['episode']['publication']['poll'] = None
            v['episode']['publication']['firstComment']['threads'] = 'A) Bolivia B) Paraguay C) Austria — reply with your letter'
        draft = self.gen(inputs(platforms=('threads',), first=True), no_poll, cfg=cfg)
        self.assertEqual([j['kind'] for j in draft['jobs']], ['post', 'comment'])

        draft = self.gen(inputs(platforms=('instagram',), first=False), videos)
        self.assertEqual([j['kind'] for j in draft['jobs']], ['post'])

    def test_x_thread_requires_verified_buffer_threads(self):
        videos = copy.deepcopy(self.videos)
        for v in videos:
            v['episode']['publication']['firstComment']['x'] = 'A) Bolivia B) Paraguay C) Austria'
        with mock.patch.object(buffer_adapter, 'X_THREAD_VERIFIED', False):
            draft = self.gen(inputs(platforms=('x',), end='2026-10-13', first=True), videos)
            self.assertEqual(us.companion_capabilities()['x']['thread'], 'unverified')
        self.assertTrue(all(j['thread'] is None for j in draft['jobs']))
        self.assertEqual(draft['warnings'].count(us.X_THREAD_SKIPPED), 1)
        with mock.patch.object(buffer_adapter, 'X_THREAD_VERIFIED', True):
            draft = self.gen(inputs(platforms=('x',), first=True), videos)
            self.assertEqual(us.companion_capabilities()['x']['thread'], 'verified')
        [job] = draft['jobs']
        self.assertEqual(job['thread'], ['A) Bolivia B) Paraguay C) Austria'])
        self.assertNotIn(us.X_THREAD_SKIPPED, draft['warnings'])
        self.assertEqual(us.COMPANIONS['x']['thread'], 'unverified')

    def test_answer_reply_only_when_enabled(self):
        videos = copy.deepcopy(self.videos)
        for v in videos:
            v['episode']['publication']['answerReply'] = {'text': '.\nIt was Bolivia.', 'delayHours': 24}
        draft = self.gen(inputs(platforms=('instagram', 'facebook'), end='2026-10-13', first=True), videos)
        self.assertFalse(any(j['kind'] == 'answer' for j in draft['jobs']))
        draft = self.gen(inputs(platforms=('instagram', 'facebook'), end='2026-10-13', first=True, answer=True), videos)
        answers = [j for j in draft['jobs'] if j['kind'] == 'answer']
        self.assertEqual([j['platform'] for j in answers], ['instagram', 'instagram'])
        # Day one's answer lands on day two's post minute and moves one minute later.
        self.assertEqual(answers[0]['slotUtc'], '2026-10-13T13:01:00+00:00')
        self.assertEqual(answers[0]['companion']['delayMinutes'], 24 * 60 + 1)
        slots = [(j['platform'], j['slotUtc']) for j in draft['jobs']]
        self.assertEqual(len(slots), len(set(slots)))

    def test_history_excludes_previous_accounts_and_companion_suffix(self):
        history = {'instagram': {'used': ['scalar:Q1:clues', 'scalar:Q2:clues#comment'], 'slots': []}}
        draft = self.gen(inputs(end='2026-10-13'), history=history)
        self.assertEqual([j['questionId'] for j in posts(draft)], ['scalar:Q3:clues'])
        self.assertEqual(draft['unfilled'][0]['reason'], us.NO_VIDEO)
        reasons = {i['questionId']: i['reason'] for i in draft['ineligible']}
        self.assertEqual(set(reasons), {'scalar:Q1:clues', 'scalar:Q2:clues'})
        variant = record(9, qid='scalar:Q3:clues')
        draft = self.gen(inputs(end='2026-10-13'), self.videos + [variant], history=history)
        self.assertEqual(len(posts(draft)), 1)

    def test_base_manifest_carried_and_counted(self):
        first = self.gen(inputs(platforms=('instagram', 'x'), first=True))
        sha = us.draft_sha256(first)
        by_id = {(v['episodeId'], v['revision']): v for v in self.videos}
        manifest = {'version': 1, 'draftSha256': sha, 'jobs': [
            {'platform': j['platform'], 'slot': j['slotUtc'], 'key': j['key'],
             'payload': us.manifest_payload(j, by_id[(j['episodeId'], j['revision'])], self.config, sha)}
            for j in first['jobs']]}
        draft = self.gen(inputs(platforms=('instagram', 'x'), end='2026-10-13', first=True), base=manifest)
        carried = [j for j in draft['jobs'] if j['carried']]
        self.assertEqual([j['key'] for j in draft['jobs'][:len(carried)]], [j['key'] for j in first['jobs']])
        self.assertEqual(draft['summary']['carried'], len(first['jobs']))
        self.assertEqual(draft['summary']['requested'], 2)
        new = [j for j in posts(draft) if not j['carried']]
        self.assertEqual({j['slotLocal'][:10] for j in new}, {'2026-10-13'})
        self.assertNotIn('scalar:Q1:clues', {j['questionId'] for j in new})
        self.assertEqual(draft['baseManifestSha256'], hashlib.sha256(lc.canonical(manifest)).hexdigest())
        for job, mjob in zip(carried, manifest['jobs']):
            self.assertEqual(us.manifest_payload(job, None, self.config, 'f' * 64), mjob['payload'])
        comment = next(j for j in carried if j['kind'] == 'comment')
        self.assertEqual(comment['parentKey'], carried[0]['key'])

    def edited(self, edits, base_first=True, history=None):
        videos = self.videos
        first = self.gen(inputs(first=base_first))
        sha = us.draft_sha256(first)
        by_id = {(v['episodeId'], v['revision']): v for v in videos}
        manifest = {'jobs': [{'platform': j['platform'], 'slot': j['slotUtc'], 'key': j['key'],
                              'payload': us.manifest_payload(j, by_id[(j['episodeId'], j['revision'])], self.config, sha)}
                             for j in first['jobs']]}
        return first, manifest

    def test_edits(self):
        base = self.gen(inputs(end='2026-10-13', first=True))
        key = posts(base)[0]['key']
        changed = self.gen(inputs(end='2026-10-13', first=True,
                                  edits={key: {'text': 'New words. A) Bolivia B) Paraguay C) Austria'}}))
        self.assertNotEqual(us.draft_sha256(base), us.draft_sha256(changed))
        job = next(j for j in changed['jobs'] if j['key'] == key)
        self.assertEqual((job['text'], job['edited'], changed['blocking']),
                         ('New words. A) Bolivia B) Paraguay C) Austria', True, []))
        spoiled = self.gen(inputs(end='2026-10-13', first=True, edits={key: {'text': 'It is Bolivia!'}}))
        self.assertTrue(spoiled['blocking'])
        self.assertIn('Reveals the answer', spoiled['blocking'][0])
        too_long = self.gen(inputs(platforms=('x',), edits={}))
        xkey = too_long['jobs'][0]['key']
        too_long = self.gen(inputs(platforms=('x',), edits={xkey: {'text': 'a' * 281}}))
        self.assertIn('Too long for x', too_long['blocking'][0])
        removed = self.gen(inputs(end='2026-10-13', first=True, edits={key: {'remove': True}}))
        self.assertFalse(any(j['key'] == key or j['parentKey'] == key for j in removed['jobs']))
        self.assertEqual(removed['summary']['filled'], 1)
        self.assertEqual(removed['summary']['removed'], 2)
        self.assertIn('Removed by edit', [u['reason'] for u in removed['unfilled']])
        stale = self.gen(inputs(edits={'instagram|nope|x': {'remove': True}}))
        self.assertTrue(any('not in this draft' in w for w in stale['warnings']))

    def test_dispatched_carried_jobs_are_immutable(self):
        first, manifest = self.edited({})
        post = first['jobs'][0]
        history = {'dispatched': [f"instagram|{post['slotUtc']}|{post['episodeKey']}"]}
        for edit in ({'text': 'Different words entirely'}, {'remove': True}):
            draft = self.gen(inputs(start='2026-10-13', end='2026-10-13', first=True, edits={post['key']: edit}),
                             history=history, base=manifest)
            self.assertEqual(draft['blocking'], [f"Instagram {post['slotLocal']}: {us.SENT}"])
            job = next(j for j in draft['jobs'] if j['key'] == post['key'])
            self.assertEqual(job['text'], post['text'])
        tuple_history = {'dispatched': {('instagram', post['slotUtc'])}}
        draft = self.gen(inputs(start='2026-10-13', end='2026-10-13', edits={post['key']: {'remove': True}}),
                         history=tuple_history, base=manifest)
        self.assertTrue(draft['blocking'])

    def test_carry_only(self):
        first, manifest = self.edited({})
        post, comment = first['jobs']
        inp = inputs(first=True, start='2026-10-01', end='2026-10-02')
        inp['carryOnly'] = True
        inp['platforms'] = {}
        normalized = us.validate_inputs(inp, self.config, dt.date(2026, 10, 20))
        self.assertTrue(normalized['carryOnly'])
        draft = us.generate(normalized, self.videos, {}, self.config, manifest)
        self.assertEqual([j['key'] for j in draft['jobs']], [post['key'], comment['key']])
        self.assertTrue(all(j['carried'] for j in draft['jobs']))
        self.assertEqual((draft['summary']['requested'], draft['unfilled'], draft['excluded']), (0, [], []))
        full = inputs(first=True, end='2026-10-20')
        full['carryOnly'] = True
        draft = self.gen(full, base=manifest)
        self.assertEqual(len(draft['jobs']), 2)
        edit = copy.deepcopy(full)
        edit['edits'] = {post['key']: {'text': 'Fresh words. A) Bolivia B) Paraguay C) Austria'}}
        draft = self.gen(edit, base=manifest)
        job = draft['jobs'][0]
        self.assertEqual(job['text'], 'Fresh words. A) Bolivia B) Paraguay C) Austria')
        payload = us.manifest_payload(job, None, self.config, 'e' * 64)
        self.assertEqual(payload['caption'], job['text'])
        self.assertEqual(payload['approval']['draftSha256'], 'e' * 64)
        self.assertEqual(payload['media'], manifest['jobs'][0]['payload']['media'])
        cancel = copy.deepcopy(full)
        cancel['edits'] = {post['key']: {'remove': True}}
        draft = self.gen(cancel, base=manifest)
        self.assertEqual((draft['jobs'], draft['summary']['removed']), ([], 2))
        draft = self.gen(cancel, base=manifest, history={'dispatched': [f"instagram|{post['slotUtc']}|{post['episodeKey']}"]})
        self.assertEqual(len(draft['jobs']), 2)
        self.assertEqual(draft['blocking'], [f"Instagram {post['slotLocal']}: {us.SENT}"])

    def test_manifest_payloads(self):
        with mock.patch.object(buffer_adapter, 'X_THREAD_VERIFIED', True):
            draft = self.gen(inputs(platforms=('instagram', 'x', 'youtube', 'bluesky'), stagger=0, first=True))
        video = self.videos[0]
        out = {(j['platform'], j['kind']): us.manifest_payload(j, video, self.config, 'd' * 64) for j in draft['jobs']}
        ig = out[('instagram', 'post')]
        self.assertEqual(ig['episode'], {'id': 'scalar:Q1:clues', 'episodeId': 'scalar-clues-001', 'revision': 1,
                                         'batchId': '2026-10-fixture', 'game': 'scalar'})
        self.assertEqual(ig['media'], {'url': f"https://media.example.test/library/{video['videoSha256']}.mp4",
                                       'sha256': video['videoSha256'], 'bytes': 9123456, 'rightsReviewed': True})
        self.assertEqual(ig['metadata'], {'instagram': {'type': 'reel', 'shouldShareToFeed': True}})
        self.assertEqual(ig['approval'], {'draftSha256': 'd' * 64, 'contentApprovalId': 1,
                                          'metadataSha256': video['metadataSha256']})
        self.assertEqual((ig['format'], ig['previous'], ig['thread'], ig['link']), ('self-contained', None, None, None))
        yt = out[('youtube', 'post')]['metadata']['youtube']
        self.assertEqual((yt['title'], yt['description'], yt['categoryId'], yt['madeForKids']),
                         ('Which country? Three clues #shorts', 'Guess before the reveal.', '27', False))
        x = out[('x', 'post')]
        self.assertTrue(x['link'].startswith('https://www.scalargame.com/scalar?utm_source=x'))
        self.assertIn(x['link'], x['caption'])
        comment = out[('instagram', 'comment')]
        self.assertEqual((comment['kind'], comment['media'], comment['episode']['id']),
                         ('comment', None, 'scalar:Q1:clues#comment'))
        self.assertEqual(comment['companion'], {'parentEpisode': 'scalar:Q1:clues', 'delayMinutes': 2})
        cfg = config()
        cfg['media']['baseUrl'] = None
        with self.assertRaises(ValueError):
            us.manifest_payload(draft['jobs'][0], video, cfg, 'd' * 64)

    def test_budget_and_missing_ledger_warnings(self):
        draft = self.gen(inputs(), history={'ledgerMissing': True, 'deploymentsLast31d': 120, 'bufferCallsLast24h': 3})
        self.assertTrue(any('No publisher ledger' in w for w in draft['warnings']))
        self.assertTrue(any('Pages deployment budget' in w for w in draft['warnings']))
        quiet = self.gen(inputs(), history={'ledgerMissing': True, 'deploymentsLast31d': 1, 'bufferCallsLast24h': 3})
        self.assertEqual(draft['historyHash'], quiet['historyHash'])


class LedgerHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'ledger.sqlite3'
        self.config = config()

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_ledger(self):
        history = us.ledger_history(self.path, self.config, now=0)
        self.assertTrue(history['ledgerMissing'])
        self.assertEqual(history['instagram'], {'used': [], 'slots': [], 'postSlots': []})
        self.assertFalse(self.path.exists())

    def test_reads_history(self):
        ledger = Ledger(self.path)
        ledger.enqueue('instagram', 'ig-old', '2026-09-01T13:00:00+00:00', {'episode': {'id': 'ep01'}})
        key = ledger.enqueue('instagram', 'ig-1', '2026-10-12T13:00:00+00:00', {'episode': {'id': 'scalar:Q1:clues'}})
        ledger.enqueue('instagram', 'ig-1', '2026-10-12T13:02:00+00:00', {'episode': {'id': 'scalar:Q2:clues#comment'}})
        ledger.enqueue('instagram', 'someone-else', '2026-10-13T13:00:00+00:00', {'episode': {'id': 'scalar:Q3:clues'}})
        ledger.update(key, 'confirmed', dispatched_at='2026-10-12T13:00:01+00:00')
        now = 2_000_000_000.0
        with ledger.db:
            ledger.db.execute('INSERT INTO calls VALUES(?)', (now - 3600,))
            ledger.db.execute('INSERT INTO calls VALUES(?)', (now - 2 * 86400,))
        ledger.db.close()
        before = self.path.read_bytes()
        history = us.ledger_history(self.path, self.config, now=now)
        self.assertEqual(history['instagram'], {
            'used': ['ep01', 'scalar:Q1:clues', 'scalar:Q2:clues'],
            'slots': ['2026-10-12T13:00:00+00:00', '2026-10-12T13:02:00+00:00'],
            'postSlots': ['2026-10-12T13:00:00+00:00']})
        self.assertEqual(history['dispatched'], ['instagram|2026-10-12T13:00:00+00:00|scalar:Q1:clues'])
        self.assertEqual((history['deploymentsLast31d'], history['bufferCallsLast24h'], history['ledgerMissing']), (0, 1, False))
        self.assertEqual(self.path.read_bytes(), before)
        ledger = Ledger(self.path)
        with ledger.db:
            ledger.db.execute('CREATE TABLE deployments(at REAL)')
            ledger.db.executemany('INSERT INTO deployments VALUES(?)', [(now - 86400,), (now - 40 * 86400,)])
        ledger.db.close()
        self.assertEqual(us.ledger_history(self.path, self.config, now=dt.datetime.fromtimestamp(now, dt.timezone.utc))['deploymentsLast31d'], 1)
        videos = [record(1), record(2), record(3)]
        draft = us.generate(inputs(end='2026-10-13'), videos, history, self.config)
        self.assertEqual([j['questionId'] for j in posts(draft)], ['scalar:Q3:clues'])


class ValidationTests(unittest.TestCase):
    def check(self, message, **changes):
        data = inputs(gap=1)
        for key, value in changes.items():
            if key in ('include', 'weekdays', 'times', 'maxPerDay'):
                data['platforms']['instagram'][key] = value
            else:
                data[key] = value
        with self.assertRaises(ValueError) as caught:
            us.validate_inputs(data, config(), dt.date(2026, 10, 6))
        self.assertIn(message, str(caught.exception))

    def test_valid_inputs_normalize(self):
        data = inputs(times=('18:30', '09:00'), weekdays=(4, 0), gap=2.0)
        data.pop('edits')
        normalized = us.validate_inputs(data, config(), '2026-10-06')
        self.assertEqual(normalized['platforms']['instagram'],
                         {'include': True, 'weekdays': [0, 4], 'times': ['09:00', '18:30'], 'maxPerDay': 1})
        self.assertEqual(normalized['platforms']['tiktok']['include'], False)
        self.assertEqual((normalized['minGapHours'], normalized['edits'], normalized['carryOnly']), ({'instagram': 2}, {}, False))
        self.assertEqual(us.validate_inputs(normalized, config(), '2026-10-06'), normalized)

    def test_errors(self):
        self.check('Choose a timezone', timezone=None)
        self.check('Choose a timezone', timezone='')
        self.check('Unknown timezone', timezone='Mars/Olympus')
        self.check('Unknown timezone', timezone='../etc/passwd')
        self.check('Start date is in the past', startDate='2026-10-05')
        self.check('End date is before', endDate='2026-10-11')
        self.check('at most 92 days', endDate='2027-01-12')
        self.check('real date', startDate='2026-02-30')
        self.check('Choose at least one platform', platforms={})
        self.check('Choose at least one platform', include=False)
        self.check('Unknown platform', platforms={'myspace': {'include': True}})
        self.check('weekdays', weekdays=[7])
        self.check('weekdays', weekdays=[])
        self.check('weekdays', weekdays=[1, 1])
        self.check('HH:MM', times=['9:00'])
        self.check('HH:MM', times=['24:00'])
        self.check('at most 6 times', times=[f'0{h}:00' for h in range(7)])
        self.check('only once', times=['09:00', '09:00'])
        self.check('at least 1', maxPerDay=0)
        self.check('minimum gap', minGapHours={'instagram': -1})
        self.check('minimum gap', minGapHours={})
        self.check('Stagger', staggerMinutes=241)
        self.check('Stagger', staggerMinutes=-1)
        self.check('content order', ordering='random')
        self.check('Companions', companions={'firstComment': True})
        self.check('Each edit', edits={'k': {'text': ''}})
        self.check('Each edit', edits={'k': {'remove': False}})
        self.check('Each edit', edits={'k': {'text': 'a', 'remove': True}})
        self.check('Unknown schedule setting', cadence='daily')
        self.check('carryOnly', carryOnly='yes')

    def test_carry_only_allows_past_dates_and_no_platform(self):
        data = inputs(start='2026-09-01', end='2026-09-02')
        data['platforms'], data['carryOnly'] = {}, True
        self.assertTrue(us.validate_inputs(data, config(), dt.date(2026, 10, 6))['carryOnly'])
        data['timezone'] = 'Nowhere/Land'
        with self.assertRaises(ValueError):
            us.validate_inputs(data, config(), dt.date(2026, 10, 6))


if __name__ == '__main__':
    unittest.main()
