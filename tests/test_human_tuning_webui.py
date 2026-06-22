from __future__ import annotations

import json
import threading
import unittest
from dataclasses import fields
from pathlib import Path
from urllib import request

from examples.human_tuning_webui import (
    FixtureEntry,
    SchedulerTuningHTTPServer,
    TuningRequestHandler,
    WebUIState,
    build_fixture_registry,
    config_schema,
    config_to_yaml,
    create_tuning_payload,
    solver_config_to_dict,
)
from scheduler.human import (
    HumanDailySolverConfig,
    human_daily_solver_config_from_dict,
    load_human_daily_fixture,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DAILY_BASIC = REPO_ROOT / "samples/human/daily_basic.yaml"


class HumanTuningWebUITest(unittest.TestCase):
    def test_config_schema_covers_solver_config_fields_in_order(self) -> None:
        schema = config_schema()

        self.assertEqual([item["key"] for item in schema], [field.name for field in fields(HumanDailySolverConfig)])
        self.assertEqual(schema[0]["key"], "kind_match_score")
        self.assertEqual(schema[0]["group"], "Fit")
        self.assertEqual(schema[0]["visibility"], "essential")
        self.assertEqual({item["visibility"] for item in schema}, {"essential", "tuning", "expert"})

    def test_create_tuning_payload_applies_config_override(self) -> None:
        fixture = load_human_daily_fixture(DAILY_BASIC)
        config = HumanDailySolverConfig(priority_score_base=12, kind_match_score=14)
        fixture = fixture.__class__(
            date=fixture.date,
            tasks=fixture.tasks,
            time_slots=fixture.time_slots,
            fixed_assignments=fixture.fixed_assignments,
            task_dependencies=fixture.task_dependencies,
            solver_config=config,
            metadata=fixture.metadata,
        )

        payload = create_tuning_payload(
            FixtureEntry(id="daily_basic", path=DAILY_BASIC, label="daily_basic.yaml"),
            fixture,
            "timeline_greedy",
        )

        self.assertEqual(payload["config"]["priority_score_base"], 12)
        self.assertEqual(payload["selected_report"]["solver_name"], "timeline_greedy")
        self.assertGreater(payload["selected_report"]["scheduled_count"], 0)
        self.assertIn("priority_score_base: 12", payload["config_yaml"])

    def test_solver_config_round_trips_as_yaml_payload(self) -> None:
        config = HumanDailySolverConfig(
            deadline_score=11,
            project_switch_penalty=0,
            small_gap_fill_score=9,
        )

        loaded = human_daily_solver_config_from_dict(json.loads(json.dumps(solver_config_to_dict(config))))
        yaml_text = config_to_yaml(loaded)

        self.assertIn("solver_config:", yaml_text)
        self.assertIn("deadline_score: 11", yaml_text)
        self.assertIn("project_switch_penalty: 0", yaml_text)
        self.assertIn("small_gap_fill_score: 9", yaml_text)

    def test_http_api_solve_smoke(self) -> None:
        registry = build_fixture_registry([DAILY_BASIC], repo_root=REPO_ROOT)
        server = SchedulerTuningHTTPServer(
            ("127.0.0.1", 0),
            TuningRequestHandler,
            WebUIState(fixtures=registry, default_solver="timeline_greedy"),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            fixture_id = next(iter(registry))
            body = json.dumps(
                {
                    "fixture_id": fixture_id,
                    "solver_name": "timeline_greedy",
                    "config": {"priority_score_base": 10},
                }
            ).encode("utf-8")
            req = request.Request(  # noqa: S310
                f"{base_url}/api/solve",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with request.urlopen(req, timeout=5) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(payload["fixture"]["id"], fixture_id)
            self.assertEqual(payload["config"]["priority_score_base"], 10)
            self.assertEqual(payload["selected_report"]["solver_name"], "timeline_greedy")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_http_api_uses_fixture_config_when_override_is_missing(self) -> None:
        registry = build_fixture_registry([DAILY_BASIC], repo_root=REPO_ROOT)
        server = SchedulerTuningHTTPServer(
            ("127.0.0.1", 0),
            TuningRequestHandler,
            WebUIState(fixtures=registry, default_solver="legacy_slot"),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            fixture_id = next(iter(registry))
            with request.urlopen(f"{base_url}/api/default-config", timeout=5) as response:  # noqa: S310
                defaults = json.loads(response.read().decode("utf-8"))
            body = json.dumps(
                {
                    "fixture_id": fixture_id,
                    "solver_name": "legacy_slot",
                }
            ).encode("utf-8")
            req = request.Request(  # noqa: S310
                f"{base_url}/api/solve",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with request.urlopen(req, timeout=5) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(defaults["default_solver"], "legacy_slot")
            self.assertEqual(payload["config"]["dependency_unlock_score"], 5)
            self.assertEqual(payload["config"]["project_switch_penalty"], 6)
            self.assertEqual(payload["config"]["small_gap_fill_score"], 3)
            self.assertEqual(payload["selected_report"]["solver_name"], "legacy_slot")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
