"""
Review B4 ($0): the video budget is per project. BudgetGuard starts from a persistent
spend ledger, existing clips are counted, and a corrupt ledger never resets to $0.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import smoke_support as sx  # noqa: F401  (must come before any src import)

from src.budget_guard import BudgetExceeded, BudgetGuard, SpendLedger
from src.config import Config
from src.steps import StepContext
from src.steps.director import DirectorShot, DirectorShots
from src.steps.scene_generator import backfill_existing_clips


def _shot(scene_id: int) -> DirectorShot:
    return DirectorShot(
        scene_id=scene_id, primary_character_id="c", location_id="l", camera_angle="eye level",
        shot_type="wide", camera_movement="static", veo_prompt="p", dialogue="d", voice_profile="v",
        model_hint="",
    )


class SpendLedgerTest(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="ledger-"))

    def test_guard_starts_from_project_spend_across_runs(self):
        ledger = SpendLedger(self.project)
        ledger.record(episode=1, scene_id=1, model_id="veo-3.1-fast", duration_sec=8, cost_usd=0.8)
        ledger.record(episode=2, scene_id=1, model_id="veo-3.1-fast", duration_sec=8, cost_usd=0.8, status="failed")

        # A new run (new objects) sees the same spend: per project, not per episode or retry
        guard = BudgetGuard(max_budget=2.0, auto_downgrade=False, ledger=SpendLedger(self.project))
        self.assertEqual(guard.cumulative_spend, 1.6)
        self.assertAlmostEqual(guard.remaining, 0.4)
        with self.assertRaises(BudgetExceeded):
            guard.check_budget("veo-3.1-fast", duration=8)
        self.assertEqual(SpendLedger(self.project).total(episode=1), 0.8)

    def test_corrupt_ledger_is_an_error_not_zero(self):
        (self.project / "spend_ledger.json").write_text("{not json")
        with self.assertRaises(RuntimeError):
            SpendLedger(self.project)

    def test_update_persists(self):
        ledger = SpendLedger(self.project)
        entry = ledger.record(episode=1, scene_id=3, model_id="wan-2.5", duration_sec=5, cost_usd=0.25)
        ledger.update(entry, status="ok")
        reread = SpendLedger(self.project)
        self.assertEqual(reread.clip_entry(1, 3)["modelId"], "wan-2.5")
        self.assertEqual(json.loads((self.project / "spend_ledger.json").read_text())["ledgerVersion"], 1)

    def test_existing_clips_are_backfilled(self):
        clips = self.project / "episodes" / "episode_1" / "clips"
        clips.mkdir(parents=True)
        for n in (1, 2):
            (clips / f"scene_{n}.mp4").write_bytes(b"x")
        (self.project / "project.json").write_text(json.dumps({"step_data": {"step_7": {"model_id": "veo-3.1-lite"}}}))
        ctx = StepContext(project_dir=self.project, gemini_client=None, episode_number=1)
        shots = DirectorShots(episode_number=1, shots=[_shot(1), _shot(2), _shot(3)])

        ledger = SpendLedger(self.project)
        backfill_existing_clips(ctx.project_dir, ctx.episode_number, ledger, shots, clips)
        backfill_existing_clips(ctx.project_dir, ctx.episode_number, ledger, shots, clips)  # idempotent

        rows = [(e["sceneId"], e["modelId"], e["status"], e["source"], e["costUsd"]) for e in SpendLedger(self.project).entries]
        self.assertEqual(rows, [(1, "veo-3.1-lite", "ok", "backfill", 0.4), (2, "veo-3.1-lite", "ok", "backfill", 0.4)])

        # A clip whose billed entry was never closed (crash after download) is not counted twice
        (clips / "scene_3.mp4").write_bytes(b"x")
        ledger.record(episode=1, scene_id=3, model_id="wan-2.5", duration_sec=5, cost_usd=0.25)
        backfill_existing_clips(ctx.project_dir, ctx.episode_number, ledger, shots, clips)
        self.assertEqual([(e["sceneId"], e["status"]) for e in ledger.entries_for(1, 3)], [(3, "ok")])
        self.assertEqual(ledger.total(), 1.05)
        with mock.patch.object(Config, "VIDEO_MAX_BUDGET", 1.5):
            guard = BudgetGuard(max_budget=Config.VIDEO_MAX_BUDGET, ledger=ledger)
        self.assertAlmostEqual(guard.remaining, 0.45)


if __name__ == "__main__":
    unittest.main()
