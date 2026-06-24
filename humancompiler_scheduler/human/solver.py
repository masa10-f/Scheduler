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
    HumanSolverComparison,
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
    chunks: tuple[_TimelineChunk, ...]
    score: HumanScoreBreakdown


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


def _solve_daily(fixture: HumanDailyFixture, *, solver_name: str, sequential_starts: bool) -> HumanSolverReport:
    tasks_by_id = {task.id: task for task in fixture.tasks}
    slots_by_index = {slot.index: slot for slot in fixture.time_slots}
    sorted_slots = sorted(fixture.time_slots, key=lambda slot: (_minutes(slot.start), slot.index))
    completed: dict[str, HumanScheduleBlock] = {}
    scheduled_blocks: list[HumanScheduleBlock] = []
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
            completed,
            scheduled_blocks,
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
            completed,
            scheduled_blocks,
            slot_usage,
            slot_cursors,
            unscheduled,
        )
    else:
        _fill_legacy_slots(
            fixture,
            sorted_slots,
            completed,
            scheduled_blocks,
            slot_usage,
            score_breakdown,
            unscheduled,
        )

    for task in fixture.tasks:
        if task.id in completed or task.id in unscheduled:
            continue
        unscheduled[task.id] = _unscheduled_reason(task, fixture, completed, slot_usage)

    _add_dependency_violations(fixture, completed, violations)
    blocks = sorted(
        scheduled_blocks,
        key=lambda block: (_minutes(block.start), block.slot_index, block.task_id),
    )
    if sequential_starts:
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
    completed: dict[str, HumanScheduleBlock],
    scheduled_blocks: list[HumanScheduleBlock],
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
    if task.id in completed:
        violations.append(
            HumanConstraintViolation(
                code="duplicate_fixed_assignment",
                message=f"task {task.id} has multiple fixed assignments",
                task_id=task.id,
                slot_index=slot.index,
            )
        )
        return

    duration = fixed.duration_minutes if fixed.duration_minutes is not None else task.remaining_minutes
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
    block = HumanScheduleBlock(
        task_id=task.id,
        slot_index=slot.index,
        start=_time_from_minutes(start_minutes),
        end=_time_from_minutes(end_minutes),
        duration_minutes=duration,
        is_fixed=True,
    )
    completed[task.id] = block
    scheduled_blocks.append(block)
    slot_usage[slot.index] += duration
    if sequential_starts:
        slot_cursors[slot.index] = end_minutes
    score_breakdown.append(_base_score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=True))


def _fill_timeline_slots(
    fixture: HumanDailyFixture,
    sorted_slots: list[HumanTimeSlot],
    completed: dict[str, HumanScheduleBlock],
    scheduled_blocks: list[HumanScheduleBlock],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    unscheduled: dict[str, str],
) -> None:
    tasks_by_id = {task.id: task for task in fixture.tasks}
    for slot_position, slot in enumerate(sorted_slots):
        future_slots = sorted_slots[slot_position + 1 :]
        while True:
            candidate_start = slot_cursors[slot.index]
            if slot.effective_capacity_minutes - slot_usage[slot.index] <= 0:
                break
            candidates = _timeline_candidates(
                fixture,
                slot,
                future_slots,
                completed,
                scheduled_blocks,
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
            final_block = _place_timeline_candidate(
                candidate,
                scheduled_blocks,
                slot_usage,
                slot_cursors,
            )
            completed[candidate.task.id] = final_block

    for task_id, prerequisites in fixture.task_dependencies.items():
        dependent_task = tasks_by_id.get(task_id)
        if dependent_task and dependent_task.id not in completed and dependent_task.id not in unscheduled:
            missing = [prereq for prereq in prerequisites if prereq not in completed]
            if missing:
                unscheduled[dependent_task.id] = "dependency_not_scheduled"


def _fill_legacy_slots(
    fixture: HumanDailyFixture,
    sorted_slots: list[HumanTimeSlot],
    completed: dict[str, HumanScheduleBlock],
    scheduled_blocks: list[HumanScheduleBlock],
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
        if task.id in completed or task.id in unscheduled:
            continue
        candidate_slots = [
            slot
            for slot in sorted_slots
            if _dependencies_allow_legacy_slot(task.id, slot, fixture, completed)
            and _can_use_slot(task, slot)
            and task.remaining_minutes <= slot.effective_capacity_minutes - slot_usage[slot.index]
        ]
        if not candidate_slots:
            unscheduled[task.id] = _unscheduled_reason(task, fixture, completed, slot_usage)
            continue
        slot = max(
            candidate_slots,
            key=lambda candidate: _legacy_candidate_key(task, candidate, fixture.date, fixture.solver_config),
        )
        start_minutes = _minutes(slot.start)
        end_minutes = start_minutes + task.remaining_minutes
        block = HumanScheduleBlock(
            task_id=task.id,
            slot_index=slot.index,
            start=_time_from_minutes(start_minutes),
            end=_time_from_minutes(end_minutes),
            duration_minutes=task.remaining_minutes,
        )
        completed[task.id] = block
        scheduled_blocks.append(block)
        slot_usage[slot.index] += task.remaining_minutes
        score_breakdown.append(_base_score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=False))


def _dependencies_finish_by(
    task_id: str,
    fixture: HumanDailyFixture,
    scheduled: dict[str, HumanScheduleBlock],
    start_minutes: int,
) -> bool:
    for prereq in fixture.task_dependencies.get(task_id, []):
        block = scheduled.get(prereq)
        if block is None or _minutes(block.end) > start_minutes:
            return False
    return True


def _dependencies_allow_legacy_slot(
    task_id: str,
    slot: HumanTimeSlot,
    fixture: HumanDailyFixture,
    scheduled: dict[str, HumanScheduleBlock],
) -> bool:
    for prereq in fixture.task_dependencies.get(task_id, []):
        block = scheduled.get(prereq)
        if block is None or _minutes(block.end) > _minutes(slot.start):
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
    future_slots: list[HumanTimeSlot],
    completed: dict[str, HumanScheduleBlock],
    scheduled_blocks: list[HumanScheduleBlock],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    tasks_by_id: dict[str, HumanTask],
    unscheduled: dict[str, str],
    candidate_start: int,
) -> list[_TimelineCandidate]:
    candidates: list[_TimelineCandidate] = []
    for task in fixture.tasks:
        if task.id in completed or task.id in unscheduled:
            continue
        if not _dependencies_finish_by(task.id, fixture, completed, candidate_start):
            continue
        if not _can_use_slot(task, slot):
            continue
        if _should_defer_for_future_kind_match(
            task,
            slot,
            future_slots,
            slot_usage,
            slot_cursors,
            fixture.date,
            fixture.solver_config,
        ):
            continue
        chunks = _build_timeline_chunks(task, slot, future_slots, slot_usage, slot_cursors)
        if chunks is None:
            continue
        score = _score_breakdown(
            task,
            slot,
            fixture,
            is_fixed=False,
            completed=completed,
            scheduled_blocks=scheduled_blocks,
            tasks_by_id=tasks_by_id,
            slot_usage=slot_usage,
            start_minutes=candidate_start,
            duration_minutes=chunks[0].duration_minutes,
        )
        candidates.append(_TimelineCandidate(task=task, chunks=chunks, score=score))
    return candidates


def _build_timeline_chunks(
    task: HumanTask,
    slot: HumanTimeSlot,
    future_slots: list[HumanTimeSlot],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
) -> tuple[_TimelineChunk, ...] | None:
    current_available = slot.effective_capacity_minutes - slot_usage[slot.index]
    if current_available <= 0:
        return None
    if not task.split_allowed or task.remaining_minutes <= current_available:
        if task.remaining_minutes <= current_available:
            return (
                _TimelineChunk(
                    slot=slot,
                    start_minutes=slot_cursors[slot.index],
                    duration_minutes=task.remaining_minutes,
                ),
            )
        return None

    split_slots = [
        _TimelineChunk(slot=slot, start_minutes=slot_cursors[slot.index], duration_minutes=current_available),
    ]
    for future_slot in future_slots:
        available_minutes = future_slot.effective_capacity_minutes - slot_usage[future_slot.index]
        if available_minutes <= 0 or not _can_use_slot(task, future_slot):
            continue
        split_slots.append(
            _TimelineChunk(
                slot=future_slot,
                start_minutes=slot_cursors[future_slot.index],
                duration_minutes=available_minutes,
            )
        )
    return _split_chunks_for_slots(task, split_slots, require_first_slot=True)


def _split_chunks_for_slots(
    task: HumanTask,
    slots: list[_TimelineChunk],
    *,
    require_first_slot: bool,
) -> tuple[_TimelineChunk, ...] | None:
    min_chunk_minutes = _min_chunk_minutes(task)
    preferred_chunk_minutes = _preferred_chunk_minutes(task, min_chunk_minutes)
    memo: dict[tuple[int, int, bool], tuple[_TimelineChunk, ...] | None] = {}

    def search(index: int, remaining_minutes: int, current_slot_required: bool) -> tuple[_TimelineChunk, ...] | None:
        if remaining_minutes == 0:
            return ()
        if index >= len(slots):
            return None
        memo_key = (index, remaining_minutes, current_slot_required)
        if memo_key in memo:
            return memo[memo_key]

        slot = slots[index]
        later_capacity = sum(item.duration_minutes for item in slots[index + 1 :])
        for duration_minutes in _chunk_duration_candidates(
            remaining_minutes,
            slot.duration_minutes,
            min_chunk_minutes,
            preferred_chunk_minutes,
        ):
            remaining_after_chunk = remaining_minutes - duration_minutes
            if remaining_after_chunk > later_capacity:
                continue
            if 0 < remaining_after_chunk < min_chunk_minutes:
                continue
            later_chunks = search(index + 1, remaining_after_chunk, current_slot_required=False)
            if later_chunks is not None:
                result = (
                    _TimelineChunk(
                        slot=slot.slot,
                        start_minutes=slot.start_minutes,
                        duration_minutes=duration_minutes,
                    ),
                    *later_chunks,
                )
                memo[memo_key] = result
                return result

        if current_slot_required:
            memo[memo_key] = None
            return None

        skipped_result = search(index + 1, remaining_minutes, current_slot_required=False)
        memo[memo_key] = skipped_result
        return skipped_result

    return search(0, task.remaining_minutes, current_slot_required=require_first_slot)


def _chunk_duration_candidates(
    remaining_minutes: int,
    available_minutes: int,
    min_chunk_minutes: int,
    preferred_chunk_minutes: int,
) -> list[int]:
    max_duration = min(remaining_minutes, available_minutes)
    minimum_duration = min(min_chunk_minutes, remaining_minutes)
    if max_duration < minimum_duration:
        return []
    return sorted(
        range(minimum_duration, max_duration + 1),
        key=lambda duration: (abs(duration - preferred_chunk_minutes), -duration),
    )


def _min_chunk_minutes(task: HumanTask) -> int:
    if task.min_chunk_minutes is None:
        return 1
    return min(task.min_chunk_minutes, task.remaining_minutes)


def _preferred_chunk_minutes(task: HumanTask, min_chunk_minutes: int) -> int:
    if task.preferred_chunk_minutes is None:
        return task.remaining_minutes
    return max(min_chunk_minutes, min(task.preferred_chunk_minutes, task.remaining_minutes))


def _place_timeline_candidate(
    candidate: _TimelineCandidate,
    scheduled_blocks: list[HumanScheduleBlock],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
) -> HumanScheduleBlock:
    final_block: HumanScheduleBlock | None = None
    for chunk in candidate.chunks:
        end_minutes = chunk.start_minutes + chunk.duration_minutes
        block = HumanScheduleBlock(
            task_id=candidate.task.id,
            slot_index=chunk.slot.index,
            start=_time_from_minutes(chunk.start_minutes),
            end=_time_from_minutes(end_minutes),
            duration_minutes=chunk.duration_minutes,
        )
        scheduled_blocks.append(block)
        slot_usage[chunk.slot.index] += chunk.duration_minutes
        slot_cursors[chunk.slot.index] = end_minutes
        final_block = block
    if final_block is None:
        raise ValueError("timeline candidate must contain at least one chunk")
    return final_block


def _should_defer_for_future_kind_match(
    task: HumanTask,
    slot: HumanTimeSlot,
    future_slots: list[HumanTimeSlot],
    slot_usage: dict[int, int],
    slot_cursors: dict[int, int],
    schedule_date: date,
    config: HumanDailySolverConfig,
) -> bool:
    if task.work_kind == slot.work_kind:
        return False
    if _deadline_score(task, schedule_date, config) > 0:
        return False
    matching_slots = [
        _TimelineChunk(
            slot=future_slot,
            start_minutes=slot_cursors[future_slot.index],
            duration_minutes=future_slot.effective_capacity_minutes - slot_usage[future_slot.index],
        )
        for future_slot in future_slots
        if task.work_kind == future_slot.work_kind
        and _can_use_slot(task, future_slot)
        and future_slot.effective_capacity_minutes - slot_usage[future_slot.index] > 0
    ]
    if not task.split_allowed:
        return any(task.remaining_minutes <= future_slot.duration_minutes for future_slot in matching_slots)
    return _split_chunks_for_slots(task, matching_slots, require_first_slot=False) is not None


def _unscheduled_reason(
    task: HumanTask,
    fixture: HumanDailyFixture,
    scheduled: dict[str, HumanScheduleBlock],
    slot_usage: dict[int, int],
) -> str:
    missing = [prereq for prereq in fixture.task_dependencies.get(task.id, []) if prereq not in scheduled]
    if missing:
        return "dependency_not_scheduled"
    if task.remaining_minutes <= 0:
        return "task_has_no_remaining_minutes"
    compatible_slots = [slot for slot in fixture.time_slots if _can_use_slot(task, slot)]
    if not compatible_slots:
        return "no_project_compatible_slot"
    reason = "not_selected_by_solver"
    if task.split_allowed:
        split_fits_empty_slots = _split_task_fits_slots(task, compatible_slots)
        split_fits_remaining_slots = _split_task_fits_slots(task, compatible_slots, slot_usage=slot_usage)
        if not split_fits_empty_slots or not split_fits_remaining_slots:
            reason = "insufficient_remaining_capacity"
    elif all(task.remaining_minutes > slot.effective_capacity_minutes for slot in compatible_slots):
        reason = "task_longer_than_any_slot"
    elif all(
        task.remaining_minutes > slot.effective_capacity_minutes - slot_usage[slot.index] for slot in compatible_slots
    ):
        reason = "insufficient_remaining_capacity"
    return reason


def _split_task_fits_slots(
    task: HumanTask,
    slots: list[HumanTimeSlot],
    *,
    slot_usage: dict[int, int] | None = None,
) -> bool:
    candidate_slots: list[_TimelineChunk] = []
    for slot in sorted(slots, key=lambda item: (_minutes(item.start), item.index)):
        used_minutes = 0 if slot_usage is None else slot_usage[slot.index]
        available_minutes = slot.effective_capacity_minutes - used_minutes
        if available_minutes <= 0:
            continue
        candidate_slots.append(
            _TimelineChunk(
                slot=slot,
                start_minutes=_minutes(slot.start) + used_minutes,
                duration_minutes=available_minutes,
            )
        )
    return _split_chunks_for_slots(task, candidate_slots, require_first_slot=False) is not None


def _timeline_candidate_key(
    candidate: _TimelineCandidate,
) -> tuple[int, int, int, str]:
    task = candidate.task
    due_key = -1_000_000_000 if task.due_at is None else -task.due_at.toordinal()
    return (candidate.score.total, due_key, -task.priority, task.id)


def _legacy_candidate_key(
    task: HumanTask,
    slot: HumanTimeSlot,
    schedule_date: date,
    config: HumanDailySolverConfig,
) -> tuple[int, int, str]:
    breakdown = _base_score_breakdown(task, slot, schedule_date, config, is_fixed=False)
    return (breakdown.total, -slot.index, task.id)


def _timeline_score_breakdowns(
    fixture: HumanDailyFixture,
    blocks: list[HumanScheduleBlock],
    tasks_by_id: dict[str, HumanTask],
    slots_by_index: dict[int, HumanTimeSlot],
) -> list[HumanScoreBreakdown]:
    scores: list[HumanScoreBreakdown] = []
    scheduled_so_far: list[HumanScheduleBlock] = []
    slot_usage_so_far = {slot.index: 0 for slot in fixture.time_slots}
    final_blocks_by_task = _final_blocks_by_task(blocks)

    for block in blocks:
        task = tasks_by_id.get(block.task_id)
        slot = slots_by_index.get(block.slot_index)
        if task is None or slot is None:
            continue
        if block.is_fixed:
            scores.append(_base_score_breakdown(task, slot, fixture.date, fixture.solver_config, is_fixed=True))
        else:
            completed_before = {
                task_id: final_block
                for task_id, final_block in final_blocks_by_task.items()
                if task_id != block.task_id and _minutes(final_block.end) <= _minutes(block.start)
            }
            is_final_task_block = final_blocks_by_task.get(block.task_id) == block
            scores.append(
                _score_breakdown(
                    task,
                    slot,
                    fixture,
                    is_fixed=False,
                    completed=completed_before,
                    scheduled_blocks=scheduled_so_far,
                    tasks_by_id=tasks_by_id,
                    slot_usage=slot_usage_so_far,
                    start_minutes=_minutes(block.start),
                    duration_minutes=block.duration_minutes,
                    include_dependency_unlock=is_final_task_block,
                )
            )
        slot_usage_so_far[block.slot_index] += block.duration_minutes
        scheduled_so_far.append(block)
    return scores


def _final_blocks_by_task(blocks: list[HumanScheduleBlock]) -> dict[str, HumanScheduleBlock]:
    final_blocks: dict[str, HumanScheduleBlock] = {}
    for block in blocks:
        existing = final_blocks.get(block.task_id)
        if existing is None or _block_order_key(block) > _block_order_key(existing):
            final_blocks[block.task_id] = block
    return final_blocks


def _block_order_key(block: HumanScheduleBlock) -> tuple[int, int, int, str]:
    return (_minutes(block.end), _minutes(block.start), block.slot_index, block.task_id)


def _score_breakdown(
    task: HumanTask,
    slot: HumanTimeSlot,
    fixture: HumanDailyFixture,
    *,
    is_fixed: bool,
    completed: dict[str, HumanScheduleBlock] | None = None,
    scheduled_blocks: list[HumanScheduleBlock] | None = None,
    tasks_by_id: dict[str, HumanTask] | None = None,
    slot_usage: dict[int, int] | None = None,
    start_minutes: int | None = None,
    duration_minutes: int | None = None,
    include_dependency_unlock: bool = True,
) -> HumanScoreBreakdown:
    config = fixture.solver_config
    breakdown = _base_score_breakdown(task, slot, fixture.date, config, is_fixed=is_fixed)
    if (
        completed is None
        or scheduled_blocks is None
        or tasks_by_id is None
        or slot_usage is None
        or start_minutes is None
    ):
        return breakdown

    score_duration = task.remaining_minutes if duration_minutes is None else duration_minutes
    components = dict(breakdown.components)
    if include_dependency_unlock:
        components["dependency_unlock"] = _dependency_unlock_score(task, fixture, completed, config)
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
    scheduled: dict[str, HumanScheduleBlock],
    config: HumanDailySolverConfig,
) -> int:
    unlocked_count = 0
    for dependent_id, prerequisites in fixture.task_dependencies.items():
        if task.id not in prerequisites or dependent_id in scheduled:
            continue
        other_prerequisites = [item for item in prerequisites if item != task.id]
        if all(prereq in scheduled for prereq in other_prerequisites):
            unlocked_count += 1
    return unlocked_count * config.dependency_unlock_score


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
