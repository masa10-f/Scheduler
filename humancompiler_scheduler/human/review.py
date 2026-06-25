from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

from .io import load_human_daily_fixture
from .model import HumanDailyFixture, HumanDailySolverConfig, HumanSolverReport
from .report import format_human_daily_compact
from .solver import solve_human_daily_timeline

HumanDailyReviewFormat = Literal["text", "markdown"]
HumanDailyReviewResult = tuple[HumanDailyFixture, HumanSolverReport]


def run_human_daily_review(
    paths: Sequence[str | Path],
    *,
    config_override: HumanDailySolverConfig | None = None,
    output_format: HumanDailyReviewFormat = "text",
) -> str:
    """Run one or more Human daily fixtures and return review text."""
    if not paths:
        raise ValueError("at least one fixture path is required")

    results = [_load_review_result(path, config_override=config_override) for path in paths]
    if output_format == "text":
        return format_human_daily_review_text(results)
    if output_format == "markdown":
        return format_human_daily_review_markdown(results)
    raise ValueError(f"unsupported review output format: {output_format}")


def write_human_daily_review(
    paths: Sequence[str | Path],
    output_path: str | Path,
    *,
    config_override: HumanDailySolverConfig | None = None,
    output_format: HumanDailyReviewFormat = "text",
) -> str:
    """Run a review, write it to disk, and return the rendered text."""
    rendered = run_human_daily_review(
        paths,
        config_override=config_override,
        output_format=output_format,
    )
    Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


def format_human_daily_review_text(
    results: Sequence[HumanDailyReviewResult],
) -> str:
    solver_name = results[0][1].solver_name if results else "timeline_greedy"
    lines = [
        "Human daily review",
        f"solver: {solver_name}",
        f"fixtures: {len(results)}",
        "",
    ]
    for index, (fixture, report) in enumerate(results):
        if index > 0:
            lines.append("")
        lines.append(format_human_daily_compact(fixture, report).rstrip())
    return "\n".join(lines).rstrip() + "\n"


def format_human_daily_review_markdown(
    results: Sequence[HumanDailyReviewResult],
) -> str:
    solver_name = results[0][1].solver_name if results else "timeline_greedy"
    lines = [
        "# Human Daily Review",
        "",
        f"- solver: `{solver_name}`",
        f"- fixtures: `{len(results)}`",
        "",
    ]
    for fixture, report in results:
        fixture_name = fixture.metadata.get("name", "unnamed")
        lines.extend(
            [
                f"## {fixture_name}",
                "",
                "```text",
                format_human_daily_compact(fixture, report).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_review_result(
    path: str | Path,
    *,
    config_override: HumanDailySolverConfig | None,
) -> HumanDailyReviewResult:
    fixture = load_human_daily_fixture(path)
    if config_override is not None:
        fixture = replace(fixture, solver_config=config_override)
    return fixture, solve_human_daily_timeline(fixture)
