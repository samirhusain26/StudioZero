"""
Prices and spend metering for the story engine's text, image and speech calls.

Every Gemini (and Groq fallback) call reports its usage here: `charge(...)` prices it
and appends an entry to the active SpendLedger (budget_guard.py), so a project's
spend_ledger.json counts LLM, image and TTS spend next to video, and render.json's
costUsd covers all of it. Video generations are priced from registry.json
(video_models.py) and recorded by the scene generator.

Prices are USD per 1M tokens (images per image), Standard paid tier, checked on
PRICES_CHECKED against the sources in PRICE_SOURCES. A model missing from the table
is charged at the table's highest rate for its kind and marked as assumed, so an
unknown model is never priced at $0.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

PRICES_CHECKED = "2026-10-12"
PRICE_SOURCES = {
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
    "groq": "https://console.groq.com/docs/pricing",
}

# model id -> (input per 1M tokens, output per 1M tokens)
TEXT_PRICES = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),  # Groq (fallback script model)
}
# image model id -> (input per 1M tokens, USD per output image)
IMAGE_PRICES = {
    "gemini-2.5-flash-image": (0.30, 0.039),
    "gemini-3-pro-image-preview": (2.00, 0.134),
}
# TTS model id -> (text input per 1M tokens, audio output per 1M tokens)
TTS_PRICES = {
    "gemini-2.5-flash-preview-tts": (0.50, 10.00),
    "gemini-2.5-pro-preview-tts": (1.00, 20.00),
}
AUDIO_TOKENS_PER_SECOND = 25  # Gemini TTS output (pricing page footnote)
CHARS_PER_TOKEN = 4  # rough text size when a response reports no usage


def _rates(table: dict, model: str) -> tuple:
    """(rates, assumed): the model's rates, or the table's highest for an unknown model."""
    if model in table:
        return table[model], False
    return tuple(max(r[i] for r in table.values()) for i in range(2)), True


def text_cost(model: str, input_tokens: int, output_tokens: int) -> tuple:
    (rin, rout), assumed = _rates(TEXT_PRICES, model)
    return round((input_tokens * rin + output_tokens * rout) / 1e6, 6), assumed


def image_cost(model: str, input_tokens: int, images: int) -> tuple:
    (rin, per_image), assumed = _rates(IMAGE_PRICES, model)
    return round(input_tokens * rin / 1e6 + images * per_image, 6), assumed


def tts_cost(model: str, input_tokens: int, audio_tokens: int) -> tuple:
    (rin, rout), assumed = _rates(TTS_PRICES, model)
    return round((input_tokens * rin + audio_tokens * rout) / 1e6, 6), assumed


def usage_of(response) -> dict:
    """Token counts from a google-genai response (zeros when absent)."""
    meta = getattr(response, "usage_metadata", None)
    get = lambda name: int(getattr(meta, name, 0) or 0) if meta is not None else 0  # noqa: E731
    return {"inputTokens": get("prompt_token_count"), "outputTokens": get("candidates_token_count")}


def images_in(response) -> int:
    """Number of inline images a google-genai response carries."""
    count = 0
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                count += 1
    return count


# ── The active ledger (one run at a time per process: the CLI or the worker's busy lock) ──

_lock = threading.Lock()
_active = {"ledger": None, "episode": None}


class charging:
    """Context manager: charge every call inside it to `ledger` (episode optional)."""

    def __init__(self, ledger, episode: Optional[int] = None):
        self.ledger, self.episode = ledger, episode

    def __enter__(self):
        with _lock:
            self._saved = dict(_active)
            _active.update(ledger=self.ledger, episode=self.episode)
        return self

    def __exit__(self, *exc):
        with _lock:
            _active.update(self._saved)
        return False


def set_episode(episode: Optional[int]) -> None:
    with _lock:
        _active["episode"] = episode


def charge(kind: str, model: str, what: str, *, input_tokens: int = 0, output_tokens: int = 0,
           images: int = 0, audio_seconds: float = 0.0, estimated: bool = False) -> float:
    """Price one call and record it in the active ledger (if any). Returns the cost in USD."""
    if kind == "llm":
        cost, assumed = text_cost(model, input_tokens, output_tokens)
    elif kind == "image":
        cost, assumed = image_cost(model, input_tokens, images)
    elif kind == "tts":
        audio_tokens = output_tokens or int(round(audio_seconds * AUDIO_TOKENS_PER_SECOND))
        estimated = estimated or not output_tokens
        cost, assumed = tts_cost(model, input_tokens, audio_tokens)
        output_tokens = audio_tokens
    else:
        raise ValueError(f"unknown kind {kind}")
    with _lock:
        ledger, episode = _active["ledger"], _active["episode"]
    if ledger is not None:
        ledger.record_usage(kind=kind, model_id=model, what=what, episode=episode, cost_usd=cost,
                            units={"inputTokens": input_tokens, "outputTokens": output_tokens, "images": images,
                                   "audioSeconds": round(audio_seconds, 3)},
                            estimated=estimated or assumed, price_assumed=assumed)
    logger.info(f"[pricing] {kind} {model} ({what}): ${cost:.4f}" + (" (price assumed)" if assumed else ""))
    return cost


def charge_genai(response, kind: str, model: str, what: str, prompt_text: str = "", audio_seconds: float = 0.0) -> float:
    """charge() from a google-genai response's usage metadata (estimated from the text when absent)."""
    u = usage_of(response)
    estimated = False
    if not u["inputTokens"] and prompt_text:
        u["inputTokens"], estimated = max(1, len(prompt_text) // CHARS_PER_TOKEN), True
    images = images_in(response) if kind == "image" else 0
    output = u["outputTokens"] if kind != "image" else 0
    if kind == "llm" and not output:
        text = getattr(response, "text", None) if kind == "llm" else None
        try:
            output = max(1, len(text or "") // CHARS_PER_TOKEN)
        except Exception:  # noqa: BLE001 (text accessor may raise on blocked responses)
            output = 0
        estimated = True
    return charge(kind, model, what, input_tokens=u["inputTokens"], output_tokens=output, images=images,
                  audio_seconds=audio_seconds, estimated=estimated)
