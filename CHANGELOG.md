# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **CI**: Added GitHub Actions workflows for Ruff, pytest, type checking, coverage, documentation builds, and Dependabot updates.
- **Development Tooling**: Added pre-commit hooks for file hygiene, Ruff formatting/linting, mypy, pyright, and pytest.
- **Packaging**: Added package build configuration, a `py.typed` marker, and locked development dependencies with uv.
- **Human Scheduling**: Added flexible daily human scheduling examples and tests, including optional CP-SAT coverage.
- **Repository Templates**: Added pull request, bug report, and feature request templates.

### Changed

- **Python Support**: Declared support for Python `>=3.10, <3.15`.
- **Code Quality**: Updated existing modules, examples, and tests to pass the configured Ruff, mypy, pyright, and pre-commit checks.

### Tests

- Added unit coverage for human daily scheduling models and solver behavior.
- Added optional CP-SAT solver coverage under the `cp_sat` pytest marker.
