from __future__ import annotations

import unittest
from datetime import time

from scheduler.human import (
    HumanAvailabilityWindow,
    HumanDailyPlan,
    HumanFixedAssignment,
    HumanFixedEvent,
    HumanScheduleBlock,
    HumanTask,
    HumanTimeSlot,
    HumanWorkKind,
)


class HumanTaskTests(unittest.TestCase):
    def test_task_uses_humancompiler_priority_semantics(self) -> None:
        task = HumanTask(
            id="task-1",
            title="Write proposal",
            remaining_minutes=90,
            priority=1,
            work_kind=HumanWorkKind.FOCUSED_WORK,
        )

        self.assertEqual(task.priority, 1)
        self.assertEqual(task.work_kind.value, "focused_work")

    def test_task_rejects_priority_outside_humancompiler_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "priority"):
            HumanTask(id="task-1", title="Invalid", remaining_minutes=30, priority=6)

    def test_task_rejects_invalid_split_policy(self) -> None:
        with self.assertRaisesRegex(ValueError, "preferred_chunk_minutes"):
            HumanTask(
                id="task-1",
                title="Invalid split",
                remaining_minutes=90,
                split_allowed=True,
                min_chunk_minutes=60,
                preferred_chunk_minutes=30,
            )


class HumanTimeSlotTests(unittest.TestCase):
    def test_slot_reports_same_day_duration_and_capacity(self) -> None:
        slot = HumanTimeSlot(
            index=0,
            start=time(9, 0),
            end=time(12, 30),
            capacity_minutes=120,
        )

        self.assertEqual(slot.duration_minutes, 210)
        self.assertEqual(slot.effective_capacity_minutes, 120)

    def test_slot_defaults_capacity_to_duration(self) -> None:
        slot = HumanTimeSlot(index=1, start=time(13, 0), end=time(15, 0))

        self.assertEqual(slot.effective_capacity_minutes, 120)

    def test_slot_rejects_reversed_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "end"):
            HumanTimeSlot(index=0, start=time(12, 0), end=time(9, 0))


class HumanAvailabilityWindowTests(unittest.TestCase):
    def test_availability_window_rejects_reversed_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "end"):
            HumanAvailabilityWindow(start=time(12, 0), end=time(9, 0))


class HumanFixedEventTests(unittest.TestCase):
    def test_fixed_event_rejects_reversed_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "end"):
            HumanFixedEvent(title="Meeting", start=time(12, 0), end=time(9, 0))


class HumanPlanTests(unittest.TestCase):
    def test_plan_can_hold_timeline_blocks_and_unscheduled_ids(self) -> None:
        block = HumanScheduleBlock(
            task_id="task-1",
            slot_index=0,
            start=time(9, 0),
            end=time(10, 0),
            duration_minutes=60,
            is_fixed=True,
        )
        plan = HumanDailyPlan(
            blocks=[block],
            unscheduled_task_ids=["task-2"],
            status="OPTIMAL",
        )

        self.assertEqual(plan.blocks[0].task_id, "task-1")
        self.assertTrue(plan.blocks[0].is_fixed)
        self.assertEqual(plan.unscheduled_task_ids, ["task-2"])

    def test_fixed_assignment_allows_solver_to_choose_duration(self) -> None:
        fixed = HumanFixedAssignment(task_id="task-1", slot_index=0)

        self.assertIsNone(fixed.duration_minutes)


if __name__ == "__main__":
    unittest.main()
