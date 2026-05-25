from __future__ import annotations

from dataclasses import asdict

from .model import HumanDailyFixture, HumanSolverComparison, HumanSolverReport


def format_human_daily_comparison(comparison: HumanSolverComparison) -> str:
    lines = [
        f"Human daily fixture: {comparison.fixture.metadata.get('name', 'unnamed')}",
        f"date: {comparison.fixture.date.isoformat()}",
        "",
    ]
    for report in comparison.reports.values():
        lines.extend(_format_report(comparison.fixture, report))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_human_daily_report(
    fixture: HumanDailyFixture, report: HumanSolverReport
) -> str:
    return "\n".join(_format_report(fixture, report)).rstrip() + "\n"


def _format_report(
    fixture: HumanDailyFixture, report: HumanSolverReport
) -> list[str]:
    task_titles = {task.id: task.title for task in fixture.tasks}
    slot_kinds = {slot.index: slot.work_kind.value for slot in fixture.time_slots}
    score_by_task = {score.task_id: score for score in report.score_breakdown}

    lines = [
        f"== {report.solver_name} ==",
        f"status: {report.plan.status}",
        f"solver settings: {_format_config(report)}",
        "timeline:",
    ]
    if report.plan.blocks:
        for block in report.plan.blocks:
            title = task_titles.get(block.task_id, block.task_id)
            fixed = " fixed" if block.is_fixed else ""
            score = score_by_task.get(block.task_id)
            score_text = f" score={score.total}" if score else ""
            lines.append(
                "  - "
                f"{block.start.strftime('%H:%M')}-{block.end.strftime('%H:%M')} "
                f"slot={block.slot_index} kind={slot_kinds.get(block.slot_index, 'unknown')} "
                f"task={block.task_id} title={title!r}{fixed}{score_text}"
            )
    else:
        lines.append("  none")

    lines.append("unscheduled:")
    if report.unscheduled_tasks:
        for item in report.unscheduled_tasks:
            lines.append(f"  - task={item.task_id} title={item.title!r} reason={item.reason}")
    else:
        lines.append("  none")

    lines.append("score breakdown:")
    if report.score_breakdown:
        for score in report.score_breakdown:
            components = ", ".join(
                f"{name}={value}" for name, value in score.components.items()
            )
            lines.append(
                f"  - task={score.task_id} slot={score.slot_index} "
                f"total={score.total} ({components})"
            )
    else:
        lines.append("  none")

    lines.append("constraint violations:")
    if report.violations:
        for violation in report.violations:
            suffix = ""
            if violation.task_id:
                suffix += f" task={violation.task_id}"
            if violation.slot_index is not None:
                suffix += f" slot={violation.slot_index}"
            lines.append(f"  - {violation.code}: {violation.message}{suffix}")
    else:
        lines.append("  none")
    return lines


def _format_config(report: HumanSolverReport) -> str:
    data = asdict(report.config)
    return ", ".join(f"{key}={value}" for key, value in data.items())
