from __future__ import annotations

from collections import deque
from dataclasses import asdict

from .model import (
    HumanDailyFixture,
    HumanScheduleBlock,
    HumanScoreBreakdown,
    HumanSolverReport,
)


def format_human_daily_compact(fixture: HumanDailyFixture, report: HumanSolverReport) -> str:
    fixture_name = fixture.metadata.get("name", "unnamed")
    lines = [
        f"Human daily fixture: {fixture_name} ({fixture.date.isoformat()})",
        (
            f"solver: {report.solver_name} | status: {report.plan.status} | "
            f"scheduled: {len(report.plan.blocks)} | "
            f"unscheduled: {len(report.unscheduled_tasks)}"
        ),
        "",
        "Timeline",
    ]
    lines.extend(_format_compact_timeline(fixture, report))
    lines.append("")
    lines.extend(_format_compact_unscheduled(report))
    lines.append("")
    lines.append("Use --verbose for solver settings and full score breakdown.")
    return "\n".join(lines).rstrip() + "\n"


def format_human_daily_report(fixture: HumanDailyFixture, report: HumanSolverReport) -> str:
    return "\n".join(_format_report(fixture, report)).rstrip() + "\n"


def _format_compact_timeline(fixture: HumanDailyFixture, report: HumanSolverReport) -> list[str]:
    if not report.plan.blocks:
        return ["  none"]

    tasks_by_id = {task.id: task for task in fixture.tasks}
    slot_kinds = {slot.index: slot.work_kind.value for slot in fixture.time_slots}
    score_queues = _score_queues_by_task_slot(report)
    scheduled_minutes_by_task = _scheduled_minutes_by_task(report)
    lines = [
        "  time         kind     score  task                            notes",
        "  -----------  -------  -----  ------------------------------  -------------------",
    ]
    for block in report.plan.blocks:
        task = tasks_by_id.get(block.task_id)
        title = task.title if task else block.task_id
        score = _pop_score_for_block(block, score_queues)
        score_text = str(score.total) if score else "-"
        is_partial = bool(task and scheduled_minutes_by_task.get(block.task_id, 0) < task.remaining_minutes)
        lines.append(
            "  "
            f"{block.start.strftime('%H:%M')}-{block.end.strftime('%H:%M')}  "
            f"{_short_kind(slot_kinds.get(block.slot_index, 'unknown')):<7}  "
            f"{score_text:>5}  "
            f"{_truncate(title, 30):<30}  "
            f"{_compact_notes(block.is_fixed, score, is_partial=is_partial)}"
        )
    return lines


def _format_compact_unscheduled(report: HumanSolverReport) -> list[str]:
    lines = [f"Unscheduled ({len(report.unscheduled_tasks)})"]
    if not report.unscheduled_tasks:
        lines.append("  none")
        return lines

    for item in report.unscheduled_tasks:
        lines.append(f"  - {item.task_id}: {_friendly_reason(item.reason)}")
    return lines


def _format_report(fixture: HumanDailyFixture, report: HumanSolverReport) -> list[str]:
    task_titles = {task.id: task.title for task in fixture.tasks}
    tasks_by_id = {task.id: task for task in fixture.tasks}
    slot_kinds = {slot.index: slot.work_kind.value for slot in fixture.time_slots}
    score_queues = _score_queues_by_task_slot(report)
    scheduled_minutes_by_task = _scheduled_minutes_by_task(report)

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
            score = _pop_score_for_block(block, score_queues)
            score_text = f" score={score.total}" if score else ""
            task = tasks_by_id.get(block.task_id)
            partial_text = ""
            if task and scheduled_minutes_by_task.get(block.task_id, 0) < task.remaining_minutes:
                partial_text = f" partial={scheduled_minutes_by_task[block.task_id]}/{task.remaining_minutes}"
            lines.append(
                "  - "
                f"{block.start.strftime('%H:%M')}-{block.end.strftime('%H:%M')} "
                f"slot={block.slot_index} kind={slot_kinds.get(block.slot_index, 'unknown')} "
                f"task={block.task_id} title={title!r}{fixed}{score_text}{partial_text}"
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
            components = ", ".join(f"{name}={value}" for name, value in score.components.items())
            lines.append(f"  - task={score.task_id} slot={score.slot_index} total={score.total} ({components})")
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


def _scheduled_minutes_by_task(report: HumanSolverReport) -> dict[str, int]:
    scheduled_minutes: dict[str, int] = {}
    for block in report.plan.blocks:
        scheduled_minutes[block.task_id] = scheduled_minutes.get(block.task_id, 0) + block.duration_minutes
    return scheduled_minutes


def _score_queues_by_task_slot(
    report: HumanSolverReport,
) -> dict[tuple[str, int], deque[HumanScoreBreakdown]]:
    score_queues: dict[tuple[str, int], deque[HumanScoreBreakdown]] = {}
    for score in report.score_breakdown:
        score_queues.setdefault((score.task_id, score.slot_index), deque()).append(score)
    return score_queues


def _pop_score_for_block(
    block: HumanScheduleBlock,
    score_queues: dict[tuple[str, int], deque[HumanScoreBreakdown]],
) -> HumanScoreBreakdown | None:
    queue = score_queues.get((block.task_id, block.slot_index))
    if not queue:
        return None
    return queue.popleft()


def _compact_notes(is_fixed: bool, score: HumanScoreBreakdown | None, *, is_partial: bool) -> str:
    notes: list[str] = []
    if is_fixed:
        notes.append("fixed")
    if is_partial:
        notes.append("partial")
    if score is None:
        return " ".join(notes) or "-"

    components = score.components
    if components.get("deadline", 0) > 0:
        notes.append("due")
    if components.get("dependency_unlock", 0) > 0:
        notes.append("unlock")
    if components.get("gap_fill", 0) > 0:
        notes.append("gap")
    if components.get("project_switch", 0) < 0:
        notes.append("switch")
    if components.get("continuous_work", 0) < 0:
        notes.append("long")
    return " ".join(notes) or "-"


def _friendly_reason(reason: str) -> str:
    labels = {
        "dependency_not_scheduled": "blocked by dependency",
        "fixed_assignment_exceeds_slot_capacity": "fixed task does not fit",
        "fixed_assignment_slot_missing": "fixed slot missing",
        "insufficient_remaining_capacity": "capacity full",
        "no_project_compatible_slot": "no compatible project slot",
        "not_selected_by_solver": "lower score",
        "task_has_no_remaining_minutes": "no remaining work",
        "task_longer_than_any_slot": "too long for slots",
    }
    return labels.get(reason, reason)


def _short_kind(kind: str) -> str:
    labels = {
        "focused_work": "focused",
        "light_work": "light",
        "study": "study",
    }
    return labels.get(kind, kind)


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."
