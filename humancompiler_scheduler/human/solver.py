from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from .model import (
    HumanConstraintViolation,
    HumanDailyFixture,
    HumanDailyPlan,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanScheduleBlock,
    HumanScoreBreakdown,
    HumanSolverReport,
    HumanTask,
    HumanTimeSlot,
    HumanUnscheduledTask,
)


@dataclass(frozen=True)
class _TimelineChunk:
    slot: HumanTimeSlot
    start_minutes: int
    duration_minutes: int


@dataclass(frozen=True)
class _TimelineCandidate:
    task: HumanTask
    chunk: _TimelineChunk
    score: HumanScoreBreakdown


def solve_human_daily_timeline(fixture: HumanDailyFixture) -> HumanSolverReport:
    return _solve_daily(fixture, solver_name="timeline_greedy")


def _solve_daily(fixture: HumanDailyFixture, *, solver_name: str) -> HumanSolverReport:
    tasks_by_id = {task.id: task for task in fixture.tasks}
    slots_by_index = {slot.index: slot for slot in fixture.time_slots}
    sorted_slots = sorted(fixture.time_slots, key=lambda slot: (_minutes(slot.start), slot.index))
    scheduled_blocks: list[HumanScheduleBlock] = []
    scheduled_minutes: dict[str, int] = {}
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
            scheduled_blocks,
            scheduled_minutes,
            slot_usage,
            slot_cursors,
            score_breakdown,
            unscheduled,
            violations,
        )

    _fill_timeline_slots(
        fixture,
        sorted_slots,
        scheduled_blocks,
        scheduled_minutes,
        slot_usage,
        slot_cursors,
        unscheduled,
    )

    for task in fixture.tasks:
        if scheduled_minutes.get(task.id, 0) > 0 or task.id in unscheduled:
            continue
        unscheduled[task.id] = _unscheduled_reason(task, fixture, scheduled_blocks, tasks_by_id, slot_usage)

    _add_dependency_violations(fixture, scheduled_blocks, tasks_by_id, violations)
    blocks = sorted(
        scheduled_blocks,
        key=lambda block: (_minutes(block.start), block.slot_index, block.task_id),
    )
    score_breakdown = _timeline_score_breakdowns(fixture, blocks, tasks_by_id, slots_by_index)
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
    scheduled_blocks: list[HumanScheduleBlock],
    scheduled_minutes: dict[str, int],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    score_breakdown: list[HumanScoreBreakdown],
    unscheduled: dict[str, str],
    violations: list[HumanConstraintViolation],
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
    if scheduled_minutes.get(task.id, 0) > 0:
        violations.append(
            HumanConstraintViolation(
                code="duplicate_fixed_assignment",
                message=f"task {task.id} has multiple fixed assignments",
                task_id=task.id,
                slot_index=slot.index,
            )
        )
        return

    remaining_capacity = slot.effective_capacity_minutes - slot_usage[slot.index]
    duration = (
        fixed.duration_minutes
        if fixed.duration_minutes is not None
        else _default_block_duration(task, fixture.solver_config, remaining_capacity, scheduled_minutes.get(task.id, 0))
    )
    if duration is None or duration <= 0:
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

    start_minutes = slot_cursors[slot.index]
    end_minutes = start_minutes + duration
    block = HumanScheduleBlock(
        task_id=task.id,
        slot_index=slot.index,
        start=_time_from_minutes(start_minutes),
        end=_time_from_minutes(end_minutes),
        duration_minutes=duration,
        is_fixed=True,
    )
    scheduled_blocks.append(block)
    scheduled_minutes[task.id] = scheduled_minutes.get(task.id, 0) + duration
    slot_usage[slot.index] += duration
    slot_cursors[slot.index] = end_minutes
    score_breakdown.append(_base_score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=True))


def _fill_timeline_slots(
    fixture: HumanDailyFixture,
    sorted_slots: list[HumanTimeSlot],
    scheduled_blocks: list[HumanScheduleBlock],
    scheduled_minutes: dict[str, int],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    unscheduled: dict[str, str],
) -> None:
    tasks_by_id = {task.id: task for task in fixture.tasks}
    for slot in sorted_slots:
        while True:
            candidate_start = slot_cursors[slot.index]
            if slot.effective_capacity_minutes - slot_usage[slot.index] <= 0:
                break
            candidates = _timeline_candidates(
                fixture,
                slot,
                scheduled_blocks,
                scheduled_minutes,
                slot_usage,
                slot_cursors,
                tasks_by_id,
                unscheduled,
                candidate_start,
            )
            if not candidates:
                break
            candidate = max(
                candidates,
                key=_timeline_candidate_key,
            )
            _place_timeline_candidate(
                candidate,
                scheduled_blocks,
                scheduled_minutes,
                slot_usage,
                slot_cursors,
            )

    for task_id, prerequisites in fixture.task_dependencies.items():
        dependent_task = tasks_by_id.get(task_id)
        if dependent_task and scheduled_minutes.get(dependent_task.id, 0) <= 0 and dependent_task.id not in unscheduled:
            missing = [
                prereq for prereq in prerequisites if not _task_completed_by_end(prereq, scheduled_blocks, tasks_by_id)
            ]
            if missing:
                unscheduled[dependent_task.id] = "dependency_not_scheduled"


def _dependencies_finish_by(
    task_id: str,
    fixture: HumanDailyFixture,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    start_minutes: int,
) -> bool:
    for prereq in fixture.task_dependencies.get(task_id, []):
        if not _task_completed_by(prereq, scheduled_blocks, tasks_by_id, start_minutes):
            return False
    return True


def _can_use_slot(task: HumanTask, slot: HumanTimeSlot) -> bool:
    if task.remaining_minutes <= 0:
        return False
    if slot.assigned_project_id and task.project_id != slot.assigned_project_id:
        return False
    return True


def _timeline_candidates(
    fixture: HumanDailyFixture,
    slot: HumanTimeSlot,
    scheduled_blocks: list[HumanScheduleBlock],
    scheduled_minutes: dict[str, int],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    tasks_by_id: dict[str, HumanTask],
    unscheduled: dict[str, str],
    candidate_start: int,
) -> list[_TimelineCandidate]:
    candidates: list[_TimelineCandidate] = []
    for task in fixture.tasks:
        if _task_is_fully_planned(task, scheduled_minutes) or task.id in unscheduled:
            continue
        already_scheduled = scheduled_minutes.get(task.id, 0)
        remaining_minutes = _remaining_task_minutes(task, already_scheduled)
        if remaining_minutes <= 0:
            continue
        if not _dependencies_finish_by(task.id, fixture, scheduled_blocks, tasks_by_id, candidate_start):
            continue
        if not _can_use_slot(task, slot):
            continue
        chunks = _timeline_chunks_for_slot(
            task,
            slot,
            scheduled_minutes,
            slot_usage,
            slot_cursors,
            fixture.solver_config,
        )
        for chunk in chunks:
            completes_task_by_end = _candidate_completes_task_by_end(task, scheduled_blocks, chunk)
            score = _score_breakdown(
                task,
                slot,
                fixture,
                is_fixed=False,
                scheduled_blocks=scheduled_blocks,
                tasks_by_id=tasks_by_id,
                slot_usage=slot_usage,
                start_minutes=candidate_start,
                duration_minutes=chunk.duration_minutes,
                include_dependency_unlock=completes_task_by_end,
            )
            candidates.append(
                _TimelineCandidate(
                    task=task,
                    chunk=chunk,
                    score=score,
                )
            )
    return candidates


def _timeline_chunks_for_slot(
    task: HumanTask,
    slot: HumanTimeSlot,
    scheduled_minutes: dict[str, int],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    config: HumanDailySolverConfig,
) -> list[_TimelineChunk]:
    current_available = slot.effective_capacity_minutes - slot_usage[slot.index]
    remaining_minutes = _remaining_task_minutes(task, scheduled_minutes.get(task.id, 0))
    return [
        _TimelineChunk(
            slot=slot,
            start_minutes=slot_cursors[slot.index],
            duration_minutes=duration_minutes,
        )
        for duration_minutes in _block_duration_candidates(
            task,
            config,
            remaining_minutes=remaining_minutes,
            available_minutes=current_available,
        )
    ]


def _remaining_task_minutes(task: HumanTask, scheduled_minutes: int) -> int:
    return max(0, task.remaining_minutes - scheduled_minutes)


def _task_is_fully_planned(task: HumanTask, scheduled_minutes: dict[str, int]) -> bool:
    return scheduled_minutes.get(task.id, 0) >= task.remaining_minutes


def _default_block_duration(
    task: HumanTask,
    config: HumanDailySolverConfig,
    available_minutes: int,
    scheduled_minutes: int,
) -> int | None:
    candidates = _block_duration_candidates(
        task,
        config,
        remaining_minutes=_remaining_task_minutes(task, scheduled_minutes),
        available_minutes=available_minutes,
    )
    if not candidates:
        return None
    if task.preferred_chunk_minutes is not None:
        preferred = min(task.preferred_chunk_minutes, max(candidates))
        preferred_candidates = [duration for duration in candidates if duration <= preferred]
        if preferred_candidates:
            return max(preferred_candidates)
    return max(candidates)


def _block_duration_candidates(
    task: HumanTask,
    config: HumanDailySolverConfig,
    *,
    remaining_minutes: int,
    available_minutes: int,
) -> list[int]:
    if remaining_minutes <= 0 or available_minutes <= 0:
        return []
    max_duration = min(remaining_minutes, available_minutes, config.max_candidate_block_minutes)
    minimum_duration = min(_effective_min_block_minutes(task, config), remaining_minutes)
    if max_duration < minimum_duration:
        return []
    durations = {minimum_duration, max_duration}
    first_aligned_duration = _ceil_to_multiple(minimum_duration, config.block_granularity_minutes)
    durations.update(range(first_aligned_duration, max_duration + 1, config.block_granularity_minutes))
    if task.preferred_chunk_minutes is not None:
        durations.add(max(minimum_duration, min(task.preferred_chunk_minutes, max_duration)))
    return sorted(duration for duration in durations if minimum_duration <= duration <= max_duration)


def _effective_min_block_minutes(task: HumanTask, config: HumanDailySolverConfig) -> int:
    if task.min_chunk_minutes is not None:
        return task.min_chunk_minutes
    return config.min_block_minutes


def _ceil_to_multiple(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


def _place_timeline_candidate(
    candidate: _TimelineCandidate,
    scheduled_blocks: list[HumanScheduleBlock],
    scheduled_minutes: dict[str, int],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
) -> HumanScheduleBlock:
    chunk = candidate.chunk
    end_minutes = chunk.start_minutes + chunk.duration_minutes
    block = HumanScheduleBlock(
        task_id=candidate.task.id,
        slot_index=chunk.slot.index,
        start=_time_from_minutes(chunk.start_minutes),
        end=_time_from_minutes(end_minutes),
        duration_minutes=chunk.duration_minutes,
    )
    scheduled_blocks.append(block)
    scheduled_minutes[candidate.task.id] = scheduled_minutes.get(candidate.task.id, 0) + chunk.duration_minutes
    slot_usage[chunk.slot.index] += chunk.duration_minutes
    slot_cursors[chunk.slot.index] = end_minutes
    return block


def _unscheduled_reason(
    task: HumanTask,
    fixture: HumanDailyFixture,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    slot_usage: dict[int, int],
) -> str:
    missing = [
        prereq
        for prereq in fixture.task_dependencies.get(task.id, [])
        if not _task_completed_by_end(prereq, scheduled_blocks, tasks_by_id)
    ]
    if missing:
        return "dependency_not_scheduled"
    if task.remaining_minutes <= 0:
        return "task_has_no_remaining_minutes"
    compatible_slots = [slot for slot in fixture.time_slots if _can_use_slot(task, slot)]
    if not compatible_slots:
        return "no_project_compatible_slot"
    if not _task_can_schedule_block(task, compatible_slots, slot_usage, fixture.solver_config):
        return "insufficient_remaining_capacity"
    return "not_selected_by_solver"


def _task_completed_by(
    task_id: str,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    end_minutes: int,
) -> bool:
    task = tasks_by_id.get(task_id)
    if task is None:
        return False
    if task.remaining_minutes <= 0:
        return True
    return _scheduled_minutes_for_task_by(task_id, scheduled_blocks, end_minutes) >= task.remaining_minutes


def _task_completed_by_end(
    task_id: str,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
) -> bool:
    task = tasks_by_id.get(task_id)
    if task is None:
        return False
    if task.remaining_minutes <= 0:
        return True
    return (
        sum(block.duration_minutes for block in scheduled_blocks if block.task_id == task_id) >= task.remaining_minutes
    )


def _candidate_completes_task_by_end(
    task: HumanTask,
    scheduled_blocks: list[HumanScheduleBlock],
    chunk: _TimelineChunk,
) -> bool:
    if task.remaining_minutes <= 0:
        return True
    candidate_end = chunk.start_minutes + chunk.duration_minutes
    completed_minutes = _scheduled_minutes_for_task_by(task.id, scheduled_blocks, candidate_end)
    return completed_minutes + chunk.duration_minutes >= task.remaining_minutes


def _scheduled_minutes_for_task_by(
    task_id: str,
    scheduled_blocks: list[HumanScheduleBlock],
    end_minutes: int,
) -> int:
    return sum(
        block.duration_minutes
        for block in scheduled_blocks
        if block.task_id == task_id and _minutes(block.end) <= end_minutes
    )


def _task_can_schedule_block(
    task: HumanTask,
    slots: list[HumanTimeSlot],
    slot_usage: dict[int, int],
    config: HumanDailySolverConfig,
) -> bool:
    if task.remaining_minutes <= 0:
        return False
    for slot in sorted(slots, key=lambda item: (_minutes(item.start), item.index)):
        if _block_duration_candidates(
            task,
            config,
            remaining_minutes=task.remaining_minutes,
            available_minutes=slot.effective_capacity_minutes - slot_usage[slot.index],
        ):
            return True
    return False


def _timeline_candidate_key(
    candidate: _TimelineCandidate,
) -> tuple[int, int, int, int, int, str]:
    task = candidate.task
    due_key = -1_000_000_000 if task.due_at is None else -task.due_at.toordinal()
    return (
        candidate.score.total,
        due_key,
        -task.priority,
        _preferred_chunk_key(task, candidate.chunk.duration_minutes),
        candidate.chunk.duration_minutes,
        task.id,
    )


def _preferred_chunk_key(task: HumanTask, duration_minutes: int) -> int:
    if task.preferred_chunk_minutes is None:
        return 0
    return -abs(duration_minutes - task.preferred_chunk_minutes)


def _timeline_score_breakdowns(
    fixture: HumanDailyFixture,
    blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    slots_by_index: dict[int, HumanTimeSlot],
) -> list[HumanScoreBreakdown]:
    scores: list[HumanScoreBreakdown] = []
    scheduled_so_far: list[HumanScheduleBlock] = []
    slot_usage_so_far = {slot.index: 0 for slot in fixture.time_slots}

    for block in blocks:
        task = tasks_by_id.get(block.task_id)
        slot = slots_by_index.get(block.slot_index)
        if task is None or slot is None:
            continue
        if block.is_fixed:
            scores.append(_base_score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=True))
        else:
            chunk = _TimelineChunk(
                slot=slot,
                start_minutes=_minutes(block.start),
                duration_minutes=block.duration_minutes,
            )
            scores.append(
                _score_breakdown(
                    task,
                    slot,
                    fixture,
                    is_fixed=False,
                    scheduled_blocks=scheduled_so_far,
                    tasks_by_id=tasks_by_id,
                    slot_usage=slot_usage_so_far,
                    start_minutes=_minutes(block.start),
                    duration_minutes=block.duration_minutes,
                    include_dependency_unlock=_candidate_completes_task_by_end(task, scheduled_so_far, chunk),
                )
            )
        slot_usage_so_far[block.slot_index] += block.duration_minutes
        scheduled_so_far.append(block)
    return scores


def _score_breakdown(
    task: HumanTask,
    slot: HumanTimeSlot,
    fixture: HumanDailyFixture,
    *,
    is_fixed: bool,
    scheduled_blocks: list[HumanScheduleBlock] | None = None,
    tasks_by_id: dict[str, HumanTask] | None = None,
    slot_usage: dict[int, int] | None = None,
    start_minutes: int | None = None,
    duration_minutes: int | None = None,
    include_dependency_unlock: bool = True,
) -> HumanScoreBreakdown:
    config = fixture.solver_config
    breakdown = _base_score_breakdown(task, slot, fixture.date, config, is_fixed=is_fixed)
    if scheduled_blocks is None or tasks_by_id is None or slot_usage is None or start_minutes is None:
        return breakdown

    score_duration = task.remaining_minutes if duration_minutes is None else duration_minutes
    components = dict(breakdown.components)
    if include_dependency_unlock and duration_minutes is not None:
        components["dependency_unlock"] = _dependency_unlock_score(
            task,
            fixture,
            scheduled_blocks,
            tasks_by_id,
            start_minutes + duration_minutes,
            duration_minutes,
            config,
        )
    components["project_switch"] = -_project_switch_penalty(task, scheduled_blocks, tasks_by_id, start_minutes, config)
    components["continuous_work"] = -_continuous_work_penalty(score_duration, scheduled_blocks, start_minutes, config)
    components["gap_fill"] = _gap_fill_score(score_duration, slot, slot_usage, config)
    return HumanScoreBreakdown(
        task_id=task.id,
        slot_index=slot.index,
        total=sum(components.values()),
        components=components,
    )


def _base_score_breakdown(
    task: HumanTask,
    slot: HumanTimeSlot,
    schedule_date: date,
    config: HumanDailySolverConfig,
    *,
    is_fixed: bool,
) -> HumanScoreBreakdown:
    priority = max(1, config.priority_score_base - task.priority)
    kind = config.kind_match_score if task.work_kind == slot.work_kind else config.kind_mismatch_score
    deadline = _deadline_score(task, schedule_date, config)
    fixed = config.fixed_assignment_score if is_fixed else 0
    components = {
        "priority": priority,
        "kind": kind,
        "deadline": deadline,
        "fixed": fixed,
        "dependency_unlock": 0,
        "project_switch": 0,
        "continuous_work": 0,
        "gap_fill": 0,
    }
    return HumanScoreBreakdown(
        task_id=task.id,
        slot_index=slot.index,
        total=sum(components.values()),
        components=components,
    )


def _dependency_unlock_score(
    task: HumanTask,
    fixture: HumanDailyFixture,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    candidate_end_minutes: int,
    candidate_duration_minutes: int,
    config: HumanDailySolverConfig,
) -> int:
    unlocked_count = 0
    for dependent_id, prerequisites in fixture.task_dependencies.items():
        if task.id not in prerequisites:
            continue
        if _task_completed_by(dependent_id, scheduled_blocks, tasks_by_id, candidate_end_minutes):
            continue
        if all(
            _prerequisite_completed_with_candidate(
                prereq,
                task,
                scheduled_blocks,
                tasks_by_id,
                candidate_end_minutes,
                candidate_duration_minutes,
            )
            for prereq in prerequisites
        ):
            unlocked_count += 1
    return unlocked_count * config.dependency_unlock_score


def _prerequisite_completed_with_candidate(
    prereq_id: str,
    candidate_task: HumanTask,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    candidate_end_minutes: int,
    candidate_duration_minutes: int,
) -> bool:
    if prereq_id != candidate_task.id:
        return _task_completed_by(prereq_id, scheduled_blocks, tasks_by_id, candidate_end_minutes)
    if candidate_task.remaining_minutes <= 0:
        return True
    completed_minutes = _scheduled_minutes_for_task_by(prereq_id, scheduled_blocks, candidate_end_minutes)
    return completed_minutes + candidate_duration_minutes >= candidate_task.remaining_minutes


def _project_switch_penalty(
    task: HumanTask,
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    start_minutes: int,
    config: HumanDailySolverConfig,
) -> int:
    if config.project_switch_penalty == 0 or not task.project_id:
        return 0
    previous_block = _previous_block(scheduled_blocks, start_minutes)
    if previous_block is None:
        return 0
    gap_minutes = start_minutes - _minutes(previous_block.end)
    if gap_minutes > 0 and gap_minutes >= config.project_switch_reset_gap_minutes:
        return 0
    previous_task = tasks_by_id.get(previous_block.task_id)
    if previous_task is None or not previous_task.project_id:
        return 0
    if previous_task.project_id == task.project_id:
        return 0
    return config.project_switch_penalty


def _continuous_work_penalty(
    duration_minutes: int,
    scheduled_blocks: list[HumanScheduleBlock],
    start_minutes: int,
    config: HumanDailySolverConfig,
) -> int:
    if config.long_continuous_penalty == 0 or config.long_continuous_threshold_minutes == 0:
        return 0
    continuous_minutes = _continuous_work_minutes_before(
        scheduled_blocks,
        start_minutes,
        config.break_reset_gap_minutes,
    )
    if continuous_minutes + duration_minutes <= config.long_continuous_threshold_minutes:
        return 0
    return config.long_continuous_penalty


def _gap_fill_score(
    duration_minutes: int,
    slot: HumanTimeSlot,
    slot_usage: dict[int, int],
    config: HumanDailySolverConfig,
) -> int:
    if config.small_gap_fill_score == 0:
        return 0
    remaining_before = slot.effective_capacity_minutes - slot_usage[slot.index]
    remaining_after = remaining_before - duration_minutes
    if 0 <= remaining_after <= config.small_gap_minutes:
        return config.small_gap_fill_score
    return 0


def _previous_block(
    scheduled_blocks: list[HumanScheduleBlock],
    start_minutes: int,
) -> HumanScheduleBlock | None:
    previous_blocks = [block for block in scheduled_blocks if _minutes(block.end) <= start_minutes]
    if not previous_blocks:
        return None
    return max(previous_blocks, key=lambda block: (_minutes(block.end), block.task_id))


def _continuous_work_minutes_before(
    scheduled_blocks: list[HumanScheduleBlock],
    start_minutes: int,
    break_reset_gap_minutes: int,
) -> int:
    continuous_minutes = 0
    cursor_minutes = start_minutes
    previous_blocks = sorted(
        (block for block in scheduled_blocks if _minutes(block.end) <= start_minutes),
        key=lambda block: (_minutes(block.end), block.task_id),
        reverse=True,
    )
    for block in previous_blocks:
        gap_minutes = cursor_minutes - _minutes(block.end)
        if gap_minutes > 0 and gap_minutes >= break_reset_gap_minutes:
            break
        continuous_minutes += block.duration_minutes
        cursor_minutes = _minutes(block.start)
    return continuous_minutes


def _deadline_score(task: HumanTask, schedule_date: date, config: HumanDailySolverConfig) -> int:
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
    scheduled_blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    violations: list[HumanConstraintViolation],
) -> None:
    for task_id, prerequisites in fixture.task_dependencies.items():
        task_blocks = [block for block in scheduled_blocks if block.task_id == task_id]
        if not task_blocks:
            continue
        for task_block in task_blocks:
            for prereq in prerequisites:
                if _task_completed_by(prereq, scheduled_blocks, tasks_by_id, _minutes(task_block.start)):
                    continue
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
