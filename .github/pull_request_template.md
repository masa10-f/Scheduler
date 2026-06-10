Before submitting, please check the following:

- Make sure you have tests for the new code and that tests pass (run `uv run --group dev pytest`)
- Format added code by `uv run --group dev ruff format`
- Run linting by `uv run --group dev ruff check`
- Type check by `uv run --group dev mypy` and `uv run --group dev pyright`
- Make sure the checks (GitHub Actions) pass.
- Check that the docs compile without errors (run `uv run --extra docs sphinx-build -W docs docs/_build/html` after `uv sync --extra docs`.)

Then, please fill in below:

**Context (if applicable):**

**Description of the change:**

**Related issue:**
