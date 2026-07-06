"""HumanCompiler-oriented weekly task selection."""

from __future__ import annotations

import math
import time as time_module
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class HumanWeeklyTaskSpec:
    """Task-shaped input for weekly selection."""

    id: str
    title: str
    hours: float
    priority_score: float
    project_id: str | None = None

    def __post_init__(self) -> None:
        if self.hours < 0:
            raise ValueError("hours must be non-negative")
        if self.priority_score < 0:
            raise ValueError("priority_score must be non-negative")


@dataclass(frozen=True)
class HumanWeeklyProjectAllocationSpec:
    """Project-level weekly target for task selection."""

    project_id: str
    target_hours: float
    max_hours: float = 0.0
    priority_weight: float = 0.0
    project_title: str | None = None

    def __post_init__(self) -> None:
        if self.target_hours < 0:
            raise ValueError("target_hours must be non-negative")
        if self.max_hours < 0:
            raise ValueError("max_hours must be non-negative")
        if self.priority_weight < 0:
            raise ValueError("priority_weight must be non-negative")


@dataclass(frozen=True)
class HumanWeeklySolverConfig:
    """Tunable parameters for weekly task selection."""

    max_time_in_seconds: float = 30.0
    hours_scale: int = 10
    priority_scale: int = 100
    project_bonus_scale: int = 1000
    zero_allocation_epsilon: float = 0.001
    ideal_min_factor: float = 0.95
    ideal_max_factor: float = 1.05

    def __post_init__(self) -> None:
        if self.max_time_in_seconds <= 0:
            raise ValueError("max_time_in_seconds must be positive")
        if self.hours_scale <= 0:
            raise ValueError("hours_scale must be positive")
        if self.priority_scale <= 0:
            raise ValueError("priority_scale must be positive")
        if self.project_bonus_scale < 0:
            raise ValueError("project_bonus_scale must be non-negative")
        if self.zero_allocation_epsilon < 0:
            raise ValueError("zero_allocation_epsilon must be non-negative")
        if not 0 <= self.ideal_min_factor <= self.ideal_max_factor:
            raise ValueError("ideal_min_factor must be between 0 and ideal_max_factor")


@dataclass(frozen=True)
class HumanWeeklySelectionFixture:
    """Plain weekly selection input accepted by adapter code."""

    tasks: list[HumanWeeklyTaskSpec]
    recurring_tasks: list[HumanWeeklyTaskSpec] = field(default_factory=list)
    project_allocations: list[HumanWeeklyProjectAllocationSpec] = field(default_factory=list)
    total_capacity_hours: float = 40.0
    solver_config: HumanWeeklySolverConfig = field(default_factory=HumanWeeklySolverConfig)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total_capacity_hours < 0:
            raise ValueError("total_capacity_hours must be non-negative")


@dataclass
class HumanWeeklySelectionResult:
    """Result returned by the weekly selection solver."""

    success: bool
    status: str = "UNKNOWN"
    selected_task_ids: list[str] = field(default_factory=list)
    selected_recurring_task_ids: list[str] = field(default_factory=list)
    assigned_task_hours: dict[str, float] = field(default_factory=dict)
    assigned_recurring_task_hours: dict[str, float] = field(default_factory=dict)
    selected_hours: float = 0.0
    selected_hours_by_project: dict[str, float] = field(default_factory=dict)
    solve_time_seconds: float = 0.0
    objective_value: float = 0.0


HumanWeeklyInput = HumanWeeklySelectionFixture | Mapping[str, Any]
HumanWeeklyConfigInput = HumanWeeklySolverConfig | Mapping[str, Any]


def plan_weekly_selection(
    payload: HumanWeeklyInput,
    *,
    solver_config: HumanWeeklyConfigInput | None = None,
) -> HumanWeeklySelectionResult:
    """Select tasks for one HumanCompiler weekly plan."""
    fixture = _coerce_weekly_fixture(payload)
    if solver_config is not None:
        fixture = replace(fixture, solver_config=_coerce_weekly_solver_config(solver_config))
    return optimize_weekly_selection(
        tasks=fixture.tasks,
        recurring_tasks=fixture.recurring_tasks,
        project_allocations=fixture.project_allocations,
        total_capacity_hours=fixture.total_capacity_hours,
        config=fixture.solver_config,
    )


def optimize_weekly_selection(
    *,
    tasks: Sequence[HumanWeeklyTaskSpec],
    recurring_tasks: Sequence[HumanWeeklyTaskSpec] = (),
    project_allocations: Sequence[HumanWeeklyProjectAllocationSpec] = (),
    total_capacity_hours: float,
    config: HumanWeeklySolverConfig | None = None,
) -> HumanWeeklySelectionResult:
    """Run weekly task selection with an optional CP-SAT backend."""
    start_time = time_module.time()
    if config is None:
        config = HumanWeeklySolverConfig()
    _validate_unique_weekly_task_ids(tasks, recurring_tasks)

    cp_model = _import_cp_model()
    model = cp_model.CpModel()
    solver = cp_model.CpSolver()

    hours_scale = int(config.hours_scale)
    priority_scale = int(config.priority_scale)
    project_bonus_scale = int(config.project_bonus_scale)

    scaled_task_hours = {task.id: _ceil_scaled_hours(task.hours, hours_scale) for task in tasks}
    scaled_recurring_hours = {task.id: _ceil_scaled_hours(task.hours, hours_scale) for task in recurring_tasks}
    task_vars = {
        task.id: model.NewIntVar(0, scaled_task_hours[task.id], f"task_hours_{task.id}") for task in tasks
    }
    recurring_vars = {
        task.id: model.NewIntVar(0, scaled_recurring_hours[task.id], f"weekly_hours_{task.id}")
        for task in recurring_tasks
    }
    task_selected_vars = {task.id: model.NewBoolVar(f"task_{task.id}") for task in tasks}
    recurring_selected_vars = {task.id: model.NewBoolVar(f"weekly_{task.id}") for task in recurring_tasks}

    for task in tasks:
        _link_positive_assignment(model, task_vars[task.id], task_selected_vars[task.id])
    for task in recurring_tasks:
        _link_positive_assignment(model, recurring_vars[task.id], recurring_selected_vars[task.id])

    total_hours_expr = []
    for task in tasks:
        total_hours_expr.append(task_vars[task.id])
    for task in recurring_tasks:
        total_hours_expr.append(recurring_vars[task.id])
    model.Add(sum(total_hours_expr) <= _floor_scaled_hours(total_capacity_hours, hours_scale))

    project_items: dict[str, list[tuple[Any, int]]] = {}
    for task in tasks:
        if task.project_id:
            project_items.setdefault(task.project_id, []).append((task_vars[task.id], scaled_task_hours[task.id]))
    for task in recurring_tasks:
        if task.project_id:
            project_items.setdefault(task.project_id, []).append(
                (recurring_vars[task.id], scaled_recurring_hours[task.id]),
            )

    for allocation in project_allocations:
        items = project_items.get(allocation.project_id, [])
        if not items:
            continue

        project_terms = [task_var for task_var, _scaled_hours in items]
        available_task_hours = sum(scaled_hours for _task_var, scaled_hours in items)

        if allocation.target_hours <= config.zero_allocation_epsilon:
            model.Add(sum(project_terms) <= 0)
            continue

        ideal_min_hours = _floor_scaled_hours(
            allocation.target_hours * config.ideal_min_factor,
            hours_scale,
        )
        ideal_max_hours = _floor_scaled_hours(
            allocation.target_hours * config.ideal_max_factor,
            hours_scale,
        )

        if available_task_hours < ideal_min_hours:
            hard_min_hours = available_task_hours
            max_hours = available_task_hours
        else:
            hard_min_hours = ideal_min_hours
            max_hours = min(ideal_max_hours, available_task_hours)

        if allocation.max_hours > 0:
            explicit_max_hours = _floor_scaled_hours(allocation.max_hours, hours_scale)
            max_hours = min(max_hours, explicit_max_hours)
            if explicit_max_hours < hard_min_hours:
                hard_min_hours = 0

        if max_hours > 0:
            model.Add(sum(project_terms) >= hard_min_hours)
            model.Add(sum(project_terms) <= max_hours)

    allocation_by_project = {allocation.project_id: allocation for allocation in project_allocations}
    priority_expr = []

    for task in tasks:
        base_priority = int(task.priority_score * priority_scale)
        bonus = _project_priority_bonus(task.project_id, allocation_by_project, project_bonus_scale)
        priority_expr.append(task_vars[task.id] * (base_priority + bonus))

    for task in recurring_tasks:
        base_priority = int(task.priority_score * priority_scale)
        bonus = _project_priority_bonus(task.project_id, allocation_by_project, project_bonus_scale)
        priority_expr.append(recurring_vars[task.id] * (base_priority + bonus))

    model.Maximize(sum(priority_expr))

    solver.parameters.max_time_in_seconds = float(config.max_time_in_seconds)

    status = solver.Solve(model)
    solve_time = time_module.time() - start_time

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return HumanWeeklySelectionResult(
            success=False,
            status="INFEASIBLE" if status == cp_model.INFEASIBLE else "UNKNOWN",
            solve_time_seconds=solve_time,
        )

    selected_task_ids = [task.id for task in tasks if solver.Value(task_selected_vars[task.id]) == 1]
    selected_recurring_ids = [
        task.id for task in recurring_tasks if solver.Value(recurring_selected_vars[task.id]) == 1
    ]

    selected_hours = 0.0
    selected_hours_by_project: dict[str, float] = {}
    assigned_task_hours: dict[str, float] = {}
    assigned_recurring_hours: dict[str, float] = {}
    task_by_id = {task.id: task for task in tasks}
    recurring_by_id = {task.id: task for task in recurring_tasks}

    for task_id in selected_task_ids:
        task = task_by_id[task_id]
        task_hours = _scaled_assignment_to_hours(
            solver.Value(task_vars[task_id]),
            scaled_task_hours[task_id],
            task.hours,
            hours_scale,
        )
        assigned_task_hours[task_id] = task_hours
        selected_hours += task_hours
        if task.project_id:
            selected_hours_by_project[task.project_id] = (
                selected_hours_by_project.get(task.project_id, 0.0) + task_hours
            )

    for task_id in selected_recurring_ids:
        task = recurring_by_id[task_id]
        task_hours = _scaled_assignment_to_hours(
            solver.Value(recurring_vars[task_id]),
            scaled_recurring_hours[task_id],
            task.hours,
            hours_scale,
        )
        assigned_recurring_hours[task_id] = task_hours
        selected_hours += task_hours
        if task.project_id:
            selected_hours_by_project[task.project_id] = (
                selected_hours_by_project.get(task.project_id, 0.0) + task_hours
            )

    return HumanWeeklySelectionResult(
        success=True,
        status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        selected_task_ids=selected_task_ids,
        selected_recurring_task_ids=selected_recurring_ids,
        assigned_task_hours=assigned_task_hours,
        assigned_recurring_task_hours=assigned_recurring_hours,
        selected_hours=selected_hours,
        selected_hours_by_project=selected_hours_by_project,
        solve_time_seconds=solve_time,
        objective_value=float(solver.ObjectiveValue()),
    )


def _ceil_scaled_hours(hours: float, scale: int) -> int:
    return math.ceil((hours * scale) - 1e-9)


def _floor_scaled_hours(hours: float, scale: int) -> int:
    return math.floor((hours * scale) + 1e-9)


def _link_positive_assignment(model: Any, assigned_hours: Any, selected: Any) -> None:
    model.Add(assigned_hours >= 1).OnlyEnforceIf(selected)
    model.Add(assigned_hours == 0).OnlyEnforceIf(selected.Not())


def _scaled_assignment_to_hours(
    assigned_scaled_hours: int,
    full_scaled_hours: int,
    full_hours: float,
    scale: int,
) -> float:
    if assigned_scaled_hours == full_scaled_hours:
        return full_hours
    return assigned_scaled_hours / scale


def _validate_unique_weekly_task_ids(
    tasks: Sequence[HumanWeeklyTaskSpec],
    recurring_tasks: Sequence[HumanWeeklyTaskSpec],
) -> None:
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for task in [*tasks, *recurring_tasks]:
        if task.id in seen_ids:
            duplicate_ids.add(task.id)
        seen_ids.add(task.id)
    if duplicate_ids:
        duplicate_list = ", ".join(sorted(duplicate_ids))
        raise ValueError(f"weekly task ids must be unique across tasks and recurring_tasks: {duplicate_list}")


def _project_priority_bonus(
    project_id: str | None,
    allocation_by_project: Mapping[str, HumanWeeklyProjectAllocationSpec],
    project_bonus_scale: int,
) -> int:
    if project_id is None:
        return 0
    project_allocation = allocation_by_project.get(project_id)
    if project_allocation is None:
        return 0
    return int(project_allocation.priority_weight * project_bonus_scale)


def _import_cp_model() -> Any:
    try:
        from ortools.sat.python import cp_model
    except ModuleNotFoundError as exc:
        message = (
            "OR-Tools is required for weekly selection. Install with `pip install humancompiler-scheduler[cp-sat]`."
        )
        raise ModuleNotFoundError(message) from exc

    return cp_model


def _coerce_weekly_fixture(payload: HumanWeeklyInput) -> HumanWeeklySelectionFixture:
    if isinstance(payload, HumanWeeklySelectionFixture):
        return payload
    return human_weekly_selection_fixture_from_dict(payload)


def human_weekly_selection_fixture_from_dict(data: Mapping[str, Any]) -> HumanWeeklySelectionFixture:
    """Build a weekly selection fixture from a plain mapping."""
    return HumanWeeklySelectionFixture(
        tasks=_parse_weekly_tasks(_required(data, "tasks")),
        recurring_tasks=_parse_weekly_tasks(data.get("recurring_tasks", [])),
        project_allocations=_parse_project_allocations(data.get("project_allocations", [])),
        total_capacity_hours=float(data.get("total_capacity_hours", 40.0)),
        solver_config=_coerce_weekly_solver_config(data.get("solver_config", {})),
        metadata=dict(data.get("metadata", {})),
    )


def human_weekly_solver_config_from_dict(data: Mapping[str, Any]) -> HumanWeeklySolverConfig:
    """Build a weekly solver config from a mapping."""
    return _coerce_weekly_solver_config(data)


def _coerce_weekly_solver_config(config: HumanWeeklyConfigInput) -> HumanWeeklySolverConfig:
    if isinstance(config, HumanWeeklySolverConfig):
        return config
    allowed_keys = {field.name for field in HumanWeeklySolverConfig.__dataclass_fields__.values()}
    values = {key: value for key, value in config.items() if key in allowed_keys and value is not None}
    return HumanWeeklySolverConfig(**values)


def _parse_weekly_tasks(raw: Any) -> list[HumanWeeklyTaskSpec]:
    tasks: list[HumanWeeklyTaskSpec] = []
    for task_id, task in _iter_named_items(raw):
        tasks.append(
            HumanWeeklyTaskSpec(
                id=task_id,
                title=str(task.get("title", task_id)),
                hours=float(_required(task, "hours")),
                priority_score=float(task.get("priority_score", 5.0)),
                project_id=_optional_str(task.get("project_id")),
            )
        )
    return tasks


def _parse_project_allocations(raw: Any) -> list[HumanWeeklyProjectAllocationSpec]:
    allocations: list[HumanWeeklyProjectAllocationSpec] = []
    for project_id, allocation in _iter_named_items(raw):
        allocations.append(
            HumanWeeklyProjectAllocationSpec(
                project_id=project_id,
                target_hours=float(_required(allocation, "target_hours")),
                max_hours=float(allocation.get("max_hours", 0.0)),
                priority_weight=float(allocation.get("priority_weight", 0.0)),
                project_title=_optional_str(allocation.get("project_title")),
            )
        )
    return allocations


def _iter_named_items(raw: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if isinstance(raw, Mapping):
        return [(str(item_id), _ensure_mapping(item)) for item_id, item in raw.items()]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        items: list[tuple[str, Mapping[str, Any]]] = []
        for item in raw:
            mapped = _ensure_mapping(item)
            items.append((str(_required(mapped, "id")), mapped))
        return items
    return []


def _ensure_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("weekly selection items must be mappings")
    return value


def _required(data: Mapping[str, Any], key: str) -> Any:
    value = data.get(key)
    if value is None:
        raise KeyError(f"missing required field: {key}")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


# Backward-readable aliases for consumers migrating from the internal optimizer.
WeeklyTaskSpec = HumanWeeklyTaskSpec
ProjectAllocationSpec = HumanWeeklyProjectAllocationSpec
WeeklySolverConfig = HumanWeeklySolverConfig
WeeklySelectionResult = HumanWeeklySelectionResult
