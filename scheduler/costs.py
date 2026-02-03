from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from scheduler.model import Problem, Resource, Schedule, Task


def _int_meta(task: Task, key: str, default: int | None = None) -> int | None:
    if key not in task.metadata:
        return default
    value = task.metadata.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"metadata field '{key}' for task '{task.id}' must be int-like"
        ) from exc


def _str_list_meta(task: Task, key: str) -> list[str] | None:
    if key not in task.metadata:
        return None
    value = task.metadata.get(key)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _int_profile(resource: Resource, key: str) -> list[int] | None:
    if key not in resource.metadata:
        return None
    value = resource.metadata.get(key)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        try:
            return [int(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"metadata field '{key}' for resource '{resource.id}' must be int-like list"
            ) from exc
    raise ValueError(
        f"metadata field '{key}' for resource '{resource.id}' must be a list"
    )


def _aggregate_profile(
    profile: Sequence[int],
    start: int,
    end: int,
    *,
    default_value: int,
    mode: str,
) -> float:
    if start >= end:
        return float(default_value)
    values: list[int] = []
    for t in range(start, end):
        if 0 <= t < len(profile):
            values.append(profile[t])
        else:
            values.append(default_value)
    if not values:
        return float(default_value)
    if mode == "avg":
        return sum(values) / len(values)
    if mode == "min":
        return float(min(values))
    raise ValueError(f"unsupported aggregation mode: {mode}")


def _estimate_horizon(problem: Problem) -> int:
    if problem.time_horizon is not None:
        return problem.time_horizon
    latest_end = max(
        (
            task.latest_end
            for task in problem.tasks.values()
            if task.latest_end is not None
        ),
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
    earliest_start = min(
        (task.earliest_start for task in problem.tasks.values()), default=0
    )
    candidates = [value for value in [latest_end, max_avail] if value is not None]
    if candidates:
        return max(max(candidates), earliest_start + total_duration)
    return earliest_start + total_duration


def _schedule_makespan(problem: Problem, schedule: Schedule) -> int:
    max_end = None
    for assignment in schedule.iter_assignments():
        if assignment.task_id not in problem.tasks:
            continue
        task = problem.task(assignment.task_id)
        end = assignment.end(task)
        if max_end is None or end > max_end:
            max_end = end
    return max_end or 0


def _cp_weight(weight: int | float) -> int:
    if isinstance(weight, float) and not weight.is_integer():
        raise ValueError("CP-SAT objective weights must be integers.")
    return int(weight)


@dataclass
class CostTerm(ABC):
    name: str
    weight: int | float = 1.0

    @abstractmethod
    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        raise NotImplementedError

    @abstractmethod
    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        raise NotImplementedError

    def schedule_cost(self, *, problem: Problem, schedule: Schedule) -> float:
        total = 0.0
        for assignment in schedule.iter_assignments():
            total += self.greedy_delta(
                problem=problem,
                schedule=schedule,
                task_id=assignment.task_id,
                resource_id=assignment.resource_id,
                start=assignment.start,
            )
        return total


@dataclass
class Objective:
    terms: Sequence[CostTerm] = field(default_factory=list)

    def greedy_score(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        return sum(
            term.weight
            * term.greedy_delta(
                problem=problem,
                schedule=schedule,
                task_id=task_id,
                resource_id=resource_id,
                start=start,
            )
            for term in self.terms
        )

    def schedule_cost(self, *, problem: Problem, schedule: Schedule) -> float:
        return sum(
            term.weight * term.schedule_cost(problem=problem, schedule=schedule)
            for term in self.terms
        )

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        return sum(
            _cp_weight(term.weight)
            * term.cp_sat_expr(
                model=model,
                problem=problem,
                start_vars=start_vars,
                end_vars=end_vars,
                presence=presence,
                horizon=horizon,
                makespan=makespan,
            )
            for term in self.terms
        )


# Example cost terms below. These are meant as templates you can customize.


@dataclass
class PriorityCompletionCost(CostTerm):
    name: str = "priority_completion"
    priority_weight_key: str = "priority_weight"

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        task = problem.task(task_id)
        meta_weight = _int_meta(task, self.priority_weight_key, 1) or 0
        end = start + task.duration
        return task.priority * meta_weight * end

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        total = 0
        for task_id, task in problem.tasks.items():
            meta_weight = _int_meta(task, self.priority_weight_key, 1) or 0
            if task.priority == 0 or meta_weight == 0:
                continue
            total += task.priority * meta_weight * end_vars[task_id]
        return total


@dataclass
class TardinessCost(CostTerm):
    name: str = "tardiness"
    due_key: str = "due"
    penalty_key: str = "late_penalty"

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        task = problem.task(task_id)
        due = _int_meta(task, self.due_key)
        if due is None:
            return 0.0
        penalty = _int_meta(task, self.penalty_key, 1) or 0
        end = start + task.duration
        return max(0, end - due) * penalty

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        bound = _estimate_horizon(problem) if horizon is None else horizon
        total = 0
        for task_id, task in problem.tasks.items():
            due = _int_meta(task, self.due_key)
            if due is None:
                continue
            penalty = _int_meta(task, self.penalty_key, 1) or 0
            if penalty == 0:
                continue
            end = end_vars[task_id]
            tardiness = model.NewIntVar(0, bound, f"tard_{task_id}")
            model.Add(tardiness >= end - due)
            total += penalty * tardiness
        return total


@dataclass
class PreferredResourceCost(CostTerm):
    name: str = "preferred_resource"
    preferred_key: str = "preferred_resources"
    preferred_single_key: str = "preferred_resource"
    penalty_key: str = "resource_penalty"

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        task = problem.task(task_id)
        preferred = _str_list_meta(task, self.preferred_key)
        if not preferred:
            preferred = _str_list_meta(task, self.preferred_single_key)
        if not preferred:
            return 0.0
        penalty = _int_meta(task, self.penalty_key, 1) or 0
        return 0.0 if resource_id in preferred else float(penalty)

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        total = 0
        for task_id, task in problem.tasks.items():
            preferred = _str_list_meta(task, self.preferred_key)
            if not preferred:
                preferred = _str_list_meta(task, self.preferred_single_key)
            if not preferred:
                continue
            penalty = _int_meta(task, self.penalty_key, 1) or 0
            if penalty == 0:
                continue
            lits = [
                presence[(task_id, resource_id)]
                for resource_id in preferred
                if (task_id, resource_id) in presence
            ]
            if not lits:
                total += penalty
                continue
            total += penalty * (1 - sum(lits))
        return total


@dataclass
class InverseSlackCost(CostTerm):
    name: str = "inverse_slack"
    due_key: str = "due"
    late_penalty_key: str = "late_penalty"
    scale: int = 100
    epsilon: int = 1
    bucket_size: int = 1
    max_penalty: int | None = None

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        task = problem.task(task_id)
        due = _int_meta(task, self.due_key)
        if due is None:
            return 0.0
        penalty = _int_meta(task, self.late_penalty_key, 1) or 0
        end = start + task.duration
        slack = due - end
        inv = self.scale / (max(slack, 0) + self.epsilon)
        if self.max_penalty is not None:
            inv = min(inv, float(self.max_penalty))
        if slack >= 0:
            return inv
        return inv + float(penalty) * (-slack)

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        bound = _estimate_horizon(problem) if horizon is None else horizon
        total = 0
        for task_id, task in problem.tasks.items():
            due = _int_meta(task, self.due_key)
            if due is None:
                continue
            late_penalty = _int_meta(task, self.late_penalty_key, 1) or 0
            end = end_vars[task_id]

            min_end = task.earliest_start + task.duration
            max_slack = max(0, due - min_end)
            diff_lower = min(0, due - bound)
            diff_upper = max_slack
            diff = model.NewIntVar(diff_lower, diff_upper, f"slack_diff_{task_id}")
            model.Add(diff == due - end)
            slack = model.NewIntVar(0, max_slack, f"slack_{task_id}")
            model.AddMaxEquality(slack, [0, diff])

            if self.bucket_size > 1:
                bucket_max = max_slack // self.bucket_size
                bucket = model.NewIntVar(0, bucket_max, f"slack_bucket_{task_id}")
                model.AddDivisionEquality(bucket, slack, self.bucket_size)
            else:
                bucket = slack
                bucket_max = max_slack

            table: list[int] = []
            scale = int(self.scale)
            eps = max(1, int(self.epsilon))
            cap = self.max_penalty
            for i in range(bucket_max + 1):
                denom = i * self.bucket_size + eps
                value = int(round(scale / denom))
                if cap is not None:
                    value = min(value, cap)
                table.append(value)
            penalty = model.NewIntVar(
                min(table), max(table), f"inv_slack_{task_id}"
            )
            model.AddElement(bucket, table, penalty)

            late_diff = model.NewIntVar(-bound, bound, f"late_diff_{task_id}")
            model.Add(late_diff == end - due)
            late = model.NewIntVar(0, bound, f"late_{task_id}")
            model.AddMaxEquality(late, [0, late_diff])

            total += penalty + late_penalty * late
        return total


@dataclass
class ResourceUtilizationCost(CostTerm):
    name: str = "resource_utilization"

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        resource = problem.resource(resource_id)
        capacity = resource.capacity

        old_min = None
        old_max = None
        old_demand = 0
        for assignment in schedule.iter_assignments():
            if assignment.resource_id != resource_id:
                continue
            if assignment.task_id not in problem.tasks:
                continue
            task = problem.task(assignment.task_id)
            old_demand += task.duration * task.resource_demand
            if old_min is None or assignment.start < old_min:
                old_min = assignment.start
            end = assignment.end(task)
            if old_max is None or end > old_max:
                old_max = end

        if old_min is None or old_max is None:
            old_span = 0
        else:
            old_span = old_max - old_min
        old_unused = old_span * capacity - old_demand

        task = problem.task(task_id)
        end = start + task.duration
        new_demand = old_demand + task.duration * task.resource_demand
        if old_min is None or old_max is None:
            new_span = task.duration
        else:
            new_min = min(old_min, start)
            new_max = max(old_max, end)
            new_span = new_max - new_min
        new_unused = new_span * capacity - new_demand
        return float(new_unused - old_unused)

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        bound = _estimate_horizon(problem) if horizon is None else horizon
        total = 0
        for resource_id, resource in problem.resources.items():
            candidates = [
                task_id
                for task_id in problem.tasks
                if (task_id, resource_id) in presence
            ]
            if not candidates:
                continue
            start_ifs = []
            end_ifs = []
            demand_terms: list[Any] = []
            for task_id in candidates:
                lit = presence[(task_id, resource_id)]
                start = start_vars[task_id]
                end = end_vars[task_id]

                start_if = model.NewIntVar(0, bound, f"start_{task_id}_{resource_id}")
                model.Add(start_if == start).OnlyEnforceIf(lit)
                model.Add(start_if == bound).OnlyEnforceIf(lit.Not())
                start_ifs.append(start_if)

                end_if = model.NewIntVar(0, bound, f"end_{task_id}_{resource_id}")
                model.Add(end_if == end).OnlyEnforceIf(lit)
                model.Add(end_if == 0).OnlyEnforceIf(lit.Not())
                end_ifs.append(end_if)

                task = problem.task(task_id)
                demand_terms.append(task.duration * task.resource_demand * lit)

            min_start = model.NewIntVar(0, bound, f"min_start_{resource_id}")
            max_end = model.NewIntVar(0, bound, f"max_end_{resource_id}")
            model.AddMinEquality(min_start, start_ifs)
            model.AddMaxEquality(max_end, end_ifs)

            diff = model.NewIntVar(-bound, bound, f"span_diff_{resource_id}")
            model.Add(diff == max_end - min_start)
            span = model.NewIntVar(0, bound, f"span_{resource_id}")
            model.AddMaxEquality(span, [0, diff])

            total_demand = sum(demand_terms)
            total += resource.capacity * span - total_demand
        return total


@dataclass
class DependencyUnlockCost(CostTerm):
    name: str = "dependency_unlock"
    base_weight: int = 1
    _cache: dict[int, dict[str, int]] = field(
        default_factory=dict, init=False, repr=False
    )

    def _weights(self, problem: Problem) -> dict[str, int]:
        cache_key = id(problem)
        if cache_key in self._cache:
            return self._cache[cache_key]
        weights = {task_id: self.base_weight for task_id in problem.tasks}
        for prec in problem.precedences:
            if prec.before not in weights:
                continue
            weights[prec.before] += 1
        self._cache[cache_key] = weights
        return weights

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        weights = self._weights(problem)
        weight = weights.get(task_id, 0)
        if weight == 0:
            return 0.0
        end = start + problem.task(task_id).duration
        return float(weight * end)

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        weights = self._weights(problem)
        total = 0
        for task_id, task in problem.tasks.items():
            weight = weights.get(task_id, 0)
            if weight == 0:
                continue
            total += weight * end_vars[task_id]
        return total


@dataclass
class TimeProfileCost(CostTerm):
    name: str = "time_profile"
    requirement_key: str = "focus_required"
    profile_key: str = "focus_profile"
    default_requirement: int = 0
    default_profile_value: int = 0
    aggregation: str = "avg"

    def _required(self, task: Task) -> int:
        return _int_meta(task, self.requirement_key, self.default_requirement) or 0

    def greedy_delta(
        self,
        *,
        problem: Problem,
        schedule: Schedule,
        task_id: str,
        resource_id: str,
        start: int,
    ) -> float:
        task = problem.task(task_id)
        required = self._required(task)
        if required <= 0:
            return 0.0
        resource = problem.resource(resource_id)
        profile = _int_profile(resource, self.profile_key)
        if not profile:
            return 0.0
        end = start + task.duration
        available = _aggregate_profile(
            profile,
            start,
            end,
            default_value=self.default_profile_value,
            mode=self.aggregation,
        )
        deficit = max(0.0, float(required) - float(available))
        return deficit * task.duration

    def cp_sat_expr(
        self,
        *,
        model: Any,
        problem: Problem,
        start_vars: Mapping[str, Any],
        end_vars: Mapping[str, Any],
        presence: Mapping[tuple[str, str], Any],
        horizon: int | None = None,
        makespan: Any | None = None,
    ) -> Any:
        bound = _estimate_horizon(problem) if horizon is None else horizon
        total = 0
        for task_id, task in problem.tasks.items():
            required = self._required(task)
            if required <= 0:
                continue
            min_start = task.earliest_start
            max_start = (
                task.latest_end - task.duration
                if task.latest_end is not None
                else bound - task.duration
            )
            if max_start < min_start:
                continue
            start_var = start_vars[task_id]
            start_index = model.NewIntVar(
                0, max_start - min_start, f"profile_idx_{task_id}_{self.name}"
            )
            model.Add(start_index == start_var - min_start)

            for resource_id in problem.resources:
                key = (task_id, resource_id)
                if key not in presence:
                    continue
                resource = problem.resource(resource_id)
                profile = _int_profile(resource, self.profile_key)
                if not profile:
                    continue

                values: list[int] = []
                for start in range(min_start, max_start + 1):
                    end = start + task.duration
                    available = _aggregate_profile(
                        profile,
                        start,
                        end,
                        default_value=self.default_profile_value,
                        mode=self.aggregation,
                    )
                    values.append(int(round(available)))

                min_value = min(values)
                max_value = max(values)
                avail = model.NewIntVar(
                    min_value, max_value, f"profile_{task_id}_{resource_id}"
                )
                model.AddElement(start_index, values, avail)

                diff_lower = required - max_value
                diff_upper = required - min_value
                deficit_diff = model.NewIntVar(
                    diff_lower, diff_upper, f"deficit_diff_{task_id}_{resource_id}"
                )
                model.Add(deficit_diff == required - avail)
                max_deficit = max(0, diff_upper)
                deficit = model.NewIntVar(
                    0, max_deficit, f"deficit_{task_id}_{resource_id}"
                )
                model.AddMaxEquality(deficit, [0, deficit_diff])

                max_cost = max_deficit * task.duration
                cost = model.NewIntVar(
                    0,
                    max_cost,
                    f"profile_cost_{task_id}_{resource_id}",
                )
                model.Add(cost == deficit * task.duration).OnlyEnforceIf(presence[key])
                model.Add(cost == 0).OnlyEnforceIf(presence[key].Not())
                total += cost
        return total


@dataclass
class SatisfactionWeights:
    priority: int = 1
    inverse_slack: int = 5
    capacity_utilization: int = 2
    dependency_unlock: int = 1
    focus_alignment: int = 3
    motivation_alignment: int = 1


def satisfaction_objective(
    *,
    weights: SatisfactionWeights | None = None,
    slack: InverseSlackCost | None = None,
    focus_profile: TimeProfileCost | None = None,
    motivation_profile: TimeProfileCost | None = None,
) -> Objective:
    weights = weights or SatisfactionWeights()
    slack_term = replace(slack or InverseSlackCost(), weight=weights.inverse_slack)
    focus_term = replace(
        focus_profile
        or TimeProfileCost(
            name="focus_alignment",
            requirement_key="focus_required",
            profile_key="focus_profile",
        ),
        weight=weights.focus_alignment,
    )
    motivation_term = replace(
        motivation_profile
        or TimeProfileCost(
            name="motivation_alignment",
            requirement_key="motivation_required",
            profile_key="motivation_profile",
        ),
        weight=weights.motivation_alignment,
    )
    return Objective(
        terms=[
            PriorityCompletionCost(weight=weights.priority),
            slack_term,
            ResourceUtilizationCost(weight=weights.capacity_utilization),
            DependencyUnlockCost(weight=weights.dependency_unlock),
            focus_term,
            motivation_term,
        ]
    )


def example_objective() -> Objective:
    return Objective(
        terms=[
            TardinessCost(weight=10),
            PreferredResourceCost(weight=2),
            PriorityCompletionCost(weight=1),
        ]
    )
