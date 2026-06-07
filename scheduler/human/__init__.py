"""Experimental HumanCompiler scheduling domain API."""

from .model import (
    HumanConstraintViolation,
    HumanDailyFixture,
    HumanDailyPlan,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanScheduleBlock,
    HumanScoreBreakdown,
    HumanSolverComparison,
    HumanSolverReport,
    HumanTask,
    HumanTaskSource,
    HumanTimeSlot,
    HumanUnscheduledTask,
    HumanWorkKind,
)
from .io import (
    human_daily_fixture_from_dict,
    human_daily_solver_config_from_dict,
    load_human_daily_fixture,
    load_human_daily_solver_config,
)
from .report import (
    format_human_daily_compact,
    format_human_daily_comparison,
    format_human_daily_report,
)
from .review import (
    format_human_daily_review_markdown,
    format_human_daily_review_text,
    run_human_daily_review,
    write_human_daily_review,
)
from .solver import (
    compare_human_daily_solvers,
    solve_human_daily_legacy,
    solve_human_daily_timeline,
)

__all__ = [
    "HumanConstraintViolation",
    "HumanDailyFixture",
    "HumanDailyPlan",
    "HumanDailySolverConfig",
    "HumanFixedAssignment",
    "HumanScheduleBlock",
    "HumanScoreBreakdown",
    "HumanSolverComparison",
    "HumanSolverReport",
    "HumanTask",
    "HumanTaskSource",
    "HumanTimeSlot",
    "HumanUnscheduledTask",
    "HumanWorkKind",
    "compare_human_daily_solvers",
    "format_human_daily_compact",
    "format_human_daily_comparison",
    "format_human_daily_report",
    "format_human_daily_review_markdown",
    "format_human_daily_review_text",
    "human_daily_fixture_from_dict",
    "human_daily_solver_config_from_dict",
    "load_human_daily_fixture",
    "load_human_daily_solver_config",
    "run_human_daily_review",
    "solve_human_daily_legacy",
    "solve_human_daily_timeline",
    "write_human_daily_review",
]
