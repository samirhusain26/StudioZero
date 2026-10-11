import copy
import datetime as dt
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'contract'))
sys.path.insert(0, str(ROOT/'contract/tests'))
import library_contract as lc
from contract_fixtures import FakeProbe, document, episode, mp4_bytes, probe_json, write_batch

NOW = dt.datetime(2026, 10, 7, 12, tzinfo=dt.timezone.utc)


def codes(report):
    return {e['code'] for e in report.errors}


def paths(report):
    return [e['path'] for e in report.errors]


class DocumentTests(unittest.TestCase):
    def check(self, data, origin='mac'):
        return lc.validate_document(data, now=NOW, origin=origin)

    def test_reference_document_passes(self):
        report = self.check(document([episode(1), episode(2, 'continuum')]))
        self.assertEqual(report.errors, [])

    def test_ids_and_enums(self):
        data = document()
        data['batchId'] = '2026-13-Bad'
        e = data['episodes'][0]
        e['episodeId'] = 'continuum-clues-001'
        e['format'] = 'quiz'
        e['difficulty'] = 'hard'
        e['questionId'] = 'scalar:has space'
        report = self.check(data)
        for path in ('batch.batchId', 'episodes[0].episodeId', 'episodes[0].format',
                     'episodes[0].difficulty', 'episodes[0].questionId'):
            self.assertIn(path, paths(report))

    def test_pi_batch_ids_only_for_pi(self):
        data = document(batch_id='manual-20261007-1')
        self.assertIn('batch.batchId', paths(self.check(data)))
        self.assertNotIn('batch.batchId', paths(self.check(data, 'pi')))

    def test_unknown_and_missing_fields(self):
        data = document()
        data['episodes'][0]['extra'] = 1
        del data['episodes'][0]['music']
        report = self.check(data)
        self.assertIn('episodes[0].extra', paths(report))
        self.assertIn('episodes[0].music', paths(report))

    def test_duplicate_episode(self):
        report = self.check(document([episode(1), episode(1)]))
        self.assertIn('episodes[1].episodeId', paths(report))

    def test_file_paths_fixed_no_traversal(self):
        data = document()
        data['episodes'][0]['video']['file'] = 'videos/../../etc/passwd'
        data['episodes'][0]['cover']['file'] = '/abs/cover.jpg'
        report = self.check(data)
        self.assertIn('episodes[0].video.file', paths(report))
        self.assertIn('episodes[0].cover.file', paths(report))

    def test_media_declarations(self):
        data = document()
        v = data['episodes'][0]['video']
        v.update(width=1080, height=1080, videoCodec='hevc', audioCodec='opus', bytes=25_000_000)
        report = self.check(data)
        for key in ('width', 'videoCodec', 'audioCodec', 'bytes'):
            self.assertIn(f'episodes[0].video.{key}', paths(report))

    def test_mac_never_sends_approved(self):
        data = document()
        data['episodes'][0]['eligibility']['status'] = 'approved'
        self.assertIn('episodes[0].eligibility.status', paths(self.check(data)))

    def test_past_review_and_expiry(self):
        data = document()
        data['episodes'][0]['eligibility'].update(reviewBy='2026-10-06', expiresAt='2026-01-01')
        report = self.check(data)
        self.assertIn('expired', codes(report))
        self.assertEqual(sum(e['code'] == 'expired' for e in report.errors), 2)

    def test_dirty_generator_is_warning(self):
        data = document()
        data['generator']['dirty'] = True
        report = self.check(data)
        self.assertTrue(report.ok)
        self.assertEqual(report.warnings[0]['code'], 'dirty_generator')


class SpoilerTests(unittest.TestCase):
    def check(self, mutate):
        data = document()
        mutate(data['episodes'][0])
        return lc.validate_document(data, now=NOW)

    def test_choice_list_is_not_a_spoiler(self):
        self.assertTrue(self.check(lambda e: None).ok)

    def test_answer_in_caption_is_spoiler(self):
        report = self.check(lambda e: e['publication']['captions'].update(threads='It is Bolivia! {link}'))
        self.assertIn('episodes[0].publication.captions.threads', paths(report))
        self.assertIn('spoiler', codes(report))

    def test_accent_and_case_insensitive_alias(self):
        def mutate(e):
            e['creative']['answer'] = 'Côte d’Ivoire'
            e['creative']['answerAliases'] = ['CIV']
            e['creative']['choices'] = [{'key': 'A', 'label': 'Côte d’Ivoire'}, {'key': 'B', 'label': 'Ghana'}]
            e['publication']['poll'] = None
            e['publication']['firstComment'] = None
            for p in e['publication']['captions']:
                e['publication']['captions'][p] = 'Guess the country.'
            e['publication']['altText'] = 'Map hints. answer: cote d ivoire'
            e['publication']['youtube']['title'] = 'Is it civ? #shorts'
        report = self.check(mutate)
        self.assertIn('episodes[0].publication.altText', paths(report))
        self.assertIn('episodes[0].publication.youtube.title', paths(report))

    def test_answer_twice_even_with_choices(self):
        report = self.check(lambda e: e['publication']['captions'].update(
            instagram='A) Bolivia B) Paraguay C) Austria. Hint: Bolivia is landlocked'))
        self.assertIn('episodes[0].publication.captions.instagram', paths(report))

    def test_poll_question_and_cover_name(self):
        def mutate(e):
            e['publication']['poll']['question'] = 'Is it Bolivia?'
        report = self.check(mutate)
        self.assertIn('episodes[0].publication.poll.question', paths(report))
        data = document([episode(1, answer='Clues', choices=None)])
        report = lc.validate_document(data, now=NOW)
        self.assertIn('episodes[0].cover.file', paths(report))

    def test_distractor_containing_answer(self):
        def mutate(e):
            e['creative']['answer'] = 'Guinea'
            e['creative']['answerAliases'] = []
            e['creative']['choices'] = [{'key': 'A', 'label': 'Guinea'}, {'key': 'B', 'label': 'Guinea-Bissau'},
                                        {'key': 'C', 'label': 'Equatorial Guinea'}]
            e['publication']['poll']['options'] = ['Guinea', 'Guinea-Bissau', 'Equatorial Guinea']
            listing = 'A) Guinea B) Guinea-Bissau C) Equatorial Guinea'
            for p in e['publication']['captions']:
                e['publication']['captions'][p] = listing
            e['publication']['firstComment']['instagram'] = listing
        self.assertTrue(self.check(mutate).ok)

    def test_answer_reply_may_contain_answer(self):
        def mutate(e):
            e['publication']['answerReply'] = {'text': '.\n\nAnswer: Bolivia', 'delayHours': 6}
        self.assertTrue(self.check(mutate).ok)

    def test_answer_reply_needs_spacer(self):
        def mutate(e):
            e['publication']['answerReply'] = {'text': 'Answer: Bolivia', 'delayHours': 6}
        self.assertIn('episodes[0].publication.answerReply.text', paths(self.check(mutate)))

    def test_choices_and_poll_contain_answer_once(self):
        def mutate(e):
            e['creative']['choices'][0]['label'] = 'Peru'
            e['publication']['poll']['options'] = ['Peru', 'Chile']
        report = self.check(mutate)
        self.assertIn('episodes[0].creative.choices', paths(report))
        self.assertIn('episodes[0].publication.poll.options', paths(report))

    def test_poll_option_length(self):
        report = self.check(lambda e: e['publication']['poll'].update(options=['Bolivia', 'x' * 26]))
        self.assertIn('episodes[0].publication.poll.options', paths(report))


class CaptionTests(unittest.TestCase):
    def check(self, mutate):
        data = document()
        mutate(data['episodes'][0])
        return lc.validate_document(data, now=NOW)

    def test_link_only_where_clickable(self):
        report = self.check(lambda e: e['publication']['captions'].update(instagram='Play {link}', tiktok='Play {link}'))
        self.assertEqual(sum(e['code'] == 'link' for e in report.errors), 2)
        report = self.check(lambda e: e['publication']['youtube'].update(description='{link}'))
        self.assertIn('episodes[0].publication.youtube.description', paths(report))

    def test_unknown_placeholder(self):
        report = self.check(lambda e: e['publication']['captions'].update(x='Hi {name}'))
        self.assertIn('episodes[0].publication.captions.x', paths(report))

    def test_lengths_after_link_expansion(self):
        report = self.check(lambda e: e['publication']['captions'].update(bluesky='a' * 250 + ' {link}'))
        self.assertIn('length', codes(report))
        # X counts any URL as 23 characters.
        self.assertTrue(self.check(lambda e: e['publication']['captions'].update(x='a' * 250 + ' {link}')).ok)
        report = self.check(lambda e: e['publication']['captions'].update(x='a' * 260 + ' {link}'))
        self.assertIn('episodes[0].publication.captions.x', paths(report))
        report = self.check(lambda e: e['publication']['youtube'].update(title='t' * 101))
        self.assertIn('episodes[0].publication.youtube.title', paths(report))

    def test_comment_routes(self):
        report = self.check(lambda e: e['publication']['firstComment'].update(facebook='A) B) C)'))
        self.assertIn('route', codes(report))

    def test_no_captions_at_all(self):
        def mutate(e):
            e['publication']['captions'] = {p: None for p in lc.CAPTION_PLATFORMS}
            e['publication']['youtube'] = None
        self.assertIn('episodes[0].publication.captions', paths(self.check(mutate)))

    def test_expand_link(self):
        e = episode(1)
        self.assertEqual(lc.expand(e, 'x', 'Go {link}'),
                         'Go https://www.scalargame.com/scalar?utm_source=x&utm_medium=organic_social'
                         '&utm_campaign=social_library_v1&utm_content=scalar-clues-001')

    def test_hashes_ignore_eligibility(self):
        e = episode(1)
        before = lc.episode_metadata_hash(e)
        e['eligibility']['status'] = 'approved'
        self.assertEqual(before, lc.episode_metadata_hash(e))
        e['publication']['captions']['x'] = 'changed'
        self.assertNotEqual(before, lc.episode_metadata_hash(e))


class MediaTests(unittest.TestCase):
    def test_faststart_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp, 'a.mp4'), Path(tmp, 'b.mp4')
            good.write_bytes(mp4_bytes(faststart=True))
            bad.write_bytes(mp4_bytes(faststart=False))
            self.assertTrue(lc.mp4_faststart(good))
            self.assertFalse(lc.mp4_faststart(bad))

    def test_hard_rules(self):
        base = lc.measure(probe_json())
        base.update(bytes=1000, fastStart=True)
        self.assertEqual(lc.media_errors(base), [])
        for probe, text in ((probe_json(vcodec='hevc'), 'H.264'), (probe_json(pix='yuv444p'), 'yuv420p'),
                            (probe_json(width=1080, height=1350), '9:16'), (probe_json(rate='44100'), 'AAC'),
                            (probe_json(channels=1), 'AAC')):
            m = lc.measure(probe)
            m.update(bytes=1000, fastStart=True)
            self.assertTrue(any(text in e for e in lc.media_errors(m)), text)
        silent = lc.measure(probe_json(audio=False))
        silent.update(bytes=1000, fastStart=True)
        self.assertEqual(lc.media_errors(silent), [])
        silent['bytes'] = 24_000_001
        self.assertTrue(lc.media_errors(silent))
        # Full-range output from the published 2026-10-05 renders is tolerated only as legacy.
        full = lc.measure(probe_json(pix='yuvj420p'))
        full.update(bytes=1000, fastStart=True)
        self.assertTrue(lc.media_errors(full))
        self.assertEqual(lc.media_errors(full, legacy=True), [])

    def test_platform_eligibility(self):
        m = lc.measure(probe_json(duration=120))
        m.update(bytes=1000, fastStart=True)
        result = lc.platform_eligibility(m)
        self.assertFalse(result['facebook'][0])
        self.assertFalse(result['bluesky'][0])
        self.assertTrue(result['instagram'][0])
        self.assertTrue(result['threads'][0])
        m = lc.measure(probe_json(fps='20/1'))
        m.update(bytes=1000, fastStart=True)
        self.assertFalse(lc.platform_eligibility(m)['instagram'][0])
        self.assertTrue(lc.platform_eligibility(m)['x'][0])
        broken = lc.measure(probe_json(vcodec='vp9'))
        broken.update(bytes=1000, fastStart=True)
        self.assertFalse(any(ok for ok, _ in lc.platform_eligibility(broken).values()))


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_folder_and_finalize(self):
        folder, data, _ = write_batch(self.root, document([episode(1), episode(2)]))
        probe = FakeProbe()
        report = lc.validate(folder, now=NOW, probe=probe)
        self.assertEqual(report.errors, [])
        self.assertEqual(probe.calls, 2)
        report = lc.finalize(folder, now=NOW, probe=probe)
        self.assertTrue(report.ok)
        marker = json.loads((folder/lc.MARKER).read_text())
        self.assertEqual(marker['finalizedAt'], '2026-10-07T12:00:00Z')
        # Re-finalizing an unchanged batch is a no-op; a changed batch.json is refused.
        self.assertTrue(lc.finalize(folder, now=NOW, probe=probe).ok)
        data['episodes'][0]['publication']['captions']['x'] = 'Changed {link}'
        (folder/'batch.json').write_text(json.dumps(data))
        report = lc.finalize(folder, now=NOW, probe=probe)
        self.assertIn('immutable', codes(report))

    def test_hash_size_and_measurement_mismatch(self):
        folder, data, blobs = write_batch(self.root)
        (folder/'covers/scalar-clues-001.jpg').write_bytes(b'\xff\xd8\xff' + b'1' * 10)
        digest = data['episodes'][0]['video']['sha256']
        probe = FakeProbe({digest: probe_json(duration=29.0)})
        report = lc.validate(folder, now=NOW, probe=probe)
        self.assertIn('hash', codes(report))
        self.assertIn('episodes[0].video.durationSeconds', paths(report))

    def test_missing_file_and_not_faststart(self):
        folder, _, _ = write_batch(self.root, faststart=False)
        (folder/'covers/scalar-clues-001.jpg').unlink()
        report = lc.validate(folder, now=NOW, probe=FakeProbe())
        self.assertIn('missing', codes(report))
        self.assertTrue(any('fast-start' in e['message'] for e in report.errors))

    def test_symlink_refused(self):
        folder, _, blobs = write_batch(self.root)
        target = folder/'covers/scalar-clues-001.jpg'
        real = self.root/'real.jpg'
        real.write_bytes(blobs['covers/scalar-clues-001.jpg'])
        target.unlink()
        target.symlink_to(real)
        report = lc.validate(folder, now=NOW, probe=FakeProbe())
        self.assertIn('episodes[0].cover.file', paths(report))

    def test_folder_must_match_batch_id(self):
        folder, _, _ = write_batch(self.root)
        moved = self.root/'2026-10-other'
        shutil.move(folder, moved)
        self.assertIn('batch.batchId', paths(lc.validate(moved, now=NOW, probe=FakeProbe())))

    def test_unreferenced_files_warn(self):
        folder, _, _ = write_batch(self.root)
        (folder/'videos/extra.mp4').write_bytes(b'x')
        report = lc.validate(folder, now=NOW, probe=FakeProbe())
        self.assertTrue(report.ok)
        self.assertEqual(report.warnings[0]['code'], 'unreferenced')

    def test_cli_exit_codes(self):
        folder, _, _ = write_batch(self.root)
        original = lc.run_ffprobe
        lc.run_ffprobe = FakeProbe()
        try:
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(lc.main(['validate', str(folder), '--json']), 2)  # default probe bound at def time
        finally:
            lc.run_ffprobe = original
        self.assertFalse(json.loads(out.getvalue())['ok'])

    def test_invalid_json(self):
        folder = self.root/'2026-10-bad'
        folder.mkdir()
        (folder/'batch.json').write_text('{')
        self.assertFalse(lc.validate(folder, now=NOW).ok)


@unittest.skipUnless(shutil.which('ffprobe') or Path('/usr/bin/ffprobe').exists() or (ROOT/'engines/motion/node_modules/.bin/remotion').exists(), 'no ffprobe')
class RealProbeTests(unittest.TestCase):
    def test_measures_existing_social_clip(self):
        clips = sorted((ROOT/'engines/motion/out/social-site/clips').glob('*-self-*.mp4'))
        if not clips:
            self.skipTest('no rendered clip')
        try:
            m = lc.measure(lc.run_ffprobe(clips[0]), clips[0])
        except (RuntimeError, ValueError) as error:
            self.skipTest(str(error))
        self.assertEqual((m['videoCodec'], m['width'], m['height']), ('h264', 1080, 1920))
        self.assertIn('fastStart', m)


if __name__ == '__main__':
    unittest.main()
