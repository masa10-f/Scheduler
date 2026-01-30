from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from scheduler.model import Assignment, Precedence, Problem, Resource, Schedule, Task, TimeWindow


def load_problem_yaml(path: str | Path) -> Problem:
    data = _load_yaml(path)
    return problem_from_dict(data)


def load_schedule_yaml(path: str | Path) -> Schedule:
    data = _load_yaml(path)
    return schedule_from_dict(data)


def problem_from_dict(data: Mapping[str, Any]) -> Problem:
    tasks_data = data.get("tasks", {})
    resources_data = data.get("resources", {})
    precedences_data = data.get("precedences", [])
    time_horizon = data.get("time_horizon")

    tasks: dict[str, Task] = {}
    for task_id, task in _iter_named_items(tasks_data):
        tasks[task_id] = Task(
            id=task_id,
            duration=_required(task, "duration"),
            earliest_start=task.get("earliest_start", 0),
            latest_end=task.get("latest_end"),
            eligible_resources=task.get("eligible_resources"),
            resource_demand=task.get("resource_demand", 1),
            priority=task.get("priority", 0),
            metadata=task.get("metadata", {}),
        )

    resources: dict[str, Resource] = {}
    for resource_id, resource in _iter_named_items(resources_data):
        resources[resource_id] = Resource(
            id=resource_id,
            capacity=resource.get("capacity", 1),
            availability=_parse_windows(resource.get("availability")),
            metadata=resource.get("metadata", {}),
        )

    precedences: list[Precedence] = []
    for prec in precedences_data:
        if isinstance(prec, (list, tuple)):
            before, after, *rest = prec
            lag = rest[0] if rest else 0
        else:
            before = prec.get("before")
            after = prec.get("after")
            lag = prec.get("lag", 0)
        precedences.append(Precedence(before=before, after=after, lag=lag))

    return Problem(
        tasks=tasks,
        resources=resources,
        precedences=precedences,
        time_horizon=time_horizon,
    )


def schedule_from_dict(data: Mapping[str, Any]) -> Schedule:
    assignments_data = data.get("assignments", [])
    assignments: dict[str, Assignment] = {}
    for item in assignments_data:
        task_id = item.get("task_id")
        assignment = Assignment(
            task_id=task_id,
            resource_id=item.get("resource_id"),
            start=item.get("start"),
        )
        assignments[task_id] = assignment
    return Schedule(assignments=assignments)


def _load_yaml(path: str | Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyYAML is required for YAML input. Install with `pip install pyyaml`."
        ) from exc
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _iter_named_items(data: Any) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(data, Mapping):
        for key, value in data.items():
            if isinstance(value, Mapping):
                yield str(key), value
        return
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        for item in data:
            if isinstance(item, Mapping) and "id" in item:
                item_id = str(item["id"])
                yield item_id, item


def _parse_windows(raw: Any) -> Sequence[TimeWindow] | None:
    if raw is None:
        return None
    windows: list[TimeWindow] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            windows.append((int(item[0]), int(item[1])))
    return windows


def _required(data: Mapping[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"missing required field: {key}")
    return data[key]
