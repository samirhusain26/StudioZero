"""
Project Manager — CRUD and state persistence for StudioZero projects.

Each project lives in output/projects/{safe_name}/ with a project.json
that tracks mode, parameters, current pipeline step, and timestamps.
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.config import Config

logger = logging.getLogger(__name__)


class Project(BaseModel):
    """Persistent project state."""
    id: str  # safe directory name
    name: str  # display name
    mode: str  # "movie", "animated", "animation-series"
    params: Dict[str, Any] = Field(default_factory=dict)
    current_step: Optional[str] = None
    status: str = "created"  # created | running | paused | completed | error
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    step_data: Dict[str, Any] = Field(default_factory=dict)  # step outputs keyed by step name
    error: Optional[str] = None


def _project_dir(project_id: str) -> Path:
    return Config.PROJECTS_DIR / project_id


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def list_projects() -> List[Project]:
    """List all projects sorted by most recent first."""
    Config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects = []
    for p in Config.PROJECTS_DIR.iterdir():
        pf = p / "project.json"
        if p.is_dir() and pf.exists():
            try:
                projects.append(Project.model_validate_json(pf.read_text()))
            except Exception as e:
                logger.warning(f"Skipping corrupt project {p.name}: {e}")
    projects.sort(key=lambda x: x.updated_at, reverse=True)
    return projects


def get_project(project_id: str) -> Optional[Project]:
    pf = _project_file(project_id)
    if not pf.exists():
        return None
    return Project.model_validate_json(pf.read_text())


_VALID_MODES = {"movie", "animation-series"}


def create_project(name: str, mode: str, params: Dict[str, Any] | None = None) -> Project:
    """Create a new project directory and state file."""
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}"
        )

    project_id = Config.safe_title(name)
    if not project_id:
        raise ValueError("Project name produces empty ID")

    if _project_file(project_id).exists():
        raise ValueError(
            f"A project named '{name}' already exists (id: '{project_id}'). "
            f"Choose a different name or delete the existing project first."
        )

    proj_dir = _project_dir(project_id)
    proj_dir.mkdir(parents=True, exist_ok=True)

    project = Project(
        id=project_id,
        name=name,
        mode=mode,
        params=params or {},
    )
    _save(project)
    return project


def update_project(project: Project) -> Project:
    """Persist updated project state."""
    project.updated_at = datetime.now(timezone.utc).isoformat()
    _save(project)
    return project


def delete_project(project_id: str) -> bool:
    proj_dir = _project_dir(project_id)
    if not proj_dir.exists():
        return False
    shutil.rmtree(proj_dir)
    # Also remove the animation pipeline temp directory so a new project
    # with the same name starts fresh instead of resuming old state.
    temp_dir = Config.TEMP_DIR / project_id
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    return True


def get_project_dir(project_id: str) -> Path:
    """Return the project's directory path, ensuring it exists."""
    d = _project_dir(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(project: Project):
    pf = _project_file(project.id)
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(project.model_dump_json(indent=2))
