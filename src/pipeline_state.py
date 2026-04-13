"""
Pipeline State Manager — Persistent step-level tracking with crash recovery.

Inspired by ShortGPT's step-based persistence and Verticals' JSON-embedded state.
Each step's completion is recorded so the pipeline can resume from the last
successful step after a crash.
"""

import json
import logging
import os
import tempfile
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

    Series-level steps (writer, screenwriter, casting, world_builder) run once.
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
    """
    Load pipeline state from disk.

    Returns None only if the state file does not exist (normal fresh-start case).
    Raises RuntimeError if the file exists but is corrupt — this prevents a silent
    full re-run that would re-bill Veo for already-rendered clips.
    """
    state_file = project_dir / "pipeline_state.json"
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return PipelineState.model_validate(data)
    except Exception as e:
        raise RuntimeError(
            f"pipeline_state.json exists but is corrupt and cannot be loaded: {e}\n"
            f"File: {state_file}\n"
            f"To start fresh, delete the file manually or delete the project and recreate it."
        ) from e


def save_state(state: PipelineState, project_dir: Path):
    """
    Atomically persist pipeline state to disk.

    Writes to a temp file in the same directory then renames to the target,
    ensuring the state file is never left in a partial/truncated state if the
    process is killed during a write (e.g. during a long Veo polling loop).
    """
    state_file = project_dir / "pipeline_state.json"
    fd, tmp_path = tempfile.mkstemp(dir=project_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))
        os.replace(tmp_path, state_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
