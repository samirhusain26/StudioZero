"""
Animation Series Pipeline — 9-step sequential pipeline with crash recovery.

Orchestrates the full animation series generation workflow:
  Series-level (run once):
    1. World Builder — Series Bible
    2. Character Designer — Reference images

  Per-episode (run for each episode):
    3. Episode Writer — Script
    4. Storyboard — Shot planning + Veo prompts
    5. Voice Director — TTS audio
    6. Scene Generator — Veo 3.1 video clips
    7. Sound Designer — Background music
    8. Editor — Final assembly
    9. Publisher — Marketing materials

State is persisted after each step, enabling resume from any failure point.
"""

import importlib
import logging
from pathlib import Path
from typing import Generator, Optional, Tuple

from google import genai as genai_lib

from src.config import Config
from src.pipeline_state import PipelineState, load_state, save_state
from src.steps import StepContext, StepResult, SERIES_STEPS, EPISODE_STEPS

logger = logging.getLogger(__name__)


# Import step modules lazily by name
def _get_step_module(step_name: str):
    return importlib.import_module(f"src.steps.{step_name}")


# Reuse PipelineStatus from existing pipeline for consistency
from src.pipeline import PipelineStatus


def run_animation_series(
    project_title: str,
    storyline: str,
    character_descriptions: str,
    num_episodes: int = 3,
    resume: bool = True,
) -> Generator[PipelineStatus, None, Optional[str]]:
    """
    Run the full 9-step animation series pipeline.

    Yields PipelineStatus updates at each step boundary.
    Returns the project directory path on completion.

    Args:
        project_title: Name of the project (used for directory naming).
        storyline: High-level storyline for the series.
        character_descriptions: Descriptions of the characters.
        num_episodes: Number of episodes to generate.
        resume: If True, resume from last completed step (default).
    """
    Config.ensure_directories()

    # Setup project directory
    safe_title = Config.safe_title(project_title)
    project_dir = Config.TEMP_DIR / safe_title
    project_dir.mkdir(parents=True, exist_ok=True)

    # Load or create pipeline state
    state = load_state(project_dir) if resume else None
    if state is None:
        state = PipelineState(project_title=project_title)
        save_state(state, project_dir)

    # Initialize Gemini client
    gemini_client = genai_lib.Client(api_key=Config.GEMINI_API_KEY)

    # Base context (episode_number set per-episode)
    base_ctx = StepContext(
        project_dir=project_dir,
        gemini_client=gemini_client,
        num_episodes=num_episodes,
        storyline=storyline,
        character_descriptions=character_descriptions,
    )

    step_counter = 0

    # =================================================================
    # Phase 1: Series-level steps (run once)
    # =================================================================
    for step_name in SERIES_STEPS:
        step_counter += 1

        if state.is_completed(step_name):
            yield PipelineStatus(
                step=step_counter,
                message=f"[{step_name}] Already completed, skipping",
            )
            continue

        yield PipelineStatus(
            step=step_counter,
            message=f"[{step_name}] Starting...",
        )

        state.mark_started(step_name)
        save_state(state, project_dir)

        try:
            module = _get_step_module(step_name)
            result: StepResult = module.run(base_ctx)

            state.mark_completed(step_name, artifact_paths=result.artifact_paths)
            save_state(state, project_dir)

            yield PipelineStatus(
                step=step_counter,
                message=f"[{step_name}] Complete — {len(result.artifact_paths)} artifact(s)",
                data=result.data,
            )
        except Exception as e:
            state.mark_failed(step_name, str(e))
            save_state(state, project_dir)
            yield PipelineStatus(
                step=step_counter,
                message=f"[{step_name}] Failed: {e}",
                is_error=True,
            )
            return None

    # =================================================================
    # Phase 2: Per-episode steps
    # =================================================================
    for ep_num in range(1, num_episodes + 1):
        yield PipelineStatus(
            step=step_counter + 1,
            message=f"--- Episode {ep_num}/{num_episodes} ---",
        )

        ep_ctx = StepContext(
            project_dir=project_dir,
            gemini_client=gemini_client,
            episode_number=ep_num,
            num_episodes=num_episodes,
            storyline=storyline,
            character_descriptions=character_descriptions,
        )

        for step_name in EPISODE_STEPS:
            step_counter += 1

            if state.is_completed(step_name, episode_number=ep_num):
                yield PipelineStatus(
                    step=step_counter,
                    message=f"[ep{ep_num}/{step_name}] Already completed, skipping",
                )
                continue

            yield PipelineStatus(
                step=step_counter,
                message=f"[ep{ep_num}/{step_name}] Starting...",
            )

            state.mark_started(step_name, episode_number=ep_num)
            save_state(state, project_dir)

            try:
                module = _get_step_module(step_name)
                result: StepResult = module.run(ep_ctx)

                state.mark_completed(step_name, episode_number=ep_num, artifact_paths=result.artifact_paths)
                save_state(state, project_dir)

                yield PipelineStatus(
                    step=step_counter,
                    message=f"[ep{ep_num}/{step_name}] Complete — {len(result.artifact_paths)} artifact(s)",
                    data=result.data,
                )
            except Exception as e:
                state.mark_failed(step_name, str(e), episode_number=ep_num)
                save_state(state, project_dir)
                yield PipelineStatus(
                    step=step_counter,
                    message=f"[ep{ep_num}/{step_name}] Failed: {e}",
                    is_error=True,
                )
                return None

    yield PipelineStatus(
        step=step_counter + 1,
        message=f"Animation series complete! {num_episodes} episodes generated.",
        data={"project_dir": str(project_dir)},
    )

    return str(project_dir)
