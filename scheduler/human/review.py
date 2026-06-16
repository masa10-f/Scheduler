from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

from .io import load_human_daily_fixture
from .model import HumanDailySolverConfig, HumanSolverComparison
from .report import format_human_daily_compact
from .solver import compare_human_daily_solvers

HumanDailyReviewFormat = Literal["text", "markdown"]


def run_human_daily_review(
    paths: Sequence[str | Path],
    *,
    solver_name: str = "timeline_greedy",
    config_override: HumanDailySolverConfig | None = None,
    output_format: HumanDailyReviewFormat = "text",
) -> str:
    """Run one or more Human daily fixtures and return review text."""
    if not paths:
        raise ValueError("at least one fixture path is required")

    comparisons = [_load_comparison(path, config_override=config_override) for path in paths]
    if output_format == "text":
        return format_human_daily_review_text(comparisons, solver_name=solver_name)
    if output_format == "markdown":
        return format_human_daily_review_markdown(comparisons, solver_name=solver_name)
    raise ValueError(f"unsupported review output format: {output_format}")


def write_human_daily_review(
    paths: Sequence[str | Path],
    output_path: str | Path,
    *,
    solver_name: str = "timeline_greedy",
    config_override: HumanDailySolverConfig | None = None,
    output_format: HumanDailyReviewFormat = "text",
) -> str:
    """Run a review, write it to disk, and return the rendered text."""
    rendered = run_human_daily_review(
        paths,
        solver_name=solver_name,
        config_override=config_override,
        output_format=output_format,
    )
    Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


def format_human_daily_review_text(
    comparisons: Sequence[HumanSolverComparison],
    *,
    solver_name: str = "timeline_greedy",
) -> str:
    lines = [
        "Human daily review",
        f"solver: {solver_name}",
        f"fixtures: {len(comparisons)}",
        "",
    ]
    for index, comparison in enumerate(comparisons):
        if index > 0:
            lines.append("")
        lines.append(format_human_daily_compact(comparison, solver_name=solver_name).rstrip())
    return "\n".join(lines).rstrip() + "\n"


def format_human_daily_review_markdown(
    comparisons: Sequence[HumanSolverComparison],
    *,
    solver_name: str = "timeline_greedy",
) -> str:
    lines = [
        "# Human Daily Review",
        "",
        f"- solver: `{solver_name}`",
        f"- fixtures: `{len(comparisons)}`",
        "",
    ]
    for comparison in comparisons:
        fixture = comparison.fixture
        fixture_name = fixture.metadata.get("name", "unnamed")
        lines.extend(
            [
                f"## {fixture_name}",
                "",
                "```text",
                format_human_daily_compact(comparison, solver_name=solver_name).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_comparison(
    path: str | Path,
    *,
    config_override: HumanDailySolverConfig | None,
) -> HumanSolverComparison:
    fixture = load_human_daily_fixture(path)
    if config_override is not None:
        fixture = replace(fixture, solver_config=config_override)
    return compare_human_daily_solvers(fixture)
