#!/usr/bin/env python3
"""
StudioZero CLI — Interactive wizard or headless video generation.

Usage:
    python -m src.cli                              # Interactive wizard
    python -m src.cli --headless "The Matrix"      # Headless movie recap
    python -m src.cli --headless "Kitchen Wars" --mode animation-series \\
        --storyline "A spatula rebels" --char-desc "Sir Spatula: dented metal"
"""

import argparse
import sys

from src.headless import RunConfig, run_single


def main():
    parser = argparse.ArgumentParser(
        description="StudioZero — AI Video Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.cli                                    # Interactive wizard
    python -m src.cli --headless "The Matrix"            # Headless movie recap
    python -m src.cli --headless "Toy Story" --offline   # Cached data
        """,
    )

    parser.add_argument(
        "idea",
        nargs="?",
        default=None,
        help="Movie name, theme, or storyline idea (optional in wizard mode)",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without interactive prompts (original CLI behavior)",
    )

    # Headless-mode flags (ignored in wizard mode)
    parser.add_argument("--mode", type=str,
                        choices=["movie", "animated", "animation-script",
                                 "animation-render", "animation-series"],
                        default="movie")
    parser.add_argument("--storyline", type=str, default=None)
    parser.add_argument("--char-desc", type=str, default=None)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--episode-num", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--assets-only", action="store_true")
    parser.add_argument("--output", "-o", type=str, default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--clean", action="store_true")

    args = parser.parse_args()

    # Decide: wizard or headless
    is_interactive = not args.headless and sys.stdin.isatty()

    if is_interactive:
        from src.wizard import start
        return start(idea=args.idea)

    # Headless mode requires a movie/idea
    if not args.idea:
        parser.error("A movie name or idea is required in --headless mode")

    # Validate animation mode requirements
    if args.mode in ("animation-script", "animation-series"):
        if not args.storyline or not args.char_desc:
            parser.error(
                f"--storyline and --char-desc are required for {args.mode} mode"
            )

    cfg = RunConfig(
        movie=args.idea,
        mode=args.mode,
        offline=args.offline,
        assets_only=args.assets_only,
        clean=args.clean,
        verbose=args.verbose,
        storyline=args.storyline,
        character_descriptions=args.char_desc,
        num_episodes=args.episodes,
        episode_number=args.episode_num,
        no_resume=args.no_resume,
        output=args.output,
    )

    return run_single(cfg)


if __name__ == "__main__":
    sys.exit(main())
