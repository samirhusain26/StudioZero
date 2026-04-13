"""
Animation Pipeline — Orchestrates the full story-to-video workflow.

Pipeline phases:
  Pre-Production (runs once for the whole project):
    1. writer          — Brief → full story + character seeds + episode outlines
    2. screenwriter    — Story → all episodes scene breakdowns (one-shot, for continuity)
    3. casting         — Scene breakdowns → character sheets + reference images
    4. world_builder   — Scene breakdowns → location layout references

  Production (runs per episode, strictly sequential):
    5. director        — Episode scenes + refs → final Veo prompts per shot
    6. scene_generator — Veo prompt per shot → MP4 clip (rate-limited, sequential)
    7. editor          — Clips → assembled episode MP4

State is persisted after every step for crash recovery and resume.
On Veo scene failure, the pipeline yields a status with retry_gate=True and
the failed scene's details, then stops. The caller is responsible for offering
the user a retry / prompt-edit flow before re-running.
"""

import importlib
import logging
from pathlib import Path
from typing import Generator, Optional

from google import genai as genai_lib

from src.config import Config
from src.pipeline_state import PipelineState, load_state, save_state
from src.steps import StepContext, StepResult, PRE_PRODUCTION_STEPS, EPISODE_STEPS
from src.steps.scene_generator import SceneGenerationError

logger = logging.getLogger(__name__)


def _load_step(step_name: str):
    return importlib.import_module(f"src.steps.{step_name}")


# Reuse PipelineStatus from the stock footage pipeline for consistency
from src.pipeline import PipelineStatus


def run_animation_pipeline(
    project_title: str,
    brief: str,
    num_episodes: int = 1,
    resume: bool = True,
    progress_callback=None,
    project_dir: Optional[Path] = None,
) -> Generator[PipelineStatus, None, Optional[str]]:
    """
    Run the full animation pipeline.

    Yields PipelineStatus updates at each step boundary.
    Returns the project directory path on completion.

    Args:
        project_title:  Name used for the output directory.
        brief:          User's 1-2 sentence story brief. Passed to the Writer agent.
        num_episodes:   Number of episodes to generate (each = multiple Veo scenes).
        resume:         If True (default), skip already-completed steps on re-run.
        project_dir:    Optional explicit project directory. If None, uses TEMP_DIR / safe_title.
    """
    Config.ensure_directories()

    if project_dir is None:
        safe_title = Config.safe_title(project_title)
        project_dir = Config.TEMP_DIR / safe_title
    project_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"[pipeline] Starting animation pipeline: '{project_title}' "
        f"— {num_episodes} episode(s), project dir: {project_dir}"
    )

    state = load_state(project_dir) if resume else None
    if state is None:
        state = PipelineState(project_title=project_title)
        save_state(state, project_dir)
        logger.info("[pipeline] New project — fresh pipeline state created")
    else:
        completed = [k for k, v in state.series_steps.items() if v.completed]
        logger.info(f"[pipeline] Resuming — already completed: {completed}")

    gemini_client = genai_lib.Client(api_key=Config.GEMINI_API_KEY)

    base_ctx = StepContext(
        project_dir=project_dir,
        gemini_client=gemini_client,
        num_episodes=num_episodes,
        brief=brief,
    )

    step_counter = 0

    # =========================================================================
    # Phase 1: Pre-production (runs once)
    # =========================================================================
    logger.info("[pipeline] === Phase 1: Pre-Production ===")

    for step_name in PRE_PRODUCTION_STEPS:
        step_counter += 1

        if state.is_completed(step_name):
            logger.info(f"[pipeline] [{step_name}] Already completed — skipping")
            yield PipelineStatus(
                step=step_counter,
                message=f"[{step_name}] Already completed, skipping",
            )
            continue

        logger.info(f"[pipeline] [{step_name}] Starting (step {step_counter})...")
        yield PipelineStatus(
            step=step_counter,
            message=f"[{step_name}] Starting...",
        )

        state.mark_started(step_name)
        save_state(state, project_dir)

        try:
            module = _load_step(step_name)
            result: StepResult = module.run(base_ctx)

            state.mark_completed(step_name, artifact_paths=result.artifact_paths)
            save_state(state, project_dir)

            logger.info(
                f"[pipeline] [{step_name}] Complete — "
                f"{len(result.artifact_paths)} artifact(s)"
            )
            yield PipelineStatus(
                step=step_counter,
                message=f"[{step_name}] Complete — {len(result.artifact_paths)} artifact(s)",
                data=result.data,
            )

        except Exception as e:
            state.mark_failed(step_name, str(e))
            save_state(state, project_dir)
            logger.error(f"[pipeline] [{step_name}] FAILED: {e}", exc_info=True)
            yield PipelineStatus(
                step=step_counter,
                message=f"[{step_name}] Failed: {e}",
                is_error=True,
            )
            return None

    # =========================================================================
    # Phase 2: Production — per episode
    # =========================================================================
    logger.info(f"[pipeline] === Phase 2: Production — {num_episodes} episode(s) ===")

    for ep_num in range(1, num_episodes + 1):
        logger.info(f"[pipeline] --- Episode {ep_num}/{num_episodes} ---")
        yield PipelineStatus(
            step=step_counter + 1,
            message=f"--- Episode {ep_num}/{num_episodes} ---",
        )

        ep_ctx = StepContext(
            project_dir=project_dir,
            gemini_client=gemini_client,
            episode_number=ep_num,
            num_episodes=num_episodes,
            brief=brief,
            progress_callback=progress_callback,
        )

        for step_name in EPISODE_STEPS:
            step_counter += 1

            if state.is_completed(step_name, episode_number=ep_num):
                logger.info(f"[pipeline] [ep{ep_num}/{step_name}] Already completed — skipping")
                yield PipelineStatus(
                    step=step_counter,
                    message=f"[ep{ep_num}/{step_name}] Already completed, skipping",
                )
                continue

            logger.info(f"[pipeline] [ep{ep_num}/{step_name}] Starting (step {step_counter})...")
            yield PipelineStatus(
                step=step_counter,
                message=f"[ep{ep_num}/{step_name}] Starting...",
            )

            state.mark_started(step_name, episode_number=ep_num)
            save_state(state, project_dir)

            try:
                module = _load_step(step_name)
                result: StepResult = module.run(ep_ctx)

                state.mark_completed(step_name, episode_number=ep_num, artifact_paths=result.artifact_paths)
                save_state(state, project_dir)

                logger.info(
                    f"[pipeline] [ep{ep_num}/{step_name}] Complete — "
                    f"{len(result.artifact_paths)} artifact(s)"
                )
                yield PipelineStatus(
                    step=step_counter,
                    message=f"[ep{ep_num}/{step_name}] Complete — {len(result.artifact_paths)} artifact(s)",
                    data=result.data,
                )

            except SceneGenerationError as e:
                # Special case: Veo scene failure — offer retry/edit to the user
                state.mark_failed(step_name, str(e), episode_number=ep_num)
                save_state(state, project_dir)

                logger.error(
                    f"[pipeline] [ep{ep_num}/{step_name}] Veo scene {e.scene_id} failed — "
                    f"pausing for user action. Error: {e.original_error}"
                )
                yield PipelineStatus(
                    step=step_counter,
                    message=(
                        f"[ep{ep_num}] Scene {e.scene_id} failed: {e.original_error}\n"
                        f"Options: retry | edit prompt | skip"
                    ),
                    is_error=True,
                    retry_gate=True,
                    data={
                        "episode_number": ep_num,
                        "scene_id": e.scene_id,
                        "veo_prompt": e.veo_prompt,
                        "project_dir": str(project_dir),
                        "override_file": str(
                            project_dir / "episodes" / f"episode_{ep_num}"
                            / "clips" / f"scene_{e.scene_id}_override.txt"
                        ),
                        "skip_marker": str(
                            project_dir / "episodes" / f"episode_{ep_num}"
                            / "clips" / f"scene_{e.scene_id}.skip"
                        ),
                    },
                )
                return None

            except Exception as e:
                state.mark_failed(step_name, str(e), episode_number=ep_num)
                save_state(state, project_dir)
                logger.error(f"[pipeline] [ep{ep_num}/{step_name}] FAILED: {e}", exc_info=True)
                yield PipelineStatus(
                    step=step_counter,
                    message=f"[ep{ep_num}/{step_name}] Failed: {e}",
                    is_error=True,
                )
                return None

    logger.info(
        f"[pipeline] Animation pipeline complete — "
        f"{num_episodes} episode(s) generated in {project_dir}"
    )
    yield PipelineStatus(
        step=step_counter + 1,
        message=f"Animation complete! {num_episodes} episode(s) generated.",
        data={"project_dir": str(project_dir)},
    )

    return str(project_dir)
