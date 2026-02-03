from __future__ import annotations

from scheduler import (
    DependencyUnlockCost,
    InverseSlackCost,
    Precedence,
    Problem,
    Resource,
    SatisfactionWeights,
    Task,
    TimeProfileCost,
    default_constraints,
    satisfaction_objective,
    solve_cp_sat,
    solve_greedy,
)


def build_problem() -> Problem:
    focus_profile = (
        [30] * 8  # 0-7
        + [80] * 4  # 8-11
        + [60] * 4  # 12-15
        + [40] * 4  # 16-19
        + [20] * 4  # 20-23
    )
    motivation_profile = (
        [40] * 8
        + [50] * 4
        + [55] * 4
        + [70] * 4
        + [45] * 4
    )

    resources = {
        "me": Resource(
            id="me",
            capacity=1,
            availability=[(0, 24)],
            metadata={
                "focus_profile": focus_profile,
                "motivation_profile": motivation_profile,
            },
        ),
        "runner": Resource(
            id="runner",
            capacity=2,
            availability=[(0, 24)],
        ),
    }

    tasks = {
        "deep_work": Task(
            id="deep_work",
            duration=3,
            earliest_start=8,
            latest_end=18,
            eligible_resources=["me"],
            priority=3,
            metadata={
                "due": 17,
                "late_penalty": 5,
                "focus_required": 70,
            },
        ),
        "email": Task(
            id="email",
            duration=1,
            earliest_start=9,
            latest_end=16,
            eligible_resources=["me"],
            priority=1,
            metadata={
                "due": 12,
                "late_penalty": 1,
                "motivation_required": 30,
            },
        ),
        "draft_report": Task(
            id="draft_report",
            duration=2,
            earliest_start=8,
            latest_end=20,
            eligible_resources=["me"],
            priority=2,
            metadata={
                "due": 18,
                "late_penalty": 3,
                "focus_required": 60,
            },
        ),
        "review_report": Task(
            id="review_report",
            duration=1,
            earliest_start=10,
            latest_end=22,
            eligible_resources=["me"],
            priority=2,
            metadata={
                "due": 21,
                "late_penalty": 2,
                "focus_required": 40,
            },
        ),
        "etl_job": Task(
            id="etl_job",
            duration=4,
            earliest_start=0,
            latest_end=24,
            eligible_resources=["runner"],
            resource_demand=1,
            priority=1,
        ),
        "backup": Task(
            id="backup",
            duration=3,
            earliest_start=0,
            latest_end=24,
            eligible_resources=["runner"],
            resource_demand=1,
            priority=1,
        ),
        "training": Task(
            id="training",
            duration=5,
            earliest_start=0,
            latest_end=24,
            eligible_resources=["runner"],
            resource_demand=1,
            priority=1,
        ),
    }

    precedences = [Precedence(before="draft_report", after="review_report", lag=0)]

    return Problem(
        tasks=tasks,
        resources=resources,
        precedences=precedences,
        time_horizon=24,
    )


def print_schedule(title: str, result) -> None:
    print(f"\n{title}: status={result.status} objective={result.objective}")
    if result.unscheduled:
        print("  unscheduled:", ", ".join(result.unscheduled))
    if result.violations:
        print("  violations:")
        for violation in result.violations:
            print(f"    - {violation.constraint}: {violation.message}")
    for assignment in sorted(
        result.schedule.assignments.values(),
        key=lambda item: (item.resource_id, item.start, item.task_id),
    ):
        print(
            f"  task={assignment.task_id} resource={assignment.resource_id} "
            f"start={assignment.start}"
        )


def main() -> int:
    problem = build_problem()

    objective = satisfaction_objective(
        weights=SatisfactionWeights(
            priority=2,
            inverse_slack=8,
            capacity_utilization=3,
            dependency_unlock=2,
            focus_alignment=4,
            motivation_alignment=2,
        ),
        slack=InverseSlackCost(scale=120, epsilon=1, bucket_size=1, max_penalty=200),
        focus_profile=TimeProfileCost(
            name="focus_alignment",
            requirement_key="focus_required",
            profile_key="focus_profile",
            aggregation="avg",
        ),
        motivation_profile=TimeProfileCost(
            name="motivation_alignment",
            requirement_key="motivation_required",
            profile_key="motivation_profile",
            aggregation="avg",
        ),
    )

    constraints = default_constraints()

    greedy = solve_greedy(problem, constraints=constraints, objective=objective)
    print_schedule("Greedy", greedy)

    try:
        cp = solve_cp_sat(problem, constraints=constraints, objective=objective, time_limit_s=5.0)
    except ModuleNotFoundError as exc:
        print(f"\nCP-SAT skipped: {exc}")
        return 0

    print_schedule("CP-SAT", cp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
