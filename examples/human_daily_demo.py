from __future__ import annotations

import argparse
from pathlib import Path

from scheduler.human import (
    compare_human_daily_solvers,
    format_human_daily_compact,
    format_human_daily_comparison,
    load_human_daily_fixture,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_path = repo_root / "samples" / "human" / "daily_basic.yaml"
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=default_path)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print solver settings and full score breakdown",
    )
    args = parser.parse_args()

    fixture = load_human_daily_fixture(args.path)
    comparison = compare_human_daily_solvers(fixture)
    formatter = format_human_daily_comparison if args.verbose else format_human_daily_compact
    print(formatter(comparison), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
