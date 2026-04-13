#!/usr/bin/env python3
"""
StudioZero CLI — Interactive wizard for all pipeline routes.
"""

import sys
import logging
from pathlib import Path

from google import genai
from src.config import Config
from src.headless import RunConfig, run_single
from src.narrative import validate_input, generate_random_story_idea
from src.batch_runner import main as run_batch

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hr():
    print("-" * 60)


def _section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


# ── Animation pipeline wizard ─────────────────────────────────────────────────

def _run_animation_wizard():
    """Interactive wizard for the animation pipeline."""
    from src.animation_pipeline import run_animation_pipeline

    _section("Animation Pipeline — New Project")

    project_title = input("Project title (used for output folder): ").strip()
    if not project_title:
        print("Project title is required.")
        return 1

    print()
    print("Describe your story in 1-3 sentences.")
    print("Example: 'A brave teapot leads a rebellion against the tyrannical blender'")
    brief = input("Story brief: ").strip()
    if not brief:
        print("Brief is required.")
        return 1

    episodes_input = input("\nNumber of episodes [1]: ").strip()
    try:
        num_episodes = int(episodes_input) if episodes_input else 1
        if num_episodes < 1 or num_episodes > 10:
            print("Episodes must be between 1 and 10. Defaulting to 1.")
            num_episodes = 1
    except ValueError:
        num_episodes = 1

    print()
    _hr()
    print(f"  Project:  {project_title}")
    print(f"  Brief:    {brief[:80]}{'...' if len(brief) > 80 else ''}")
    print(f"  Episodes: {num_episodes}")
    _hr()
    confirm = input("\nStart pipeline? [Y/n]: ").strip().lower()
    if confirm not in ("", "y", "yes"):
        print("Cancelled.")
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    return _run_animation_loop(
        project_title=project_title,
        brief=brief,
        num_episodes=num_episodes,
        resume=False,
    )


def _run_animation_loop(
    project_title: str,
    brief: str,
    num_episodes: int,
    resume: bool = True,
) -> int:
    """
    Main execution loop for the animation pipeline.

    Handles the retry_gate flow: when a Veo scene fails, the user is offered
    the option to retry, edit the Veo prompt, or skip the scene.
    The loop re-runs the pipeline (which resumes from state) after any user action.
    """
    from src.animation_pipeline import run_animation_pipeline

    while True:
        print()
        if resume:
            print("[pipeline] Resuming from last completed step...")

        pipeline_completed = False

        for status in run_animation_pipeline(
            project_title=project_title,
            brief=brief,
            num_episodes=num_episodes,
            resume=resume,
        ):
            _print_status(status)

            if status.retry_gate:
                # Veo scene failed — ask user what to do
                action = _handle_scene_failure(status)
                if action == "abort":
                    print("\nPipeline aborted.")
                    return 1
                # After user action (retry / edit / skip), re-run with resume=True
                resume = True
                break  # restart the for-loop (pipeline will resume from state)

            if status.is_error and not status.retry_gate:
                # Hard error — nothing to retry
                print(f"\n[ERROR] {status.message}")
                print("Pipeline stopped. Fix the issue and re-run to resume.")
                return 1

        else:
            # Generator exhausted without a retry_gate — pipeline completed
            pipeline_completed = True

        if pipeline_completed:
            print("\n[pipeline] All done!")
            return 0

        # Loop continues with resume=True after retry_gate handling


def _print_status(status):
    """Print a pipeline status update to the terminal."""
    from src.pipeline import PipelineStatus
    prefix = "  [ERROR]" if status.is_error else f"  [step {status.step}]"
    print(f"{prefix} {status.message}")


def _handle_scene_failure(status) -> str:
    """
    Prompt the user for action after a Veo scene failure.

    Returns: 'retry' | 'edit' | 'skip' | 'abort'
    """
    data = status.data or {}
    scene_id = data.get("scene_id", "?")
    veo_prompt = data.get("veo_prompt", "")
    override_file = data.get("override_file", "")
    skip_marker = data.get("skip_marker", "")

    print()
    print("=" * 60)
    print(f"  Veo Scene {scene_id} Failed")
    print("=" * 60)
    print(f"\nError: {status.message.split(chr(10))[0]}")
    print(f"\nPrompt sent to Veo ({len(veo_prompt.split())} words):")
    print("-" * 40)
    print(veo_prompt)
    print("-" * 40)
    print()
    print("What would you like to do?")
    print("  r) Retry with the same prompt")
    print("  e) Edit the prompt and retry")
    print("  s) Skip this scene and continue")
    print("  a) Abort pipeline")
    print()

    while True:
        choice = input("Choice [r/e/s/a]: ").strip().lower()

        if choice in ("r", "retry", ""):
            print(f"\n[pipeline] Retrying scene {scene_id} with same prompt...")
            return "retry"

        elif choice in ("e", "edit"):
            print(f"\nEnter new prompt for scene {scene_id}.")
            print("(Press Enter twice when done)\n")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            new_prompt = "\n".join(lines).strip()
            if new_prompt:
                Path(override_file).parent.mkdir(parents=True, exist_ok=True)
                Path(override_file).write_text(new_prompt, encoding="utf-8")
                print(f"\n[pipeline] Override saved. Retrying scene {scene_id}...")
            else:
                print("[pipeline] No prompt entered — retrying with original prompt")
            return "edit"

        elif choice in ("s", "skip"):
            confirm = input(f"Skip scene {scene_id}? It will be omitted from the final video. [y/N]: ").strip().lower()
            if confirm in ("y", "yes"):
                Path(skip_marker).parent.mkdir(parents=True, exist_ok=True)
                Path(skip_marker).touch()
                print(f"[pipeline] Scene {scene_id} marked as skipped.")
                return "skip"
            else:
                continue

        elif choice in ("a", "abort"):
            return "abort"

        else:
            print("Please enter r, e, s, or a.")


# ── Stock footage wizard ──────────────────────────────────────────────────────

def _run_stock_wizard():
    _section("Stock Footage Route")
    print("1. Sheet Automated (Fetch from Google Sheet)")
    print("2. User Entry (Manual Movie/Story Name)")

    sub_choice = input("\nEnter sub-choice (1 or 2): ").strip()

    if sub_choice == "1":
        print("\nStarting Sheet Automated processing...")
        logging.basicConfig(level=logging.INFO)
        run_batch()
        return 0

    elif sub_choice == "2":
        movie_name = input("\nEnter the movie name or story idea: ").strip()

        client = genai.Client(api_key=Config.GEMINI_API_KEY)

        print(f"Validating input: '{movie_name}'...")
        validation = validate_input(movie_name, client)

        final_idea = movie_name
        if not validation.get("is_valid"):
            print("Input unrecognizable. Generating a random story idea...")
            final_idea = generate_random_story_idea(client)
            print(f"Generated Story Idea: {final_idea}")

        cfg = RunConfig(movie=final_idea, mode="movie", verbose=True)
        return run_single(cfg)

    else:
        print("Invalid choice.")
        return 1


# ── Main wizard ───────────────────────────────────────────────────────────────

def interactive_wizard():
    print("\n" + "=" * 60)
    print("  StudioZero — AI Video Generation")
    print("=" * 60 + "\n")
    print("  1. Stock Footage  (Movie Recap / Story)")
    print("  2. Animation      (Story → Veo short-form series)")

    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == "1":
        return _run_stock_wizard()
    elif choice == "2":
        return _run_animation_wizard()
    else:
        print("Invalid choice.")
        return 1


def main():
    import argparse
    parser = argparse.ArgumentParser(description="StudioZero CLI")
    parser.add_argument("--headless", action="store_true")
    args, _ = parser.parse_known_args()

    if not args.headless:
        return interactive_wizard()
    else:
        print("Headless mode requires arguments. Use --help for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
