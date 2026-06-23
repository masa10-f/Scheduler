"""Stable adapter-facing entry points for HumanCompiler daily planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .io import (
    compile_human_flexible_daily_fixture,
    human_daily_fixture_from_dict,
    human_daily_solver_config_from_dict,
)
from .model import HumanDailyFixture, HumanDailySolverConfig, HumanFlexibleDailyFixture, HumanSolverReport
from .solver import solve_human_daily_timeline

HumanDailyInput = HumanDailyFixture | HumanFlexibleDailyFixture | Mapping[str, Any]
HumanDailyConfigInput = HumanDailySolverConfig | Mapping[str, Any]


def plan_daily_schedule(
    payload: HumanDailyInput,
    *,
    solver_config: HumanDailyConfigInput | None = None,
) -> HumanSolverReport:
    """Plan one HumanCompiler-oriented daily schedule.

    This is the public integration entry point intended for HumanCompiler API
    adapters. It accepts either an already-built fixture or a plain mapping in
    the documented fixture shape, then returns the timeline solver report.
    """
    fixture = _coerce_daily_fixture(payload)
    if solver_config is not None:
        fixture = replace(fixture, solver_config=_coerce_solver_config(solver_config))
    return solve_human_daily_timeline(fixture)


def optimize_human_daily_schedule(
    payload: HumanDailyInput,
    *,
    solver_config: HumanDailyConfigInput | None = None,
) -> HumanSolverReport:
    """Backward-readable alias for :func:`plan_daily_schedule`."""
    return plan_daily_schedule(payload, solver_config=solver_config)


def _coerce_daily_fixture(payload: HumanDailyInput) -> HumanDailyFixture:
    if isinstance(payload, HumanDailyFixture):
        return payload
    if isinstance(payload, HumanFlexibleDailyFixture):
        return compile_human_flexible_daily_fixture(payload)
    return human_daily_fixture_from_dict(payload)


def _coerce_solver_config(config: HumanDailyConfigInput) -> HumanDailySolverConfig:
    if isinstance(config, HumanDailySolverConfig):
        return config
    return human_daily_solver_config_from_dict(config)
