from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

from humancompiler_scheduler.human import (
    HumanDailyFixture,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanTask,
    HumanTimeSlot,
    HumanWorkKind,
    compare_human_daily_solvers,
    compile_human_flexible_daily_fixture,
    format_human_daily_compact,
    format_human_daily_comparison,
    human_daily_fixture_from_dict,
    human_flexible_daily_fixture_from_dict,
    load_human_daily_fixture,
    load_human_daily_solver_config,
    plan_daily_schedule,
    run_human_daily_review,
    solve_human_daily_legacy,
    solve_human_daily_timeline,
    write_human_daily_review,
)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "human"
REPO_ROOT = SAMPLES_DIR.parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


class HumanDailyFixtureTests(unittest.TestCase):
    def test_loads_editable_yaml_fixture(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")

        self.assertEqual(fixture.date.isoformat(), "2025-09-18")
        self.assertEqual(fixture.metadata["name"], "daily_basic")
        self.assertGreaterEqual(len(fixture.tasks), 20)
        self.assertEqual(fixture.tasks[0].priority, 1)
        self.assertEqual(fixture.time_slots[0].work_kind.value, "focused_work")
        self.assertIn("project_brief_revision", fixture.task_dependencies)

    def test_loads_tasks_from_relative_task_database(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_dependencies.yaml")
        task_ids = {task.id for task in fixture.tasks}

        self.assertIn("project_brief_outline", task_ids)
        self.assertIn("literature_summary", fixture.task_dependencies)
        self.assertEqual(
            fixture.task_dependencies["literature_summary"],
            ["research_notes"],
        )

    def test_public_plan_daily_schedule_accepts_mapping_and_config_override(self) -> None:
        report = plan_daily_schedule(
            {
                "date": "2026-05-20",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "10:00",
                        "work_kind": "focused_work",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Focused task",
                        "remaining_minutes": 30,
                        "priority": 1,
                        "work_kind": "focused_work",
                    }
                ],
            },
            solver_config={"kind_match_score": 20},
        )

        self.assertEqual(report.plan.status, "ok")
        self.assertEqual(report.plan.blocks[0].task_id, "task")
        self.assertEqual(report.config.kind_match_score, 20)

    def test_flexible_fixture_generates_slots_around_fixed_events_and_now(
        self,
    ) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "now": "2026-05-20T10:20:00",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                    },
                    {
                        "start": "13:00",
                        "end": "18:00",
                        "default_work_kind": "light_work",
                    },
                ],
                "fixed_events": [
                    {
                        "title": "Team sync",
                        "start": "11:00",
                        "end": "11:30",
                    },
                    {
                        "title": "Lab reservation",
                        "start": "15:00",
                        "end": "16:30",
                    },
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 30,
                    }
                ],
            }
        )

        slot_windows = [
            (
                slot.index,
                slot.start.strftime("%H:%M"),
                slot.end.strftime("%H:%M"),
                slot.work_kind.value,
            )
            for slot in fixture.time_slots
        ]

        self.assertEqual(
            slot_windows,
            [
                (0, "10:20", "11:00", "focused_work"),
                (1, "11:30", "12:00", "focused_work"),
                (2, "13:00", "15:00", "light_work"),
                (3, "16:30", "18:00", "light_work"),
            ],
        )

    def test_explicit_time_slots_take_precedence_over_flexible_windows(self) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "18:00",
                        "work_kind": "focused_work",
                    }
                ],
                "time_slots": [
                    {
                        "index": 7,
                        "start": "14:00",
                        "end": "15:00",
                        "work_kind": "study",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 30,
                    }
                ],
            }
        )

        self.assertEqual(len(fixture.time_slots), 1)
        self.assertEqual(fixture.time_slots[0].index, 7)
        self.assertEqual(fixture.time_slots[0].start.strftime("%H:%M"), "14:00")
        self.assertEqual(fixture.time_slots[0].work_kind, HumanWorkKind.STUDY)

    def test_flexible_fixture_clips_capacity_to_generated_slot_duration(
        self,
    ) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                        "capacity_minutes": 180,
                    },
                    {
                        "start": "13:00",
                        "end": "16:00",
                        "work_kind": "light_work",
                        "capacity_minutes": 45,
                    },
                ],
                "fixed_events": [
                    {
                        "title": "Morning break",
                        "start": "10:00",
                        "end": "11:00",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 30,
                    }
                ],
            }
        )

        self.assertEqual(
            [slot.effective_capacity_minutes for slot in fixture.time_slots],
            [60, 60, 45],
        )

    def test_flexible_fixture_distributes_window_capacity_across_split_slots(
        self,
    ) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                        "capacity_minutes": 90,
                    }
                ],
                "fixed_events": [
                    {
                        "title": "Meeting",
                        "start": "10:00",
                        "end": "11:00",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 30,
                    }
                ],
            }
        )

        self.assertEqual(
            [slot.effective_capacity_minutes for slot in fixture.time_slots],
            [60, 30],
        )

    def test_rolling_flexible_fixture_preserves_future_slot_indexes(self) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "now": "2026-05-20T10:30:00",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                    }
                ],
                "fixed_events": [
                    {
                        "title": "Meeting",
                        "start": "10:00",
                        "end": "11:00",
                    }
                ],
                "fixed_assignments": [
                    {
                        "task_id": "fixed_task",
                        "slot_index": 1,
                        "duration_minutes": 30,
                    }
                ],
                "tasks": [
                    {
                        "id": "fixed_task",
                        "title": "Fixed future task",
                        "remaining_minutes": 30,
                        "work_kind": "focused_work",
                    }
                ],
            }
        )

        self.assertEqual(
            [
                (
                    slot.index,
                    slot.start.strftime("%H:%M"),
                    slot.end.strftime("%H:%M"),
                )
                for slot in fixture.time_slots
            ],
            [(1, "11:00", "12:00")],
        )

        report = solve_human_daily_timeline(fixture)

        self.assertEqual(report.unscheduled_tasks, [])
        self.assertEqual(report.violations, [])
        self.assertEqual(report.plan.blocks[0].task_id, "fixed_task")
        self.assertEqual(report.plan.blocks[0].slot_index, 1)

    def test_flexible_fixture_keeps_task_split_policy(self) -> None:
        flexible = human_flexible_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 90,
                        "work_kind": "focused_work",
                        "split_allowed": True,
                        "min_chunk_minutes": 30,
                        "preferred_chunk_minutes": 60,
                    }
                ],
            }
        )

        fixture = compile_human_flexible_daily_fixture(flexible)

        self.assertTrue(fixture.tasks[0].split_allowed)
        self.assertEqual(fixture.tasks[0].min_chunk_minutes, 30)
        self.assertEqual(fixture.tasks[0].preferred_chunk_minutes, 60)

    def test_flexible_fixture_parses_string_false_split_policy(self) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 90,
                        "split_allowed": "false",
                    }
                ],
            }
        )

        self.assertFalse(fixture.tasks[0].split_allowed)

    def test_flexible_fixture_rejects_invalid_split_policy_boolean(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid boolean"):
            human_daily_fixture_from_dict(
                {
                    "date": "2026-05-20",
                    "availability_windows": [
                        {
                            "start": "09:00",
                            "end": "12:00",
                            "work_kind": "focused_work",
                        }
                    ],
                    "tasks": [
                        {
                            "id": "task",
                            "title": "Task",
                            "remaining_minutes": 90,
                            "split_allowed": "sometimes",
                        }
                    ],
                }
            )

    def test_now_after_fixture_date_drops_generated_slots(self) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "now": "2026-05-21T09:00:00",
                "availability_windows": [
                    {
                        "start": "09:00",
                        "end": "12:00",
                        "work_kind": "focused_work",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 30,
                    }
                ],
            }
        )

        self.assertEqual(fixture.time_slots, [])


class HumanDailySolverComparisonTests(unittest.TestCase):
    def test_legacy_solver_exposes_duplicate_slot_start_limitation(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")
        report = compare_human_daily_solvers(fixture).reports["legacy_slot"]

        starts_by_slot: dict[int, list[str]] = {}
        for block in report.plan.blocks:
            starts_by_slot.setdefault(block.slot_index, []).append(block.start.strftime("%H:%M"))

        self.assertIn("09:00", starts_by_slot[0])
        self.assertGreater(starts_by_slot[0].count("09:00"), 1)

    def test_timeline_solver_uses_sequential_starts_inside_slot(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(11, 0),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            tasks=[
                HumanTask(
                    id="first",
                    title="First",
                    remaining_minutes=60,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="second",
                    title="Second",
                    remaining_minutes=60,
                    priority=2,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )
        report = solve_human_daily_timeline(fixture)

        slot_zero_blocks = [block for block in report.plan.blocks if block.slot_index == 0]
        slot_zero_starts = [block.start.strftime("%H:%M") for block in slot_zero_blocks]

        self.assertGreaterEqual(len(slot_zero_starts), 2)
        self.assertEqual(len(slot_zero_starts), len(set(slot_zero_starts)))

    def test_dependencies_block_tasks_without_prerequisites(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_dependencies.yaml")
        report = compare_human_daily_solvers(fixture).reports["timeline_greedy"]

        unscheduled = {item.task_id: item.reason for item in report.unscheduled_tasks}
        scheduled_ids = {block.task_id for block in report.plan.blocks}

        self.assertIn("project_brief_outline", scheduled_ids)
        self.assertIn("project_brief_revision", scheduled_ids)
        self.assertEqual(unscheduled["integration_plan"], "dependency_not_scheduled")

    def test_timeline_solver_waits_for_prerequisite_finish_time(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(10, 0),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTimeSlot(
                    index=1,
                    start=time(15, 0),
                    end=time(15, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="prerequisite", slot_index=1)],
            task_dependencies={"dependent": ["prerequisite"]},
            tasks=[
                HumanTask(
                    id="prerequisite",
                    title="Prerequisite",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="dependent",
                    title="Dependent",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        scheduled_ids = {block.task_id for block in report.plan.blocks}
        self.assertNotIn("dependent", scheduled_ids)
        self.assertEqual(report.violations, [])

    def test_legacy_dependency_checks_use_slot_start_time(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            time_slots=[
                HumanTimeSlot(
                    index=10,
                    start=time(9, 0),
                    end=time(9, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTimeSlot(
                    index=0,
                    start=time(13, 0),
                    end=time(13, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="prerequisite", slot_index=10)],
            task_dependencies={"dependent": ["prerequisite"]},
            tasks=[
                HumanTask(
                    id="prerequisite",
                    title="Prerequisite",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="dependent",
                    title="Dependent",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )

        report = solve_human_daily_legacy(fixture)

        blocks = {block.task_id: block for block in report.plan.blocks}
        self.assertEqual(blocks["dependent"].start, time(13, 0))
        self.assertEqual(report.violations, [])

    def test_fixed_assignment_zero_duration_does_not_consume_capacity(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(9, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            fixed_assignments=[
                HumanFixedAssignment(
                    task_id="zero_duration_fixed",
                    slot_index=0,
                    duration_minutes=0,
                )
            ],
            tasks=[
                HumanTask(
                    id="zero_duration_fixed",
                    title="Zero duration fixed task",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="normal_task",
                    title="Normal task",
                    remaining_minutes=30,
                    priority=2,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        scheduled_ids = {block.task_id for block in report.plan.blocks}
        self.assertNotIn("zero_duration_fixed", scheduled_ids)
        self.assertIn("normal_task", scheduled_ids)

    def test_timeline_solver_prefers_task_that_unlocks_dependencies(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(10, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            task_dependencies={"dependent": ["prerequisite"]},
            tasks=[
                HumanTask(
                    id="unrelated",
                    title="Unrelated implementation task",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="prerequisite",
                    title="Prerequisite design note",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="dependent",
                    title="Dependent patch",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        self.assertEqual(report.plan.blocks[0].task_id, "prerequisite")
        score = next(item for item in report.score_breakdown if item.task_id == "prerequisite")
        self.assertEqual(score.components["dependency_unlock"], 3)

    def test_timeline_solver_penalizes_short_gap_project_switches(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            solver_config=HumanDailySolverConfig(project_switch_penalty=10),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(10, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="alpha_fixed", slot_index=0)],
            tasks=[
                HumanTask(
                    id="alpha_fixed",
                    title="Alpha setup",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                    project_id="alpha",
                ),
                HumanTask(
                    id="beta_followup",
                    title="Beta follow-up",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                    project_id="beta",
                ),
                HumanTask(
                    id="alpha_followup",
                    title="Alpha follow-up",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                    project_id="alpha",
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        self.assertEqual(report.plan.blocks[1].task_id, "alpha_followup")
        beta_score = next(item for item in report.score_breakdown if item.task_id == "beta_followup")
        self.assertEqual(beta_score.components["project_switch"], -10)

    def test_zero_project_switch_reset_gap_still_penalizes_contiguous_switch(
        self,
    ) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            solver_config=HumanDailySolverConfig(
                project_switch_penalty=10,
                project_switch_reset_gap_minutes=0,
            ),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(10, 0),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="alpha_fixed", slot_index=0)],
            tasks=[
                HumanTask(
                    id="alpha_fixed",
                    title="Alpha setup",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                    project_id="alpha",
                ),
                HumanTask(
                    id="beta_followup",
                    title="Beta follow-up",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                    project_id="beta",
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        beta_score = next(item for item in report.score_breakdown if item.task_id == "beta_followup")
        self.assertEqual(beta_score.components["project_switch"], -10)

    def test_timeline_solver_penalizes_long_continuous_work(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            solver_config=HumanDailySolverConfig(
                long_continuous_threshold_minutes=120,
                long_continuous_penalty=8,
            ),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(11, 30),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="deep_work", slot_index=0)],
            tasks=[
                HumanTask(
                    id="deep_work",
                    title="Deep work",
                    remaining_minutes=100,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="long_followup",
                    title="Long follow-up",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="short_followup",
                    title="Short follow-up",
                    remaining_minutes=10,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        self.assertEqual(report.plan.blocks[1].task_id, "short_followup")
        long_score = next(item for item in report.score_breakdown if item.task_id == "long_followup")
        self.assertEqual(long_score.components["continuous_work"], -8)

    def test_zero_break_reset_gap_still_counts_contiguous_work(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            solver_config=HumanDailySolverConfig(
                break_reset_gap_minutes=0,
                long_continuous_threshold_minutes=120,
                long_continuous_penalty=8,
            ),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(11, 10),
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                )
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="deep_work", slot_index=0)],
            tasks=[
                HumanTask(
                    id="deep_work",
                    title="Deep work",
                    remaining_minutes=100,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
                HumanTask(
                    id="long_followup",
                    title="Long follow-up",
                    remaining_minutes=30,
                    priority=1,
                    work_kind=HumanWorkKind.FOCUSED_WORK,
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        long_score = next(item for item in report.score_breakdown if item.task_id == "long_followup")
        self.assertEqual(long_score.components["continuous_work"], -8)

    def test_timeline_solver_rewards_small_gap_fill(self) -> None:
        fixture = HumanDailyFixture(
            date=date(2026, 5, 20),
            solver_config=HumanDailySolverConfig(
                small_gap_minutes=0,
                small_gap_fill_score=10,
            ),
            time_slots=[
                HumanTimeSlot(
                    index=0,
                    start=time(9, 0),
                    end=time(10, 0),
                    work_kind=HumanWorkKind.LIGHT_WORK,
                )
            ],
            fixed_assignments=[HumanFixedAssignment(task_id="fixed_work", slot_index=0)],
            tasks=[
                HumanTask(
                    id="fixed_work",
                    title="Fixed work",
                    remaining_minutes=40,
                    priority=1,
                    work_kind=HumanWorkKind.LIGHT_WORK,
                ),
                HumanTask(
                    id="high_priority_task",
                    title="High priority short task",
                    remaining_minutes=10,
                    priority=1,
                    work_kind=HumanWorkKind.LIGHT_WORK,
                ),
                HumanTask(
                    id="gap_filler",
                    title="Exact gap filler",
                    remaining_minutes=20,
                    priority=3,
                    work_kind=HumanWorkKind.LIGHT_WORK,
                ),
            ],
        )

        report = solve_human_daily_timeline(fixture)

        self.assertEqual(report.plan.blocks[1].task_id, "gap_filler")
        score = next(item for item in report.score_breakdown if item.task_id == "gap_filler")
        self.assertEqual(score.components["gap_fill"], 10)

    def test_parses_phase_two_solver_config_fields(self) -> None:
        fixture = human_daily_fixture_from_dict(
            {
                "date": "2026-05-20",
                "time_slots": [
                    {
                        "index": 0,
                        "start": "09:00",
                        "end": "10:00",
                        "work_kind": "focused_work",
                    }
                ],
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "remaining_minutes": 30,
                        "work_kind": "focused_work",
                    }
                ],
                "solver_config": {
                    "dependency_unlock_score": 7,
                    "project_switch_penalty": 8,
                    "project_switch_reset_gap_minutes": 45,
                    "long_continuous_threshold_minutes": 150,
                    "long_continuous_penalty": 9,
                    "break_reset_gap_minutes": 25,
                    "small_gap_minutes": 5,
                    "small_gap_fill_score": 6,
                },
            }
        )

        self.assertEqual(fixture.solver_config.dependency_unlock_score, 7)
        self.assertEqual(fixture.solver_config.project_switch_penalty, 8)
        self.assertEqual(fixture.solver_config.project_switch_reset_gap_minutes, 45)
        self.assertEqual(fixture.solver_config.long_continuous_threshold_minutes, 150)
        self.assertEqual(fixture.solver_config.long_continuous_penalty, 9)
        self.assertEqual(fixture.solver_config.break_reset_gap_minutes, 25)
        self.assertEqual(fixture.solver_config.small_gap_minutes, 5)
        self.assertEqual(fixture.solver_config.small_gap_fill_score, 6)

    def test_comparison_report_includes_review_fields(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")
        comparison = compare_human_daily_solvers(fixture)
        output = format_human_daily_comparison(comparison)

        self.assertIn("== legacy_slot ==", output)
        self.assertIn("== timeline_greedy ==", output)
        self.assertIn("unscheduled:", output)
        self.assertIn("score breakdown:", output)
        self.assertIn("constraint violations:", output)
        self.assertIn("solver settings:", output)

    def test_compact_report_keeps_terminal_output_short(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")
        comparison = compare_human_daily_solvers(fixture)
        output = format_human_daily_compact(comparison)

        self.assertIn("solver: timeline_greedy", output)
        self.assertIn("Timeline", output)
        self.assertIn("Unscheduled", output)
        self.assertIn("Use --verbose", output)
        self.assertNotIn("score breakdown:", output)
        self.assertNotIn("solver settings:", output)


class HumanDailyReviewTests(unittest.TestCase):
    def test_review_runs_multiple_fixtures_in_one_output(self) -> None:
        output = run_human_daily_review(
            [
                SAMPLES_DIR / "daily_mixed_energy.yaml",
                SAMPLES_DIR / "daily_deadline_pressure.yaml",
            ]
        )

        self.assertIn("Human daily review", output)
        self.assertIn("fixtures: 2", output)
        self.assertIn("daily_mixed_energy", output)
        self.assertIn("daily_deadline_pressure", output)

    def test_review_runs_flexible_fixture(self) -> None:
        output = run_human_daily_review([SAMPLES_DIR / "daily_flexible_normal.yaml"])

        self.assertIn("daily_flexible_normal", output)
        self.assertIn("Timeline", output)
        self.assertIn("Unscheduled", output)

    def test_review_writes_markdown_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "review.md"

            rendered = write_human_daily_review(
                [SAMPLES_DIR / "daily_mixed_energy.yaml"],
                output_path,
                output_format="markdown",
            )

            self.assertEqual(output_path.read_text(encoding="utf-8"), rendered)
            self.assertIn("# Human Daily Review", rendered)
            self.assertIn("```text", rendered)
            self.assertIn("daily_mixed_energy", rendered)

    def test_review_applies_yaml_solver_config_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "fixture.yaml"
            config_path = Path(directory) / "config.yaml"
            fixture_path.write_text(
                "\n".join(
                    [
                        'date: "2026-05-20"',
                        "metadata:",
                        "  name: override_fixture",
                        "time_slots:",
                        "  - index: 0",
                        '    start: "09:00"',
                        '    end: "10:00"',
                        "    work_kind: focused_work",
                        "tasks:",
                        "  - id: focused_task",
                        "    title: Focused task",
                        "    remaining_minutes: 30",
                        "    priority: 1",
                        "    work_kind: focused_work",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                "\n".join(
                    [
                        "solver_config:",
                        "  kind_match_score: 20",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_human_daily_solver_config(config_path)

            default_output = run_human_daily_review([fixture_path])
            override_output = run_human_daily_review(
                [fixture_path],
                config_override=config,
            )

            self.assertEqual(config.kind_match_score, 20)
            self.assertIn("override_fixture", override_output)
            self.assertNotEqual(default_output, override_output)

    def test_review_cli_writes_markdown_with_config_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "review.md"
            default_output_path = Path(directory) / "default-review.md"
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "solver_config:",
                        "  kind_match_score: 20",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env = dict(os.environ)
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                str(REPO_ROOT) if not existing_pythonpath else str(REPO_ROOT) + os.pathsep + existing_pythonpath
            )

            subprocess.run(
                [
                    sys.executable,
                    str(EXAMPLES_DIR / "human_daily_review.py"),
                    str(SAMPLES_DIR / "daily_mixed_energy.yaml"),
                    "--format",
                    "markdown",
                    "--output",
                    str(default_output_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                check=True,
                text=True,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(EXAMPLES_DIR / "human_daily_review.py"),
                    str(SAMPLES_DIR / "daily_mixed_energy.yaml"),
                    "--format",
                    "markdown",
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                check=True,
                text=True,
            )

            rendered = output_path.read_text(encoding="utf-8")
            self.assertEqual(result.stdout, "")
            self.assertIn("# Human Daily Review", rendered)
            self.assertIn("daily_mixed_energy", rendered)
            self.assertIn("solver: `timeline_greedy`", rendered)
            self.assertNotEqual(
                default_output_path.read_text(encoding="utf-8"),
                rendered,
            )

    def test_review_requires_at_least_one_fixture(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one fixture"):
            run_human_daily_review([])


if __name__ == "__main__":
    unittest.main()
