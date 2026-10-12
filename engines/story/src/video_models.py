"""
Video Model Configuration Registry — Central source of truth for all supported
video generation models across providers (fal.ai, Vertex AI).

This module is pure configuration with no pipeline dependencies. The data lives in
engines/story/registry.json.
"""

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class VideoModelConfig(BaseModel):
    """Configuration for a single video generation model."""
    model_id: str
    provider: Literal["fal.ai", "vertex_ai", "gemini_api"]
    display_name: str
    endpoint_t2v: str = Field(..., description="Text-to-video endpoint identifier")
    endpoint_i2v: Optional[str] = Field(None, description="Image-to-video endpoint")
    endpoint_ref2v: Optional[str] = Field(None, description="Reference-to-video endpoint")
    cost_per_second: Optional[float] = Field(None, description="USD per second of video (None if token-based)")
    max_resolution: str
    max_duration_sec: int
    has_audio: bool
    has_reference_images: bool
    tier: Literal["cheapest", "recommended", "high_fidelity"]
    description: str = Field(..., description="Short description for UI display")


# ── Model Registry ──────────────────────────────────────────────────────────
# One source of truth: engines/story/registry.json (also read by the studio catalog
# exporter). Entries are validated with VideoModelConfig at import.

REGISTRY_FILE = Path(__file__).resolve().parent.parent / "registry.json"


def load_registry_file(path: Path = REGISTRY_FILE) -> dict:
    """Load the story engine registry JSON (routes, default models, video models)."""
    return json.loads(path.read_text(encoding="utf-8"))


_REGISTRY = load_registry_file()

VIDEO_MODEL_REGISTRY: Dict[str, VideoModelConfig] = {
    entry["model_id"]: VideoModelConfig.model_validate(entry)
    for entry in _REGISTRY["videoModels"]
}


# ── Tier defaults (used when no specific model is selected) ─────────────────

_TIER_DEFAULTS: Dict[str, str] = dict(_REGISTRY["tierDefaults"])

# ── Fallback order per tier (used by BudgetGuard / UnifiedVideoClient) ──────

TIER_FALLBACK_ORDER: Dict[str, List[str]] = {
    tier: list(model_ids) for tier, model_ids in _REGISTRY["fallbackOrder"].items()
}


# ── Helper Functions ────────────────────────────────────────────────────────

def get_model(model_id: str) -> VideoModelConfig:
    """Get a model config by ID. Raises KeyError if not found."""
    if model_id not in VIDEO_MODEL_REGISTRY:
        raise KeyError(f"Unknown video model: '{model_id}'. Available: {list(VIDEO_MODEL_REGISTRY.keys())}")
    return VIDEO_MODEL_REGISTRY[model_id]


def get_models_by_tier(tier: str) -> List[VideoModelConfig]:
    """Return all models in a given tier."""
    return [m for m in VIDEO_MODEL_REGISTRY.values() if m.tier == tier]


def get_default_for_tier(tier: str) -> VideoModelConfig:
    """Return the default model for a tier."""
    model_id = _TIER_DEFAULTS.get(tier)
    if not model_id:
        raise KeyError(f"Unknown tier: '{tier}'. Available: {list(_TIER_DEFAULTS.keys())}")
    return VIDEO_MODEL_REGISTRY[model_id]


def estimate_cost(model_id: str, duration_sec: int, include_audio: bool = False) -> float:
    """
    Estimate cost for a single video generation.

    For models with per-second pricing, returns cost_per_second * duration.
    Audio surcharges are applied for models where audio significantly changes price:
      - Veo 3.1 standard: 2x with audio
      - Veo 3.1 fast: 1.5x with audio
      - Kling 3.0 Pro: 1.5x with audio
    For token-based models (Seedance), uses a rough estimate of $0.052/sec.
    """
    model = get_model(model_id)
    base_cost = model.cost_per_second

    if base_cost is None:
        # Token-based models — rough estimate
        base_cost = 0.052

    cost = base_cost * duration_sec

    # Audio surcharges — Gemini API Veo models include audio in base price
    if include_audio and model.has_audio and model.provider == "fal.ai":
        if model_id == "kling-3.0-pro":
            cost *= 1.5

    return round(cost, 4)


def estimate_episode_cost(
    model_id: str,
    num_shots: int = 6,
    duration_per_shot: int = 8,
    include_audio: bool = False,
) -> float:
    """Estimate total cost for a full episode."""
    return round(
        sum(estimate_cost(model_id, duration_per_shot, include_audio) for _ in range(num_shots)),
        2,
    )
