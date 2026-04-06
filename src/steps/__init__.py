"""
Animation Series Pipeline Steps

Each step module exports a `run()` function with a consistent interface.
Steps are organized into series-level (run once) and episode-level (run per episode).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai


@dataclass
class StepContext:
    """Shared context passed to every step."""
    project_dir: Path
    gemini_client: genai.Client
    episode_number: Optional[int] = None
    num_episodes: int = 3
    storyline: str = ""
    character_descriptions: str = ""

    @property
    def episode_dir(self) -> Path:
        """Directory for the current episode's artifacts."""
        if self.episode_number is None:
            raise ValueError("episode_number not set")
        d = self.project_dir / "episodes" / f"episode_{self.episode_number}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def characters_dir(self) -> Path:
        d = self.project_dir / "characters"
        d.mkdir(parents=True, exist_ok=True)
        return d


@dataclass
class StepResult:
    """Return value from a step's run() function."""
    artifact_paths: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


# Step ordering — series-level steps run once, episode steps run per-episode
SERIES_STEPS = ["world_builder", "character_designer"]
EPISODE_STEPS = [
    "episode_writer",
    "storyboard",
    "voice_director",
    "scene_generator",
    "sound_designer",
    "editor",
    "publisher",
]
