"""Offline regressions for legacy captions crossing the library/scheduler boundary."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'publisher/app'))
from test_ui_schedule import config, inputs, record
from test_contract_v2_pi import v2_record
from contract_fixtures import originals_v2, scalargame_v2
from bluesky_adapter import link_facets
import library_contract as lc
import ui_library as ul
import ui_schedule as us


class BlueskyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.video = record()
        self.config = config()
        self.inputs = inputs(platforms=('bluesky',))

    def draft(self, text=None, *, edits=None, base=None):
        if text is not None:
            self.video['episode']['publication']['captions']['bluesky'] = text
        settings = {**self.inputs, 'edits': edits or {}}
        return us.generate(settings, [self.video], {}, self.config, base)

    def payload(self, job):
        return us.manifest_payload(job, self.video, self.config, 'd' * 64)

    def test_legacy_literal_urls_survive_to_clickable_manifest_unchanged(self):
        bank = json.loads((ROOT / 'publisher/tests/fixtures/social-bank.json').read_text())
        for source in bank['episodes']:
            with self.subTest(episode=source['id']):
                ep = ul.legacy_episode(source, 'a' * 64, {}, 1000, 'b' * 64, 100)
                self.video = record()
                self.video.update(episode=ep, episodeId=ep['episodeId'])
                text = ep['publication']['captions']['bluesky']
                draft = self.draft()
                self.assertEqual(draft['blocking'], [])
                payload = self.payload(draft['jobs'][0])
                self.assertEqual(payload['caption'], text)
                self.assertIsNotNone(payload['link'])
                self.assertTrue(payload['link'].endswith(source['id'] + '_self-contained'))
                facet = link_facets(text, payload['link'])[0]
                index = facet['index']
                self.assertEqual(text.encode()[index['byteStart']:index['byteEnd']].decode(), payload['link'])

    def test_literal_link_and_placeholder_produce_the_same_payload(self):
        template = 'Try this puzzle. {link}'
        placeholder = self.payload(self.draft(template)['jobs'][0])
        literal = self.payload(self.draft(lc.expand(self.video['episode'], 'bluesky', template))['jobs'][0])
        self.assertEqual(literal, placeholder)

    def test_sentence_punctuation_does_not_change_the_link(self):
        for platform in lc.LINK_PLATFORMS:
            for template in ('Try this: {link}.', 'Try this ({link}).'):
                with self.subTest(platform=platform, text=template):
                    self.inputs = inputs(platforms=(platform,))
                    self.video['episode']['publication']['captions'][platform] = template
                    draft = self.draft()
                    self.assertEqual(draft['blocking'], [])
                    payload = self.payload(draft['jobs'][0])
                    link = lc.link_for(self.video['episode'], platform)
                    self.assertEqual(payload['caption'], lc.expand(self.video['episode'], platform, template))
                    self.assertEqual(payload['link'], link)
                    link_facets(payload['caption'], link)

    def test_invalid_links_block_without_rewriting_caption(self):
        link = lc.link_for(self.video['episode'], 'bluesky')
        for text in ('No link.', 'Try ' + link[:-5], 'Try ' + link.replace('/scalar?', '/tectonic?'),
                     'Try https://www.google.com/url?q=' + link, link + '\n' + link):
            with self.subTest(text=text):
                draft = self.draft(text)
                job = draft['jobs'][0]
                self.assertTrue(draft['blocking'])
                self.assertEqual(job['text'], text)
                with self.assertRaises(ValueError):
                    self.payload(job)

    def test_full_url_and_unicode_are_counted_before_scheduling(self):
        link = lc.link_for(self.video['episode'], 'bluesky')
        good = 'é' * (299 - len(link)) + '\n' + link
        draft = self.draft(good)
        self.assertEqual(draft['blocking'], [])
        payload = self.payload(draft['jobs'][0])
        facet = link_facets(good, payload['link'])[0]
        self.assertEqual(facet['index']['byteStart'], len(good[:-len(link)].encode()))
        for text in ('é' + good, 'x' * 300 + '\n{link}'):
            with self.subTest(length=len(text)):
                draft = self.draft(text)
                self.assertTrue(any('300' in error for error in draft['blocking']))
                self.assertEqual(draft['jobs'][0]['text'], lc.expand(self.video['episode'], 'bluesky', text))
                with self.assertRaises(ValueError):
                    self.payload(draft['jobs'][0])

    def test_edit_cannot_remove_link_and_literal_edit_can_repair_it(self):
        first = self.draft()
        key = first['jobs'][0]['key']
        bad = self.draft(edits={key: {'text': 'Try the puzzle.'}})
        self.assertTrue(bad['blocking'])
        with self.assertRaises(ValueError):
            self.payload(bad['jobs'][0])
        link = lc.link_for(self.video['episode'], 'bluesky')
        good = self.draft(edits={key: {'text': 'Try the puzzle. ' + link}})
        self.assertEqual(good['blocking'], [])
        self.assertEqual(self.payload(good['jobs'][0])['link'], link)

    def test_unchanged_approved_payload_is_carried_verbatim(self):
        first = self.draft()
        job = first['jobs'][0]
        original = self.payload(job)
        # Historical approved payload with the missing metadata: never silently repair it.
        original['link'] = None
        manifest = {'jobs': [{'key': job['key'], 'platform': 'bluesky', 'slot': job['slotUtc'],
                              'payload': original}]}
        before = copy.deepcopy(manifest)
        self.inputs['carryOnly'] = True
        carried = self.draft(base=manifest)['jobs'][0]
        self.assertEqual(self.payload(carried), original)
        self.assertEqual(manifest, before)
        edited = self.draft(base=manifest, edits={job['key']: {'text': original['caption']}})
        self.assertEqual(edited['blocking'], [])
        self.assertIsNotNone(self.payload(edited['jobs'][0])['link'])

    def test_v2_scalar_links_and_optional_originals_links_keep_their_contract(self):
        for source in (scalargame_v2(1), originals_v2(1)):
            with self.subTest(episode=source['episodeId']):
                self.video = v2_record(source)
                draft = self.draft()
                self.assertEqual(draft['blocking'], [])
                payload = self.payload(draft['jobs'][0])
                expected = lc.link_for(source, 'bluesky') if source['link'] else None
                self.assertEqual(payload['link'], expected)


if __name__ == '__main__':
    unittest.main()
