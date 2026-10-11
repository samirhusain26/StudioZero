"""
Video Model Configuration Registry — Central source of truth for all supported
video generation models across providers (fal.ai, Vertex AI).

This module is pure configuration with no pipeline dependencies.
"""

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

VIDEO_MODEL_REGISTRY: Dict[str, VideoModelConfig] = {

    # ─── BUDGET TIER ────────────────────────────────────────────────────────

    "wan-2.5": VideoModelConfig(
        model_id="wan-2.5",
        provider="fal.ai",
        display_name="Wan 2.5",
        endpoint_t2v="fal-ai/wan2.5/v1/text-to-video",
        endpoint_i2v="fal-ai/wan2.5/v1/image-to-video",
        cost_per_second=0.05,
        max_resolution="480p",
        max_duration_sec=5,
        has_audio=False,
        has_reference_images=False,
        tier="cheapest",
        description="Cheapest option. 480p only — good for drafts and prompt testing.",
    ),
    "kling-2.5-turbo-pro": VideoModelConfig(
        model_id="kling-2.5-turbo-pro",
        provider="fal.ai",
        display_name="Kling 2.5 Turbo Pro",
        endpoint_t2v="fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
        endpoint_i2v="fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        cost_per_second=0.07,
        max_resolution="1080p",
        max_duration_sec=10,
        has_audio=False,
        has_reference_images=False,
        tier="cheapest",
        description="Best price-performance ratio. Excellent motion fluidity. No native audio.",
    ),
    "wan-2.2": VideoModelConfig(
        model_id="wan-2.2",
        provider="fal.ai",
        display_name="Wan 2.2",
        endpoint_t2v="fal-ai/wan-t2v",
        endpoint_i2v="fal-ai/wan-i2v",
        cost_per_second=0.10,
        max_resolution="720p",
        max_duration_sec=5,
        has_audio=False,
        has_reference_images=False,
        tier="cheapest",
        description="Open source (Alibaba). Budget option at 720p. No native audio.",
    ),

    # ─── RECOMMENDED TIER ───────────────────────────────────────────────────

    "seedance-1.5-pro-fast": VideoModelConfig(
        model_id="seedance-1.5-pro-fast",
        provider="fal.ai",
        display_name="Seedance 1.5 Pro Fast",
        endpoint_t2v="fal-ai/seedance/v1.5/pro/fast/text-to-video",
        endpoint_i2v="fal-ai/seedance/v1.5/pro/fast/image-to-video",
        cost_per_second=0.052,
        max_resolution="1080p",
        max_duration_sec=12,
        has_audio=True,
        has_reference_images=True,
        tier="recommended",
        description="ByteDance. Native audio + start/end frame control. Token-based pricing.",
    ),
    "seedance-2.0-fast": VideoModelConfig(
        model_id="seedance-2.0-fast",
        provider="fal.ai",
        display_name="Seedance 2.0 Fast",
        endpoint_t2v="bytedance/seedance-2.0/fast/text-to-video",
        endpoint_i2v="bytedance/seedance-2.0/fast/image-to-video",
        endpoint_ref2v="bytedance/seedance-2.0/fast/reference-to-video",
        cost_per_second=None,
        max_resolution="720p",
        max_duration_sec=15,
        has_audio=True,
        has_reference_images=True,
        tier="recommended",
        description="Newest model (Apr 2026). Multi-shot editing, native audio, reference-to-video with up to 9 images.",
    ),
    "veo-3.1-fast": VideoModelConfig(
        model_id="veo-3.1-fast",
        provider="gemini_api",
        display_name="Veo 3.1 Fast",
        endpoint_t2v="veo-3.1-fast-generate-preview",
        endpoint_i2v=None,
        cost_per_second=0.10,
        max_resolution="1080p",
        max_duration_sec=8,
        has_audio=True,
        has_reference_images=True,
        tier="recommended",
        description="Google Gemini API. Fast generation with reference images (up to 3). Audio included. $0.12/s at 1080p.",
    ),

    # ─── HIGH FIDELITY TIER ─────────────────────────────────────────────────

    "kling-3.0-pro": VideoModelConfig(
        model_id="kling-3.0-pro",
        provider="fal.ai",
        display_name="Kling 3.0 Pro",
        endpoint_t2v="fal-ai/kling-video/v3/pro/text-to-video",
        endpoint_i2v="fal-ai/kling-video/v3/pro/image-to-video",
        cost_per_second=0.224,
        max_resolution="1080p",
        max_duration_sec=15,
        has_audio=True,
        has_reference_images=True,
        tier="high_fidelity",
        description="Multi-shot sequences with subject consistency. Native audio. Art-house aesthetic.",
    ),
    "seedance-2.0": VideoModelConfig(
        model_id="seedance-2.0",
        provider="fal.ai",
        display_name="Seedance 2.0",
        endpoint_t2v="bytedance/seedance-2.0/text-to-video",
        endpoint_i2v="bytedance/seedance-2.0/image-to-video",
        endpoint_ref2v="bytedance/seedance-2.0/reference-to-video",
        cost_per_second=None,
        max_resolution="720p",
        max_duration_sec=15,
        has_audio=True,
        has_reference_images=True,
        tier="high_fidelity",
        description="Standard quality tier of Seedance 2.0. Higher quality than fast variant.",
    ),
    "veo-3.1": VideoModelConfig(
        model_id="veo-3.1",
        provider="gemini_api",
        display_name="Veo 3.1",
        endpoint_t2v="veo-3.1-generate-preview",
        endpoint_i2v=None,
        cost_per_second=0.40,
        max_resolution="4K",
        max_duration_sec=8,
        has_audio=True,
        has_reference_images=True,
        tier="high_fidelity",
        description="Google Gemini API. Best quality — cinematic video with lip-sync, audio, reference images. $0.60/s at 4K.",
    ),
    "sora-2-pro": VideoModelConfig(
        model_id="sora-2-pro",
        provider="fal.ai",
        display_name="Sora 2 Pro",
        endpoint_t2v="fal-ai/sora-2/pro",
        endpoint_i2v="fal-ai/sora-2/image-to-video/pro",
        cost_per_second=0.30,
        max_resolution="1080p",
        max_duration_sec=25,
        has_audio=True,
        has_reference_images=False,
        tier="high_fidelity",
        description="OpenAI. Best physics simulation. Longest clips (up to 25s). Most expensive.",
    ),

    # ─── GEMINI API BUDGET ──────────────────────────────────────────────────

    "veo-3.1-lite": VideoModelConfig(
        model_id="veo-3.1-lite",
        provider="gemini_api",
        display_name="Veo 3.1 Lite",
        endpoint_t2v="veo-3.1-lite-generate-preview",
        endpoint_i2v=None,
        cost_per_second=0.05,
        max_resolution="1080p",
        max_duration_sec=8,
        has_audio=True,
        has_reference_images=False,
        tier="cheapest",
        description="Google Gemini API. Cheapest Veo — 50% less than Fast. Audio included. $0.08/s at 1080p.",
    ),
}


# ── Tier defaults (used when no specific model is selected) ─────────────────

_TIER_DEFAULTS = {
    "cheapest": "veo-3.1-lite",
    "recommended": "veo-3.1-fast",
    "high_fidelity": "veo-3.1",
}

# ── Fallback order per tier (used by BudgetGuard / UnifiedVideoClient) ──────

TIER_FALLBACK_ORDER: Dict[str, List[str]] = {
    "cheapest": ["veo-3.1-lite", "wan-2.5", "kling-2.5-turbo-pro", "wan-2.2"],
    "recommended": ["veo-3.1-fast", "seedance-2.0-fast", "seedance-1.5-pro-fast"],
    "high_fidelity": ["veo-3.1", "kling-3.0-pro", "seedance-2.0", "sora-2-pro"],
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
