from __future__ import annotations

from pathlib import Path
import sys

from scheduler import default_constraints, load_problem_yaml, solve_cp_sat, solve_greedy


def _print_schedule(title: str, schedule) -> None:
    print(f"\n{title}")
    for assignment in sorted(
        schedule.assignments.values(),
        key=lambda item: (item.start, item.resource_id, item.task_id),
    ):
        print(
            f"- task={assignment.task_id} resource={assignment.resource_id} "
            f"start={assignment.start}"
        )


def _print_violations(violations) -> None:
    if not violations:
        print("  violations: none")
        return
    print("  violations:")
    for violation in violations:
        print(f"    - {violation.constraint}: {violation.message}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_path = repo_root / "samples" / "sample.yaml"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path

    problem = load_problem_yaml(path)
    constraints = default_constraints()

    greedy = solve_greedy(problem, constraints=constraints)
    print("Greedy:", greedy.status, "makespan=", greedy.objective)
    if greedy.unscheduled:
        print("  unscheduled:", ", ".join(greedy.unscheduled))
    _print_violations(greedy.violations)
    _print_schedule("Greedy schedule", greedy.schedule)

    try:
        cp = solve_cp_sat(problem, constraints=constraints, time_limit_s=5.0)
    except ModuleNotFoundError as exc:
        print("\nCP-SAT skipped:", exc)
        return 0

    print("\nCP-SAT:", cp.status, "makespan=", cp.objective)
    if cp.unscheduled:
        print("  unscheduled:", ", ".join(cp.unscheduled))
    _print_violations(cp.violations)
    _print_schedule("CP-SAT schedule", cp.schedule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
