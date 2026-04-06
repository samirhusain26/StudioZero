"""
StudioZero Interactive Wizard — stepwise video creation flow.

Guides the user through idea → type selection → options → generation
with review gates at key decision points.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.text import Text
from rich.rule import Rule

from src.pipeline import VideoGenerationPipeline, PipelineStatus

console = Console()
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────

def _banner():
    console.print()
    console.print(Panel.fit(
        "[bold cyan]StudioZero[/bold cyan]  [dim]— AI Video Generator[/dim]",
        border_style="cyan",
    ))
    console.print()


def _consume_with_progress(gen, label: str = "Working") -> object:
    """
    Consume a PipelineStatus generator, showing a live progress spinner.

    Pauses and returns (status, gen) at any review_gate=True yield.
    Otherwise runs to completion and returns the generator's return value.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(label, total=None)

        try:
            while True:
                status = next(gen)

                # Update progress display
                if status.is_error:
                    progress.update(task, description=f"[red]{status.message}[/red]")
                else:
                    progress.update(task, description=status.message)

                # Pause at review gates — return control to caller
                if status.review_gate and status.data:
                    progress.stop()
                    return ("review", status, gen)

        except StopIteration as e:
            return ("done", e.value)


def _display_script_table(script_data: dict):
    """Display a VideoScript as a rich table."""
    table = Table(title="Generated Script", show_lines=True)
    table.add_column("#", style="cyan", width=3)
    table.add_column("Narration", ratio=3)
    table.add_column("Visuals", ratio=2, style="dim")
    table.add_column("Mood", width=12)

    scenes = script_data.get("scenes", [])
    for i, scene in enumerate(scenes, 1):
        narration = scene.get("narration", "")
        if len(narration) > 120:
            narration = narration[:117] + "..."
        visuals = ", ".join(scene.get("visual_queries", [])[:2])
        mood = scene.get("mood", scene.get("scene_mood", "—"))
        table.add_row(str(i), narration, visuals, mood)

    console.print(table)
    console.print(f"  [dim]Genre:[/dim] {script_data.get('genre', '?')}  "
                  f"[dim]Voice:[/dim] {script_data.get('selected_voice_id', '?')}  "
                  f"[dim]Music:[/dim] {script_data.get('selected_music_file', '?')}")
    console.print()


def _display_movie_info(data: dict):
    """Display movie lookup results."""
    details = data.get("movie_details", {})
    title = details.get("title", "?")
    year = details.get("year", "?")
    overview = details.get("overview", details.get("plot", ""))
    if len(overview) > 300:
        overview = overview[:297] + "..."
    console.print(Panel(
        f"[bold]{title}[/bold] ({year})\n\n{overview}",
        title="Movie Found",
        border_style="green",
    ))


def _display_animation_script(data: dict):
    """Display animation world bible / episode outlines."""
    table = Table(title="Series Overview", show_lines=True)
    table.add_column("Episode", width=8)
    table.add_column("Title", ratio=2)
    table.add_column("Summary", ratio=4)

    episodes = data.get("episodes", [])
    for ep in episodes:
        num = str(ep.get("episode_number", "?"))
        title = ep.get("episode_title", "?")
        # Try to get a summary from the first scene narration
        scenes = ep.get("script", {}).get("scenes", [])
        summary = scenes[0].get("narration", "—")[:100] if scenes else "—"
        table.add_row(num, title, summary)

    console.print(table)
    console.print()


# ── Movie Recap Flow ─────────────────────────────────────────────────

def _run_movie_recap(idea: str) -> int:
    """Interactive movie recap pipeline."""
    console.print(Rule("[bold]Movie Recap[/bold]"))
    console.print(f"  Creating a recap video for: [cyan]{idea}[/cyan]\n")

    pipeline = VideoGenerationPipeline(offline=False, clean=False)
    gen = pipeline.run(idea, mode="movie")

    # Phase 1: Run until first review gate (script generated)
    result = _consume_with_progress(gen, f"Fetching data & generating script for '{idea}'...")

    if result[0] == "review":
        _, status, gen = result
        script_data = status.data.get("script", {})

        console.print()
        _display_script_table(script_data)

        if not Confirm.ask("Proceed with this script?", default=True):
            console.print("[yellow]Aborted.[/yellow]")
            return 0

        console.print()

        # Phase 2: Run rest of pipeline (generation + render)
        result = _consume_with_progress(gen, "Generating assets & rendering...")

    if result[0] == "done":
        final = result[1]
        if final:
            scene_assets, script, video_path = final
            if video_path:
                console.print(Panel(
                    f"[bold green]Video ready![/bold green]\n\n{video_path}",
                    border_style="green",
                ))
                return 0

    console.print("[red]Pipeline did not produce a video.[/red]")
    return 1


# ── Animation Flow ───────────────────────────────────────────────────

def _run_animation(idea: str) -> int:
    """Interactive animation pipeline."""
    console.print(Rule("[bold]Animation[/bold]"))

    # Gather storyline and character details
    storyline = Prompt.ask("Describe your storyline", default=idea)
    char_desc = Prompt.ask("Describe your characters")
    console.print()

    # Format choice
    format_choice = Prompt.ask(
        "Format",
        choices=["one-shot", "series"],
        default="series",
    )

    num_episodes = 1
    if format_choice == "series":
        num_episodes = IntPrompt.ask("How many episodes?", default=3)

    console.print()

    if format_choice == "one-shot":
        # One-shot animated mode
        pipeline = VideoGenerationPipeline(offline=False, clean=False)
        gen = pipeline.run(idea, mode="animated")

        result = _consume_with_progress(gen, "Generating animated video...")

        # Handle review gates for character blueprints
        while result[0] == "review":
            _, status, gen = result
            console.print()
            if "characters" in str(status.data):
                console.print(Panel("Character blueprints generated.", border_style="blue"))
            else:
                console.print(f"[dim]{status.message}[/dim]")

            if not Confirm.ask("Proceed?", default=True):
                console.print("[yellow]Aborted.[/yellow]")
                return 0

            result = _consume_with_progress(gen, "Continuing generation...")

        if result[0] == "done" and result[1]:
            _, _, video_path = result[1]
            if video_path:
                console.print(Panel(
                    f"[bold green]Video ready![/bold green]\n\n{video_path}",
                    border_style="green",
                ))
                return 0

    else:
        # Series mode (9-step pipeline)
        from src.animation_pipeline import run_animation_series

        gen = run_animation_series(
            project_title=idea,
            storyline=storyline,
            character_descriptions=char_desc,
            num_episodes=num_episodes,
            resume=True,
        )

        result = _consume_with_progress(gen, "Building animation series...")

        # Handle review gates (world bible, characters)
        while result[0] == "review":
            _, status, gen = result
            console.print()

            if status.data and "episodes" in status.data:
                _display_animation_script(status.data)
            elif status.data and "characters" in status.data:
                chars = status.data.get("characters", {})
                console.print(Panel(
                    "\n".join(f"  • {name}: {path}" for name, path in chars.items()),
                    title="Character Blueprints",
                    border_style="blue",
                ))
            else:
                console.print(f"[dim]{status.message}[/dim]")

            if not Confirm.ask("Proceed?", default=True):
                console.print("[yellow]Aborted.[/yellow]")
                return 0

            result = _consume_with_progress(gen, "Continuing generation...")

        if result[0] == "done" and result[1]:
            project_dir = result[1]
            console.print(Panel(
                f"[bold green]Series complete![/bold green]\n\n"
                f"Project directory: {project_dir}",
                border_style="green",
            ))
            return 0

    console.print("[red]Pipeline did not produce output.[/red]")
    return 1


# ── Main Entry ───────────────────────────────────────────────────────

def start(idea: Optional[str] = None) -> int:
    """
    Launch the interactive wizard.

    Args:
        idea: Optional pre-filled idea from CLI args.

    Returns:
        Exit code (0 = success).
    """
    _banner()

    # Screen 1: Idea input
    if not idea:
        idea = Prompt.ask("[bold]What's your idea?[/bold]  (movie name, theme, or storyline)")

    if not idea.strip():
        console.print("[red]No idea provided. Exiting.[/red]")
        return 1

    console.print(f"\n  Idea: [cyan]{idea}[/cyan]\n")

    # Screen 2: Video type
    console.print("  [bold]What kind of video?[/bold]\n")
    console.print("  [cyan]1[/cyan]  Movie Recap   — stock footage + Hormozi subtitles + voiceover")
    console.print("  [cyan]2[/cyan]  Animation     — AI-generated animated movie (Veo 3.1)")
    console.print()

    choice = Prompt.ask("Choose", choices=["1", "2"], default="1")

    console.print()

    try:
        if choice == "1":
            return _run_movie_recap(idea)
        else:
            return _run_animation(idea)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Wizard failed")
        return 1
