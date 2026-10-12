"""registry.json: loads, every video model validates, and it agrees with the code."""

import json
import re
import unittest

import smoke_support as sx  # noqa: F401  (must come before any src import)

from src.config import Config
from src.narrative import GROQ_FALLBACK_MODEL
from src.pipeline import WHISPER_MODEL_NAME
from src.video_models import (
    REGISTRY_FILE,
    TIER_FALLBACK_ORDER,
    VIDEO_MODEL_REGISTRY,
    VideoModelConfig,
    get_default_for_tier,
)


class RegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))

    def test_top_level_shape(self):
        self.assertEqual(
            list(self.reg),
            ["registryVersion", "kitVersion", "routes", "defaultModels", "videoModels", "tierDefaults", "fallbackOrder"],
        )
        self.assertEqual(self.reg["registryVersion"], 1)
        self.assertEqual(self.reg["kitVersion"], "story-1")

    def test_routes(self):
        routes = {r["id"]: r for r in self.reg["routes"]}
        self.assertEqual(list(routes), ["recap", "series"])
        self.assertEqual(routes["recap"]["formats"], ["movie-recap", "story-recap"])
        self.assertEqual(routes["series"]["formats"], ["animated-short"])
        for r in routes.values():
            for key in ("name", "description", "inputs", "paidServices"):
                self.assertTrue(r[key], f"{r['id']}.{key}")

    def test_every_video_model_validates(self):
        ids = [m["model_id"] for m in self.reg["videoModels"]]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in self.reg["videoModels"]:
            VideoModelConfig.model_validate(entry)
        self.assertEqual(list(VIDEO_MODEL_REGISTRY), ids)

    def test_tiers_and_fallbacks_reference_known_models(self):
        for tier, model_id in self.reg["tierDefaults"].items():
            self.assertEqual(VIDEO_MODEL_REGISTRY[model_id].tier, tier)
            self.assertEqual(get_default_for_tier(tier).model_id, model_id)
        self.assertEqual(TIER_FALLBACK_ORDER, self.reg["fallbackOrder"])
        for tier, order in self.reg["fallbackOrder"].items():
            for model_id in order:
                self.assertEqual(VIDEO_MODEL_REGISTRY[model_id].tier, tier)

    def test_default_models_match_config_defaults(self):
        d = self.reg["defaultModels"]
        self.assertEqual(d["llm"], Config.GEMINI_MODEL_NAME)
        self.assertEqual(d["image"], Config.GEMINI_IMAGE_MODEL)
        self.assertEqual(d["tts"], Config.TTS_MODEL)
        self.assertEqual(d["llmFallback"], GROQ_FALLBACK_MODEL)
        self.assertEqual(d["asr"], f"openai-whisper-{WHISPER_MODEL_NAME}")

    def test_descriptions_agree_with_prices(self):
        """Review B8: a $X/s in a description must match cost_per_second (or the $0.052/s estimate)."""
        for m in VIDEO_MODEL_REGISTRY.values():
            for price in re.findall(r"\$(\d+(?:\.\d+)?)/s", m.description):
                self.assertEqual(float(price), m.cost_per_second or 0.052, m.model_id)

    def test_no_secrets_or_paths(self):
        text = REGISTRY_FILE.read_text(encoding="utf-8")
        for needle in ("/" + "Users/", "api_key", "API_KEY", "@"):
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
