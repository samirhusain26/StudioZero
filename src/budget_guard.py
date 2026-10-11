"""
Budget Guard — Tracks cumulative spend and enforces budget limits per project.

Before each video generation, the guard checks whether the estimated cost
would exceed the remaining budget. If so, it can:
  1. Switch to a cheaper model in the same tier
  2. Switch to the cheapest tier
  3. Pause and yield a PipelineStatus with retry_gate=True
"""

import logging
from typing import Optional, Tuple

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

    def __init__(self, max_budget: float = 10.0, auto_downgrade: bool = True):
        self.max_budget = max_budget
        self.auto_downgrade = auto_downgrade
        self._cumulative_spend: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_budget - self._cumulative_spend)

    @property
    def cumulative_spend(self) -> float:
        return round(self._cumulative_spend, 4)

    def record_spend(self, cost: float) -> None:
        """Record actual spend after a successful generation."""
        self._cumulative_spend += cost
        logger.info(
            f"[budget_guard] Recorded ${cost:.4f} — "
            f"cumulative: ${self._cumulative_spend:.4f} / ${self.max_budget:.2f} "
            f"(${self.remaining:.2f} remaining)"
        )

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
