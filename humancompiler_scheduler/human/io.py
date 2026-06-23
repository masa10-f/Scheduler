"""YAML input helpers for HumanCompiler-oriented daily scheduling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time
from operator import itemgetter
from pathlib import Path
from typing import Any

import yaml

from .model import (
    HumanAvailabilityWindow,
    HumanDailyFixture,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanFixedEvent,
    HumanFlexibleDailyFixture,
    HumanMetadataValue,
    HumanTask,
    HumanTaskSource,
    HumanTimeSlot,
    HumanWorkKind,
)


def load_human_daily_fixture(path: str | Path) -> HumanDailyFixture:
    """Load a Human daily fixture from YAML."""
    fixture_path = Path(path)
    data = _load_yaml(fixture_path)
    if data.get("task_database") is not None:
        data = _merge_task_database(data, fixture_path.parent)
    return human_daily_fixture_from_dict(data)


def load_human_daily_solver_config(path: str | Path) -> HumanDailySolverConfig:
    """Load a Human daily solver config from YAML."""
    data = _load_yaml(path)
    raw_config = data.get("solver_config", data)
    return human_daily_solver_config_from_dict(raw_config)


def human_daily_fixture_from_dict(data: Mapping[str, Any]) -> HumanDailyFixture:
    """Build a Human daily fixture from a mapping."""
    if data.get("time_slots") is None and data.get("availability_windows") is not None:
        return compile_human_flexible_daily_fixture(human_flexible_daily_fixture_from_dict(data))
    return HumanDailyFixture(
        date=_parse_date(_required(data, "date")),
        tasks=_parse_tasks(_required(data, "tasks")),
        time_slots=_parse_time_slots(_required(data, "time_slots")),
        fixed_assignments=_parse_fixed_assignments(data.get("fixed_assignments", [])),
        task_dependencies=_parse_task_dependencies(data.get("task_dependencies", {})),
        solver_config=_parse_solver_config(data.get("solver_config", {})),
        metadata=_parse_metadata(data.get("metadata", {})),
    )


def human_flexible_daily_fixture_from_dict(
    data: Mapping[str, Any],
) -> HumanFlexibleDailyFixture:
    """Build a flexible Human daily fixture from a mapping."""
    return HumanFlexibleDailyFixture(
        date=_parse_date(_required(data, "date")),
        tasks=_parse_tasks(_required(data, "tasks")),
        availability_windows=_parse_availability_windows(_required(data, "availability_windows")),
        fixed_events=_parse_fixed_events(data.get("fixed_events", [])),
        now=_parse_datetime_or_none(data.get("now")),
        fixed_assignments=_parse_fixed_assignments(data.get("fixed_assignments", [])),
        task_dependencies=_parse_task_dependencies(data.get("task_dependencies", {})),
        solver_config=_parse_solver_config(data.get("solver_config", {})),
        metadata=_parse_metadata(data.get("metadata", {})),
    )


def human_daily_solver_config_from_dict(
    data: Mapping[str, Any],
) -> HumanDailySolverConfig:
    """Build a Human daily solver config from a mapping."""
    return _parse_solver_config(data)


def compile_human_flexible_daily_fixture(
    fixture: HumanFlexibleDailyFixture,
) -> HumanDailyFixture:
    """Compile flexible availability into concrete daily time slots."""
    return HumanDailyFixture(
        date=fixture.date,
        tasks=fixture.tasks,
        time_slots=_generate_time_slots(
            fixture.availability_windows,
            fixture.fixed_events,
            fixture.date,
            fixture.now,
        ),
        fixed_assignments=fixture.fixed_assignments,
        task_dependencies=fixture.task_dependencies,
        solver_config=fixture.solver_config,
        metadata=dict(fixture.metadata),
    )


def _merge_task_database(
    fixture_data: Mapping[str, Any],
    fixture_directory: Path,
) -> Mapping[str, Any]:
    database_path = fixture_directory / str(_required(fixture_data, "task_database"))
    database_data = _load_yaml(database_path)
    merged: dict[str, Any] = dict(fixture_data)
    if "tasks" not in merged:
        merged["tasks"] = database_data.get("tasks", [])
    if "task_dependencies" not in merged:
        merged["task_dependencies"] = database_data.get("task_dependencies", {})
    return merged


def _load_yaml(path: str | Path) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, Mapping):
        raise TypeError("fixture root must be a mapping")
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
                split_allowed=_parse_bool(task.get("split_allowed", False)),
                min_chunk_minutes=(
                    int(task["min_chunk_minutes"]) if task.get("min_chunk_minutes") is not None else None
                ),
                preferred_chunk_minutes=(
                    int(task["preferred_chunk_minutes"]) if task.get("preferred_chunk_minutes") is not None else None
                ),
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
                capacity_minutes=(int(slot["capacity_minutes"]) if slot.get("capacity_minutes") is not None else None),
                assigned_project_id=_optional_str(slot.get("assigned_project_id")),
                metadata=_parse_metadata(slot.get("metadata", {})),
            )
        )
    return slots


def _parse_availability_windows(raw: Any) -> list[HumanAvailabilityWindow]:
    windows: list[HumanAvailabilityWindow] = []
    for _window_id, window in _iter_named_items(raw):
        work_kind = window.get("work_kind", window.get("default_work_kind", "light_work"))
        windows.append(
            HumanAvailabilityWindow(
                start=_parse_time(_required(window, "start")),
                end=_parse_time(_required(window, "end")),
                work_kind=_parse_work_kind(work_kind),
                capacity_minutes=(
                    int(window["capacity_minutes"]) if window.get("capacity_minutes") is not None else None
                ),
                assigned_project_id=_optional_str(window.get("assigned_project_id")),
                metadata=_parse_metadata(window.get("metadata", {})),
            )
        )
    return windows


def _parse_fixed_events(raw: Any) -> list[HumanFixedEvent]:
    fixed_events: list[HumanFixedEvent] = []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return fixed_events
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        fixed_events.append(
            HumanFixedEvent(
                title=str(item.get("title", "fixed event")),
                start=_parse_time(_required(item, "start")),
                end=_parse_time(_required(item, "end")),
                metadata=_parse_metadata(item.get("metadata", {})),
            )
        )
    return fixed_events


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
                duration_minutes=(int(item["duration_minutes"]) if item.get("duration_minutes") is not None else None),
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
            dependencies[task_id] = [str(value) for value in _as_sequence(item.get("depends_on", []))]
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
        project_switch_reset_gap_minutes=int(raw.get("project_switch_reset_gap_minutes", 30)),
        long_continuous_threshold_minutes=int(raw.get("long_continuous_threshold_minutes", 120)),
        long_continuous_penalty=int(raw.get("long_continuous_penalty", 5)),
        break_reset_gap_minutes=int(raw.get("break_reset_gap_minutes", 20)),
        small_gap_minutes=int(raw.get("small_gap_minutes", 15)),
        small_gap_fill_score=int(raw.get("small_gap_fill_score", 2)),
    )


def _generate_time_slots(
    availability_windows: Sequence[HumanAvailabilityWindow],
    fixed_events: Sequence[HumanFixedEvent],
    fixture_date: date,
    now: datetime | None,
) -> list[HumanTimeSlot]:
    now_minutes = _now_minutes_for_date(now, fixture_date)
    raw_segments: list[tuple[int, int, int, HumanAvailabilityWindow]] = []
    for window_index, window in enumerate(availability_windows):
        window_segments = [(_minutes(window.start), _minutes(window.end))]
        sorted_events = sorted(
            fixed_events,
            key=lambda item: (_minutes(item.start), _minutes(item.end)),
        )
        for event in sorted_events:
            window_segments = _subtract_event_segments(window_segments, event)
        for start_minutes, end_minutes in window_segments:
            if end_minutes > start_minutes:
                raw_segments.append((start_minutes, end_minutes, window_index, window))

    slots: list[HumanTimeSlot] = []
    remaining_capacity_by_window = {
        window_index: window.capacity_minutes for window_index, window in enumerate(availability_windows)
    }
    sorted_segments = sorted(
        raw_segments,
        key=itemgetter(0, 1, 2),
    )
    for index, (start_minutes, end_minutes, window_index, window) in enumerate(sorted_segments):
        slot_start_minutes = start_minutes
        if now_minutes is not None:
            if end_minutes <= now_minutes:
                continue
            slot_start_minutes = max(slot_start_minutes, now_minutes)
        if end_minutes <= slot_start_minutes:
            continue
        duration_minutes = end_minutes - slot_start_minutes
        capacity_minutes = None
        remaining_capacity = remaining_capacity_by_window[window_index]
        if remaining_capacity is not None:
            assigned_capacity = min(remaining_capacity, duration_minutes)
            capacity_minutes = assigned_capacity
            remaining_capacity_by_window[window_index] = remaining_capacity - assigned_capacity
        slots.append(
            HumanTimeSlot(
                index=index,
                start=_time_from_minutes(slot_start_minutes),
                end=_time_from_minutes(end_minutes),
                work_kind=window.work_kind,
                capacity_minutes=capacity_minutes,
                assigned_project_id=window.assigned_project_id,
                metadata=dict(window.metadata),
            )
        )
    return slots


def _subtract_event_segments(
    segments: Sequence[tuple[int, int]],
    event: HumanFixedEvent,
) -> list[tuple[int, int]]:
    event_start = _minutes(event.start)
    event_end = _minutes(event.end)
    remaining: list[tuple[int, int]] = []
    for start_minutes, end_minutes in segments:
        if event_end <= start_minutes or event_start >= end_minutes:
            remaining.append((start_minutes, end_minutes))
            continue
        if event_start > start_minutes:
            remaining.append((start_minutes, event_start))
        if event_end < end_minutes:
            remaining.append((event_end, end_minutes))
    return remaining


def _now_minutes_for_date(now: datetime | None, fixture_date: date) -> int | None:
    if now is None:
        return None
    if now.date() < fixture_date:
        return None
    if now.date() > fixture_date:
        return 24 * 60
    return _minutes(now.time())


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


def _parse_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.lower()
        if value in {"true", "yes", "1"}:
            return True
        if value in {"false", "no", "0"}:
            return False
    raise ValueError(f"invalid boolean value: {raw}")


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time_from_minutes(value: int) -> time:
    return time(hour=value // 60, minute=value % 60)


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
        message = f"missing required field: {key}"
        raise ValueError(message)
    return data[key]
