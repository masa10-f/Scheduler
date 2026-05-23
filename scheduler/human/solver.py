from __future__ import annotations

from datetime import date, time

from .model import (
    HumanConstraintViolation,
    HumanDailyFixture,
    HumanDailyPlan,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanScheduleBlock,
    HumanScoreBreakdown,
    HumanSolverComparison,
    HumanSolverReport,
    HumanTask,
    HumanTimeSlot,
    HumanUnscheduledTask,
)


def compare_human_daily_solvers(fixture: HumanDailyFixture) -> HumanSolverComparison:
    return HumanSolverComparison(
        fixture=fixture,
        reports={
            "legacy_slot": solve_human_daily_legacy(fixture),
            "timeline_greedy": solve_human_daily_timeline(fixture),
        },
    )


def solve_human_daily_legacy(fixture: HumanDailyFixture) -> HumanSolverReport:
    return _solve_daily(fixture, solver_name="legacy_slot", sequential_starts=False)


def solve_human_daily_timeline(fixture: HumanDailyFixture) -> HumanSolverReport:
    return _solve_daily(fixture, solver_name="timeline_greedy", sequential_starts=True)


def _solve_daily(
    fixture: HumanDailyFixture, *, solver_name: str, sequential_starts: bool
) -> HumanSolverReport:
    tasks_by_id = {task.id: task for task in fixture.tasks}
    slots_by_index = {slot.index: slot for slot in fixture.time_slots}
    sorted_slots = sorted(fixture.time_slots, key=lambda slot: (_minutes(slot.start), slot.index))
    scheduled: dict[str, HumanScheduleBlock] = {}
    slot_usage = {slot.index: 0 for slot in fixture.time_slots}
    slot_cursors = {slot.index: _minutes(slot.start) for slot in fixture.time_slots}
    unscheduled: dict[str, str] = {}
    score_breakdown: list[HumanScoreBreakdown] = []
    violations: list[HumanConstraintViolation] = []

    for fixed in fixture.fixed_assignments:
        _place_fixed_assignment(
            fixed,
            fixture,
            tasks_by_id,
            slots_by_index,
            scheduled,
            slot_usage,
            slot_cursors,
            score_breakdown,
            unscheduled,
            violations,
            sequential_starts=sequential_starts,
        )

    if sequential_starts:
        _fill_timeline_slots(
            fixture,
            sorted_slots,
            scheduled,
            slot_usage,
            slot_cursors,
            score_breakdown,
            unscheduled,
        )
    else:
        _fill_legacy_slots(
            fixture,
            sorted_slots,
            scheduled,
            slot_usage,
            score_breakdown,
            unscheduled,
        )

    for task in fixture.tasks:
        if task.id in scheduled or task.id in unscheduled:
            continue
        unscheduled[task.id] = _unscheduled_reason(task, fixture, scheduled, slot_usage)

    _add_dependency_violations(fixture, scheduled, violations)
    blocks = sorted(
        scheduled.values(),
        key=lambda block: (_minutes(block.start), block.slot_index, block.task_id),
    )
    unscheduled_tasks = [
        HumanUnscheduledTask(
            task_id=task.id,
            title=task.title,
            reason=unscheduled[task.id],
        )
        for task in fixture.tasks
        if task.id in unscheduled
    ]
    status = "ok"
    if unscheduled_tasks:
        status = "partial"
    if violations and status == "ok":
        status = "violations"

    plan = HumanDailyPlan(
        blocks=blocks,
        unscheduled_task_ids=[item.task_id for item in unscheduled_tasks],
        status=status,
        metadata={"solver": solver_name},
    )
    return HumanSolverReport(
        solver_name=solver_name,
        plan=plan,
        unscheduled_tasks=unscheduled_tasks,
        score_breakdown=score_breakdown,
        violations=violations,
        config=fixture.solver_config,
    )


def _place_fixed_assignment(
    fixed: HumanFixedAssignment,
    fixture: HumanDailyFixture,
    tasks_by_id: dict[str, HumanTask],
    slots_by_index: dict[int, HumanTimeSlot],
    scheduled: dict[str, HumanScheduleBlock],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    score_breakdown: list[HumanScoreBreakdown],
    unscheduled: dict[str, str],
    violations: list[HumanConstraintViolation],
    *,
    sequential_starts: bool,
) -> None:
    task = tasks_by_id.get(fixed.task_id)
    slot = slots_by_index.get(fixed.slot_index)
    if task is None:
        violations.append(
            HumanConstraintViolation(
                code="unknown_fixed_task",
                message=f"fixed assignment references unknown task {fixed.task_id}",
                task_id=fixed.task_id,
                slot_index=fixed.slot_index,
            )
        )
        return
    if slot is None:
        unscheduled[task.id] = "fixed_assignment_slot_missing"
        violations.append(
            HumanConstraintViolation(
                code="unknown_fixed_slot",
                message=f"fixed assignment references unknown slot {fixed.slot_index}",
                task_id=task.id,
                slot_index=fixed.slot_index,
            )
        )
        return
    if task.id in scheduled:
        violations.append(
            HumanConstraintViolation(
                code="duplicate_fixed_assignment",
                message=f"task {task.id} has multiple fixed assignments",
                task_id=task.id,
                slot_index=slot.index,
            )
        )
        return

    duration = fixed.duration_minutes or task.remaining_minutes
    remaining_capacity = slot.effective_capacity_minutes - slot_usage[slot.index]
    if duration <= 0:
        unscheduled[task.id] = "task_has_no_remaining_minutes"
        return
    if duration > remaining_capacity:
        unscheduled[task.id] = "fixed_assignment_exceeds_slot_capacity"
        violations.append(
            HumanConstraintViolation(
                code="fixed_capacity",
                message=f"fixed assignment for {task.id} does not fit in slot {slot.index}",
                task_id=task.id,
                slot_index=slot.index,
            )
        )
        return

    start_minutes = slot_cursors[slot.index] if sequential_starts else _minutes(slot.start)
    end_minutes = start_minutes + duration
    scheduled[task.id] = HumanScheduleBlock(
        task_id=task.id,
        slot_index=slot.index,
        start=_time_from_minutes(start_minutes),
        end=_time_from_minutes(end_minutes),
        duration_minutes=duration,
        is_fixed=True,
    )
    slot_usage[slot.index] += duration
    if sequential_starts:
        slot_cursors[slot.index] = end_minutes
    score_breakdown.append(
        _score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=True)
    )


def _fill_timeline_slots(
    fixture: HumanDailyFixture,
    sorted_slots: list[HumanTimeSlot],
    scheduled: dict[str, HumanScheduleBlock],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    score_breakdown: list[HumanScoreBreakdown],
    unscheduled: dict[str, str],
) -> None:
    task_by_id = {task.id: task for task in fixture.tasks}
    for slot_position, slot in enumerate(sorted_slots):
        future_slots = sorted_slots[slot_position + 1 :]
        while True:
            candidates = [
                task
                for task in fixture.tasks
                if task.id not in scheduled
                and task.id not in unscheduled
                and _dependencies_are_scheduled(task.id, fixture, scheduled)
                and _can_use_slot(task, slot)
                and task.remaining_minutes <= slot.effective_capacity_minutes - slot_usage[slot.index]
                and not _should_defer_for_future_kind_match(
                    task,
                    slot,
                    future_slots,
                    slot_usage,
                    fixture.date,
                    fixture.solver_config,
                )
            ]
            if not candidates:
                break
            task = max(
                candidates,
                key=lambda candidate: _timeline_candidate_key(
                    candidate, slot, fixture.date, fixture.solver_config
                ),
            )
            start_minutes = slot_cursors[slot.index]
            end_minutes = start_minutes + task.remaining_minutes
            scheduled[task.id] = HumanScheduleBlock(
                task_id=task.id,
                slot_index=slot.index,
                start=_time_from_minutes(start_minutes),
                end=_time_from_minutes(end_minutes),
                duration_minutes=task.remaining_minutes,
            )
            slot_usage[slot.index] += task.remaining_minutes
            slot_cursors[slot.index] = end_minutes
            score_breakdown.append(
                _score_breakdown(
                    task,
                    slot,
                    fixture.date,
                    fixture.solver_config,
                    is_fixed=False,
                )
            )

    for task_id, prerequisites in fixture.task_dependencies.items():
        task = task_by_id.get(task_id)
        if task and task.id not in scheduled and task.id not in unscheduled:
            missing = [prereq for prereq in prerequisites if prereq not in scheduled]
            if missing:
                unscheduled[task.id] = "dependency_not_scheduled"


def _fill_legacy_slots(
    fixture: HumanDailyFixture,
    sorted_slots: list[HumanTimeSlot],
    scheduled: dict[str, HumanScheduleBlock],
    slot_usage: dict[int, int],
    score_breakdown: list[HumanScoreBreakdown],
    unscheduled: dict[str, str],
) -> None:
    for task in sorted(
        fixture.tasks,
        key=lambda item: (
            item.priority,
            item.due_at.date() if item.due_at else date.max,
            item.id,
        ),
    ):
        if task.id in scheduled or task.id in unscheduled:
            continue
        candidate_slots = [
            slot
            for slot in sorted_slots
            if _dependencies_allow_legacy_slot(task.id, slot.index, fixture, scheduled)
            and _can_use_slot(task, slot)
            and task.remaining_minutes <= slot.effective_capacity_minutes - slot_usage[slot.index]
        ]
        if not candidate_slots:
            unscheduled[task.id] = _unscheduled_reason(task, fixture, scheduled, slot_usage)
            continue
        slot = max(
            candidate_slots,
            key=lambda candidate: _legacy_candidate_key(
                task, candidate, fixture.date, fixture.solver_config
            ),
        )
        start_minutes = _minutes(slot.start)
        end_minutes = start_minutes + task.remaining_minutes
        scheduled[task.id] = HumanScheduleBlock(
            task_id=task.id,
            slot_index=slot.index,
            start=_time_from_minutes(start_minutes),
            end=_time_from_minutes(end_minutes),
            duration_minutes=task.remaining_minutes,
        )
        slot_usage[slot.index] += task.remaining_minutes
        score_breakdown.append(
            _score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=False)
        )


def _dependencies_are_scheduled(
    task_id: str, fixture: HumanDailyFixture, scheduled: dict[str, HumanScheduleBlock]
) -> bool:
    return all(prereq in scheduled for prereq in fixture.task_dependencies.get(task_id, []))


def _dependencies_allow_legacy_slot(
    task_id: str,
    slot_index: int,
    fixture: HumanDailyFixture,
    scheduled: dict[str, HumanScheduleBlock],
) -> bool:
    for prereq in fixture.task_dependencies.get(task_id, []):
        block = scheduled.get(prereq)
        if block is None or block.slot_index >= slot_index:
            return False
    return True


def _can_use_slot(task: HumanTask, slot: HumanTimeSlot) -> bool:
    if task.remaining_minutes <= 0:
        return False
    if slot.assigned_project_id and task.project_id != slot.assigned_project_id:
        return False
    return True


def _should_defer_for_future_kind_match(
    task: HumanTask,
    slot: HumanTimeSlot,
    future_slots: list[HumanTimeSlot],
    slot_usage: dict[int, int],
    schedule_date: date,
    config: HumanDailySolverConfig,
) -> bool:
    if task.work_kind == slot.work_kind:
        return False
    if _deadline_score(task, schedule_date, config) > 0:
        return False
    return any(
        task.work_kind == future_slot.work_kind
        and _can_use_slot(task, future_slot)
        and task.remaining_minutes
        <= future_slot.effective_capacity_minutes - slot_usage[future_slot.index]
        for future_slot in future_slots
    )


def _unscheduled_reason(
    task: HumanTask,
    fixture: HumanDailyFixture,
    scheduled: dict[str, HumanScheduleBlock],
    slot_usage: dict[int, int],
) -> str:
    missing = [
        prereq for prereq in fixture.task_dependencies.get(task.id, []) if prereq not in scheduled
    ]
    if missing:
        return "dependency_not_scheduled"
    if task.remaining_minutes <= 0:
        return "task_has_no_remaining_minutes"
    compatible_slots = [slot for slot in fixture.time_slots if _can_use_slot(task, slot)]
    if not compatible_slots:
        return "no_project_compatible_slot"
    if all(task.remaining_minutes > slot.effective_capacity_minutes for slot in compatible_slots):
        return "task_longer_than_any_slot"
    if all(
        task.remaining_minutes > slot.effective_capacity_minutes - slot_usage[slot.index]
        for slot in compatible_slots
    ):
        return "insufficient_remaining_capacity"
    return "not_selected_by_solver"


def _timeline_candidate_key(
    task: HumanTask,
    slot: HumanTimeSlot,
    schedule_date: date,
    config: HumanDailySolverConfig,
) -> tuple[int, int, int, str]:
    breakdown = _score_breakdown(task, slot, schedule_date, config, is_fixed=False)
    due_key = -9999 if task.due_at is None else -(
        task.due_at.date() - schedule_date
    ).days
    return (breakdown.total, due_key, -task.priority, task.id)


def _legacy_candidate_key(
    task: HumanTask,
    slot: HumanTimeSlot,
    schedule_date: date,
    config: HumanDailySolverConfig,
) -> tuple[int, int, str]:
    breakdown = _score_breakdown(task, slot, schedule_date, config, is_fixed=False)
    return (breakdown.total, -slot.index, task.id)


def _score_breakdown(
    task: HumanTask,
    slot: HumanTimeSlot,
    schedule_date: date,
    config: HumanDailySolverConfig,
    *,
    is_fixed: bool,
) -> HumanScoreBreakdown:
    priority = max(1, config.priority_score_base - task.priority)
    kind = (
        config.kind_match_score
        if task.work_kind == slot.work_kind
        else config.kind_mismatch_score
    )
    deadline = _deadline_score(task, schedule_date, config)
    fixed = config.fixed_assignment_score if is_fixed else 0
    components = {
        "priority": priority,
        "kind": kind,
        "deadline": deadline,
        "fixed": fixed,
    }
    return HumanScoreBreakdown(
        task_id=task.id,
        slot_index=slot.index,
        total=sum(components.values()),
        components=components,
    )


def _deadline_score(
    task: HumanTask, schedule_date: date, config: HumanDailySolverConfig
) -> int:
    if task.due_at is None:
        return 0
    days_until_due = (task.due_at.date() - schedule_date).days
    if days_until_due < 0:
        return config.overdue_score
    if days_until_due <= config.deadline_soon_days:
        return (config.deadline_soon_days - days_until_due + 1) * config.deadline_score
    return 0


def _add_dependency_violations(
    fixture: HumanDailyFixture,
    scheduled: dict[str, HumanScheduleBlock],
    violations: list[HumanConstraintViolation],
) -> None:
    for task_id, prerequisites in fixture.task_dependencies.items():
        task_block = scheduled.get(task_id)
        if task_block is None:
            continue
        for prereq in prerequisites:
            prereq_block = scheduled.get(prereq)
            if prereq_block is None:
                continue
            if _minutes(task_block.start) < _minutes(prereq_block.end):
                violations.append(
                    HumanConstraintViolation(
                        code="dependency_order",
                        message=f"{task_id} starts before prerequisite {prereq} finishes",
                        task_id=task_id,
                        slot_index=task_block.slot_index,
                    )
                )


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time_from_minutes(value: int) -> time:
    value = value % (24 * 60)
    return time(value // 60, value % 60)
