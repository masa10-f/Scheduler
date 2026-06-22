from __future__ import annotations

import argparse
from pathlib import Path

from humancompiler_scheduler.human import (
    load_human_daily_solver_config,
    run_human_daily_review,
    write_human_daily_review,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--solver",
        choices=["timeline_greedy", "legacy_slot"],
        default="timeline_greedy",
        help="solver report to include in the review output",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="text",
        help="review output format",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="YAML solver config override applied to every fixture",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write the review snapshot to this path instead of stdout",
    )
    args = parser.parse_args()

    config_override = load_human_daily_solver_config(args.config) if args.config else None
    if args.output:
        write_human_daily_review(
            args.paths,
            args.output,
            solver_name=args.solver,
            config_override=config_override,
            output_format=args.format,
        )
        return 0

    print(
        run_human_daily_review(
            args.paths,
            solver_name=args.solver,
            config_override=config_override,
            output_format=args.format,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
