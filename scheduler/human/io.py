from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from .model import (
    HumanDailyFixture,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanMetadataValue,
    HumanTask,
    HumanTaskSource,
    HumanTimeSlot,
    HumanWorkKind,
)


def load_human_daily_fixture(path: str | Path) -> HumanDailyFixture:
    data = _load_yaml(path)
    return human_daily_fixture_from_dict(data)


def human_daily_fixture_from_dict(data: Mapping[str, Any]) -> HumanDailyFixture:
    return HumanDailyFixture(
        date=_parse_date(_required(data, "date")),
        tasks=_parse_tasks(_required(data, "tasks")),
        time_slots=_parse_time_slots(_required(data, "time_slots")),
        fixed_assignments=_parse_fixed_assignments(data.get("fixed_assignments", [])),
        task_dependencies=_parse_task_dependencies(data.get("task_dependencies", {})),
        solver_config=_parse_solver_config(data.get("solver_config", {})),
        metadata=_parse_metadata(data.get("metadata", {})),
    )


def _load_yaml(path: str | Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyYAML is required for YAML input. Install with `pip install pyyaml`."
        ) from exc
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, Mapping):
        raise ValueError("fixture root must be a mapping")
    return loaded


def _parse_tasks(raw: Any) -> list[HumanTask]:
    tasks: list[HumanTask] = []
    for task_id, task in _iter_named_items(raw):
        tasks.append(
            HumanTask(
                id=task_id,
                title=str(_required(task, "title")),
                remaining_minutes=int(_required(task, "remaining_minutes")),
                priority=int(task.get("priority", 3)),
                work_kind=_parse_work_kind(task.get("work_kind", "light_work")),
                due_at=_parse_datetime_or_none(task.get("due_at")),
                project_id=_optional_str(task.get("project_id")),
                goal_id=_optional_str(task.get("goal_id")),
                source=_parse_task_source(task.get("source", "task")),
                metadata=_parse_metadata(task.get("metadata", {})),
            )
        )
    return tasks


def _parse_time_slots(raw: Any) -> list[HumanTimeSlot]:
    slots: list[HumanTimeSlot] = []
    for default_index, (_slot_id, slot) in enumerate(_iter_named_items(raw)):
        index = int(slot.get("index", default_index))
        slots.append(
            HumanTimeSlot(
                index=index,
                start=_parse_time(_required(slot, "start")),
                end=_parse_time(_required(slot, "end")),
                work_kind=_parse_work_kind(slot.get("work_kind", "light_work")),
                capacity_minutes=(
                    int(slot["capacity_minutes"])
                    if slot.get("capacity_minutes") is not None
                    else None
                ),
                assigned_project_id=_optional_str(slot.get("assigned_project_id")),
                metadata=_parse_metadata(slot.get("metadata", {})),
            )
        )
    return slots


def _parse_fixed_assignments(raw: Any) -> list[HumanFixedAssignment]:
    fixed_assignments: list[HumanFixedAssignment] = []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return fixed_assignments
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        fixed_assignments.append(
            HumanFixedAssignment(
                task_id=str(_required(item, "task_id")),
                slot_index=int(_required(item, "slot_index")),
                duration_minutes=(
                    int(item["duration_minutes"])
                    if item.get("duration_minutes") is not None
                    else None
                ),
            )
        )
    return fixed_assignments


def _parse_task_dependencies(raw: Any) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    if isinstance(raw, Mapping):
        for task_id, prereqs in raw.items():
            dependencies[str(task_id)] = [str(item) for item in _as_sequence(prereqs)]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            task_id = str(_required(item, "task_id"))
            dependencies[task_id] = [
                str(value) for value in _as_sequence(item.get("depends_on", []))
            ]
    return dependencies


def _parse_solver_config(raw: Any) -> HumanDailySolverConfig:
    if not isinstance(raw, Mapping):
        return HumanDailySolverConfig()
    return HumanDailySolverConfig(
        kind_match_score=int(raw.get("kind_match_score", 8)),
        kind_mismatch_score=int(raw.get("kind_mismatch_score", 1)),
        priority_score_base=int(raw.get("priority_score_base", 6)),
        deadline_soon_days=int(raw.get("deadline_soon_days", 2)),
        deadline_score=int(raw.get("deadline_score", 4)),
        overdue_score=int(raw.get("overdue_score", 20)),
        fixed_assignment_score=int(raw.get("fixed_assignment_score", 100)),
        dependency_unlock_score=int(raw.get("dependency_unlock_score", 3)),
        project_switch_penalty=int(raw.get("project_switch_penalty", 4)),
        project_switch_reset_gap_minutes=int(
            raw.get("project_switch_reset_gap_minutes", 30)
        ),
        long_continuous_threshold_minutes=int(
            raw.get("long_continuous_threshold_minutes", 120)
        ),
        long_continuous_penalty=int(raw.get("long_continuous_penalty", 5)),
        break_reset_gap_minutes=int(raw.get("break_reset_gap_minutes", 20)),
        small_gap_minutes=int(raw.get("small_gap_minutes", 15)),
        small_gap_fill_score=int(raw.get("small_gap_fill_score", 2)),
    )


def _iter_named_items(data: Any) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(data, Mapping):
        for key, value in data.items():
            if isinstance(value, Mapping):
                yield str(key), value
        return
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        for index, item in enumerate(data):
            if isinstance(item, Mapping):
                item_id = str(item.get("id", index))
                yield item_id, item


def _parse_date(raw: Any) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    return date.fromisoformat(str(raw))


def _parse_datetime_or_none(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime.combine(raw, time())
    return datetime.fromisoformat(str(raw))


def _parse_time(raw: Any) -> time:
    if isinstance(raw, time):
        return raw
    return time.fromisoformat(str(raw))


def _parse_work_kind(raw: Any) -> HumanWorkKind:
    return HumanWorkKind(str(raw))


def _parse_task_source(raw: Any) -> HumanTaskSource:
    value = str(raw)
    if value == "task":
        return "task"
    if value == "quick_task":
        return "quick_task"
    if value == "weekly_recurring_task":
        return "weekly_recurring_task"
    raise ValueError(f"invalid task source: {value}")


def _parse_metadata(raw: Any) -> dict[str, HumanMetadataValue]:
    metadata: dict[str, HumanMetadataValue] = {}
    if not isinstance(raw, Mapping):
        return metadata
    for key, value in raw.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            metadata[str(key)] = value
    return metadata


def _as_sequence(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return list(raw)
    return [raw]


def _optional_str(raw: Any) -> str | None:
    if raw is None:
        return None
    return str(raw)


def _required(data: Mapping[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"missing required field: {key}")
    return data[key]
