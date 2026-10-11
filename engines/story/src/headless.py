"""
Headless (non-interactive) runner for StudioZero pipelines.

Extracted from the original app.py CLI. Used by:
  - cli.py --headless  (backwards-compatible CLI)
  - batch_runner.py    (Google Sheets automation)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple, List

from src.logging_utils import setup_logging
from src.pipeline import VideoGenerationPipeline, PipelineStatus, SceneAssets

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    """Configuration for a single headless pipeline run."""
    movie: str
    mode: str = "movie"
    offline: bool = False
    assets_only: bool = False
    clean: bool = False
    verbose: bool = False
    storyline: Optional[str] = None
    character_descriptions: Optional[str] = None
    num_episodes: int = 3
    episode_number: Optional[int] = None
    no_resume: bool = False
    output: Optional[str] = None


def print_banner():
    """Print a simple startup banner."""
    print("\n" + "=" * 60)
    print("  StudioZero - AI Movie Video Generator")
    print("  Modular Pipeline with Parallel Processing")
    print("=" * 60 + "\n")


def print_scene_assets(scene_assets: list, script=None):
    """Print a summary of generated scene assets."""
    if not scene_assets:
        return

    print("\n" + "-" * 60)
    print("  GENERATED ASSETS SUMMARY")
    print("-" * 60)

    if script:
        print(f"\n  Genre: {script.genre}")
        print(f"  Voice: {script.selected_voice_id}")
        print(f"  Music: {script.selected_music_file}")
        print(f"  BPM: {script.bpm}")

    for asset in scene_assets:
        print(f"\n  Scene {asset.index}:")
        narration_preview = asset.narration[:60] + "..." if len(asset.narration) > 60 else asset.narration
        print(f"    Narration: {narration_preview}")
        print(f"    Visuals:   {', '.join(asset.visual_queries[:2])}...")
        print(f"    Audio:     {asset.audio_path} ({asset.audio_duration:.2f}s)")
        print(f"    Video:     {asset.video_path}")

    print("\n" + "-" * 60 + "\n")


def consume_generator(gen, log: logging.Logger, assets_only: bool = False):
    """
    Consume a PipelineStatus generator, logging each status.

    Returns the generator's return value (via StopIteration).
    """
    result = None
    try:
        while True:
            status = next(gen)
            prefix = f"[Step {status.step}]" if status.step > 0 else "[INFO]"
            if status.is_error:
                log.error(f"{prefix} {status.message}")
            else:
                log.info(f"{prefix} {status.message}")

            if status.data:
                log.debug(f"Data: {status.data}")

            if assets_only and status.step == 2 and "complete" in status.message.lower():
                log.info("Assets-only mode: stopping before transcription/rendering")
                break
    except StopIteration as e:
        result = e.value
    return result


def run_single(cfg: RunConfig) -> int:
    """
    Run a single pipeline job in headless mode.

    Returns exit code (0 = success, 1 = failure, 130 = interrupted).
    """
    log = setup_logging(verbose=cfg.verbose, logger_name='src.headless')

    print_banner()
    log.info(f"Input: {cfg.movie}")

    mode_labels = {
        "movie": "MOVIE RECAP",
        "animated": "ANIMATED (episodic parody via Veo 3.1)",
        "animation-script": f"ANIMATION SCRIPT WRITER ({cfg.num_episodes} episodes)",
        "animation-render": f"ANIMATION RENDERER (episode {cfg.episode_number or 'next pending'})",
        "animation-series": f"ANIMATION SERIES (9-step pipeline, {cfg.num_episodes} episodes)",
    }
    log.info(f"Mode: {mode_labels.get(cfg.mode, cfg.mode)}")
    if cfg.offline:
        log.info("Mode: OFFLINE (using cached data)")
    if cfg.assets_only:
        log.info("Mode: ASSETS-ONLY (skip rendering)")
    if cfg.clean:
        log.info("Mode: CLEAN (temp files will be deleted after render)")
    print()

    start_time = datetime.now()

    try:
        # Animation Series mode uses a separate pipeline
        if cfg.mode == "animation-series":
            from src.animation_pipeline import run_animation_pipeline

            gen = run_animation_pipeline(
                project_title=cfg.movie,
                brief=cfg.storyline or "",
                num_episodes=cfg.num_episodes,
                resume=not cfg.no_resume,
            )

            project_dir = consume_generator(gen, log)

            elapsed = datetime.now() - start_time
            log.info(f"Total time: {elapsed.total_seconds():.1f} seconds")
            if project_dir:
                print(f"\nDone! Project directory: {project_dir}\n")
                return 0
            else:
                log.error("Pipeline failed — check logs and re-run to resume from last step")
                return 1

        # Standard pipeline modes
        pipeline = VideoGenerationPipeline(offline=cfg.offline, clean=cfg.clean)
        gen = pipeline.run(
            cfg.movie,
            mode=cfg.mode,
            storyline=cfg.storyline,
            character_descriptions=cfg.character_descriptions,
            num_episodes=cfg.num_episodes,
            episode_number=cfg.episode_number,
        )

        result = consume_generator(gen, log, assets_only=cfg.assets_only)
        scene_assets, script, final_video_path = result if result else ([], None, None)

        elapsed = datetime.now() - start_time

        if cfg.mode == "animation-script":
            log.info(f"Total time: {elapsed.total_seconds():.1f} seconds")
            if final_video_path:
                print(f"\nDone! Project saved: {final_video_path}")
                print(f"Next step: render episodes with:")
                print(f'  python -m src.cli "{cfg.movie}" --mode animation-render\n')
                return 0
            log.error("Pipeline completed but produced no output")
            return 1

        if cfg.mode == "animation-render":
            log.info(f"Total time: {elapsed.total_seconds():.1f} seconds")
            if final_video_path:
                print(f"\nDone! Video: {final_video_path}\n")
                return 0
            log.error("Pipeline completed but produced no output")
            return 1

        if scene_assets:
            print_scene_assets(scene_assets, script)
            log.info(f"Successfully processed {len(scene_assets)} scenes")
            log.info(f"Total time: {elapsed.total_seconds():.1f} seconds")

            if final_video_path:
                print(f"\nDone! Final video: {final_video_path}\n")
            else:
                print("\nDone! Assets gathered.\n")
            return 0
        else:
            log.error("No scene assets were generated")
            return 1

    except KeyboardInterrupt:
        log.warning("\nInterrupted by user")
        return 130
    except Exception as e:
        log.exception(f"Pipeline failed: {e}")
        return 1
