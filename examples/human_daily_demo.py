from __future__ import annotations

from pathlib import Path
import sys

from scheduler.human import (
    compare_human_daily_solvers,
    format_human_daily_comparison,
    load_human_daily_fixture,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_path = repo_root / "samples" / "human" / "daily_basic.yaml"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path

    fixture = load_human_daily_fixture(path)
    comparison = compare_human_daily_solvers(fixture)
    print(format_human_daily_comparison(comparison), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
