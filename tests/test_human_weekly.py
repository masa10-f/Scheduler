from __future__ import annotations

import unittest

import pytest

ortools = pytest.importorskip("ortools.sat.python.cp_model")

from humancompiler_scheduler.human import (  # noqa: E402
    HumanWeeklyProjectAllocationSpec,
    HumanWeeklySelectionFixture,
    HumanWeeklySolverConfig,
    HumanWeeklyTaskSpec,
    human_weekly_selection_fixture_from_dict,
    optimize_weekly_selection,
    plan_weekly_selection,
)


@pytest.mark.cp_sat
class TestHumanWeeklySelection(unittest.TestCase):
    def test_single_task_within_capacity_is_selected(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="task1",
                    title="Task 1",
                    hours=5.0,
                    priority_score=5.0,
                )
            ],
            total_capacity_hours=40.0,
        )

        self.assertTrue(result.success)
        self.assertIn("task1", result.selected_task_ids)

    def test_respects_total_capacity(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="task1",
                    title="Task 1",
                    hours=30.0,
                    priority_score=5.0,
                ),
                HumanWeeklyTaskSpec(
                    id="task2",
                    title="Task 2",
                    hours=30.0,
                    priority_score=5.0,
                ),
            ],
            total_capacity_hours=40.0,
        )

        self.assertTrue(result.success)
        self.assertLessEqual(result.selected_hours, 40.0)

    def test_prefers_higher_priority_task(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="low",
                    title="Low",
                    hours=20.0,
                    priority_score=1.0,
                ),
                HumanWeeklyTaskSpec(
                    id="high",
                    title="High",
                    hours=20.0,
                    priority_score=10.0,
                ),
            ],
            total_capacity_hours=25.0,
        )

        self.assertTrue(result.success)
        self.assertIn("high", result.selected_task_ids)

    def test_respects_project_allocation(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="proj_a_task1",
                    title="A1",
                    hours=5.0,
                    priority_score=5.0,
                    project_id="proj_a",
                ),
                HumanWeeklyTaskSpec(
                    id="proj_a_task2",
                    title="A2",
                    hours=5.0,
                    priority_score=5.0,
                    project_id="proj_a",
                ),
                HumanWeeklyTaskSpec(
                    id="proj_b_task1",
                    title="B1",
                    hours=5.0,
                    priority_score=5.0,
                    project_id="proj_b",
                ),
            ],
            project_allocations=[
                HumanWeeklyProjectAllocationSpec(
                    project_id="proj_a",
                    target_hours=10.0,
                )
            ],
            total_capacity_hours=40.0,
        )

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.selected_hours_by_project.get("proj_a", 0), 9.5)

    def test_zero_allocation_excludes_project(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="proj_a_task",
                    title="A",
                    hours=5.0,
                    priority_score=5.0,
                    project_id="proj_a",
                ),
                HumanWeeklyTaskSpec(
                    id="proj_b_task",
                    title="B",
                    hours=5.0,
                    priority_score=5.0,
                    project_id="proj_b",
                ),
            ],
            project_allocations=[
                HumanWeeklyProjectAllocationSpec(
                    project_id="proj_a",
                    target_hours=0.0,
                )
            ],
            total_capacity_hours=40.0,
        )

        self.assertTrue(result.success)
        self.assertNotIn("proj_a_task", result.selected_task_ids)

    def test_selected_recurring_tasks_count_toward_capacity(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="regular",
                    title="Regular",
                    hours=35.0,
                    priority_score=5.0,
                )
            ],
            recurring_tasks=[
                HumanWeeklyTaskSpec(
                    id="weekly1",
                    title="Weekly",
                    hours=10.0,
                    priority_score=8.0,
                )
            ],
            total_capacity_hours=40.0,
        )

        self.assertTrue(result.success)
        self.assertLessEqual(result.selected_hours, 40.0)

    def test_fractional_hours_do_not_exceed_capacity(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id=f"task{i}",
                    title=f"Task {i}",
                    hours=0.25,
                    priority_score=5.0,
                )
                for i in range(3)
            ],
            total_capacity_hours=0.6,
        )

        self.assertTrue(result.success)
        self.assertLessEqual(result.selected_hours, 0.6)
        self.assertLess(len(result.selected_task_ids), 3)

    def test_respects_project_allocation_max_hours(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="proj_task1",
                    title="Project Task 1",
                    hours=4.0,
                    priority_score=5.0,
                    project_id="project",
                ),
                HumanWeeklyTaskSpec(
                    id="proj_task2",
                    title="Project Task 2",
                    hours=4.0,
                    priority_score=5.0,
                    project_id="project",
                ),
            ],
            project_allocations=[
                HumanWeeklyProjectAllocationSpec(
                    project_id="project",
                    target_hours=10.0,
                    max_hours=6.0,
                )
            ],
            total_capacity_hours=20.0,
        )

        self.assertTrue(result.success)
        self.assertLessEqual(result.selected_hours_by_project.get("project", 0.0), 6.0)
        self.assertEqual(len(result.selected_task_ids), 1)

    def test_recurring_project_hours_count_toward_allocation_max_hours(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="regular",
                    title="Regular",
                    hours=4.0,
                    priority_score=1.0,
                    project_id="project",
                )
            ],
            recurring_tasks=[
                HumanWeeklyTaskSpec(
                    id="weekly",
                    title="Weekly",
                    hours=8.0,
                    priority_score=10.0,
                    project_id="project",
                )
            ],
            project_allocations=[
                HumanWeeklyProjectAllocationSpec(
                    project_id="project",
                    target_hours=4.0,
                    max_hours=6.0,
                )
            ],
            total_capacity_hours=20.0,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.selected_task_ids, ["regular"])
        self.assertEqual(result.selected_recurring_task_ids, [])
        self.assertEqual(result.selected_hours_by_project, {"project": 4.0})

    def test_zero_allocation_excludes_recurring_project_task(self) -> None:
        result = optimize_weekly_selection(
            tasks=[
                HumanWeeklyTaskSpec(
                    id="other",
                    title="Other",
                    hours=1.0,
                    priority_score=1.0,
                    project_id="other-project",
                )
            ],
            recurring_tasks=[
                HumanWeeklyTaskSpec(
                    id="weekly",
                    title="Weekly",
                    hours=2.0,
                    priority_score=10.0,
                    project_id="blocked-project",
                )
            ],
            project_allocations=[
                HumanWeeklyProjectAllocationSpec(
                    project_id="blocked-project",
                    target_hours=0.0,
                )
            ],
            total_capacity_hours=10.0,
        )

        self.assertTrue(result.success)
        self.assertNotIn("weekly", result.selected_recurring_task_ids)

    def test_recurring_project_hours_are_reported_by_project(self) -> None:
        result = optimize_weekly_selection(
            tasks=[],
            recurring_tasks=[
                HumanWeeklyTaskSpec(
                    id="weekly",
                    title="Weekly",
                    hours=2.0,
                    priority_score=8.0,
                    project_id="project",
                )
            ],
            project_allocations=[
                HumanWeeklyProjectAllocationSpec(
                    project_id="project",
                    target_hours=2.0,
                )
            ],
            total_capacity_hours=10.0,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.selected_recurring_task_ids, ["weekly"])
        self.assertEqual(result.selected_hours_by_project, {"project": 2.0})

    def test_rejects_duplicate_ids_across_regular_and_recurring_tasks(self) -> None:
        with self.assertRaisesRegex(ValueError, "weekly task ids must be unique"):
            optimize_weekly_selection(
                tasks=[
                    HumanWeeklyTaskSpec(
                        id="duplicate",
                        title="Regular",
                        hours=1.0,
                        priority_score=1.0,
                    )
                ],
                recurring_tasks=[
                    HumanWeeklyTaskSpec(
                        id="duplicate",
                        title="Weekly",
                        hours=1.0,
                        priority_score=1.0,
                    )
                ],
                total_capacity_hours=10.0,
            )

    def test_public_plan_weekly_selection_accepts_mapping_and_config_override(self) -> None:
        result = plan_weekly_selection(
            {
                "tasks": [
                    {
                        "id": "task",
                        "title": "Task",
                        "hours": 1.0,
                        "priority_score": 5.0,
                    }
                ],
                "total_capacity_hours": 2.0,
            },
            solver_config={"max_time_in_seconds": 1.0},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.selected_task_ids, ["task"])

    def test_fixture_from_dict_parses_named_project_allocations(self) -> None:
        fixture = human_weekly_selection_fixture_from_dict(
            {
                "tasks": {
                    "task": {
                        "title": "Task",
                        "hours": 2.0,
                        "priority_score": 4.0,
                        "project_id": "project",
                    }
                },
                "project_allocations": {
                    "project": {
                        "target_hours": 2.0,
                        "priority_weight": 0.5,
                    }
                },
                "solver_config": {
                    "ideal_min_factor": 0.9,
                    "ideal_max_factor": 1.1,
                },
            }
        )

        self.assertIsInstance(fixture, HumanWeeklySelectionFixture)
        self.assertEqual(fixture.tasks[0].id, "task")
        self.assertEqual(fixture.project_allocations[0].project_id, "project")
        self.assertIsInstance(fixture.solver_config, HumanWeeklySolverConfig)
        self.assertEqual(fixture.solver_config.ideal_min_factor, 0.9)


if __name__ == "__main__":
    unittest.main()
