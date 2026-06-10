"""Core scheduling data model."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

TimeWindow = tuple[int, int]  # [start, end) in discrete slots


@dataclass(frozen=True)
class Task:
    """A schedulable unit of work."""

    id: str
    duration: int
    earliest_start: int = 0
    latest_end: int | None = None
    eligible_resources: Sequence[str] | None = None
    resource_demand: int = 1
    priority: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Resource:
    """A resource that can execute tasks over available time windows."""

    id: str
    capacity: int = 1
    availability: Sequence[TimeWindow] | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Precedence:
    """A dependency requiring one task to finish before another can start."""

    before: str
    after: str
    lag: int = 0


@dataclass(frozen=True)
class Assignment:
    """A concrete placement of a task on a resource."""

    task_id: str
    resource_id: str
    start: int

    def end(self, task: Task) -> int:
        """Return the exclusive end time for this assignment."""
        return self.start + task.duration


@dataclass
class Schedule:
    """A collection of task assignments keyed by task id."""

    assignments: dict[str, Assignment] = field(default_factory=dict)

    def assignment_for(self, task_id: str) -> Assignment | None:
        """Return the assignment for a task if it exists."""
        return self.assignments.get(task_id)

    def iter_assignments(self) -> Iterable[Assignment]:
        """Iterate over all assignments in this schedule."""
        return self.assignments.values()


@dataclass
class Problem:
    """A scheduling problem containing tasks, resources, and constraints."""

    tasks: dict[str, Task]
    resources: dict[str, Resource]
    precedences: list[Precedence] = field(default_factory=list)
    time_horizon: int | None = None

    def task(self, task_id: str) -> Task:
        """Return a task by id."""
        return self.tasks[task_id]

    def resource(self, resource_id: str) -> Resource:
        """Return a resource by id."""
        return self.resources[resource_id]
