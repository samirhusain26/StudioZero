"""
Video Model Configuration Registry — Central source of truth for all supported
video generation models across providers (fal.ai, Gemini API).

This module is pure configuration with no pipeline dependencies. The data lives in
engines/story/registry.json.

Every model records where its endpoints, parameters and prices were checked
(`verified`); a model without that record is unavailable: the client refuses to
submit to it and it is in no fallback order (review B8). Prices are per second of
output at the resolution the engine requests; `cost_per_second_audio` is the price
with native audio where the provider charges more for it.
"""

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FalParams(BaseModel):
    """How the engine's request maps onto one fal.ai model's input schema."""
    image: Optional[str] = Field(None, description="Input field for the start image (image-to-video)")
    audio: Optional[str] = Field(None, description="Boolean input that switches native audio on or off")
    references: Optional[str] = Field(None, description="List input for reference image URLs (reference-to-video)")
    aspect_ratio: List[Literal["t2v", "i2v", "ref2v"]] = Field(default_factory=list,
                                                              description="Modes that take aspect_ratio (sent as 9:16)")
    resolution: bool = Field(False, description="Whether the model takes a resolution input (sent as max_resolution)")
    durations: Optional[List[int]] = Field(None, description="Allowed duration values in seconds; None = no duration input")


class Verified(BaseModel):
    at: str
    sources: List[str]


class VideoModelConfig(BaseModel):
    """Configuration for a single video generation model."""
    model_id: str
    provider: Literal["fal.ai", "gemini_api"]
    display_name: str
    endpoint_t2v: str = Field(..., description="Text-to-video endpoint identifier")
    endpoint_i2v: Optional[str] = Field(None, description="Image-to-video endpoint")
    endpoint_ref2v: Optional[str] = Field(None, description="Reference-to-video endpoint")
    cost_per_second: float = Field(..., description="USD per second of video (silent, or audio included)")
    cost_per_second_audio: Optional[float] = Field(None, description="USD per second with native audio, when priced differently")
    max_resolution: str
    max_duration_sec: int
    clip_seconds: int = Field(..., description="Length the scene generator requests per shot")
    has_audio: bool
    has_reference_images: bool
    tier: Literal["cheapest", "recommended", "high_fidelity"]
    params: Optional[FalParams] = None
    verified: Optional[Verified] = None
    description: str = Field(..., description="Short description for UI display")

    @property
    def available(self) -> bool:
        return self.verified is not None


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

# Renamed models: settings and projects saved under the old id keep working.
MODEL_ALIASES: Dict[str, str] = {"seedance-1.5-pro-fast": "seedance-1.5-pro"}


# ── Tier defaults (used when no specific model is selected) ─────────────────

_TIER_DEFAULTS: Dict[str, str] = dict(_REGISTRY["tierDefaults"])

# ── Fallback order per tier: available models, cheapest first (with native audio) ──

TIER_FALLBACK_ORDER: Dict[str, List[str]] = {
    tier: list(model_ids) for tier, model_ids in _REGISTRY["fallbackOrder"].items()
}


# ── Helper Functions ────────────────────────────────────────────────────────

def get_model(model_id: str) -> VideoModelConfig:
    """Get a model config by ID (or a renamed model's old ID). Raises KeyError if not found."""
    model_id = MODEL_ALIASES.get(model_id, model_id)
    if model_id not in VIDEO_MODEL_REGISTRY:
        raise KeyError(f"Unknown video model: '{model_id}'. Available: {list(VIDEO_MODEL_REGISTRY.keys())}")
    return VIDEO_MODEL_REGISTRY[model_id]


def available_models() -> List[VideoModelConfig]:
    """Models whose endpoints and prices are verified (the only ones the engine calls)."""
    return [m for m in VIDEO_MODEL_REGISTRY.values() if m.available]


def get_models_by_tier(tier: str) -> List[VideoModelConfig]:
    """Return all models in a given tier."""
    return [m for m in VIDEO_MODEL_REGISTRY.values() if m.tier == tier]


def get_default_for_tier(tier: str) -> VideoModelConfig:
    """Return the default model for a tier."""
    model_id = _TIER_DEFAULTS.get(tier)
    if not model_id:
        raise KeyError(f"Unknown tier: '{tier}'. Available: {list(_TIER_DEFAULTS.keys())}")
    return VIDEO_MODEL_REGISTRY[model_id]


def price_per_second(model_id: str, include_audio: bool = False) -> float:
    """USD per second for one generation (native audio priced where it costs more)."""
    model = get_model(model_id)
    if include_audio and model.has_audio and model.cost_per_second_audio is not None:
        return model.cost_per_second_audio
    return model.cost_per_second


def estimate_cost(model_id: str, duration_sec: float, include_audio: bool = False) -> float:
    """Estimated cost of one generation of `duration_sec` seconds."""
    return round(price_per_second(model_id, include_audio) * duration_sec, 4)


def clip_duration(model_id: str, requested: Optional[float] = None) -> int:
    """Seconds one generation will produce: the request (default clip_seconds) snapped to an allowed value."""
    model = get_model(model_id)
    allowed = model.params.durations if model.params else None
    if not allowed:
        return model.clip_seconds  # fixed length: no duration input (Veo through the Gemini API, Wan 2.2)
    want = int(round(requested if requested is not None else model.clip_seconds))
    want = max(1, min(want, model.max_duration_sec))
    fitting = [d for d in allowed if d >= want]
    return min(fitting) if fitting else max(allowed)


def estimate_episode_cost(
    model_id: str,
    num_shots: int = 6,
    duration_per_shot: Optional[float] = None,
    include_audio: bool = False,
) -> float:
    """Estimate total cost for a full episode."""
    seconds = clip_duration(model_id, duration_per_shot)
    return round(num_shots * estimate_cost(model_id, seconds, include_audio), 2)
