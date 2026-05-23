from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Literal, TypeAlias

HumanMetadataValue: TypeAlias = str | int | float | bool | None
HumanTaskSource: TypeAlias = Literal["task", "quick_task", "weekly_recurring_task"]


class HumanWorkKind(str, Enum):
    """Work type shared by tasks and available time slots."""

    LIGHT_WORK = "light_work"
    FOCUSED_WORK = "focused_work"
    STUDY = "study"


@dataclass(frozen=True)
class HumanTask:
    """Task-shaped input for HumanCompiler-oriented daily scheduling.

    This is intentionally independent from HumanCompiler database models. Adapter
    code should convert DB/API objects into this small scheduling contract.
    """

    id: str
    title: str
    remaining_minutes: int
    priority: int = 3
    work_kind: HumanWorkKind = HumanWorkKind.LIGHT_WORK
    due_at: datetime | None = None
    project_id: str | None = None
    goal_id: str | None = None
    source: HumanTaskSource = "task"
    metadata: dict[str, HumanMetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.remaining_minutes < 0:
            raise ValueError("remaining_minutes must be non-negative")
        if not 1 <= self.priority <= 5:
            raise ValueError("priority must be between 1 and 5")


@dataclass(frozen=True)
class HumanTimeSlot:
    """Available same-day scheduling window."""

    index: int
    start: time
    end: time
    work_kind: HumanWorkKind = HumanWorkKind.LIGHT_WORK
    capacity_minutes: int | None = None
    assigned_project_id: str | None = None
    metadata: dict[str, HumanMetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("index must be non-negative")
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        if self.capacity_minutes is not None and self.capacity_minutes < 0:
            raise ValueError("capacity_minutes must be non-negative")

    @property
    def duration_minutes(self) -> int:
        start_minutes = self.start.hour * 60 + self.start.minute
        end_minutes = self.end.hour * 60 + self.end.minute
        return end_minutes - start_minutes

    @property
    def effective_capacity_minutes(self) -> int:
        if self.capacity_minutes is None:
            return self.duration_minutes
        return min(self.capacity_minutes, self.duration_minutes)


@dataclass(frozen=True)
class HumanFixedAssignment:
    """User-pinned task placement that the solver must preserve."""

    task_id: str
    slot_index: int
    duration_minutes: int | None = None

    def __post_init__(self) -> None:
        if self.slot_index < 0:
            raise ValueError("slot_index must be non-negative")
        if self.duration_minutes is not None and self.duration_minutes < 0:
            raise ValueError("duration_minutes must be non-negative")


@dataclass(frozen=True)
class HumanScheduleBlock:
    """Scheduled task block with concrete start and end times."""

    task_id: str
    slot_index: int
    start: time
    end: time
    duration_minutes: int
    is_fixed: bool = False
    metadata: dict[str, HumanMetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.slot_index < 0:
            raise ValueError("slot_index must be non-negative")
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        if self.duration_minutes < 0:
            raise ValueError("duration_minutes must be non-negative")


@dataclass(frozen=True)
class HumanDailyPlan:
    """Human daily scheduling result shape.

    Blocks are expected to be timeline blocks, not just slot assignments.
    """

    blocks: list[HumanScheduleBlock] = field(default_factory=list)
    unscheduled_task_ids: list[str] = field(default_factory=list)
    status: str = "UNKNOWN"
    metadata: dict[str, HumanMetadataValue] = field(default_factory=dict)
