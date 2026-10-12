import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'contract'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import library_contract as lc
from contract_fixtures import (TMDB, WIKI, WORLD_BANK, FakeProbe, credit, document, document_v2, episode,
                               originals_v2, scalargame_v2, write_batch)

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)
FINALIZED = ('2026-10-pilots', '2026-10-b01')


def paths(report):
    return [e['path'] for e in report.errors]


def codes(report):
    return {e['code'] for e in report.errors}


def check(data, origin='mac'):
    return lc.validate_document(data, now=NOW, origin=origin)


class RegistryTests(unittest.TestCase):
    def test_projects_and_namespaces(self):
        self.assertEqual(lc.project_names(), ('originals', 'scalargame'))
        owners = lc.namespace_owners()
        self.assertEqual(owners['originals'], 'originals')
        self.assertEqual({n for n, p in owners.items() if p == 'scalargame'}, set(lc.GAMES))

    def test_project_of_and_view(self):
        v1, v2, orig = episode(1), scalargame_v2(1), originals_v2(1)
        self.assertEqual([lc.project_of(e) for e in (v1, v2, orig)], ['scalargame', 'scalargame', 'originals'])
        self.assertEqual(lc.content_id(v1), lc.content_id(v2))  # v1 and v2 share the duplicate key
        view = lc.episode_view(v1)
        self.assertEqual((view['project'], view['contentId'], view['engine'], view['renderer'], view['disclosure']),
                         ('scalargame', 'scalar:Q1:clues', 'motion', None, None))
        self.assertEqual(view['link']['url'], 'https://www.scalargame.com/scalar')
        view = lc.episode_view(orig)
        self.assertEqual((view['project'], view['group'], view['engine'], view['route']), ('originals', 'originals', 'story', 'recap'))

    def test_link_expansion_same_for_v1_and_v2(self):
        self.assertEqual(lc.expand(episode(1), 'x', 'Go {link}'), lc.expand(scalargame_v2(1), 'x', 'Go {link}'))


class FinalizedV1Tests(unittest.TestCase):
    """Both finalized 2026-10 batches stay valid on every run (document checks, at their finalize time)."""
    def test_finalized_documents_validate(self):
        for batch in FINALIZED:
            path = ROOT/'library'/batch/'batch.json'
            if not path.is_file():
                self.skipTest('library/ is not in this checkout (the Pi checks out publisher/ and contract/ only)')
            data = json.loads(path.read_text())
            now = dt.datetime.fromisoformat(data['createdAt'].replace('Z', '+00:00'))
            report = lc.validate_document(data, now=now)
            self.assertEqual(report.errors, [], batch)
            self.assertEqual([w['code'] for w in report.warnings], ['dirty_generator'], batch)

    def test_v1_fixture_unchanged(self):
        self.assertEqual(check(document([episode(1), episode(2, 'continuum')])).errors, [])


class V2DocumentTests(unittest.TestCase):
    def test_reference_documents_pass(self):
        self.assertEqual(check(document_v2([scalargame_v2(1), scalargame_v2(2, 'continuum')])).errors, [])
        self.assertEqual(check(document_v2([originals_v2(1), originals_v2(2, 'animated-short')], 'originals')).errors, [])

    def test_unknown_project_and_version(self):
        data = document_v2()
        data['project'] = 'nope'
        self.assertIn('project', codes(check(data)))
        data = document_v2()
        data['schemaVersion'] = 3
        self.assertFalse(check(data).ok)

    def test_one_project_per_batch(self):
        report = check(document_v2([scalargame_v2(1), originals_v2(1)]))
        self.assertIn('episodes[1].episodeId', paths(report))
        self.assertIn('namespace', codes(report))

    def test_colliding_namespace(self):
        e = originals_v2(1)
        e['contentId'] = 'scalar:Q1:clues'
        report = check(document_v2([e], 'originals'))
        self.assertIn('namespace', codes(report))
        self.assertTrue(any('belongs to scalargame' in x['message'] for x in report.errors))
        e = scalargame_v2(1)
        e['contentId'] = 'continuum:Q1'
        self.assertIn('namespace', codes(check(document_v2([e]))))

    def test_missing_attribution_on_a_posting_platform(self):
        e = originals_v2(1)
        e['publication']['captions']['x'] = 'A film in 60 seconds.'
        report = check(document_v2([e], 'originals'))
        self.assertIn('episodes[0].publication.captions.x', paths(report))
        self.assertIn('attribution', codes(report))
        e = originals_v2(1)
        e['publication']['youtube']['description'] = f'{WIKI}.'
        report = check(document_v2([e], 'originals'))
        self.assertIn('episodes[0].publication.youtube.description', paths(report))
        self.assertTrue(any(TMDB in x['message'] for x in report.errors))

    def test_attribution_in_first_comment_and_skipped_platforms(self):
        e = originals_v2(1)
        e['publication']['captions']['instagram'] = 'A film in 60 seconds.'
        e['publication']['firstComment'] = {'instagram': f'{TMDB}. {WIKI}.'}
        e['publication']['captions']['tiktok'] = None  # a platform that does not post needs nothing
        self.assertEqual(check(document_v2([e], 'originals')).errors, [])

    def test_continuum_needs_world_bank_attribution(self):
        e = scalargame_v2(1, 'continuum')
        e['publication']['captions']['bluesky'] = e['publication']['captions']['bluesky'].replace(WORLD_BANK, '')
        self.assertIn('episodes[0].publication.captions.bluesky', paths(check(document_v2([e]))))

    def test_licences(self):
        e = originals_v2(1)
        e['credits'][0]['license'] = 'unknown'
        self.assertIn('license', codes(check(document_v2([e], 'originals'))))
        e = originals_v2(1)
        e['credits'][1]['attribution'] = 'TMDB'
        self.assertIn('episodes[0].credits[1].attribution', paths(check(document_v2([e], 'originals'))))
        e = scalargame_v2(1)
        e['credits'].append(credit('data', 'Figures', 'CC-BY-4.0'))
        self.assertIn('episodes[0].credits[2].attribution', paths(check(document_v2([e]))))

    def test_disclosure(self):
        e = originals_v2(1)
        e['disclosure'].update(aiGenerated=False, aiKinds=[])
        report = check(document_v2([e], 'originals'))
        self.assertIn('disclosure', codes(report))
        e = originals_v2(1)
        e['disclosure']['aiKinds'] = []
        self.assertIn('episodes[0].disclosure.aiGenerated', paths(check(document_v2([e], 'originals'))))
        e = scalargame_v2(1)
        e['disclosure']['realisticSynthetic'] = None
        self.assertIn('episodes[0].disclosure.realisticSynthetic', paths(check(document_v2([e]))))

    def test_link_rules(self):
        e = scalargame_v2(1)
        e['link'] = None
        report = check(document_v2([e]))
        self.assertIn('episodes[0].link', paths(report))
        self.assertIn('episodes[0].publication.captions.x', paths(report))  # {link} without a link
        e = scalargame_v2(1)
        e['link']['url'] = 'https://evil.example/scalar'
        self.assertIn('episodes[0].link.url', paths(check(document_v2([e]))))
        e = scalargame_v2(1)
        e['link']['url'] = 'https://www.scalargame.com/scalar?x=1'
        self.assertIn('episodes[0].link.url', paths(check(document_v2([e]))))
        e = originals_v2(1)
        e['publication']['captions']['facebook'] += ' {link}'
        self.assertIn('episodes[0].publication.captions.facebook', paths(check(document_v2([e], 'originals'))))
        e = originals_v2(1)
        e['link'] = {'url': 'https://studiozero.example/watch', 'utmCampaign': 'originals_v1'}
        e['publication']['captions']['facebook'] += ' {link}'
        e['publication']['captions']['instagram'] += ' {link}'  # no clickable links on Instagram
        report = check(document_v2([e], 'originals'))
        self.assertEqual(paths(report), ['episodes[0].publication.captions.instagram'])

    def test_render_block(self):
        e = originals_v2(1)
        e['render'].update(engine='motion', renderer='blender', renderSha256='x', costUsd=-1)
        e['render']['models'].append({'role': 'painter', 'id': 'x'})
        report = check(document_v2([e], 'originals'))
        for key in ('engine', 'renderer', 'renderSha256', 'costUsd', 'models[2]'):
            self.assertTrue(any(p.startswith(f'episodes[0].render.{key}') for p in paths(report)), key)
        e = originals_v2(2, 'animated-short')
        e['render']['route'] = 'recap'
        self.assertIn('episodes[0].render.engine', paths(check(document_v2([e], 'originals'))))

    def test_project_rules(self):
        e = originals_v2(1)
        e['publication']['poll'] = {'question': 'Seen it?', 'options': ['Yes', 'No']}
        e['projectData']['checks']['garbage'] = False
        e['credits'] = [c for c in e['credits'] if c['kind'] != 'footage']
        report = check(document_v2([e], 'originals'))
        for path in ('episodes[0].publication.poll', 'episodes[0].projectData.checks.garbage', 'episodes[0].credits'):
            self.assertIn(path, paths(report))
        e = originals_v2(2, 'animated-short')
        e['projectData']['series'] = None
        self.assertIn('episodes[0].projectData.series', paths(check(document_v2([e], 'originals'))))
        data = document_v2([originals_v2(1)], 'originals')
        data['projectData'] = {'x': 1}
        self.assertIn('batch.projectData', paths(check(data)))
        data = document_v2()
        data['projectData'] = {}
        self.assertIn('batch.projectData.sourceSnapshotHash', paths(check(data)))

    def test_scalargame_spoilers_and_style(self):
        e = scalargame_v2(1)
        e['publication']['captions']['threads'] = 'It is Bolivia! {link}'
        data = document_v2([e])
        e['projectData']['styleId'] = 'nope'
        report = check(data)
        self.assertIn('spoiler', codes(report))
        self.assertIn('episodes[0].projectData.styleId', paths(report))
        e = scalargame_v2(1)
        e['projectData']['game'] = 'continuum'
        self.assertIn('episodes[0].episodeId', paths(check(document_v2([e]))))

    def test_mac_never_sends_approved_and_pi_ids(self):
        data = document_v2()
        data['episodes'][0]['eligibility']['status'] = 'approved'
        self.assertIn('episodes[0].eligibility.status', paths(check(data)))
        data = document_v2(batch_id='manual-20261007-1')
        self.assertIn('batch.batchId', paths(check(data)))
        self.assertNotIn('batch.batchId', paths(check(data, 'pi')))

    def test_unknown_fields_and_v1_fields_refused(self):
        data = document_v2()
        data['sourceSnapshotHash'] = 'a' * 64
        data['episodes'][0]['questionId'] = 'scalar:Q1:clues'
        report = check(data)
        self.assertIn('batch.sourceSnapshotHash', paths(report))
        self.assertIn('episodes[0].questionId', paths(report))


class V2FolderTests(unittest.TestCase):
    def test_folder_validate_and_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, _, _ = write_batch(tmp, document_v2([originals_v2(1)], 'originals'))
            probe = FakeProbe()
            report = lc.finalize(folder, now=NOW, probe=probe)
            self.assertEqual(report.errors, [])
            self.assertEqual(json.loads((folder/lc.MARKER).read_text())['schemaVersion'], 2)
            data = json.loads((folder/'batch.json').read_text())
            data['episodes'][0]['publication']['altText'] = 'Changed.'
            (folder/'batch.json').write_text(json.dumps(data))
            self.assertIn('immutable', codes(lc.validate(folder, now=NOW, probe=probe)))


if __name__ == '__main__':
    unittest.main()
