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

    def test_submit_with_uncertain_outcome_is_counted_not_retried(self):
        # A timeout after sending may have started a paid job: never retried, counted as billed
        fake = FakeFal(submit_errors=[TimeoutError("read timeout after sending")])
        fake.install(self, self.client)
        self.assertIsNone(self._generate())
        self.assertEqual(fake.calls["submit"], 1)
        self.assertEqual(self.events, [("submitted", "wan-2.5"), ("failed", "wan-2.5")])
        attempt = self.client.attempts[-1]
        self.assertTrue(attempt["submitted"] and attempt["uncertain"])
        self.assertEqual(self.client.get_total_cost(), 0.25)

    def test_server_error_on_submit_is_counted(self):
        error = RuntimeError("502 bad gateway")
        error.status_code = 502
        fake = FakeFal(submit_errors=[error])
        fake.install(self, self.client)
        self.assertIsNone(self._generate())
        self.assertTrue(self.client.attempts[-1]["uncertain"])
        self.assertEqual(self.client.get_total_cost(), 0.25)

    def test_rejected_submit_is_not_counted(self):
        # A 4xx rejection starts no job
        error = RuntimeError("422 unprocessable")
        error.status_code = 422
        fake = FakeFal(submit_errors=[error])
        fake.install(self, self.client)
        self.assertIsNone(self._generate())
        self.assertEqual(self.events, [("failed", "wan-2.5")])
        self.assertFalse(self.client.attempts[-1]["submitted"])
        self.assertEqual(self.client.get_total_cost(), 0.0)

    def test_fal_sdk_submit_posts_exactly_once(self):
        """fal_client retries requests on its own (timeouts, dropped connections, 408/409/429); a paid
        submit must go out once. The real SDK runs; only its single-request primitive is replaced."""
        import httpx
        import fal_client.client as sdk
        posts = []

        def request(client, method, url, **kwargs):
            posts.append((method, url))
            raise httpx.ReadTimeout("timed out after the request was sent")

        with mock.patch.object(sdk, "_request", request), mock.patch.object(sdk.time, "sleep", lambda s: None):
            self.assertIsNone(self._generate())
        self.assertEqual(len(posts), 1, posts)
        self.assertEqual(sdk.MAX_ATTEMPTS, 10)  # restored for the SDK's other (free) calls
        attempt = self.client.attempts[-1]
        self.assertTrue(attempt["submitted"] and attempt["uncertain"])
        self.assertEqual(self.client.get_total_cost(), 0.25)

    def test_unexplained_submit_error_is_counted(self):
        # Not a refusal, not a 4xx: the job may exist, so it is counted
        fake = FakeFal(submit_errors=[KeyError("request_id")])
        fake.install(self, self.client)
        self.assertIsNone(self._generate())
        self.assertTrue(self.client.attempts[-1]["uncertain"])

    def test_unverified_model_is_never_called(self):
        client = UnifiedVideoClient("sora-2-pro")
        fake = FakeFal()
        fake.install(self, client)
        self.assertIsNone(client.generate_video(prompt="p", output_dir=self.out, filename="s.mp4"))
        self.assertEqual(fake.calls, {"submit": 0, "wait": 0, "download": 0})
        self.assertIn("not verified", client._last_error)

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


class FalRequestTest(unittest.TestCase):
    """Review B8: each fal.ai request matches that model's verified input schema."""

    def request(self, model_id, **kw):
        client = UnifiedVideoClient(model_id)
        with mock.patch.object(client, "_fal_upload", lambda path: f"https://fal.invalid/{Path(path).name}"):
            args = dict(prompt="A robot waves.", duration=5, include_audio=False, image_url=None, image_path=None,
                        reference_images=None, dialogue="")
            args.update(kw)
            return client._fal_request(**args)

    def test_seedance_reference_to_video(self):
        endpoint, args, uploads = self.request("seedance-2.0-fast", reference_images=["/tmp/a.png", "https://x.invalid/b.png"],
                                               include_audio=True, dialogue="Hello")
        self.assertEqual(endpoint, "bytedance/seedance-2.0/fast/reference-to-video")
        self.assertEqual(args["image_urls"], ["https://fal.invalid/a.png", "https://x.invalid/b.png"])
        self.assertEqual((args["aspect_ratio"], args["resolution"], args["duration"], args["generate_audio"]),
                         ("9:16", "720p", "5", True))
        self.assertIn('says: "Hello"', args["prompt"])
        self.assertEqual(uploads, 1)

    def test_kling_3_image_to_video_uses_start_image_url(self):
        endpoint, args, _ = self.request("kling-3.0-pro", image_path="/tmp/start.png")
        self.assertEqual(endpoint, "fal-ai/kling-video/v3/pro/image-to-video")
        self.assertEqual(args["start_image_url"], "https://fal.invalid/start.png")
        self.assertNotIn("image_url", args)
        self.assertNotIn("aspect_ratio", args)  # image-to-video takes the image's shape
        self.assertNotIn("resolution", args)
        self.assertIs(args["generate_audio"], False)

    def test_seedance_1_5_image_to_video_is_vertical(self):
        endpoint, args, _ = self.request("seedance-1.5-pro", image_url="https://x.invalid/s.png", duration=8)
        self.assertEqual(endpoint, "fal-ai/bytedance/seedance/v1.5/pro/image-to-video")
        self.assertEqual((args["image_url"], args["aspect_ratio"], args["duration"]), ("https://x.invalid/s.png", "9:16", "8"))

    def test_fixed_length_models_get_no_duration(self):
        _, args, _ = self.request("wan-2.2")
        self.assertNotIn("duration", args)
        self.assertEqual(args["aspect_ratio"], "9:16")
        _, args, _ = self.request("kling-2.5-turbo-pro", duration=8)
        self.assertEqual(args["duration"], "10")  # snapped up to an allowed value

    def test_silent_models_never_get_dialogue(self):
        _, args, _ = self.request("wan-2.5", include_audio=False, dialogue="Hi")
        self.assertEqual(args["prompt"], "A robot waves.")
        self.assertNotIn("generate_audio", args)


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
            error = RuntimeError("400 rejected (fake, not billed)")
            error.code = 400
            raise error

        for name, fn in (("_fal_submit", submit), ("_fal_wait", wait), ("_gemini_submit", gemini_submit),
                         ("_fal_upload", lambda p: "u"), ("_fal_download", lambda u, o: None)):
            patcher = mock.patch.object(client, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)

        spent = []
        client.on_attempt = lambda event, attempt: spent.append(attempt["cost"]) if event == "submitted" else None
        remaining = 0.7
        asked = []

        def budget_check(model_id, cost):
            asked.append(model_id)
            return cost <= remaining - sum(spent)

        result = client.generate_with_fallback(
            prompt="p", output_dir=self.out, filename="c.mp4", duration=5, budget_check=budget_check,
        )
        self.assertIsNone(result)
        # Current model first, then the tier cheapest first. wan-2.5 ($0.25, 5 s) is billed and
        # fails; veo-3.1-lite ($0.40, always 8 s) fits and is rejected unbilled; kling ($0.35)
        # fits, is billed and fails; wan-2.2 ($0.40) no longer fits and is never switched to.
        self.assertEqual(asked, ["wan-2.5", "veo-3.1-lite", "kling-2.5-turbo-pro", "wan-2.2"])
        self.assertEqual(submitted, ["wan-2.5", "kling-2.5-turbo-pro"])
        self.assertEqual(spent, [0.25, 0.35])
        errors = client.get_fallback_errors()
        self.assertTrue(any("Wan 2.2: skipped" in e for e in errors), errors)
        self.assertEqual(client.model_id, "kling-2.5-turbo-pro")

if __name__ == "__main__":
    unittest.main()
