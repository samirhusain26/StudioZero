"""Contract v2 on the Pi: v1 and v2 batches in one library, the duplicate key (contentId = v1 questionId),
the v2 views, and attribution verification in the schedule generator."""
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'publisher/app'))
sys.path.insert(0, str(ROOT/'contract'))
sys.path.insert(0, str(ROOT/'contract/tests'))
sys.path.insert(0, str(ROOT/'publisher/tests'))
import library_contract as lc
import ui_library as ul
import ui_schedule as us
from contract_fixtures import TMDB, WIKI, FakeProbe, document, document_v2, episode, originals_v2, scalargame_v2, write_batch
from test_ui_schedule import ALL, config, inputs, posts

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)


def grabber(video, out):
    Path(out).write_bytes(b'\xff\xd8\xff' + hashlib.sha256(Path(video).read_bytes()).digest())


class MixedLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)/'state'
        self.state.mkdir()
        self.src = Path(self.tmp.name)/'mac'
        self.index = ul.open_index(self.state)
        self._reserve, ul.FREE_SPACE_RESERVE = ul.FREE_SPACE_RESERVE, 0

    def tearDown(self):
        ul.FREE_SPACE_RESERVE = self._reserve
        self.index.close()
        self.tmp.cleanup()

    def load(self, data):
        folder, data, blobs = write_batch(self.src, data)
        result = ul.import_batch_json(self.index, self.state, (folder/'batch.json').read_bytes(), NOW)
        self.assertEqual(result['problems'], [], result)
        for e in data['episodes']:
            for kind in ('video', 'cover'):
                name = e[kind]['file']
                r = ul.accept_batch_file(self.index, self.state, data['batchId'], name, io.BytesIO(blobs[name]),
                                         len(blobs[name]), FakeProbe(), grabber, NOW)
                self.assertTrue(r['ok'], r)
        return data

    def test_v1_and_v2_in_one_library(self):
        self.load(document([episode(1)], batch_id='2026-10-v1'))
        v2 = self.load(document_v2([scalargame_v2(7, 'continuum')], batch_id='2026-10-v2'))
        orig = self.load(document_v2([originals_v2(1)], 'originals', batch_id='2026-10-o01'))
        rows = {r['episode_id']: r for r in self.index.execute('SELECT * FROM episodes')}
        self.assertEqual({k: (r['question_id'], r['game'], r['status']) for k, r in rows.items()}, {
            'scalar-clues-001': ('scalar:Q1:clues', 'scalar', 'reviewable'),
            'continuum-clues-007': ('continuum:Q7:clues', 'continuum', 'reviewable'),
            'originals-recap-001': ('originals:movie-recap:1', 'originals', 'reviewable')})
        self.assertEqual(rows['continuum-clues-007']['difficulty'], 'approachable')
        # The episode is stored exactly as imported; its approval hashes cover it as in v1.
        self.assertEqual(json.loads(rows['originals-recap-001']['metadata']), orig['episodes'][0])
        items = [{'episodeId': e, 'revision': 1} for e in rows]
        self.assertEqual(ul.approve(self.index, items, 'owner', NOW, self.state)['count'], 3)
        records = {r['episodeId']: r for r in ul.schedulable_videos(self.index, NOW.date())}
        self.assertEqual(set(records), set(rows))
        self.assertEqual(set(records['originals-recap-001']), set(records['scalar-clues-001']))  # same record shape
        view = {e['episodeId']: e for b in ul.library_view(self.index, self.state, lambda k, s: '') for e in b['episodes']}
        self.assertEqual((view['scalar-clues-001']['project'], view['scalar-clues-001']['engine'], view['scalar-clues-001']['renderer'],
                          view['scalar-clues-001']['schemaVersion']), ('scalargame', 'motion', None, 1))
        self.assertEqual((view['continuum-clues-007']['renderer'], view['continuum-clues-007']['creative']['answer']), ('render.sh', 'Bolivia'))
        o = view['originals-recap-001']
        self.assertEqual((o['project'], o['engine'], o['route'], o['links'], o['disclosure']['aiGenerated']),
                         ('originals', 'story', 'recap', {}, True))
        self.assertEqual(view['continuum-clues-007']['links']['x'], lc.link_for(v2['episodes'][0], 'x'))
        self.assertTrue(view['continuum-clues-007']['links']['x'].startswith('https://www.scalargame.com/continuum?'))

    def test_merge_rules_hold_for_v2(self):
        data = self.load(document_v2([originals_v2(1)], 'originals', batch_id='2026-10-o01'))
        again = copy.deepcopy(data)
        again['episodes'][0]['publication']['altText'] = 'Changed.'
        folder, _, _ = write_batch(Path(self.tmp.name)/'mac2', again)
        result = ul.import_batch_json(self.index, self.state, (folder/'batch.json').read_bytes(), NOW)
        self.assertEqual(result['merge'][0]['outcome'], 'rejected')
        again['episodes'][0]['revision'] = 2
        folder, _, _ = write_batch(Path(self.tmp.name)/'mac3', again)
        result = ul.import_batch_json(self.index, self.state, (folder/'batch.json').read_bytes(), NOW)
        self.assertEqual(result['merge'][0]['outcome'], 'new-revision')

    def test_invalid_v2_refused_with_plain_paths(self):
        e = originals_v2(1)
        e['contentId'] = 'scalar:Q1:clues'
        folder, _, _ = write_batch(self.src, document_v2([e], 'originals'))
        result = ul.import_batch_json(self.index, self.state, (folder/'batch.json').read_bytes(), NOW)
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(p.startswith('originals-recap-001 · contentId') for p in result['problems']), result['problems'])


def v2_record(ep, n=1):
    ep = copy.deepcopy(ep)
    sha = hashlib.sha256(ep['episodeId'].encode()).hexdigest()
    ep['video']['sha256'], ep['eligibility']['status'] = sha, 'approved'
    view = lc.episode_view(ep)
    return {'episodeId': ep['episodeId'], 'revision': 1, 'batchId': '2026-10-v2', 'questionId': view['contentId'],
            'game': view['group'], 'difficulty': view['difficulty'], 'videoSha256': sha, 'coverSha256': sha,
            'bytes': 9123456, 'durationSeconds': 22.0, 'platforms': {p: {'eligible': True, 'reason': None} for p in ALL},
            'eligibility': {'notBefore': None, 'reviewBy': '2027-04-01', 'expiresAt': None},
            'approvalId': n, 'metadataSha256': lc.episode_metadata_hash(ep), 'episode': ep}


class ScheduleTests(unittest.TestCase):
    def test_contentid_shares_the_ledger_with_v1(self):
        history = {'instagram': {'used': ['scalar:Q1:clues'], 'slots': [], 'postSlots': []}}
        draft = us.generate(inputs(end='2026-10-13'), [v2_record(scalargame_v2(1)), v2_record(scalargame_v2(2))], history, config())
        self.assertEqual([j['questionId'] for j in posts(draft)], ['scalar:Q2:clues'])
        self.assertIn('Already posted', next(i['reason'] for i in draft['ineligible'] if i['questionId'] == 'scalar:Q1:clues'))

    def test_v2_post_payload_expands_its_link(self):
        draft = us.generate(inputs(platforms=('x',)), [v2_record(scalargame_v2(1))], {}, config())
        job = posts(draft)[0]
        self.assertEqual(job['link'], lc.link_for(scalargame_v2(1), 'x'))
        self.assertIn(job['link'], job['text'])

    def test_originals_follow_scalargame_without_targets(self):
        videos = [v2_record(originals_v2(1)), v2_record(scalargame_v2(1)), v2_record(scalargame_v2(2, 'continuum'))]
        draft = us.generate(inputs(end='2026-10-14'), videos, {}, config())
        self.assertEqual([j['game'] for j in posts(draft)], ['scalar', 'continuum', 'originals'])

    def test_attribution_must_post(self):
        e = originals_v2(1)
        e['publication']['captions']['instagram'] = 'A film in 60 seconds.'
        e['publication']['firstComment'] = {'instagram': f'{TMDB}. {WIKI}.'}
        video = v2_record(e)
        off = us.generate(inputs(), [video], {}, config())
        self.assertEqual(posts(off), [])
        self.assertEqual(off['ineligible'][0]['reason'], us.ATTRIBUTION_MISSING)
        on = us.generate(inputs(first=True), [video], {}, config())
        self.assertEqual([j['kind'] for j in on['jobs']], ['post', 'comment'])
        self.assertIn(TMDB, on['jobs'][1]['text'])

    def test_edits_keep_the_attribution(self):
        video = v2_record(originals_v2(1))
        draft = us.generate(inputs(platforms=('facebook',)), [video], {}, config())
        key = posts(draft)[0]['key']
        edited = us.generate(inputs(platforms=('facebook',), edits={key: {'text': 'A film in 60 seconds.'}}), [video], {}, config())
        self.assertTrue(any('required attribution' in b for b in edited['blocking']), edited['blocking'])
        ok = us.generate(inputs(platforms=('facebook',), edits={key: {'text': f'New hook. {TMDB}. {WIKI}.'}}), [video], {}, config())
        self.assertEqual(ok['blocking'], [])


if __name__ == '__main__':
    unittest.main()


class LabelTests(unittest.TestCase):
    def payloads(self, ep):
        video = v2_record(ep) if 'contentId' in ep else None
        if video is None:
            from test_ui_schedule import record
            video = record(1)
        cfg = config()
        draft = us.generate(inputs(platforms=ALL), [video], {}, cfg)
        return {j['platform']: us.manifest_payload(j, video, cfg, 'd' * 64) for j in posts(draft)}

    def test_v1_payloads_are_unchanged(self):
        out = self.payloads(episode(1))
        self.assertTrue(all('disclosure' not in p for p in out.values()))
        self.assertFalse(out['youtube']['metadata']['youtube']['isAiGenerated'])
        self.assertEqual(out['tiktok']['metadata'], {})

    def test_ai_generated_originals(self):
        out = self.payloads(originals_v2(1))
        labels = {p: (v['disclosure']['label'], v['disclosure']['field']) for p, v in out.items()}
        self.assertEqual({p: l for p, (l, _) in labels.items()}, {
            'instagram': 'applied', 'facebook': 'not-supported', 'threads': 'not-supported', 'x': 'applied',
            'youtube': 'not-needed', 'bluesky': 'not-supported', 'tiktok': 'applied'})
        self.assertEqual(out['tiktok']['metadata'], {'tiktok': {'isAiGenerated': True}})
        self.assertEqual(out['x']['metadata'], {'twitter': {'isAiGenerated': True}})
        self.assertFalse(out['youtube']['metadata']['youtube']['isAiGenerated'])  # not realistic: no YouTube label
        e = originals_v2(2, 'animated-short')
        e['disclosure'].update(aiKinds=['script', 'video'], realisticSynthetic=True)
        self.assertTrue(self.payloads(e)['youtube']['metadata']['youtube']['isAiGenerated'])

    def test_no_ai_content_needs_no_label(self):
        out = self.payloads(scalargame_v2(1))
        self.assertEqual({v['disclosure']['label'] for v in out.values()}, {'not-needed'})
        self.assertEqual(out['tiktok']['metadata'], {})


class MixTests(unittest.TestCase):
    def videos(self, scalar=6, originals=3):
        return ([v2_record(scalargame_v2(n, ('scalar', 'continuum')[n % 2]), n) for n in range(1, scalar + 1)]
                + [v2_record(originals_v2(n), 100 + n) for n in range(1, originals + 1)])

    def test_no_targets_is_exactly_today(self):
        import autopilot
        catalog = json.loads((ROOT/'publisher/catalog.json').read_text())
        self.assertTrue(all(p['mix']['target'] is None for p in catalog['projects']))
        self.assertIsNone(autopilot.catalog_mix(catalog))
        today = dt.date(2026, 10, 12)
        self.assertEqual(autopilot.recommended_inputs(config(), today, catalog), autopilot.recommended_inputs(config(), today))
        self.assertEqual(autopilot.recommended_inputs(config(), today, catalog)['ordering'], 'game-round-robin')
        self.assertNotIn('mix', us._normalize(inputs()))
        a = us.generate(inputs(end='2026-10-20'), self.videos(), {}, config())
        self.assertNotIn('byProject', a['summary'])

    def test_targets_fill_slots_by_share(self):
        inp = inputs(end='2026-10-19')
        inp.update(ordering='project-mix', mix={'scalargame': 0.75, 'originals': 0.25})
        draft = us.generate(inp, self.videos(), {}, config())
        projects = [lc.project_of(j_episode) for j_episode in
                    (next(v['episode'] for v in self.videos() if v['episodeId'] == j['episodeId']) for j in posts(draft))]
        self.assertEqual(projects, ['scalargame', 'originals', 'scalargame', 'scalargame', 'scalargame', 'originals', 'scalargame', 'scalargame'])
        self.assertEqual(draft['summary']['byProject'], {'originals': 2, 'scalargame': 6})
        again = us.generate(copy.deepcopy(inp), list(reversed(self.videos())), {}, config())
        self.assertEqual(us.draft_sha256(draft), us.draft_sha256(again))

    def test_a_project_runs_out_and_the_other_fills(self):
        inp = inputs(end='2026-10-16')
        inp.update(ordering='project-mix', mix={'scalargame': 0.5, 'originals': 0.5})
        draft = us.generate(inp, self.videos(scalar=4, originals=1), {}, config())
        self.assertEqual(draft['summary']['byProject'], {'originals': 1, 'scalargame': 4})

    def test_share_zero_or_missing_is_left_out(self):
        inp = inputs(end='2026-10-16')
        inp.update(ordering='project-mix', mix={'scalargame': 1, 'originals': 0})
        draft = us.generate(inp, self.videos(scalar=2, originals=2), {}, config())
        self.assertEqual(draft['summary']['byProject'], {'scalargame': 2})
        self.assertEqual({i['reason'] for i in draft['ineligible'] if i['questionId'].startswith('originals:')}, {us.NOT_IN_MIX})
        import autopilot
        self.assertEqual(autopilot.catalog_mix({'projects': [{'id': 'scalargame', 'mix': {'target': 0.8}},
                                                             {'id': 'originals', 'mix': {'target': None}}]}),
                         {'scalargame': 0.8, 'originals': 0})

    def test_mix_inputs_are_checked(self):
        for bad in ({'ordering': 'game-round-robin', 'mix': {'scalargame': 1}}, {'ordering': 'project-mix'},
                    {'ordering': 'project-mix', 'mix': {'scalargame': 2}}, {'ordering': 'project-mix', 'mix': {'scalargame': 0}},
                    {'ordering': 'project-mix', 'mix': {'Bad Name': 1}}):
            inp = inputs()
            inp.update(bad)
            with self.assertRaises(ValueError):
                us._normalize(inp)
        inp = inputs()
        inp.update(ordering='project-mix', mix={'scalargame': 1.0, 'originals': 0.25})
        self.assertEqual(us._normalize(inp)['mix'], {'originals': 0.25, 'scalargame': 1})
