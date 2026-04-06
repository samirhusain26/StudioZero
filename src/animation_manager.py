import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from src.config import Config
from src.narrative import AnimationProject

logger = logging.getLogger(__name__)

class EpisodeStatus(BaseModel):
    """Status of an individual episode."""
    episode_number: int
    status: str = Field(default="pending")  # pending, rendering, completed, failed
    output_path: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

class ProjectLog(BaseModel):
    """Tracking log for an animation project."""
    project_title: str
    episode_statuses: List[EpisodeStatus] = []

class AnimationManager:
    """Manages the persistence and state of animation projects."""

    def __init__(self, project_name: str):
        self.project_name = Config.safe_title(project_name)
        self.project_dir = Config.TEMP_DIR / self.project_name
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.project_file = self.project_dir / "project.json"
        self.log_file = self.project_dir / "project_log.json"

    def save_project(self, project: AnimationProject):
        """Save the full animation project script."""
        with open(self.project_file, "w", encoding="utf-8") as f:
            json.dump(project.model_dump(), f, indent=2, ensure_ascii=False)
        
        # Initialize log if not exists
        if not self.log_file.exists():
            episode_statuses = [
                EpisodeStatus(episode_number=ep.episode_number)
                for ep in project.episodes
            ]
            log = ProjectLog(project_title=project.project_title, episode_statuses=episode_statuses)
            self.save_log(log)
            
        logger.info(f"Animation project saved to {self.project_file}")

    def load_project(self) -> Optional[AnimationProject]:
        """Load the animation project script."""
        if not self.project_file.exists():
            return None
        with open(self.project_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return AnimationProject.model_validate(data)

    def save_log(self, log: ProjectLog):
        """Save the project progress log."""
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(log.model_dump(), f, indent=2, ensure_ascii=False)

    def load_log(self) -> Optional[ProjectLog]:
        """Load the project progress log."""
        if not self.log_file.exists():
            return None
        with open(self.log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ProjectLog.model_validate(data)

    def update_episode_status(self, episode_number: int, status: str, output_path: Optional[str] = None, error: Optional[str] = None):
        """Update the status of a specific episode in the log."""
        log = self.load_log()
        if not log:
            return

        from datetime import datetime
        timestamp = datetime.now().isoformat()

        for ep_status in log.episode_statuses:
            if ep_status.episode_number == episode_number:
                ep_status.status = status
                if status == "rendering":
                    ep_status.started_at = timestamp
                elif status == "completed":
                    ep_status.completed_at = timestamp
                    ep_status.output_path = output_path
                elif status == "failed":
                    ep_status.completed_at = timestamp
                    ep_status.error = error
                break
        
        self.save_log(log)

    def get_next_pending_episode(self) -> Optional[int]:
        """Find the next episode number that hasn't been completed."""
        log = self.load_log()
        if not log:
            return None
        
        for ep_status in log.episode_statuses:
            if ep_status.status == "pending" or ep_status.status == "failed":
                return ep_status.episode_number
        return None

    @staticmethod
    def list_projects() -> List[str]:
        """List all existing animation projects."""
        projects = []
        if Config.TEMP_DIR.exists():
            for d in Config.TEMP_DIR.iterdir():
                if d.is_dir() and (d / "project.json").exists():
                    projects.append(d.name)
        return projects

    @staticmethod
    def find_project_by_theme(theme: str) -> Optional[str]:
        """
        Find a project name by matching the original theme/movie name.
        Checks saved project.json files for matching theme or storyline fields.
        Falls back to safe_title matching.

        Returns:
            The project directory name if found, or None.
        """
        safe_theme = Config.safe_title(theme)

        # First try direct safe_title match
        direct_path = Config.TEMP_DIR / safe_theme
        if direct_path.exists() and (direct_path / "project.json").exists():
            return safe_theme

        # Search all projects for matching theme/storyline
        if Config.TEMP_DIR.exists():
            for d in Config.TEMP_DIR.iterdir():
                if not d.is_dir() or not (d / "project.json").exists():
                    continue
                try:
                    with open(d / "project.json", "r", encoding="utf-8") as f:
                        data = json.load(f)
                    storyline = data.get("storyline", "")
                    if (safe_theme.lower() in d.name.lower() or
                            theme.lower() in storyline.lower()):
                        return d.name
                except (json.JSONDecodeError, IOError):
                    continue
        return None
