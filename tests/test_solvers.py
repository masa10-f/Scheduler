from __future__ import annotations

import pytest

from scheduler import Problem, Resource, Task, solve_cp_sat


@pytest.mark.cp_sat
def test_cp_sat_solves_simple_single_resource_problem() -> None:
    problem = Problem(
        tasks={
            "short": Task(id="short", duration=1),
            "long": Task(id="long", duration=2),
        },
        resources={"worker": Resource(id="worker", capacity=1)},
    )

    result = solve_cp_sat(problem, time_limit_s=5.0)

    assert result.status == "ok"
    assert result.objective == 3
    assert sorted(result.schedule.assignments) == ["long", "short"]
