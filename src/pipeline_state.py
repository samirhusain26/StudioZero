"""
Pipeline State Manager — Persistent step-level tracking with crash recovery.

Inspired by ShortGPT's step-based persistence and Verticals' JSON-embedded state.
Each step's completion is recorded so the pipeline can resume from the last
successful step after a crash.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StepStatus(BaseModel):
    """Status of a single pipeline step."""
    step_name: str
    completed: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    artifact_paths: List[str] = Field(default_factory=list)


class EpisodeState(BaseModel):
    """Tracks step completion for a single episode."""
    episode_number: int
    steps: Dict[str, StepStatus] = Field(default_factory=dict)

    def get_step(self, step_name: str) -> StepStatus:
        if step_name not in self.steps:
            self.steps[step_name] = StepStatus(step_name=step_name)
        return self.steps[step_name]


class PipelineState(BaseModel):
    """
    Full pipeline state for an animation series project.

    Series-level steps (world_builder, character_designer) run once.
    Episode-level steps run per-episode.
    """
    project_title: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    series_steps: Dict[str, StepStatus] = Field(default_factory=dict)
    episodes: Dict[int, EpisodeState] = Field(default_factory=dict)

    def get_series_step(self, step_name: str) -> StepStatus:
        if step_name not in self.series_steps:
            self.series_steps[step_name] = StepStatus(step_name=step_name)
        return self.series_steps[step_name]

    def get_episode(self, episode_number: int) -> EpisodeState:
        if episode_number not in self.episodes:
            self.episodes[episode_number] = EpisodeState(episode_number=episode_number)
        return self.episodes[episode_number]

    def mark_started(self, step_name: str, episode_number: Optional[int] = None):
        """Mark a step as started."""
        step = (
            self.get_episode(episode_number).get_step(step_name)
            if episode_number is not None
            else self.get_series_step(step_name)
        )
        step.started_at = datetime.now(timezone.utc).isoformat()
        step.completed = False
        step.error = None

    def mark_completed(
        self,
        step_name: str,
        episode_number: Optional[int] = None,
        artifact_paths: Optional[List[str]] = None,
    ):
        """Mark a step as completed with optional artifact paths."""
        step = (
            self.get_episode(episode_number).get_step(step_name)
            if episode_number is not None
            else self.get_series_step(step_name)
        )
        step.completed = True
        step.completed_at = datetime.now(timezone.utc).isoformat()
        step.error = None
        if artifact_paths:
            step.artifact_paths = artifact_paths

    def mark_failed(self, step_name: str, error: str, episode_number: Optional[int] = None):
        """Mark a step as failed with error message."""
        step = (
            self.get_episode(episode_number).get_step(step_name)
            if episode_number is not None
            else self.get_series_step(step_name)
        )
        step.completed = False
        step.error = error

    def is_completed(self, step_name: str, episode_number: Optional[int] = None) -> bool:
        """Check if a step has been completed."""
        step = (
            self.get_episode(episode_number).get_step(step_name)
            if episode_number is not None
            else self.get_series_step(step_name)
        )
        return step.completed


def load_state(project_dir: Path) -> Optional[PipelineState]:
    """Load pipeline state from disk, or return None if no state file exists."""
    state_file = project_dir / "pipeline_state.json"
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return PipelineState.model_validate(data)
    except Exception as e:
        logger.warning(f"Failed to load pipeline state: {e}")
        return None


def save_state(state: PipelineState, project_dir: Path):
    """Persist pipeline state to disk."""
    state_file = project_dir / "pipeline_state.json"
    state_file.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
