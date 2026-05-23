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
from .io import human_daily_fixture_from_dict, load_human_daily_fixture
from .report import format_human_daily_comparison, format_human_daily_report
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
    "format_human_daily_comparison",
    "format_human_daily_report",
    "human_daily_fixture_from_dict",
    "load_human_daily_fixture",
    "solve_human_daily_legacy",
    "solve_human_daily_timeline",
]
