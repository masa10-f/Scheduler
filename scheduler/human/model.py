from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
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


@dataclass(frozen=True)
class HumanDailySolverConfig:
    """Tunable scores for the Phase 1 Human daily comparison solvers."""

    kind_match_score: int = 8
    kind_mismatch_score: int = 1
    priority_score_base: int = 6
    deadline_soon_days: int = 2
    deadline_score: int = 4
    overdue_score: int = 20
    fixed_assignment_score: int = 100

    def __post_init__(self) -> None:
        if self.kind_match_score < 0:
            raise ValueError("kind_match_score must be non-negative")
        if self.kind_mismatch_score < 0:
            raise ValueError("kind_mismatch_score must be non-negative")
        if self.priority_score_base < 1:
            raise ValueError("priority_score_base must be positive")
        if self.deadline_soon_days < 0:
            raise ValueError("deadline_soon_days must be non-negative")
        if self.deadline_score < 0:
            raise ValueError("deadline_score must be non-negative")
        if self.overdue_score < 0:
            raise ValueError("overdue_score must be non-negative")
        if self.fixed_assignment_score < 0:
            raise ValueError("fixed_assignment_score must be non-negative")


@dataclass(frozen=True)
class HumanDailyFixture:
    """Editable fixture input for Human daily scheduling review."""

    date: date
    tasks: list[HumanTask]
    time_slots: list[HumanTimeSlot]
    fixed_assignments: list[HumanFixedAssignment] = field(default_factory=list)
    task_dependencies: dict[str, list[str]] = field(default_factory=dict)
    solver_config: HumanDailySolverConfig = field(
        default_factory=HumanDailySolverConfig
    )
    metadata: dict[str, HumanMetadataValue] = field(default_factory=dict)


@dataclass(frozen=True)
class HumanUnscheduledTask:
    task_id: str
    title: str
    reason: str


@dataclass(frozen=True)
class HumanConstraintViolation:
    code: str
    message: str
    task_id: str | None = None
    slot_index: int | None = None


@dataclass(frozen=True)
class HumanScoreBreakdown:
    task_id: str
    slot_index: int
    total: int
    components: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class HumanSolverReport:
    solver_name: str
    plan: HumanDailyPlan
    unscheduled_tasks: list[HumanUnscheduledTask] = field(default_factory=list)
    score_breakdown: list[HumanScoreBreakdown] = field(default_factory=list)
    violations: list[HumanConstraintViolation] = field(default_factory=list)
    config: HumanDailySolverConfig = field(default_factory=HumanDailySolverConfig)


@dataclass(frozen=True)
class HumanSolverComparison:
    fixture: HumanDailyFixture
    reports: dict[str, HumanSolverReport]
