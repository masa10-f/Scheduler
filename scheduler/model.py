from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

TimeWindow = tuple[int, int]  # [start, end) in discrete slots


@dataclass(frozen=True)
class Task:
    id: str
    duration: int
    earliest_start: int = 0
    latest_end: int | None = None
    eligible_resources: Sequence[str] | None = None
    resource_demand: int = 1
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Resource:
    id: str
    capacity: int = 1
    availability: Sequence[TimeWindow] | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Precedence:
    before: str
    after: str
    lag: int = 0


@dataclass(frozen=True)
class Assignment:
    task_id: str
    resource_id: str
    start: int

    def end(self, task: Task) -> int:
        return self.start + task.duration


@dataclass
class Schedule:
    assignments: dict[str, Assignment] = field(default_factory=dict)

    def assignment_for(self, task_id: str) -> Assignment | None:
        return self.assignments.get(task_id)

    def iter_assignments(self) -> Iterable[Assignment]:
        return self.assignments.values()


@dataclass
class Problem:
    tasks: dict[str, Task]
    resources: dict[str, Resource]
    precedences: list[Precedence] = field(default_factory=list)
    time_horizon: int | None = None

    def task(self, task_id: str) -> Task:
        return self.tasks[task_id]

    def resource(self, resource_id: str) -> Resource:
        return self.resources[resource_id]
