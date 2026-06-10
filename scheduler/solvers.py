"""Scheduling solver implementations."""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from scheduler.constraints import (
    Constraint,
    Violation,
    default_constraints,
    evaluate_constraints,
)
from scheduler.model import Assignment, Precedence, Problem, Schedule, Task


@dataclass
class SolverResult:
    """Result returned by a scheduling solver."""

    schedule: Schedule
    status: str
    violations: list[Violation] = field(default_factory=list)
    unscheduled: list[str] = field(default_factory=list)
    objective: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def solve_greedy(problem: Problem, constraints: Iterable[Constraint] | None = None) -> SolverResult:
    """Solve a problem with a deterministic greedy heuristic."""
    constraints = list(constraints) if constraints is not None else default_constraints()
    horizon = _compute_time_horizon(problem)
    order, preds_by_task = _topological_order(problem)
    usage_by_resource: dict[str, dict[int, int]] = {}

    schedule = Schedule()
    unscheduled: list[str] = []

    for task_id in order:
        task = problem.tasks[task_id]
        min_start = _min_start_from_predecessors(problem, schedule, preds_by_task.get(task_id, []), task)
        if min_start is None:
            unscheduled.append(task_id)
            continue
        latest_start = _latest_start(task, horizon)
        if latest_start is None or latest_start < min_start:
            unscheduled.append(task_id)
            continue

        candidate = _find_best_slot(
            problem,
            task,
            min_start,
            latest_start,
            usage_by_resource,
        )
        if candidate is None:
            unscheduled.append(task_id)
            continue

        resource_id, start = candidate
        assignment = Assignment(task_id=task_id, resource_id=resource_id, start=start)
        schedule.assignments[task_id] = assignment
        _apply_usage(problem, assignment, usage_by_resource)

    violations = evaluate_constraints(problem, schedule, constraints)
    status = "ok"
    if unscheduled:
        status = "partial"
    if violations and status == "ok":
        status = "violations"
    return SolverResult(
        schedule=schedule,
        status=status,
        violations=violations,
        unscheduled=unscheduled,
        objective=_makespan(problem, schedule),
        metadata={"solver": "greedy"},
    )


def solve_cp_sat(
    problem: Problem,
    constraints: Iterable[Constraint] | None = None,
    time_limit_s: float | None = 5.0,
) -> SolverResult:
    """Solve a problem with the optional OR-Tools CP-SAT backend."""
    try:
        cp_model: Any = import_module("ortools.sat.python.cp_model")
    except ModuleNotFoundError as exc:
        message = "OR-Tools is required for CP-SAT. Install with `pip install ortools`."
        raise ModuleNotFoundError(message) from exc

    constraints = list(constraints) if constraints is not None else default_constraints()
    horizon = _compute_time_horizon(problem)

    model = cp_model.CpModel()

    tasks = problem.tasks
    resources = problem.resources
    eligible_resources: dict[str, list[str]] = {}
    for task_id, task in tasks.items():
        if task.eligible_resources is None:
            eligible = list(resources.keys())
        else:
            eligible = [rid for rid in task.eligible_resources if rid in resources]
        if not eligible:
            return SolverResult(
                schedule=Schedule(),
                status="infeasible",
                violations=[],
                unscheduled=[task_id],
                objective=None,
                metadata={"solver": "cp-sat", "reason": "no eligible resources"},
            )
        eligible_resources[task_id] = eligible

    start_vars: dict[str, Any] = {}
    end_vars: dict[str, Any] = {}
    presence: dict[tuple[str, str], Any] = {}
    intervals_by_resource: dict[str, list[Any]] = {rid: [] for rid in resources}
    demands_by_resource: dict[str, list[int]] = {rid: [] for rid in resources}

    for task_id, task in tasks.items():
        min_start = task.earliest_start
        max_start = _latest_start(task, horizon)
        if max_start is None or max_start < min_start:
            return SolverResult(
                schedule=Schedule(),
                status="infeasible",
                violations=[],
                unscheduled=[task_id],
                objective=None,
                metadata={"solver": "cp-sat", "reason": "invalid time window"},
            )

        start = model.new_int_var(min_start, max_start, f"start_{task_id}")
        end = model.new_int_var(min_start + task.duration, max_start + task.duration, f"end_{task_id}")
        model.add(end == start + task.duration)
        start_vars[task_id] = start
        end_vars[task_id] = end

        presence_lits: list[Any] = []
        for resource_id in eligible_resources[task_id]:
            lit = model.new_bool_var(f"assign_{task_id}_{resource_id}")
            interval = model.new_optional_interval_var(
                start, task.duration, end, lit, f"interval_{task_id}_{resource_id}"
            )
            presence[task_id, resource_id] = lit
            presence_lits.append(lit)
            intervals_by_resource[resource_id].append(interval)
            demands_by_resource[resource_id].append(task.resource_demand)

            resource = resources[resource_id]
            if resource.availability is not None:
                if not resource.availability:
                    model.add(lit == 0)
                else:
                    window_lits: list[Any] = []
                    for idx, (win_start, win_end) in enumerate(resource.availability):
                        wlit = model.new_bool_var(f"avail_{task_id}_{resource_id}_{idx}")
                        model.add(start >= win_start).only_enforce_if(wlit)
                        model.add(end <= win_end).only_enforce_if(wlit)
                        model.add_implication(wlit, lit)
                        window_lits.append(wlit)
                    model.add_bool_or(window_lits).only_enforce_if(lit)

        model.add_exactly_one(presence_lits)

        if task.latest_end is not None:
            model.add(end <= task.latest_end)

    for prec in problem.precedences:
        if prec.before not in tasks or prec.after not in tasks:
            continue
        model.add(start_vars[prec.after] >= end_vars[prec.before] + prec.lag)

    for resource_id, intervals in intervals_by_resource.items():
        if not intervals:
            continue
        capacity = resources[resource_id].capacity
        model.add_cumulative(intervals, demands_by_resource[resource_id], capacity)

    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, [end_vars[tid] for tid in tasks])
    model.minimize(makespan)

    solver = cp_model.CpSolver()
    if time_limit_s is not None:
        solver.parameters.max_time_in_seconds = float(time_limit_s)

    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return SolverResult(
            schedule=Schedule(),
            status="infeasible",
            violations=[],
            unscheduled=list(tasks.keys()),
            objective=None,
            metadata={"solver": "cp-sat", "cp_status": solver.status_name(status)},
        )

    schedule = Schedule()
    for task_id in tasks:
        start = int(solver.value(start_vars[task_id]))
        assigned_resource = None
        for resource_id in eligible_resources[task_id]:
            if solver.value(presence[task_id, resource_id]) == 1:
                assigned_resource = resource_id
                break
        if assigned_resource is None:
            continue
        schedule.assignments[task_id] = Assignment(task_id=task_id, resource_id=assigned_resource, start=start)

    violations = evaluate_constraints(problem, schedule, constraints)
    return SolverResult(
        schedule=schedule,
        status="ok" if not violations else "violations",
        violations=violations,
        unscheduled=[],
        objective=int(solver.value(makespan)),
        metadata={"solver": "cp-sat", "cp_status": solver.status_name(status)},
    )


def compare_solvers(
    problem: Problem,
    constraints: Iterable[Constraint] | None = None,
    time_limit_s: float | None = 5.0,
) -> dict[str, SolverResult]:
    """Run all available solvers and return their results by solver name."""
    return {
        "greedy": solve_greedy(problem, constraints=constraints),
        "cp-sat": solve_cp_sat(problem, constraints=constraints, time_limit_s=time_limit_s),
    }


def _task_sort_key(task: Task, task_id: str) -> tuple[int, int, str]:
    return (-task.priority, task.earliest_start, task_id)


def _topological_order(problem: Problem) -> tuple[list[str], dict[str, list[Precedence]]]:
    tasks = problem.tasks
    indegree = dict.fromkeys(tasks, 0)
    adj: dict[str, list[str]] = {task_id: [] for task_id in tasks}
    preds: dict[str, list[Precedence]] = {task_id: [] for task_id in tasks}

    for prec in problem.precedences:
        if prec.before not in tasks or prec.after not in tasks:
            continue
        adj[prec.before].append(prec.after)
        indegree[prec.after] += 1
        preds[prec.after].append(prec)

    heap: list[tuple[int, int, str]] = []
    for task_id, deg in indegree.items():
        if deg == 0:
            heapq.heappush(heap, _task_sort_key(tasks[task_id], task_id))

    order: list[str] = []
    while heap:
        _, _, task_id = heapq.heappop(heap)
        order.append(task_id)
        for succ in adj[task_id]:
            indegree[succ] -= 1
            if indegree[succ] == 0:
                heapq.heappush(heap, _task_sort_key(tasks[succ], succ))

    remaining = [task_id for task_id, deg in indegree.items() if deg > 0]
    remaining.sort(key=lambda tid: _task_sort_key(tasks[tid], tid))
    order.extend(remaining)
    return order, preds


def _min_start_from_predecessors(
    problem: Problem,
    schedule: Schedule,
    predecessors: Sequence[Precedence],
    task: Task,
) -> int | None:
    min_start = task.earliest_start
    for prec in predecessors:
        assignment = schedule.assignment_for(prec.before)
        if assignment is None:
            return None
        before_task = problem.task(prec.before)
        min_start = max(min_start, assignment.end(before_task) + prec.lag)
    return min_start


def _latest_start(task: Task, horizon: int) -> int | None:
    if task.latest_end is not None:
        return task.latest_end - task.duration
    return horizon - task.duration


def _find_best_slot(
    problem: Problem,
    task: Task,
    min_start: int,
    latest_start: int,
    usage_by_resource: dict[str, dict[int, int]],
) -> tuple[str, int] | None:
    if task.eligible_resources is None:
        resources = list(problem.resources.keys())
    else:
        resources = [rid for rid in task.eligible_resources if rid in problem.resources]

    best: tuple[int, int, str] | None = None
    for resource_id in resources:
        candidate = _earliest_feasible_start(
            problem,
            resource_id,
            task,
            min_start,
            latest_start,
            usage_by_resource,
        )
        if candidate is None:
            continue
        end = candidate + task.duration
        key = (end, candidate, resource_id)
        if best is None or key < best:
            best = key
    if best is None:
        return None
    _, start, resource_id = best
    return resource_id, start


def _earliest_feasible_start(
    problem: Problem,
    resource_id: str,
    task: Task,
    min_start: int,
    latest_start: int,
    usage_by_resource: dict[str, dict[int, int]],
) -> int | None:
    resource = problem.resources[resource_id]
    availability = resource.availability
    if availability is None:
        ranges = [(min_start, latest_start)]
    else:
        ranges = []
        for win_start, win_end in availability:
            start = max(min_start, win_start)
            end = min(latest_start, win_end - task.duration)
            if start <= end:
                ranges.append((start, end))

    usage = usage_by_resource.setdefault(resource_id, {})
    capacity = resource.capacity
    demand = task.resource_demand

    for start_range, end_range in ranges:
        for start in range(start_range, end_range + 1):
            if _fits_capacity(usage, start, start + task.duration, demand, capacity):
                return start
    return None


def _fits_capacity(
    usage: Mapping[int, int],
    start: int,
    end: int,
    demand: int,
    capacity: int,
) -> bool:
    return all(usage.get(t, 0) + demand <= capacity for t in range(start, end))


def _apply_usage(
    problem: Problem,
    assignment: Assignment,
    usage_by_resource: dict[str, dict[int, int]],
) -> None:
    task = problem.task(assignment.task_id)
    usage = usage_by_resource.setdefault(assignment.resource_id, {})
    for t in range(assignment.start, assignment.end(task)):
        usage[t] = usage.get(t, 0) + task.resource_demand


def _compute_time_horizon(problem: Problem) -> int:
    if problem.time_horizon is not None:
        return problem.time_horizon
    latest_end = max(
        (task.latest_end for task in problem.tasks.values() if task.latest_end is not None),
        default=None,
    )
    max_avail = max(
        (
            window_end
            for resource in problem.resources.values()
            if resource.availability
            for _, window_end in resource.availability
        ),
        default=None,
    )
    total_duration = sum(task.duration for task in problem.tasks.values())
    earliest_start = min((task.earliest_start for task in problem.tasks.values()), default=0)
    candidates = [value for value in [latest_end, max_avail] if value is not None]
    if candidates:
        return max(*candidates, earliest_start + total_duration)
    return earliest_start + total_duration


def _makespan(problem: Problem, schedule: Schedule) -> int | None:
    if not schedule.assignments:
        return None
    end_times = []
    for assignment in schedule.iter_assignments():
        if assignment.task_id not in problem.tasks:
            continue
        task = problem.task(assignment.task_id)
        end_times.append(assignment.end(task))
    return max(end_times) if end_times else None
