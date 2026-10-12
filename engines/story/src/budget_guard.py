"""
Budget Guard — Tracks cumulative spend and enforces budget limits per project.

Before each video generation, the guard checks whether the estimated cost
would exceed the remaining budget. If so, it can:
  1. Switch to a cheaper model in the same tier
  2. Switch to the cheapest tier
  3. Pause and yield a PipelineStatus with retry_gate=True

Spend is per project, not per run: SpendLedger keeps every billed video generation
in <project_dir>/spend_ledger.json (recorded when the provider accepts the job, so a
crash while polling still counts), and BudgetGuard starts from the ledger total.
Only video generation is in the ledger; LLM, image and TTS calls are not yet counted.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from src.video_models import (
    VideoModelConfig,
    TIER_FALLBACK_ORDER,
    get_model,
    get_models_by_tier,
    estimate_cost,
)

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Raised when the budget is exhausted and no cheaper model is available."""
    def __init__(self, remaining: float, estimated: float, model_id: str):
        self.remaining = remaining
        self.estimated = estimated
        self.model_id = model_id
        super().__init__(
            f"Budget exceeded: ${remaining:.2f} remaining, "
            f"${estimated:.2f} estimated for {model_id}"
        )


LEDGER_FILENAME = "spend_ledger.json"


class SpendLedger:
    """
    Persistent per-project spend ledger (JSON next to pipeline_state.json).

    One entry per paid video generation the provider accepted:
        {episode, sceneId, modelId, durationSec, costUsd, estimated, status, source, at}
    status: "submitted" (billed, result pending), "ok" (clip saved) or "failed"
    (billed, no clip). source: "generated", or "backfill" for a clip that existed
    before the ledger did (its cost is an estimate for the assumed model).
    """

    def __init__(self, project_dir: Path):
        self.path = Path(project_dir) / LEDGER_FILENAME
        self.entries: List[dict] = []
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.entries = list(data["entries"])
            except Exception as e:
                # Never silently restart from $0: that is how a budget gets spent twice.
                raise RuntimeError(f"{self.path} exists but cannot be read: {e}") from e

    def total(self, episode: Optional[int] = None) -> float:
        """Total recorded spend (USD) for the project, or for one episode."""
        return round(sum(
            e.get("costUsd", 0.0) for e in self.entries
            if episode is None or e.get("episode") == episode
        ), 4)

    def entries_for(self, episode: int, scene_id: Optional[int] = None) -> List[dict]:
        return [
            e for e in self.entries
            if e.get("episode") == episode and (scene_id is None or e.get("sceneId") == scene_id)
        ]

    def clip_entry(self, episode: int, scene_id: int) -> Optional[dict]:
        """The entry that produced the current clip of a scene (last "ok" entry), if any."""
        ok = [e for e in self.entries_for(episode, scene_id) if e.get("status") == "ok"]
        return ok[-1] if ok else None

    def record(
        self,
        episode: int,
        scene_id: int,
        model_id: str,
        duration_sec: float,
        cost_usd: float,
        status: str = "submitted",
        source: str = "generated",
    ) -> dict:
        """Append an entry and persist the ledger immediately."""
        entry = {
            "episode": episode,
            "sceneId": scene_id,
            "modelId": model_id,
            "durationSec": duration_sec,
            "costUsd": round(cost_usd, 4),
            "estimated": True,
            "status": status,
            "source": source,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.entries.append(entry)
        self.save()
        return entry

    def update(self, entry: dict, **fields) -> None:
        """Update an entry returned by record() and persist."""
        entry.update(fields)
        self.save()

    def save(self) -> None:
        """Atomically write the ledger (same pattern as pipeline_state.save_state)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"ledgerVersion": 1, "entries": self.entries}, f, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


class BudgetGuard:
    """
    Tracks cumulative spend and enforces a per-project budget cap.

    Usage:
        guard = BudgetGuard(max_budget=10.0)
        model_id = guard.check_budget("kling-2.5-turbo-pro", duration=8)
        # model_id may be different if the guard downgraded
        client.switch_model(model_id)
        # ... generate video ...
        guard.record_spend(cost)
    """

    def __init__(
        self,
        max_budget: float = 10.0,
        auto_downgrade: bool = True,
        ledger: Optional[SpendLedger] = None,
    ):
        self.max_budget = max_budget
        self.auto_downgrade = auto_downgrade
        # Start from what the project has already spent (all episodes, earlier runs).
        self._cumulative_spend: float = ledger.total() if ledger is not None else 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_budget - self._cumulative_spend)

    @property
    def cumulative_spend(self) -> float:
        return round(self._cumulative_spend, 4)

    def record_spend(self, cost: float) -> None:
        """Record spend for a generation the provider accepted (billed)."""
        self._cumulative_spend += cost
        logger.info(
            f"[budget_guard] Recorded ${cost:.4f} — "
            f"cumulative: ${self._cumulative_spend:.4f} / ${self.max_budget:.2f} "
            f"(${self.remaining:.2f} remaining)"
        )

    def can_afford(self, cost: float) -> bool:
        return cost <= self.remaining

    def check_budget(
        self,
        model_id: str,
        duration: int = 8,
        include_audio: bool = False,
    ) -> str:
        """
        Check if the estimated cost fits within the remaining budget.

        Returns the model_id to use (may differ from input if downgraded).
        Raises BudgetExceeded if even the cheapest model exceeds the budget
        and auto_downgrade is disabled.
        """
        estimated = estimate_cost(model_id, duration, include_audio)

        if estimated <= self.remaining:
            return model_id

        logger.warning(
            f"[budget_guard] Model {model_id} estimated ${estimated:.4f} "
            f"exceeds remaining ${self.remaining:.2f}"
        )

        if not self.auto_downgrade:
            raise BudgetExceeded(self.remaining, estimated, model_id)

        # Try cheaper model in same tier
        downgraded = self._find_cheaper_model(model_id, duration, include_audio)
        if downgraded:
            return downgraded

        # Try cheapest tier
        downgraded = self._find_cheapest_model(duration, include_audio)
        if downgraded:
            return downgraded

        raise BudgetExceeded(self.remaining, estimated, model_id)

    def _find_cheaper_model(
        self,
        current_model_id: str,
        duration: int,
        include_audio: bool,
    ) -> Optional[str]:
        """Find a cheaper model in the same tier that fits the budget."""
        current = get_model(current_model_id)
        tier = current.tier
        fallback_order = TIER_FALLBACK_ORDER.get(tier, [])

        # Try models after the current one in the fallback order
        current_idx = fallback_order.index(current_model_id) if current_model_id in fallback_order else -1

        for model_id in fallback_order[current_idx + 1:]:
            cost = estimate_cost(model_id, duration, include_audio)
            if cost <= self.remaining:
                logger.info(
                    f"[budget_guard] Downgrading within tier '{tier}': "
                    f"{current_model_id} -> {model_id} (${cost:.4f})"
                )
                return model_id

        return None

    def _find_cheapest_model(
        self,
        duration: int,
        include_audio: bool,
    ) -> Optional[str]:
        """Find the cheapest model across all tiers that fits the budget."""
        for model_id in TIER_FALLBACK_ORDER.get("cheapest", []):
            cost = estimate_cost(model_id, duration, include_audio)
            if cost <= self.remaining:
                logger.info(
                    f"[budget_guard] Downgrading to cheapest tier: "
                    f"{model_id} (${cost:.4f})"
                )
                return model_id

        return None

    def summary(self) -> dict:
        """Return a summary of budget usage."""
        return {
            "max_budget": self.max_budget,
            "cumulative_spend": self.cumulative_spend,
            "remaining": round(self.remaining, 4),
            "utilization_pct": round(
                (self._cumulative_spend / self.max_budget * 100) if self.max_budget > 0 else 0,
                1,
            ),
        }
