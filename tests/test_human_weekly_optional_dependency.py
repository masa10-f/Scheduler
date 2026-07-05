from __future__ import annotations

import builtins
from unittest.mock import patch

import pytest

from humancompiler_scheduler.human import weekly


def test_weekly_solver_reports_missing_optional_cp_sat_extra() -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, object] | None = None,  # noqa: A002
        locals: dict[str, object] | None = None,  # noqa: A002
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "ortools.sat.python":
            raise ModuleNotFoundError("No module named 'ortools'")
        return real_import(name, globals, locals, fromlist, level)

    with (
        patch("builtins.__import__", side_effect=fake_import),
        pytest.raises(ModuleNotFoundError, match="humancompiler-scheduler\\[cp-sat\\]"),
    ):
        weekly._import_cp_model()
