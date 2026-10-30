import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_episode as ce  # noqa: E402

FORMATS = ce.load_formats()

LEDGER = {
    'episodeId': 'roomba-cliff',
    'format': 'how-it-works',
    'patent': {'number': 'US 6,883,201 B2', 'title': 'Autonomous floor-cleaning robot', 'assignee': 'iRobot Corp.',
               'inventors': ['Joseph L. Jones'], 'priorityDate': '2002-01-03', 'filingDate': '2002-12-16',
               'grantDate': '2005-04-26', 'url': 'https://patents.google.com/patent/US6883201B2/en'},
    'status': {'statement': 'granted 2005-04-26', 'checkedAt': None, 'checkUrl': None},
    'copyrightNotice': {'checked': True, 'present': False},
    'claims': [{'id': 'c1', 'text': 'A robot with a cliff detector that steers away from a drop.', 'location': 'claim 1'}],
    'facts': [
        {'id': f'f{i}', 'kind': k, 'text': 'fact', 'source': {'url': None, 'location': 'col. 1'}, 'confidence': 'verified'}
        for i, k in enumerate(['problem', 'old-way', 'insight', 'mechanism', 'product'], start=1)
    ],
    'productLink': {'level': 3, 'product': 'Roomba', 'evidence': [{'url': 'https://www.irobot.com/en_US/patents.html', 'what': 'marking page', 'checkedAt': '2026-10-13'}]},
    'visuals': [{'id': 'v1', 'kind': 'patent-figure', 'description': 'Fig. 1', 'source': 'https://patents.google.com/patent/US6883201B2/en', 'licence': 'patent document'}],
    'risks': [],
}

FILLER = 'the robot keeps cleaning the floor while it moves around the room and checks the edges again'
SCRIPT = {
    'episodeId': 'roomba-cliff',
    'format': 'how-it-works',
    'status': 'draft',
    'angle': 'It feels for the missing floor.',
    'title': 'Why your Roomba never falls down the stairs',
    'lines': [
        {'id': 'l1', 'beat': 'hook', 'vo': 'A Roomba cannot see the stairs, so why does it never fall?', 'banner': 'It never falls', 'factRefs': ['c1']},
        {'id': 'l2', 'beat': 'problem', 'vo': f'Stairs are a drop. {FILLER}.', 'banner': None, 'factRefs': ['f1']},
        {'id': 'l3', 'beat': 'old-way', 'vo': f'Old robots bumped into things. {FILLER}.', 'banner': None, 'factRefs': ['f2']},
        {'id': 'l4', 'beat': 'insight', 'vo': f'It feels for missing floor. {FILLER}.', 'banner': 'Feel, not see', 'factRefs': ['f3']},
        {'id': 'l5', 'beat': 'mechanism', 'vo': f'Sensors underneath look down. {FILLER}. {FILLER}.', 'banner': None, 'factRefs': ['f4']},
        {'id': 'l6', 'beat': 'product', 'vo': f'iRobot lists the patent for its Roomba lines. {FILLER}.', 'banner': None, 'factRefs': ['f5']},
        {'id': 'l7', 'beat': 'loop', 'vo': 'So next time it stops at the edge, it is feeling for the floor.', 'banner': None, 'noClaim': True, 'factRefs': []},
    ],
    'caption': {'hook': 'Your Roomba cannot see the stairs.', 'payoff': 'It feels for missing floor.', 'question': 'Which gadget next?'},
}


class LedgerTests(unittest.TestCase):
    def test_valid_ledger(self):
        errors, warnings, ids = ce.check_ledger(LEDGER, FORMATS)
        self.assertEqual(errors, [])
        self.assertIn('c1', ids)

    def test_status_word_needs_dated_check(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['status']['statement'] = 'expired 2023-05-23'
        errors, _, _ = ce.check_ledger(ledger, FORMATS)
        self.assertTrue(any('checkedAt' in e for e in errors))
        ledger['status'].update(checkedAt='2026-10-14', checkUrl='https://fees.uspto.gov/MaintenanceFees')
        self.assertEqual(ce.check_ledger(ledger, FORMATS)[0], [])

    def test_level_three_needs_evidence(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['productLink']['evidence'] = []
        self.assertTrue(any('level 3+' in e for e in ce.check_ledger(ledger, FORMATS)[0]))

    def test_copyright_notice_blocks_figures(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['copyrightNotice']['present'] = True
        self.assertTrue(any('no figures' in e for e in ce.check_ledger(ledger, FORMATS)[0]))

    def test_licensed_image_needs_licence_and_author(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['visuals'].append({'id': 'v2', 'kind': 'licensed-image', 'description': 'photo', 'source': 'https://commons.wikimedia.org/x'})
        self.assertTrue(any('licensed image' in e for e in ce.check_ledger(ledger, FORMATS)[0]))

    def test_image_licences(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['visuals'].append({'id': 'v2', 'kind': 'licensed-image', 'description': 'p', 'source': 'https://x', 'licence': 'CC BY-SA 4.0', 'author': 'A'})
        ledger['visuals'].append({'id': 'v3', 'kind': 'licensed-image', 'description': 'p', 'source': 'https://y', 'licence': 'CC BY-NC-SA 3.0', 'author': 'B'})
        errors, warnings, _ = ce.check_ledger(ledger, FORMATS)
        self.assertTrue(any('visuals[2]' in e and 'NonCommercial' in e for e in errors))
        self.assertTrue(any('ShareAlike' in w and 'visuals[1]' in w for w in warnings))

    def test_duplicate_ids(self):
        ledger = copy.deepcopy(LEDGER)
        ledger['facts'][0]['id'] = 'c1'
        self.assertTrue(any('duplicate id' in e for e in ce.check_ledger(ledger, FORMATS)[0]))


class ScriptTests(unittest.TestCase):
    def run_script(self, script, ledger=LEDGER):
        _, _, ids = ce.check_ledger(ledger, FORMATS)
        return ce.check_script(script, ledger, ids, FORMATS)

    def test_valid_script(self):
        errors, warnings, stats = self.run_script(SCRIPT)
        self.assertEqual(errors, [])
        self.assertTrue(110 <= stats['words'] <= 180)

    def test_unsourced_line(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][1]['factRefs'] = []
        self.assertTrue(any('no factRefs' in e for e in self.run_script(script)[0]))

    def test_unknown_ref(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][1]['factRefs'] = ['f99']
        self.assertTrue(any('not in the ledger' in e for e in self.run_script(script)[0]))

    def test_spine_order_and_missing_beats(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][2], script['lines'][3] = script['lines'][3], script['lines'][2]
        self.assertTrue(any('out of spine order' in e for e in self.run_script(script)[0]))
        script = copy.deepcopy(SCRIPT)
        del script['lines'][5]
        self.assertTrue(any('missing beats product' in e for e in self.run_script(script)[0]))

    def test_optional_beat_may_be_skipped(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][2]['beat'] = 'problem'  # no old-way line: optional in how-it-works
        self.assertFalse(any('missing beats' in e for e in self.run_script(script)[0]))

    def test_hook_length_and_banner(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][0]['vo'] = ' '.join(['word'] * 20)
        script['lines'][0]['banner'] = 'one two three four five six'
        errors = self.run_script(script)[0]
        self.assertTrue(any('the hook is 20 words' in e for e in errors))
        self.assertTrue(any('banner' in e for e in errors))

    def test_status_claim_without_check(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][5]['vo'] += ' The patent has expired.'
        self.assertTrue(any('dated USPTO check' in e for e in self.run_script(script)[0]))

    def test_ladder_and_risky_words_warn(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][5]['vo'] = f'This is how your Roomba works, and iRobot invented it. {FILLER}.'
        warnings = self.run_script(script)[1]
        self.assertTrue(any('claims product use' in w for w in warnings))
        self.assertTrue(any('invented' in w for w in warnings))

    def test_first_only_flags_superlatives(self):
        script = copy.deepcopy(SCRIPT)
        script['lines'][4]['vo'] += ' Back in the first patent, it was the first robot to do it.'
        warnings = [w for w in self.run_script(script)[1] if 'needs a source' in w]
        self.assertEqual(len(warnings), 1)
        self.assertIn('was the first', warnings[0])

    def test_word_budget(self):
        script = copy.deepcopy(SCRIPT)
        for line in script['lines'][1:6]:
            line['vo'] = 'Sensors look down.'
        self.assertTrue(any('spoken words' in e for e in self.run_script(script)[0]))

    def test_check_dir(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'ledger.json').write_text(json.dumps(LEDGER))
            Path(d, 'script.json').write_text(json.dumps(SCRIPT))
            result = ce.check_dir(d, FORMATS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual(ce.main([d]), 0)


if __name__ == '__main__':
    unittest.main()
