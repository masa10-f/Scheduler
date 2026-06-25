"""Experimental HumanCompiler scheduling domain API."""

from .api import HumanDailyConfigInput, HumanDailyInput, optimize_human_daily_schedule, plan_daily_schedule
from .io import (
    compile_human_flexible_daily_fixture,
    human_daily_fixture_from_dict,
    human_daily_solver_config_from_dict,
    human_flexible_daily_fixture_from_dict,
    load_human_daily_fixture,
    load_human_daily_solver_config,
)
from .model import (
    HumanAvailabilityWindow,
    HumanConstraintViolation,
    HumanDailyFixture,
    HumanDailyPlan,
    HumanDailySolverConfig,
    HumanFixedAssignment,
    HumanFixedEvent,
    HumanFlexibleDailyFixture,
    HumanScheduleBlock,
    HumanScoreBreakdown,
    HumanSolverReport,
    HumanTask,
    HumanTaskSource,
    HumanTimeSlot,
    HumanUnscheduledTask,
    HumanWorkKind,
)
from .report import (
    format_human_daily_compact,
    format_human_daily_report,
)
from .review import (
    format_human_daily_review_markdown,
    format_human_daily_review_text,
    run_human_daily_review,
    write_human_daily_review,
)
from .solver import solve_human_daily_timeline

__all__ = [
    "HumanAvailabilityWindow",
    "HumanConstraintViolation",
    "HumanDailyConfigInput",
    "HumanDailyFixture",
    "HumanDailyInput",
    "HumanDailyPlan",
    "HumanDailySolverConfig",
    "HumanFixedAssignment",
    "HumanFixedEvent",
    "HumanFlexibleDailyFixture",
    "HumanScheduleBlock",
    "HumanScoreBreakdown",
    "HumanSolverReport",
    "HumanTask",
    "HumanTaskSource",
    "HumanTimeSlot",
    "HumanUnscheduledTask",
    "HumanWorkKind",
    "compile_human_flexible_daily_fixture",
    "format_human_daily_compact",
    "format_human_daily_report",
    "format_human_daily_review_markdown",
    "format_human_daily_review_text",
    "human_daily_fixture_from_dict",
    "human_daily_solver_config_from_dict",
    "human_flexible_daily_fixture_from_dict",
    "load_human_daily_fixture",
    "load_human_daily_solver_config",
    "optimize_human_daily_schedule",
    "plan_daily_schedule",
    "run_human_daily_review",
    "solve_human_daily_timeline",
    "write_human_daily_review",
]
