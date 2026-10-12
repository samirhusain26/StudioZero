"""
Cost estimates before a run ($0: list prices times typical usage, no network).

Shared by the worker agent (GET …/estimate, which the owner confirms before a paid run)
and the CLI (`python -m src.cli --headless … --estimate`). Prices: src/pricing.py (text,
image, TTS) and registry.json (video). Usage figures are deliberately on the high side.
"""

from typing import List, Optional, Tuple

from src.config import Config
from src.pricing import AUDIO_TOKENS_PER_SECOND, image_cost, text_cost, tts_cost
from src.video_models import clip_duration, estimate_cost, get_model

SHOTS_PER_EPISODE = 6  # episodes whose director step has not run yet
CAST_SIZE = 3  # characters and locations assumed before the writer has run
IMAGE_PROMPT_TOKENS = 1500  # prompt plus reference images sent with an image request
NARRATION_WORDS_PER_SECOND = 2.5
TYPICAL_RECAP_WORDS = 7 * 30  # six scenes and the ending, about 30 words each
SCRIPT_TOKENS = (5000, 3000)  # plot + instructions in, the JSON script out


def text_line(what: str, calls: int, tokens_in: int, tokens_out: int) -> dict:
    usd, assumed = text_cost(Config.GEMINI_MODEL_NAME, calls * tokens_in, calls * tokens_out)
    return {"what": f"{what} ({Config.GEMINI_MODEL_NAME}{', price assumed' if assumed else ''})", "usd": round(usd, 4)}


def image_line(what: str, images: int) -> dict:
    usd, assumed = image_cost(Config.GEMINI_IMAGE_MODEL, images * IMAGE_PROMPT_TOKENS, images)
    return {"what": f"{what} ({Config.GEMINI_IMAGE_MODEL}{', price assumed' if assumed else ''})", "usd": round(usd, 4)}


def narration_line(words: int, scenes: int) -> dict:
    seconds = words / NARRATION_WORDS_PER_SECOND
    usd, assumed = tts_cost(Config.TTS_MODEL, words * 2 + 200 * scenes, int(seconds * AUDIO_TOKENS_PER_SECOND))
    return {"what": f"Narration, about {seconds:.0f} s ({Config.TTS_MODEL}{', price assumed' if assumed else ''})",
            "usd": round(usd, 4)}


def recap_lines(approved_script: Optional[dict] = None, whole_run: bool = False) -> Tuple[List[dict], List[str]]:
    """
    (lines, unpriced) for a recap run. With an approved script: its narration. Otherwise the
    script; `whole_run` (the CLI, which has no review gate) adds a typical narration too.
    """
    if approved_script:
        scenes = approved_script.get("scenes", [])
        words = sum(len(str(sc.get("narration", "")).split()) for sc in scenes) + 12  # + the ending line
        return [narration_line(words, len(scenes) + 1)], []
    lines = [text_line("Recap script", 1, *SCRIPT_TOKENS)]
    if whole_run:
        return lines + [narration_line(TYPICAL_RECAP_WORDS, 7)], []
    return lines, ["then, after you approve the script, the narration (estimated on the next run)"]


def series_lines(model_id: str, episodes: int, state: Optional[dict] = None,
                 remaining_clips: Optional[int] = None) -> List[dict]:
    """Lines for a series run: pre-production not done yet, shot lists, scene starts and clips."""
    state = state or {}
    model = get_model(model_id)
    audio = Config.SERIES_NATIVE_AUDIO and model.has_audio
    done = lambda step: bool((state.get("series_steps") or {}).get(step, {}).get("completed"))  # noqa: E731
    todo_eps = [ep for ep in range(1, episodes + 1)
                if not (state.get("episodes") or {}).get(str(ep), {}).get("steps", {}).get("director", {}).get("completed")]
    lines: List[dict] = []
    if not done("writer") or not done("screenwriter"):
        lines.append(text_line("Story and episode scripts", 2, 6000, 6000))
    if not done("casting"):
        lines += [text_line(f"Character sheets (about {CAST_SIZE})", CAST_SIZE, 3000, 1500),
                  image_line(f"Character reference images (about {CAST_SIZE})", CAST_SIZE)]
    if not done("world_builder"):
        lines += [text_line(f"Location layouts (about {CAST_SIZE})", CAST_SIZE, 3000, 1500),
                  image_line(f"Location reference images (about {CAST_SIZE})", CAST_SIZE)]
    if todo_eps:
        lines += [text_line(f"Shot lists for {len(todo_eps)} episode(s)", len(todo_eps), 8000, 4000),
                  image_line(f"Scene start images (about {SHOTS_PER_EPISODE} per episode)", SHOTS_PER_EPISODE * len(todo_eps))]
    clips = SHOTS_PER_EPISODE * episodes if remaining_clips is None else remaining_clips
    if clips:
        seconds = clip_duration(model_id)
        per = estimate_cost(model_id, seconds, audio)
        lines.append({"what": f"{clips} video clip(s) with {model.display_name}, {seconds} s each"
                              + (" with native audio" if audio else ""), "usd": round(per * clips, 4)})
    return lines


def total(lines: List[dict]) -> float:
    return round(sum(line["usd"] for line in lines), 4)
