"""
Review B6 ($0, fakes only): a retry must never re-submit a paid generation once the
submit succeeded, and fallback must re-check the budget before switching model.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import smoke_support as sx  # noqa: F401  (must come before any src import)

from tenacity import wait_none

import src.video_client as video_client
from src.video_client import UnifiedVideoClient, VideoGenerationError


class FakeFal:
    """Counts calls to each fal.ai phase; each phase can fail with a list of exceptions first."""

    def __init__(self, submit_errors=(), wait_errors=(), download_errors=()):
        self.errors = {"submit": list(submit_errors), "wait": list(wait_errors), "download": list(download_errors)}
        self.calls = {"submit": 0, "wait": 0, "download": 0}

    def _step(self, phase):
        self.calls[phase] += 1
        if self.errors[phase]:
            raise self.errors[phase].pop(0)

    def install(self, test, client):
        def submit(_endpoint, _arguments):
            self._step("submit")
            return "req-1"

        def wait(_endpoint, _request_id):
            self._step("wait")
            return {"video": {"url": "https://fal.invalid/out.mp4"}}

        def download(_url, output_path):
            self._step("download")
            Path(output_path).write_bytes(b"fake mp4")

        for name, fn in (("_fal_submit", submit), ("_fal_wait", wait), ("_fal_download", download),
                         ("_fal_upload", lambda path: "https://fal.invalid/up.png")):
            patcher = mock.patch.object(client, name, fn)
            patcher.start()
            test.addCleanup(patcher.stop)


class VideoClientRetryTest(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(sx.NETWORK_ATTEMPTS, [])

    def setUp(self):
        patcher = mock.patch.object(video_client, "_RETRY_WAIT", wait_none())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="vc-"))
        self.client = UnifiedVideoClient("wan-2.5")
        self.events = []
        self.client.on_attempt = lambda event, attempt: self.events.append((event, attempt["model_id"]))

    def _generate(self):
        return self.client.generate_video(prompt="p", output_dir=self.out, filename="c.mp4", duration=5)

    def test_submit_that_never_started_is_retried(self):
        fake = FakeFal(submit_errors=[ConnectionRefusedError("refused"), ConnectionRefusedError("refused")])
        fake.install(self, self.client)
        self.assertIsNotNone(self._generate())
        self.assertEqual(fake.calls, {"submit": 3, "wait": 1, "download": 1})
        self.assertEqual(self.events, [("submitted", "wan-2.5"), ("succeeded", "wan-2.5")])
        self.assertEqual(self.client.get_total_cost(), 0.25)  # billed once

    def test_submit_with_uncertain_outcome_is_not_retried(self):
        fake = FakeFal(submit_errors=[TimeoutError("read timeout after sending")])
        fake.install(self, self.client)
        self.assertIsNone(self._generate())
        self.assertEqual(fake.calls["submit"], 1)
        self.assertEqual(self.events, [("failed", "wan-2.5")])
        self.assertFalse(self.client.attempts[-1]["submitted"])

    def test_wait_errors_never_resubmit(self):
        fake = FakeFal(wait_errors=[ConnectionResetError("reset"), TimeoutError("slow")])
        fake.install(self, self.client)
        self.assertIsNotNone(self._generate())
        self.assertEqual(fake.calls, {"submit": 1, "wait": 3, "download": 1})

    def test_download_errors_are_retried_alone(self):
        fake = FakeFal(download_errors=[OSError("disk hiccup"), ConnectionResetError("reset")])
        fake.install(self, self.client)
        self.assertIsNotNone(self._generate())
        self.assertEqual(fake.calls, {"submit": 1, "wait": 1, "download": 3})
        self.assertEqual(self.client.get_total_cost(), 0.25)

    def test_billed_attempt_that_fails_still_counts(self):
        fake = FakeFal(download_errors=[OSError("x")] * 3)
        fake.install(self, self.client)
        self.assertIsNone(self._generate())
        self.assertEqual(fake.calls, {"submit": 1, "wait": 1, "download": 3})
        attempt = self.client.attempts[-1]
        self.assertTrue(attempt["submitted"])
        self.assertFalse(attempt["ok"])
        self.assertEqual(self.events, [("submitted", "wan-2.5"), ("failed", "wan-2.5")])
        self.assertEqual(self.client.get_total_cost(), 0.25)
        self.assertEqual(self.client.get_generation_count(), 0)

    def test_gemini_poll_errors_never_resubmit(self):
        client = UnifiedVideoClient("veo-3.1-lite")
        calls = {"generate_videos": 0, "get": 0}
        done = mock.Mock(done=True, error=None, response=mock.Mock(
            generated_videos=[mock.Mock(video=mock.Mock(video_bytes=b"fake mp4", uri=None))]))

        def generate_videos(**kwargs):
            calls["generate_videos"] += 1
            return mock.Mock(done=False)

        def get(operation):
            calls["get"] += 1
            if calls["get"] == 1:
                raise ConnectionResetError("reset while polling")
            return done

        client._gemini_client = mock.Mock()
        client._gemini_client.models.generate_videos = generate_videos
        client._gemini_client.operations.get = get
        with mock.patch.object(video_client.time, "sleep", lambda s: None):
            result = client.generate_video(prompt="p", output_dir=self.out, filename="g.mp4", duration=8)
        self.assertIsNotNone(result)
        self.assertEqual(calls, {"generate_videos": 1, "get": 2})
        self.assertEqual(Path(result).read_bytes(), b"fake mp4")
        self.assertEqual(client.get_total_cost(), 0.4)


class FallbackBudgetTest(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(sx.NETWORK_ATTEMPTS, [])

    def setUp(self):
        patcher = mock.patch.object(video_client, "_RETRY_WAIT", wait_none())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="fb-"))

    def test_fallback_rechecks_budget_before_switching(self):
        client = UnifiedVideoClient("wan-2.5")
        submitted = []

        def submit(endpoint, arguments):
            submitted.append(client.model_id)
            return "req"

        def wait(endpoint, request_id):
            raise VideoGenerationError("model failed (billed)")

        def gemini_submit(kwargs):
            raise RuntimeError("400 rejected (fake, not billed)")

        for name, fn in (("_fal_submit", submit), ("_fal_wait", wait), ("_gemini_submit", gemini_submit),
                         ("_fal_upload", lambda p: "u"), ("_fal_download", lambda u, o: None)):
            patcher = mock.patch.object(client, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)

        spent = []
        client.on_attempt = lambda event, attempt: spent.append(attempt["cost"]) if event == "submitted" else None
        remaining = 0.5
        asked = []

        def budget_check(model_id, cost):
            asked.append(model_id)
            return cost <= remaining - sum(spent)

        result = client.generate_with_fallback(
            prompt="p", output_dir=self.out, filename="c.mp4", duration=5, budget_check=budget_check,
        )
        self.assertIsNone(result)
        # wan-2.5 ($0.25) runs and is billed; kling ($0.35) and wan-2.2 ($0.50) no longer fit,
        # veo-3.1-lite ($0.25) does and is tried; the client never switched to a refused model.
        self.assertEqual(asked, ["wan-2.5", "kling-2.5-turbo-pro", "wan-2.2", "veo-3.1-lite"])
        self.assertEqual(submitted, ["wan-2.5"])
        errors = client.get_fallback_errors()
        self.assertTrue(any("Kling 2.5 Turbo Pro: skipped" in e for e in errors), errors)
        self.assertTrue(any("Wan 2.2: skipped" in e for e in errors), errors)
        self.assertEqual(client.model_id, "veo-3.1-lite")


if __name__ == "__main__":
    unittest.main()
