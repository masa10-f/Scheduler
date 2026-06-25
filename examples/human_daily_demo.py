from __future__ import annotations

import argparse
from pathlib import Path

from humancompiler_scheduler.human import (
    format_human_daily_compact,
    format_human_daily_report,
    load_human_daily_fixture,
    solve_human_daily_timeline,
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
    report = solve_human_daily_timeline(fixture)
    output = format_human_daily_report(fixture, report) if args.verbose else format_human_daily_compact(fixture, report)
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
