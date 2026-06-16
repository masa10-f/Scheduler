# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, ClassVar, cast
from urllib.parse import parse_qs, urlparse

import yaml

from scheduler.human import (
    HumanDailyFixture,
    HumanDailySolverConfig,
    HumanSolverReport,
    compare_human_daily_solvers,
    human_daily_solver_config_from_dict,
    load_human_daily_fixture,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_GLOB = "samples/human/*.yaml"
MAX_REQUEST_BYTES = 128 * 1024


@dataclass(frozen=True)
class ConfigControl:
    key: str
    label: str
    group: str
    minimum: int
    maximum: int
    step: int = 1
    help: str = ""


CONFIG_CONTROLS: tuple[ConfigControl, ...] = (
    ConfigControl(
        "kind_match_score",
        "Kind match",
        "Fit",
        0,
        30,
        help="Reward when task work_kind matches the slot work_kind.",
    ),
    ConfigControl(
        "kind_mismatch_score",
        "Kind mismatch",
        "Fit",
        0,
        30,
        help="Fallback score when a task can run in a non-matching slot.",
    ),
    ConfigControl("priority_score_base", "Priority base", "Priority", 1, 20),
    ConfigControl("deadline_soon_days", "Deadline horizon", "Priority", 0, 14),
    ConfigControl("deadline_score", "Deadline score", "Priority", 0, 30),
    ConfigControl("overdue_score", "Overdue score", "Priority", 0, 80),
    ConfigControl("fixed_assignment_score", "Fixed assignment", "Hard hints", 0, 200),
    ConfigControl("dependency_unlock_score", "Dependency unlock", "Hard hints", 0, 30),
    ConfigControl("project_switch_penalty", "Project switch", "Flow", 0, 30),
    ConfigControl("project_switch_reset_gap_minutes", "Switch reset gap", "Flow", 0, 180, 5),
    ConfigControl("long_continuous_threshold_minutes", "Long work threshold", "Flow", 0, 360, 5),
    ConfigControl("long_continuous_penalty", "Long work penalty", "Flow", 0, 40),
    ConfigControl("break_reset_gap_minutes", "Break reset gap", "Flow", 0, 180, 5),
    ConfigControl("small_gap_minutes", "Small gap", "Packing", 0, 120, 5),
    ConfigControl("small_gap_fill_score", "Gap fill score", "Packing", 0, 30),
)


@dataclass(frozen=True)
class FixtureEntry:
    id: str
    path: Path
    label: str


@dataclass(frozen=True)
class WebUIState:
    fixtures: Mapping[str, FixtureEntry]
    default_solver: str


class SchedulerTuningHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        state: WebUIState,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.state = state


class TuningRequestHandler(BaseHTTPRequestHandler):
    server: SchedulerTuningHTTPServer
    error_content_type = "application/json"
    server_version = "SchedulerTuningWebUI/0.1"

    _STATIC_ROUTES: ClassVar[dict[str, str]] = {
        "/": "index",
        "/index.html": "index",
    }

    def do_GET(self) -> None:
        route = self._STATIC_ROUTES.get(urlparse(self.path).path)
        if route == "index":
            self._send_html(render_index_html())
            return

        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/fixtures":
            self._send_json({"fixtures": [fixture_entry_to_dict(item) for item in self.server.state.fixtures.values()]})
            return
        if parsed.path == "/api/default-config":
            self._send_json(
                {
                    "config": solver_config_to_dict(HumanDailySolverConfig()),
                    "schema": config_schema(),
                }
            )
            return
        if parsed.path == "/api/config-yaml":
            params = parse_qs(parsed.query)
            raw_config = _query_config(params)
            try:
                config = human_daily_solver_config_from_dict(raw_config)
            except (TypeError, ValueError) as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._send_text(config_to_yaml(config), content_type="application/x-yaml; charset=utf-8")
            return

        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/solve":
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        try:
            payload = self._read_json_body()
            fixture_id = str(payload.get("fixture_id", ""))
            solver_name = str(payload.get("solver_name", self.server.state.default_solver))
            config = human_daily_solver_config_from_dict(_mapping(payload.get("config", {})))
            fixture_entry = self.server.state.fixtures[fixture_id]
        except KeyError:
            self._send_error(HTTPStatus.NOT_FOUND, "unknown fixture")
            return
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        try:
            fixture = replace(load_human_daily_fixture(fixture_entry.path), solver_config=config)
            response = create_tuning_payload(fixture_entry, fixture, solver_name)
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json(response)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002, PLR6301
        return

    def _read_json_body(self) -> Mapping[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        raw_body = self.rfile.read(content_length).decode("utf-8")
        data = json.loads(raw_body or "{}")
        return _mapping(data)

    def _send_html(self, value: str) -> None:
        self._send_text(value, content_type="text/html; charset=utf-8")

    def _send_text(self, value: str, *, content_type: str) -> None:
        body = value.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, value: Mapping[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def discover_default_fixtures(repo_root: Path = REPO_ROOT) -> list[Path]:
    return sorted(path for path in repo_root.glob(DEFAULT_FIXTURE_GLOB) if path.is_file())


def build_fixture_registry(paths: Sequence[Path], *, repo_root: Path = REPO_ROOT) -> dict[str, FixtureEntry]:
    registry: dict[str, FixtureEntry] = {}
    for path in paths:
        resolved = path.resolve()
        fixture_id = _fixture_id(resolved, repo_root=repo_root)
        label = _fixture_label(resolved, repo_root=repo_root)
        registry[fixture_id] = FixtureEntry(id=fixture_id, path=resolved, label=label)
    return dict(sorted(registry.items(), key=lambda item: item[1].label))


def create_tuning_payload(
    fixture_entry: FixtureEntry,
    fixture: HumanDailyFixture,
    solver_name: str,
) -> dict[str, Any]:
    comparison = compare_human_daily_solvers(fixture)
    if solver_name not in comparison.reports:
        raise KeyError(f"unknown solver: {solver_name}")
    selected_report = comparison.reports[solver_name]
    return {
        "fixture": fixture_to_dict(fixture_entry, fixture),
        "solver_name": solver_name,
        "config": solver_config_to_dict(fixture.solver_config),
        "config_yaml": config_to_yaml(fixture.solver_config),
        "selected_report": report_to_dict(fixture, selected_report),
        "reports": {name: report_to_dict(fixture, report) for name, report in comparison.reports.items()},
    }


def fixture_to_dict(fixture_entry: FixtureEntry, fixture: HumanDailyFixture) -> dict[str, Any]:
    return {
        "id": fixture_entry.id,
        "label": fixture_entry.label,
        "date": fixture.date.isoformat(),
        "name": fixture.metadata.get("name", fixture_entry.label),
        "task_count": len(fixture.tasks),
        "slot_count": len(fixture.time_slots),
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "remaining_minutes": task.remaining_minutes,
                "priority": task.priority,
                "work_kind": task.work_kind.value,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "project_id": task.project_id,
                "goal_id": task.goal_id,
            }
            for task in fixture.tasks
        ],
        "time_slots": [
            {
                "index": slot.index,
                "start": slot.start.strftime("%H:%M"),
                "end": slot.end.strftime("%H:%M"),
                "work_kind": slot.work_kind.value,
                "capacity_minutes": slot.effective_capacity_minutes,
                "assigned_project_id": slot.assigned_project_id,
            }
            for slot in fixture.time_slots
        ],
    }


def report_to_dict(fixture: HumanDailyFixture, report: HumanSolverReport) -> dict[str, Any]:
    tasks_by_id = {task.id: task for task in fixture.tasks}
    slots_by_index = {slot.index: slot for slot in fixture.time_slots}
    score_by_task = {score.task_id: score for score in report.score_breakdown}
    return {
        "solver_name": report.solver_name,
        "status": report.plan.status,
        "scheduled_count": len(report.plan.blocks),
        "unscheduled_count": len(report.unscheduled_tasks),
        "blocks": [
            {
                "task_id": block.task_id,
                "title": tasks_by_id[block.task_id].title if block.task_id in tasks_by_id else block.task_id,
                "slot_index": block.slot_index,
                "slot_kind": slots_by_index[block.slot_index].work_kind.value
                if block.slot_index in slots_by_index
                else "unknown",
                "start": block.start.strftime("%H:%M"),
                "end": block.end.strftime("%H:%M"),
                "duration_minutes": block.duration_minutes,
                "is_fixed": block.is_fixed,
                "score": score_by_task[block.task_id].total if block.task_id in score_by_task else None,
                "components": score_by_task[block.task_id].components if block.task_id in score_by_task else {},
            }
            for block in report.plan.blocks
        ],
        "unscheduled": [
            {"task_id": task.task_id, "title": task.title, "reason": task.reason} for task in report.unscheduled_tasks
        ],
        "violations": [
            {
                "code": violation.code,
                "message": violation.message,
                "task_id": violation.task_id,
                "slot_index": violation.slot_index,
            }
            for violation in report.violations
        ],
        "score_breakdown": [
            {
                "task_id": score.task_id,
                "title": tasks_by_id[score.task_id].title if score.task_id in tasks_by_id else score.task_id,
                "slot_index": score.slot_index,
                "total": score.total,
                "components": score.components,
            }
            for score in report.score_breakdown
        ],
    }


def fixture_entry_to_dict(entry: FixtureEntry) -> dict[str, str]:
    return {"id": entry.id, "label": entry.label}


def solver_config_to_dict(config: HumanDailySolverConfig) -> dict[str, int]:
    return {field.name: cast("int", value) for field in fields(config) for value in [getattr(config, field.name)]}


def config_schema() -> list[dict[str, Any]]:
    control_by_key = {control.key: control for control in CONFIG_CONTROLS}
    schema: list[dict[str, Any]] = []
    for field in fields(HumanDailySolverConfig):
        control = control_by_key[field.name]
        schema.append(
            {
                "key": control.key,
                "label": control.label,
                "group": control.group,
                "min": control.minimum,
                "max": control.maximum,
                "step": control.step,
                "help": control.help,
            }
        )
    return schema


def config_to_yaml(config: HumanDailySolverConfig) -> str:
    return cast(
        "str",
        yaml.safe_dump(
            {"solver_config": solver_config_to_dict(config)},
            sort_keys=False,
            default_flow_style=False,
        ),
    )


def render_index_html() -> str:
    return INDEX_HTML


def serve_webui(
    *,
    host: str,
    port: int,
    fixture_paths: Sequence[Path],
    default_solver: str,
    open_browser: bool,
) -> None:
    registry = build_fixture_registry(fixture_paths)
    if not registry:
        raise ValueError("no fixture YAML files found")

    server = SchedulerTuningHTTPServer(
        (host, port),
        TuningRequestHandler,
        WebUIState(fixtures=registry, default_solver=default_solver),
    )
    actual_host, actual_port = cast("tuple[str, int]", server.server_address)
    url = f"http://{actual_host}:{actual_port}/"
    print(f"Scheduler tuning WebUI: {url}")
    if open_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Scheduler tuning WebUI")
    finally:
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a standalone Scheduler tuning WebUI.")
    parser.add_argument(
        "fixtures",
        nargs="*",
        type=Path,
        help="Fixture YAML files to expose. Defaults to samples/human/*.yaml.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    parser.add_argument(
        "--solver",
        choices=["timeline_greedy", "legacy_slot"],
        default="timeline_greedy",
        help="Default solver selected in the UI.",
    )
    parser.add_argument("--open", action="store_true", help="Open the WebUI in a browser.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixtures = args.fixtures or discover_default_fixtures()
    serve_webui(
        host=args.host,
        port=args.port,
        fixture_paths=fixtures,
        default_solver=args.solver,
        open_browser=args.open,
    )
    return 0


def _fixture_id(path: Path, *, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _fixture_label(path: Path, *, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected object")
    return value


def _query_config(params: Mapping[str, Sequence[str]]) -> dict[str, int]:
    config: dict[str, int] = {}
    for field in fields(HumanDailySolverConfig):
        values = params.get(field.name)
        if values:
            config[field.name] = int(values[0])
    return config


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scheduler Tuning</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #172033;
      --muted: #5c667a;
      --accent: #1f7a64;
      --accent-2: #375a9e;
      --warn: #9a5b13;
      --bad: #a53838;
      --shadow: 0 1px 2px rgb(20 28 40 / 10%);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.4;
      letter-spacing: 0;
    }

    button, input, select, textarea { font: inherit; }
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      min-height: 34px;
      padding: 0 12px;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 650;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    select, input[type="number"], textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    select, input[type="number"] { min-height: 34px; padding: 0 9px; }
    textarea {
      min-height: 182px;
      padding: 10px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }

    .app {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(420px, 1fr);
      min-height: 100vh;
    }
    aside {
      border-right: 1px solid var(--line);
      background: #eef1f5;
      padding: 18px;
      overflow: auto;
    }
    main {
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 22px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    h1, h2, h3 { margin: 0; line-height: 1.2; letter-spacing: 0; }
    h1 { font-size: 19px; }
    h2 { font-size: 14px; text-transform: uppercase; color: var(--muted); }
    h3 { font-size: 15px; }
    .subtitle { color: var(--muted); margin-top: 4px; }
    .section {
      padding: 16px 0;
      border-top: 1px solid var(--line);
    }
    .section:first-child { border-top: 0; padding-top: 0; }
    .field { margin-top: 12px; }
    .field label {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      text-transform: uppercase;
    }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
    .content {
      display: grid;
      grid-template-columns: minmax(330px, 0.9fr) minmax(360px, 1.1fr);
      gap: 18px;
      padding: 18px 22px;
      overflow: auto;
      min-width: 0;
    }
    .band {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-width: 0;
    }
    .band > .band-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
    }
    .band > .band-body { padding: 14px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfd;
    }
    .metric strong { display: block; font-size: 20px; }
    .metric span { color: var(--muted); font-size: 12px; }
    .control-group {
      margin-top: 16px;
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }
    .control-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 76px;
      gap: 9px;
      align-items: center;
      margin-top: 10px;
    }
    input[type="range"] { width: 100%; accent-color: var(--accent-2); }
    .timeline {
      display: grid;
      gap: 8px;
    }
    .block {
      display: grid;
      grid-template-columns: 96px minmax(0, 1fr) 58px;
      gap: 10px;
      align-items: center;
      border: 1px solid var(--line);
      border-left: 5px solid var(--accent-2);
      border-radius: 8px;
      padding: 9px 10px;
      background: #fff;
    }
    .block.light_work { border-left-color: #7d8a98; }
    .block.focused_work { border-left-color: #1f7a64; }
    .block.study { border-left-color: #8a6f21; }
    .time { color: var(--muted); font-variant-numeric: tabular-nums; }
    .task-title {
      overflow-wrap: anywhere;
      font-weight: 650;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      background: #edf3ff;
      color: #294a86;
      font-size: 12px;
      font-weight: 650;
      white-space: nowrap;
    }
    .pill.warn { background: #fff3db; color: var(--warn); }
    .pill.bad { background: #ffe8e8; color: var(--bad); }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 7px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }
    .empty, .error {
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 14px;
      color: var(--muted);
      background: #fbfcfd;
    }
    .error { color: var(--bad); border-color: #e2aaa8; background: #fff5f5; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }

    @media (max-width: 980px) {
      .app, .content { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <section class="section">
        <h1>Scheduler Tuning</h1>
        <div class="subtitle">Local fixture playground for human daily solver weights.</div>
        <div class="field">
          <label for="fixtureSelect">Fixture</label>
          <select id="fixtureSelect"></select>
        </div>
        <div class="field">
          <label for="solverSelect">Solver</label>
          <select id="solverSelect">
            <option value="timeline_greedy">timeline_greedy</option>
            <option value="legacy_slot">legacy_slot</option>
          </select>
        </div>
        <div class="actions">
          <button class="primary" id="runButton" type="button">Run</button>
          <button id="resetButton" type="button">Reset</button>
        </div>
      </section>
      <section class="section">
        <h2>Parameters</h2>
        <div id="configControls"></div>
      </section>
      <section class="section">
        <h2>Export</h2>
        <textarea id="yamlExport" spellcheck="false"></textarea>
        <div class="actions">
          <button id="copyYamlButton" type="button">Copy YAML</button>
          <button id="downloadYamlButton" type="button">Download</button>
        </div>
      </section>
    </aside>
    <main>
      <header>
        <div>
          <h1 id="fixtureTitle">Fixture</h1>
          <div class="subtitle" id="fixtureSubtitle">Waiting for input</div>
        </div>
        <span class="pill" id="statusPill">idle</span>
      </header>
      <div class="content">
        <section class="band">
          <div class="band-head">
            <h3>Timeline</h3>
            <span class="pill" id="solverPill">timeline_greedy</span>
          </div>
          <div class="band-body">
            <div class="metrics" id="metrics"></div>
            <div class="timeline" id="timeline" style="margin-top: 14px;"></div>
          </div>
        </section>
        <section class="band">
          <div class="band-head">
            <h3>Diagnostics</h3>
            <span class="pill" id="scorePill">scores</span>
          </div>
          <div class="band-body">
            <h3>Unscheduled</h3>
            <div id="unscheduled" style="margin-top: 10px;"></div>
            <h3 style="margin-top: 18px;">Score Breakdown</h3>
            <div id="scoreBreakdown" style="margin-top: 10px;"></div>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script>
    const state = {
      config: {},
      defaultConfig: {},
      schema: [],
      fixtures: [],
      lastPayload: null,
    };

    const $ = (id) => document.getElementById(id);

    async function boot() {
      const [fixturesResponse, configResponse] = await Promise.all([
        fetch("/api/fixtures"),
        fetch("/api/default-config"),
      ]);
      const fixturesPayload = await fixturesResponse.json();
      const configPayload = await configResponse.json();
      state.fixtures = fixturesPayload.fixtures;
      state.defaultConfig = configPayload.config;
      state.config = { ...configPayload.config };
      state.schema = configPayload.schema;
      renderFixtureSelect();
      renderControls();
      bindEvents();
      updateYaml();
      await runSolve();
    }

    function renderFixtureSelect() {
      const select = $("fixtureSelect");
      select.innerHTML = "";
      for (const fixture of state.fixtures) {
        const option = document.createElement("option");
        option.value = fixture.id;
        option.textContent = fixture.label;
        select.appendChild(option);
      }
    }

    function renderControls() {
      const container = $("configControls");
      container.innerHTML = "";
      const groups = [...new Set(state.schema.map((item) => item.group))];
      for (const group of groups) {
        const groupNode = document.createElement("div");
        groupNode.className = "control-group";
        groupNode.innerHTML = `<h3>${escapeHtml(group)}</h3>`;
        for (const item of state.schema.filter((entry) => entry.group === group)) {
          const wrapper = document.createElement("div");
          wrapper.className = "field";
          wrapper.innerHTML = `
            <label title="${escapeHtml(item.help || item.key)}">
              <span>${escapeHtml(item.label)}</span>
              <span class="mono">${escapeHtml(item.key)}</span>
            </label>
            <div class="control-grid">
              <input type="range" min="${item.min}" max="${item.max}" step="${item.step}" value="${state.config[item.key]}" data-key="${item.key}">
              <input type="number" min="${item.min}" max="${item.max}" step="${item.step}" value="${state.config[item.key]}" data-key="${item.key}">
            </div>
          `;
          groupNode.appendChild(wrapper);
        }
        container.appendChild(groupNode);
      }
    }

    function bindEvents() {
      $("runButton").addEventListener("click", runSolve);
      $("resetButton").addEventListener("click", () => {
        state.config = { ...state.defaultConfig };
        renderControls();
        bindControlEvents();
        updateYaml();
        runSolve();
      });
      $("fixtureSelect").addEventListener("change", runSolve);
      $("solverSelect").addEventListener("change", runSolve);
      $("copyYamlButton").addEventListener("click", async () => {
        await navigator.clipboard.writeText($("yamlExport").value);
      });
      $("downloadYamlButton").addEventListener("click", () => {
        const blob = new Blob([$("yamlExport").value], { type: "application/x-yaml" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "scheduler-solver-config.yaml";
        link.click();
        URL.revokeObjectURL(link.href);
      });
      bindControlEvents();
    }

    function bindControlEvents() {
      for (const input of document.querySelectorAll("[data-key]")) {
        input.addEventListener("input", (event) => {
          const key = event.target.dataset.key;
          const value = Number.parseInt(event.target.value, 10);
          state.config[key] = value;
          for (const twin of document.querySelectorAll(`[data-key="${key}"]`)) {
            if (twin !== event.target) twin.value = String(value);
          }
          updateYaml();
        });
        input.addEventListener("change", runSolve);
      }
    }

    async function runSolve() {
      setBusy(true);
      try {
        const response = await fetch("/api/solve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fixture_id: $("fixtureSelect").value,
            solver_name: $("solverSelect").value,
            config: state.config,
          }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "solve failed");
        state.lastPayload = payload;
        $("yamlExport").value = payload.config_yaml;
        renderPayload(payload);
      } catch (error) {
        renderError(error);
      } finally {
        setBusy(false);
      }
    }

    function renderPayload(payload) {
      const fixture = payload.fixture;
      const report = payload.selected_report;
      $("fixtureTitle").textContent = fixture.name;
      $("fixtureSubtitle").textContent = `${fixture.label} / ${fixture.date} / ${fixture.task_count} tasks / ${fixture.slot_count} slots`;
      $("solverPill").textContent = payload.solver_name;
      $("statusPill").textContent = report.status;
      $("statusPill").className = `pill ${report.status === "ok" ? "" : "warn"}`;
      $("metrics").innerHTML = `
        ${metric("Scheduled", report.scheduled_count)}
        ${metric("Unscheduled", report.unscheduled_count)}
        ${metric("Violations", report.violations.length)}
        ${metric("Blocks", report.blocks.length)}
      `;
      renderTimeline(report.blocks);
      renderUnscheduled(report.unscheduled, report.violations);
      renderScoreBreakdown(report.score_breakdown);
    }

    function renderTimeline(blocks) {
      const target = $("timeline");
      if (!blocks.length) {
        target.innerHTML = `<div class="empty">No scheduled blocks.</div>`;
        return;
      }
      target.innerHTML = blocks.map((block) => `
        <div class="block ${escapeHtml(block.slot_kind)}">
          <div class="time">${escapeHtml(block.start)}-${escapeHtml(block.end)}</div>
          <div>
            <div class="task-title">${escapeHtml(block.title)}</div>
            <div class="subtitle">${escapeHtml(block.task_id)} / ${escapeHtml(block.slot_kind)} / ${block.duration_minutes} min</div>
          </div>
          <span class="pill">${block.score ?? "-"}</span>
        </div>
      `).join("");
    }

    function renderUnscheduled(items, violations) {
      const target = $("unscheduled");
      const rows = [];
      for (const item of items) {
        rows.push(`<tr><td>${escapeHtml(item.title)}</td><td class="mono">${escapeHtml(item.reason)}</td></tr>`);
      }
      for (const violation of violations) {
        rows.push(`<tr><td>${escapeHtml(violation.message)}</td><td class="mono">${escapeHtml(violation.code)}</td></tr>`);
      }
      target.innerHTML = rows.length ? table(["Item", "Reason"], rows) : `<div class="empty">No unscheduled tasks or violations.</div>`;
    }

    function renderScoreBreakdown(scores) {
      const target = $("scoreBreakdown");
      if (!scores.length) {
        target.innerHTML = `<div class="empty">No score rows.</div>`;
        return;
      }
      target.innerHTML = table(
        ["Task", "Total", "Components"],
        scores.map((score) => `
          <tr>
            <td>${escapeHtml(score.title)}<div class="subtitle mono">${escapeHtml(score.task_id)}</div></td>
            <td><span class="pill">${score.total}</span></td>
            <td class="mono">${escapeHtml(formatComponents(score.components))}</td>
          </tr>
        `),
      );
    }

    function updateYaml() {
      const lines = ["solver_config:"];
      for (const item of state.schema) {
        lines.push(`  ${item.key}: ${state.config[item.key]}`);
      }
      $("yamlExport").value = `${lines.join("\\n")}\\n`;
    }

    function setBusy(isBusy) {
      $("runButton").disabled = isBusy;
      $("statusPill").textContent = isBusy ? "running" : ($("statusPill").textContent || "idle");
    }

    function renderError(error) {
      $("timeline").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
      $("unscheduled").innerHTML = "";
      $("scoreBreakdown").innerHTML = "";
      $("statusPill").textContent = "error";
      $("statusPill").className = "pill bad";
    }

    function metric(label, value) {
      return `<div class="metric"><strong>${value}</strong><span>${escapeHtml(label)}</span></div>`;
    }

    function table(headers, rows) {
      return `<table><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
    }

    function formatComponents(components) {
      return Object.entries(components).map(([key, value]) => `${key}=${value}`).join(", ");
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    boot();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
