# HumanCompiler Scheduler

HumanCompiler Scheduler is a small Python package for HumanCompiler-oriented
daily planning experiments. It provides plain dataclass models, YAML fixture
loading, review tools, and a timeline solver that can be called from
HumanCompiler adapter code without depending on HumanCompiler database models.

The distribution name is `humancompiler-scheduler`; the import package is
`humancompiler_scheduler`.

## Installation

Install from PyPI after the first release:

```bash
uv add humancompiler-scheduler
```

Or install the current repository checkout:

```bash
uv pip install -e .
```

## HumanCompiler Integration API

HumanCompiler-oriented scheduling models live under
`humancompiler_scheduler.human`. Use `plan_daily_schedule` as the stable
adapter-facing entry point:

```python
from humancompiler_scheduler.human import plan_daily_schedule

report = plan_daily_schedule(
    {
        "date": "2026-05-20",
        "availability_windows": [
            {"start": "09:00", "end": "12:00", "work_kind": "focused_work"},
            {"start": "13:00", "end": "18:00", "work_kind": "light_work"},
        ],
        "fixed_events": [
            {"title": "Team sync", "start": "11:00", "end": "11:30"},
        ],
        "tasks": [
            {
                "id": "proposal",
                "title": "Draft proposal",
                "remaining_minutes": 90,
                "priority": 1,
                "work_kind": "focused_work",
                "source": "task",
            },
        ],
        "solver_config": {
            "kind_match_score": 8,
            "kind_mismatch_score": 1,
        },
    }
)

for block in report.plan.blocks:
    print(block.task_id, block.start, block.end)
```

The lower-level fixture helpers and solver functions remain available for
review tooling and experiments.

## Known Limitations

The `0.1.0` release intentionally keeps the solver compact. It does not yet:

- split one task across multiple scheduled blocks;
- insert break blocks automatically;
- preserve prior scheduled blocks or model current-task interruptibility for
  full rolling reschedule.

## Fixture Review

Run one fixture:

```bash
uv run python examples/human_daily_demo.py samples/human/daily_basic.yaml
```

Run a batch review and save a snapshot:

```bash
uv run python examples/human_daily_review.py samples/human/*.yaml --format markdown --output human_daily_review.md
```

The sample review fixtures share the same synthetic HumanCompiler task database
at `samples/human/data/humancompiler_common_database.yaml`. The fixture files
vary the available time windows and constraints, not the underlying task set.

Apply a shared solver config override to every fixture in the review:

```bash
uv run python examples/human_daily_review.py samples/human/*.yaml --config review_config.yaml
```

## Documentation

Sphinx documentation lives in `docs/`.

```bash
uv run --extra docs sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` after the build completes.

## Releasing

Releases are tag-driven. Update `CHANGELOG.md`, create a semantic version tag
such as `v0.1.0`, and push it. The release workflow builds the package, checks
the distribution metadata, publishes to PyPI through Trusted Publishing, and
creates GitHub release notes from the matching changelog section.
