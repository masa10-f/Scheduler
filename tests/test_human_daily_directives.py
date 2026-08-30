from __future__ import annotations

from datetime import date, time

from humancompiler_scheduler.human import (
    HumanAvailabilityWindow,
    HumanCandidatePool,
    HumanDailyFixture,
    HumanFixedEvent,
    HumanFlexibleDailyFixture,
    HumanFrozenTaskBlock,
    HumanTask,
    HumanTimeSlot,
    HumanWorkKind,
    compile_human_flexible_daily_fixture,
    human_daily_fixture_from_dict,
    solve_human_daily_timeline,
)


def _task(task_id: str, *, priority: int = 3, minutes: int = 60) -> HumanTask:
    return HumanTask(
        id=task_id,
        title=task_id,
        remaining_minutes=minutes,
        priority=priority,
        work_kind=HumanWorkKind.FOCUSED_WORK,
    )


def test_required_directive_wins_and_keeps_directive_id() -> None:
    required = _task("required", priority=5)
    urgent = _task("urgent", priority=1)
    fixture = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[required, urgent],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(10),
                work_kind=HumanWorkKind.FOCUSED_WORK,
            )
        ],
        candidate_pools=[
            HumanCandidatePool(
                id="specific",
                eligible_task_ids=frozenset({"required"}),
                required_task_id="required",
                requested_minutes=60,
            ),
            HumanCandidatePool(
                id="pool",
                eligible_task_ids=frozenset({"required", "urgent"}),
            ),
        ],
    )

    report = solve_human_daily_timeline(compile_human_flexible_daily_fixture(fixture))

    assert [block.task_id for block in report.plan.blocks] == ["required"]
    assert report.plan.blocks[0].directive_id == "specific"


def test_filter_pool_excludes_tasks_not_in_pool() -> None:
    included = _task("included", priority=5)
    excluded = _task("excluded", priority=1)
    fixture = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[included, excluded],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(10),
                work_kind=HumanWorkKind.FOCUSED_WORK,
            )
        ],
        candidate_pools=[
            HumanCandidatePool(
                id="project-a",
                eligible_task_ids=frozenset({"included"}),
            )
        ],
    )

    report = solve_human_daily_timeline(compile_human_flexible_daily_fixture(fixture))

    assert [block.task_id for block in report.plan.blocks] == ["included"]
    assert report.plan.blocks[0].directive_id == "project-a"


def test_specific_directive_splits_around_fixed_event() -> None:
    task = _task("specific", minutes=120)
    flexible = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[task],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(12),
                work_kind=HumanWorkKind.FOCUSED_WORK,
            )
        ],
        fixed_events=[HumanFixedEvent(title="meeting", start=time(10), end=time(11))],
        candidate_pools=[
            HumanCandidatePool(
                id="specific-request",
                eligible_task_ids=frozenset({task.id}),
                required_task_id=task.id,
                requested_minutes=120,
            )
        ],
    )

    report = solve_human_daily_timeline(compile_human_flexible_daily_fixture(flexible))

    assert [(block.start, block.end) for block in report.plan.blocks] == [
        (time(9), time(10)),
        (time(11), time(12)),
    ]
    assert {block.directive_id for block in report.plan.blocks} == {"specific-request"}


def test_overlapping_candidate_pools_are_assigned_deterministically() -> None:
    task = _task("shared", minutes=60)
    fixture = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[task],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(10),
                work_kind=HumanWorkKind.FOCUSED_WORK,
            )
        ],
        candidate_pools=[
            HumanCandidatePool(id="first", eligible_task_ids=frozenset({task.id})),
            HumanCandidatePool(id="second", eligible_task_ids=frozenset({task.id})),
        ],
    )

    report = solve_human_daily_timeline(compile_human_flexible_daily_fixture(fixture))

    assert [block.directive_id for block in report.plan.blocks] == ["first"]


def test_frozen_block_is_preserved_and_removed_from_availability() -> None:
    frozen = _task("frozen", minutes=120)
    flexible = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[frozen],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(12),
                work_kind=HumanWorkKind.FOCUSED_WORK,
            )
        ],
        frozen_blocks=[
            HumanFrozenTaskBlock(
                task_id="frozen",
                start=time(10),
                end=time(11),
                directive_id="manual",
            )
        ],
        candidate_pools=[
            HumanCandidatePool(
                id="remaining",
                eligible_task_ids=frozenset({"frozen"}),
            )
        ],
    )

    fixture = compile_human_flexible_daily_fixture(flexible)
    report = solve_human_daily_timeline(fixture)

    assert [(slot.start, slot.end) for slot in fixture.time_slots] == [
        (time(9), time(10)),
        (time(11), time(12)),
    ]
    frozen_result = next(block for block in report.plan.blocks if block.is_fixed)
    assert (frozen_result.start, frozen_result.end) == (time(10), time(11))
    assert frozen_result.directive_id == "manual"
    assert sum(block.duration_minutes for block in report.plan.blocks) == 120


def test_frozen_block_reserves_time_in_direct_time_slots() -> None:
    frozen = _task("frozen", minutes=60)
    other = _task("other", minutes=120)
    fixture = HumanDailyFixture(
        date=date(2030, 1, 2),
        tasks=[frozen, other],
        time_slots=[
            HumanTimeSlot(
                index=0,
                start=time(9),
                end=time(11),
                work_kind=HumanWorkKind.FOCUSED_WORK,
            )
        ],
        frozen_blocks=[
            HumanFrozenTaskBlock(
                task_id="frozen",
                start=time(9, 30),
                end=time(10, 30),
            )
        ],
    )

    report = solve_human_daily_timeline(fixture)

    for earlier, later in zip(report.plan.blocks, report.plan.blocks[1:], strict=False):
        assert earlier.end <= later.start
    other_blocks = [(block.start, block.end) for block in report.plan.blocks if block.task_id == "other"]
    assert other_blocks == [(time(9), time(9, 30)), (time(10, 30), time(11))]
    assert sum(block.duration_minutes for block in report.plan.blocks) == 120


def test_frozen_block_deducts_from_window_capacity() -> None:
    frozen = _task("frozen", minutes=60)
    other = _task("other", minutes=120)
    flexible = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[frozen, other],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(12),
                work_kind=HumanWorkKind.FOCUSED_WORK,
                capacity_minutes=90,
            )
        ],
        frozen_blocks=[
            HumanFrozenTaskBlock(
                task_id="frozen",
                start=time(9),
                end=time(10),
            )
        ],
    )

    fixture = compile_human_flexible_daily_fixture(flexible)
    report = solve_human_daily_timeline(fixture)

    assert [slot.effective_capacity_minutes for slot in fixture.time_slots] == [30]
    other_blocks = [(block.start, block.end) for block in report.plan.blocks if block.task_id == "other"]
    assert other_blocks == [(time(10), time(10, 30))]
    assert sum(block.duration_minutes for block in report.plan.blocks) == 90


def test_frozen_block_exhausting_window_capacity_blocks_other_tasks() -> None:
    frozen = _task("frozen", minutes=60)
    other = _task("other", minutes=60)
    flexible = HumanFlexibleDailyFixture(
        date=date(2030, 1, 2),
        tasks=[frozen, other],
        availability_windows=[
            HumanAvailabilityWindow(
                start=time(9),
                end=time(12),
                work_kind=HumanWorkKind.FOCUSED_WORK,
                capacity_minutes=60,
            )
        ],
        frozen_blocks=[
            HumanFrozenTaskBlock(
                task_id="frozen",
                start=time(9),
                end=time(10),
            )
        ],
    )

    fixture = compile_human_flexible_daily_fixture(flexible)
    report = solve_human_daily_timeline(fixture)

    assert [slot.effective_capacity_minutes for slot in fixture.time_slots] == [0]
    assert [block.task_id for block in report.plan.blocks] == ["frozen"]
    assert "other" in report.plan.unscheduled_task_ids


def test_mapping_parser_accepts_directive_fields() -> None:
    fixture = human_daily_fixture_from_dict(
        {
            "date": "2030-01-02",
            "tasks": [
                {
                    "id": "task",
                    "title": "Task",
                    "remaining_minutes": 60,
                    "work_kind": "focused_work",
                }
            ],
            "availability_windows": [{"start": "09:00", "end": "11:00", "work_kind": "focused_work"}],
            "frozen_blocks": [
                {
                    "task_id": "task",
                    "start": "09:00",
                    "end": "09:30",
                    "directive_id": "frozen",
                }
            ],
            "candidate_pools": [
                {
                    "id": "specific",
                    "eligible_task_ids": ["task"],
                    "required_task_id": "task",
                    "requested_minutes": 60,
                }
            ],
        }
    )

    assert fixture.frozen_blocks[0].directive_id == "frozen"
    assert fixture.candidate_pools[0].required_task_id == "task"
