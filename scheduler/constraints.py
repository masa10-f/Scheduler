"""Constraint evaluation for schedules."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from scheduler.model import Problem, Schedule, TimeWindow


@dataclass(frozen=True)
class Violation:
    """A single constraint violation detected in a schedule."""

    constraint: str
    message: str
    task_id: str | None = None
    resource_id: str | None = None
    magnitude: int = 1


class Constraint:
    """Base class for schedule constraints."""

    name = "constraint"

    def violations(self, problem: Problem, schedule: Schedule) -> list[Violation]:
        """Return violations for the given problem and schedule."""
        raise NotImplementedError


def evaluate_constraints(problem: Problem, schedule: Schedule, constraints: Iterable[Constraint]) -> list[Violation]:
    """Evaluate all constraints and return the combined violations."""
    violations: list[Violation] = []
    for constraint in constraints:
        violations.extend(constraint.violations(problem, schedule))
    return violations


class TimeWindowConstraint(Constraint):
    """Validate task earliest-start and latest-end windows."""

    name = "time_window"

    def violations(self, problem: Problem, schedule: Schedule) -> list[Violation]:
        """Return time-window violations."""
        results: list[Violation] = []
        for assignment in schedule.iter_assignments():
            if assignment.task_id not in problem.tasks:
                continue
            task = problem.task(assignment.task_id)
            end = assignment.end(task)
            if assignment.start < task.earliest_start:
                results.append(
                    Violation(
                        constraint=self.name,
                        message=(f"task starts before earliest_start ({assignment.start} < {task.earliest_start})"),
                        task_id=assignment.task_id,
                        resource_id=assignment.resource_id,
                        magnitude=task.earliest_start - assignment.start,
                    )
                )
            if task.latest_end is not None and end > task.latest_end:
                results.append(
                    Violation(
                        constraint=self.name,
                        message=(f"task ends after latest_end ({end} > {task.latest_end})"),
                        task_id=assignment.task_id,
                        resource_id=assignment.resource_id,
                        magnitude=end - task.latest_end,
                    )
                )
        return results


class PrecedenceConstraint(Constraint):
    """Validate precedence relationships between scheduled tasks."""

    name = "precedence"

    def violations(self, problem: Problem, schedule: Schedule) -> list[Violation]:
        """Return precedence violations."""
        results: list[Violation] = []
        for prec in problem.precedences:
            before = schedule.assignment_for(prec.before)
            after = schedule.assignment_for(prec.after)
            if before is None or after is None:
                continue
            if prec.before not in problem.tasks or prec.after not in problem.tasks:
                continue
            before_task = problem.task(prec.before)
            before_end = before.end(before_task)
            min_start = before_end + prec.lag
            if after.start < min_start:
                results.append(
                    Violation(
                        constraint=self.name,
                        message=(
                            f"precedence violated: {prec.after} starts at "
                            f"{after.start} before {prec.before} ends + lag "
                            f"({min_start})"
                        ),
                        task_id=prec.after,
                        resource_id=after.resource_id,
                        magnitude=min_start - after.start,
                    )
                )
        return results


class ResourceEligibilityConstraint(Constraint):
    """Validate that tasks are assigned only to eligible resources."""

    name = "resource_eligibility"

    def violations(self, problem: Problem, schedule: Schedule) -> list[Violation]:
        """Return resource eligibility violations."""
        results: list[Violation] = []
        for assignment in schedule.iter_assignments():
            if assignment.task_id not in problem.tasks:
                continue
            task = problem.task(assignment.task_id)
            eligible = task.eligible_resources
            if eligible is None:
                continue
            if assignment.resource_id not in eligible:
                results.append(
                    Violation(
                        constraint=self.name,
                        message=(f"resource {assignment.resource_id} is not eligible for task {assignment.task_id}"),
                        task_id=assignment.task_id,
                        resource_id=assignment.resource_id,
                    )
                )
        return results


class ResourceAvailabilityConstraint(Constraint):
    """Validate that assignments fit resource availability windows."""

    name = "resource_availability"

    def violations(self, problem: Problem, schedule: Schedule) -> list[Violation]:
        """Return resource availability violations."""
        results: list[Violation] = []
        for assignment in schedule.iter_assignments():
            if assignment.task_id not in problem.tasks:
                continue
            if assignment.resource_id not in problem.resources:
                continue
            task = problem.task(assignment.task_id)
            resource = problem.resource(assignment.resource_id)
            if resource.availability is None:
                continue
            if not _interval_within_windows(assignment.start, assignment.end(task), resource.availability):
                results.append(
                    Violation(
                        constraint=self.name,
                        message=(
                            f"task {assignment.task_id} not within availability of resource {assignment.resource_id}"
                        ),
                        task_id=assignment.task_id,
                        resource_id=assignment.resource_id,
                    )
                )
        return results


class ResourceCapacityConstraint(Constraint):
    """Validate that resource capacity is not exceeded."""

    name = "resource_capacity"

    def violations(self, problem: Problem, schedule: Schedule) -> list[Violation]:
        """Return resource capacity violations."""
        usage: dict[str, dict[int, int]] = {}
        for assignment in schedule.iter_assignments():
            if assignment.task_id not in problem.tasks:
                continue
            if assignment.resource_id not in problem.resources:
                continue
            task = problem.task(assignment.task_id)
            resource_usage = usage.setdefault(assignment.resource_id, {})
            start = assignment.start
            end = assignment.end(task)
            for t in range(start, end):
                resource_usage[t] = resource_usage.get(t, 0) + task.resource_demand

        results: list[Violation] = []
        for resource_id, time_usage in usage.items():
            capacity = problem.resource(resource_id).capacity
            for t, used in time_usage.items():
                if used > capacity:
                    results.append(
                        Violation(
                            constraint=self.name,
                            message=(f"resource {resource_id} over capacity at t={t} ({used} > {capacity})"),
                            resource_id=resource_id,
                            magnitude=used - capacity,
                        )
                    )
        return results


def default_constraints() -> list[Constraint]:
    """Return the default constraint set used by solvers."""
    return [
        TimeWindowConstraint(),
        PrecedenceConstraint(),
        ResourceEligibilityConstraint(),
        ResourceAvailabilityConstraint(),
        ResourceCapacityConstraint(),
    ]


def _interval_within_windows(start: int, end: int, windows: Sequence[TimeWindow]) -> bool:
    return any(start >= window_start and end <= window_end for window_start, window_end in windows)
