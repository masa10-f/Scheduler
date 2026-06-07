# Scheduler
A general purpose scheduling solver

## HumanCompiler experimental API

HumanCompiler-oriented scheduling models live under `scheduler.human`.
This namespace is experimental and exists to keep HumanCompiler domain concepts
separate from the generic `Task` / `Resource` / `Problem` solver API.

Use this layer for adapter-facing concepts such as human tasks, daily time
slots, fixed assignments, and timeline blocks. The models intentionally do not
depend on HumanCompiler database types.

Run one fixture:

```bash
uv run python examples/human_daily_demo.py samples/human/daily_basic.yaml
```

Run a batch review and save a snapshot:

```bash
uv run python examples/human_daily_review.py samples/human/*.yaml --format markdown --output human_daily_review.md
```

The sample review fixtures share the same curated TaskAgent task database at
`samples/human/data/taskagent_common_database.yaml`. The fixture files vary the
available time windows and constraints, not the underlying task set.

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
