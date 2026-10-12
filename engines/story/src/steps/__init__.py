"""
Animation Series Pipeline Steps

Each step module exports a `run()` function with a consistent interface.
Steps are organized into pre-production (run once for the whole project)
and production (run per episode).
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai


@dataclass
class StepContext:
    """Shared context passed to every step."""
    project_dir: Path
    gemini_client: genai.Client
    episode_number: Optional[int] = None
    num_episodes: int = 1
    brief: str = ""  # Original user brief — used only by the Writer step
    progress_callback: Optional[Callable[[dict], None]] = None  # pushes WS messages mid-step
    # Set by the worker agent's cancel: long steps stop before their next paid call (StepCancelled).
    cancel_event: Optional[threading.Event] = None

    def check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise StepCancelled()

    @property
    def episode_dir(self) -> Path:
        """Directory for the current episode's artifacts."""
        if self.episode_number is None:
            raise ValueError("episode_number not set on StepContext")
        d = self.project_dir / "episodes" / f"episode_{self.episode_number}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def characters_dir(self) -> Path:
        d = self.project_dir / "characters"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def worlds_dir(self) -> Path:
        d = self.project_dir / "worlds"
        d.mkdir(parents=True, exist_ok=True)
        return d


class StepCancelled(Exception):
    """The run was cancelled; the step stops before its next paid call and is not marked complete."""


@dataclass
class StepResult:
    """Return value from a step's run() function."""
    artifact_paths: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


# ── Pre-production steps (run once for the whole project) ───────────────────
# Order: Writer → Screenwriter → Casting → World Builder
PRE_PRODUCTION_STEPS = [
    "writer",        # Brief → full story + character seeds + episode outlines
    "screenwriter",  # Story → all episodes scene breakdowns (one-shot)
    "casting",       # Scene breakdowns → character sheets + reference images
    "world_builder", # Scene breakdowns → world/location layout references
]

# ── Production steps (run once per episode, sequentially) ───────────────────
EPISODE_STEPS = [
    "director",         # Episode scenes + refs → final Veo prompts per shot
    "set_designer",     # Director shots + character/world refs → scene starting images
    "scene_generator",  # Veo prompt per shot → MP4 clip (sequential, rate-limited)
    "editor",           # Clips → assembled episode MP4
]
