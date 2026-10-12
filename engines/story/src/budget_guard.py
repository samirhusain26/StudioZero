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
LLM, image and TTS calls are in the same ledger (kind llm/image/tts, priced by
src/pricing.py), so the budget and render.json's costUsd count them too.
"""

import contextlib
import fcntl
import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from src.video_models import (
    TIER_FALLBACK_ORDER,
    clip_duration,
    get_model,
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
    status: "submitted" (billed, result pending), "ok" (clip saved), "failed"
    (billed, no clip) or "uncertain" (the submit failed after it may have reached the
    provider: counted, never retried). source: "generated", or "backfill" for a clip
    that existed before the ledger did (its cost is an estimate for the assumed model).

    Text, image and speech calls add {kind: llm|image|tts, what, modelId, episode,
    units, costUsd, estimated, status: "ok", at} (episode null for project-level work).
    Entries without `kind` are video generations.

    Several instances may hold the same file (the spend meter, the scene generator, the
    worker, or the CLI and the worker in two processes): every write re-reads the file under
    a per-file lock (a thread lock plus flock on spend_ledger.json.lock) first, so none drops
    another's entries. Updates find their entry by its id.
    """

    _locks: dict = {}
    _locks_guard = threading.Lock()

    def __init__(self, project_dir: Path):
        self.path = Path(project_dir) / LEDGER_FILENAME
        self.entries: List[dict] = []
        with SpendLedger._locks_guard:
            self._lock = SpendLedger._locks.setdefault(str(self.path.resolve()), threading.RLock())
        self._reload()

    @contextlib.contextmanager
    def _locked(self):
        """Thread lock plus an advisory file lock, so another process's writes are not lost."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path.with_name(LEDGER_FILENAME + ".lock"), "a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _reload(self) -> None:
        if not self.path.exists():
            return
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

    def episode_cost(self, episode: int, num_episodes: int) -> float:
        """An episode's own spend plus its equal share of project-level spend (story, cast, worlds)."""
        shared = sum(e.get("costUsd", 0.0) for e in self.entries if e.get("episode") is None)
        return round(self.total(episode) + shared / max(1, num_episodes), 4)

    def by_kind(self) -> dict:
        """Spend per kind (video, llm, image, tts)."""
        out: dict = {}
        for e in self.entries:
            kind = e.get("kind", "video")
            out[kind] = round(out.get(kind, 0.0) + e.get("costUsd", 0.0), 6)
        return out

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
            "id": uuid.uuid4().hex[:12],
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
        with self._locked():
            self._reload()
            self.entries.append(entry)
            self.save()
        return entry

    def record_usage(self, kind: str, model_id: str, what: str, episode: Optional[int], cost_usd: float,
                     units: dict, estimated: bool, price_assumed: bool = False) -> dict:
        """Append a priced text, image or speech call and persist (src/pricing.py calls this)."""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "what": what,
            "modelId": model_id,
            "episode": episode,
            "units": units,
            "costUsd": round(cost_usd, 6),
            "estimated": bool(estimated),
            "status": "ok",
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if price_assumed:
            entry["priceAssumed"] = True
        with self._locked():
            self._reload()
            self.entries.append(entry)
            self.save()
        return entry

    def update(self, entry: dict, **fields) -> None:
        """Update an entry returned by record() (or read from this ledger) and persist."""
        with self._locked():
            before = dict(entry)
            self._reload()
            target = next((e for e in self.entries if (e.get("id") == before["id"] if before.get("id") else e == before)), None)
            entry.update(fields)
            if target is None:
                raise RuntimeError(f"{self.path}: entry to update not found ({before.get('modelId')}, scene {before.get('sceneId')})")
            target.update(fields)
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
        estimated = estimate_cost(model_id, clip_duration(model_id, duration), include_audio)

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
        """The priciest cheaper model in the same tier that fits the budget."""
        current = get_model(current_model_id)
        tier = current.tier
        current_cost = estimate_cost(current_model_id, clip_duration(current_model_id, duration), include_audio)

        # The tier's fallback order is cheapest first: walk it from the most expensive down
        for model_id in reversed(TIER_FALLBACK_ORDER.get(tier, [])):
            if model_id == current.model_id:
                continue
            cost = estimate_cost(model_id, clip_duration(model_id, duration), include_audio)
            if cost < current_cost and cost <= self.remaining:
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
            cost = estimate_cost(model_id, clip_duration(model_id, duration), include_audio)
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
