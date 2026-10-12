"""Text, image and speech pricing and the shared spend ledger ($0: no provider is called)."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import smoke_support as sx  # noqa: F401  (must come before any src import)

from src import pricing
from src.budget_guard import SpendLedger
from src.pricing import charge, charge_genai, charging, set_episode


def response(prompt=0, output=0, images=0, text=None):
    parts = [SimpleNamespace(inline_data=SimpleNamespace(data=b"png", mime_type="image/png")) for _ in range(images)]
    return SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=prompt, candidates_token_count=output),
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))],
        text=text,
    )


class PricingTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="price-"))

    def test_list_prices(self):
        self.assertEqual(pricing.text_cost("gemini-2.5-flash", 1_000_000, 1_000_000), (2.8, False))
        self.assertEqual(pricing.image_cost("gemini-2.5-flash-image", 0, 2), (0.078, False))
        # 60 s of narration: 1,500 audio tokens at $10/1M
        self.assertEqual(pricing.tts_cost("gemini-2.5-flash-preview-tts", 0, 60 * pricing.AUDIO_TOKENS_PER_SECOND), (0.015, False))

    def test_unknown_model_is_priced_at_the_highest_rate_never_zero(self):
        cost, assumed = pricing.text_cost("some-new-model", 1_000_000, 0)
        self.assertTrue(assumed)
        self.assertEqual(cost, max(r[0] for r in pricing.TEXT_PRICES.values()))

    def test_charges_go_to_the_active_ledger_with_the_episode(self):
        ledger = SpendLedger(self.dir)
        with charging(ledger):
            charge_genai(response(prompt=1000, output=500), "llm", "gemini-2.5-flash", "story")
            set_episode(2)
            charge_genai(response(prompt=300, images=1), "image", "gemini-2.5-flash-image", "scene start")
            charge("tts", "gemini-2.5-flash-preview-tts", "narration", input_tokens=40, audio_seconds=4.0)
        charge("llm", "gemini-2.5-flash", "outside any run", input_tokens=10)  # no active ledger: not recorded
        entries = SpendLedger(self.dir).entries
        self.assertEqual([(e["kind"], e["episode"]) for e in entries], [("llm", None), ("image", 2), ("tts", 2)])
        self.assertAlmostEqual(entries[0]["costUsd"], (1000 * 0.30 + 500 * 2.50) / 1e6)
        self.assertAlmostEqual(entries[1]["costUsd"], 300 * 0.30 / 1e6 + 0.039)
        self.assertTrue(entries[2]["estimated"])  # audio tokens from the duration
        self.assertEqual(entries[2]["units"]["outputTokens"], 100)

    def test_missing_usage_is_estimated_from_text(self):
        ledger = SpendLedger(self.dir)
        with charging(ledger):
            cost = charge_genai(SimpleNamespace(usage_metadata=None, text="x" * 400), "llm", "gemini-2.5-flash", "s", "y" * 800)
        self.assertGreater(cost, 0)
        self.assertTrue(SpendLedger(self.dir).entries[0]["estimated"])

    def test_episode_cost_shares_project_work(self):
        ledger = SpendLedger(self.dir)
        ledger.record_usage(kind="llm", model_id="m", what="story", episode=None, cost_usd=1.0, units={}, estimated=True)
        ledger.record(episode=1, scene_id=1, model_id="wan-2.5", duration_sec=5, cost_usd=0.25)
        ledger.record(episode=2, scene_id=1, model_id="wan-2.5", duration_sec=5, cost_usd=0.25)
        self.assertEqual(ledger.episode_cost(1, 2), 0.75)
        self.assertEqual(SpendLedger(self.dir).by_kind(), {"llm": 1.0, "video": 0.5})


class SharedLedgerTest(unittest.TestCase):
    def test_two_instances_never_drop_each_others_entries(self):
        folder = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="ledger-"))
        meter, scenes = SpendLedger(folder), SpendLedger(folder)
        clip = scenes.record(episode=1, scene_id=1, model_id="wan-2.5", duration_sec=5, cost_usd=0.25)
        meter.record_usage(kind="llm", model_id="m", what="director", episode=1, cost_usd=0.01, units={}, estimated=False)
        scenes.update(clip, status="ok")
        entries = SpendLedger(folder).entries
        self.assertEqual([(e.get("kind", "video"), e["status"]) for e in entries], [("video", "ok"), ("llm", "ok")])
        self.assertEqual(SpendLedger(folder).total(), 0.26)

    def test_uncertain_submits_count(self):
        folder = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="ledger-"))
        ledger = SpendLedger(folder)
        ledger.record(episode=1, scene_id=1, model_id="wan-2.5", duration_sec=5, cost_usd=0.25, status="uncertain")
        self.assertEqual(SpendLedger(folder).total(), 0.25)


if __name__ == "__main__":
    unittest.main()
