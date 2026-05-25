from __future__ import annotations

from pathlib import Path
import unittest

from scheduler.human import (
    compare_human_daily_solvers,
    format_human_daily_comparison,
    load_human_daily_fixture,
)


SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples" / "human"


class HumanDailyFixtureTests(unittest.TestCase):
    def test_loads_editable_yaml_fixture(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")

        self.assertEqual(fixture.date.isoformat(), "2026-05-20")
        self.assertEqual(fixture.metadata["name"], "daily_basic")
        self.assertEqual(len(fixture.tasks), 4)
        self.assertEqual(fixture.tasks[0].priority, 1)
        self.assertEqual(fixture.time_slots[0].work_kind.value, "focused_work")


class HumanDailySolverComparisonTests(unittest.TestCase):
    def test_legacy_solver_exposes_duplicate_slot_start_limitation(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")
        report = compare_human_daily_solvers(fixture).reports["legacy_slot"]

        starts_by_slot: dict[int, list[str]] = {}
        for block in report.plan.blocks:
            starts_by_slot.setdefault(block.slot_index, []).append(
                block.start.strftime("%H:%M")
            )

        self.assertIn("09:00", starts_by_slot[0])
        self.assertGreater(starts_by_slot[0].count("09:00"), 1)

    def test_timeline_solver_uses_sequential_starts_inside_slot(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_basic.yaml")
        report = compare_human_daily_solvers(fixture).reports["timeline_greedy"]

        slot_zero_blocks = [
            block for block in report.plan.blocks if block.slot_index == 0
        ]
        slot_zero_starts = [block.start.strftime("%H:%M") for block in slot_zero_blocks]

        self.assertGreaterEqual(len(slot_zero_starts), 2)
        self.assertEqual(len(slot_zero_starts), len(set(slot_zero_starts)))

    def test_dependencies_block_tasks_without_prerequisites(self) -> None:
        fixture = load_human_daily_fixture(SAMPLES_DIR / "daily_dependencies.yaml")
        report = compare_human_daily_solvers(fixture).reports["timeline_greedy"]

        unscheduled = {item.task_id: item.reason for item in report.unscheduled_tasks}
        scheduled_ids = {block.task_id for block in report.plan.blocks}

        self.assertIn("paper_review", scheduled_ids)
        self.assertIn("proof_outline", scheduled_ids)
        self.assertEqual(
            unscheduled["blocked_experiment_followup"], "dependency_not_scheduled"
        )

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


if __name__ == "__main__":
    unittest.main()
