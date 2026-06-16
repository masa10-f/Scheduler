"""Public API for the taskagent scheduler package."""

from .constraints import (
    Constraint,
    PrecedenceConstraint,
    ResourceAvailabilityConstraint,
    ResourceCapacityConstraint,
    ResourceEligibilityConstraint,
    TimeWindowConstraint,
    Violation,
    default_constraints,
    evaluate_constraints,
)
from .io import load_problem_yaml, load_schedule_yaml, problem_from_dict, schedule_from_dict
from .model import Assignment, Precedence, Problem, Resource, Schedule, Task
from .solvers import SolverResult, compare_solvers, solve_cp_sat, solve_greedy

__all__ = [
    "Assignment",
    "Constraint",
    "Precedence",
    "PrecedenceConstraint",
    "Problem",
    "Resource",
    "ResourceAvailabilityConstraint",
    "ResourceCapacityConstraint",
    "ResourceEligibilityConstraint",
    "Schedule",
    "SolverResult",
    "Task",
    "TimeWindowConstraint",
    "Violation",
    "compare_solvers",
    "default_constraints",
    "evaluate_constraints",
    "load_problem_yaml",
    "load_schedule_yaml",
    "problem_from_dict",
    "schedule_from_dict",
    "solve_cp_sat",
    "solve_greedy",
]
