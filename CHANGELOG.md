# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-22

### Added

- Added the `humancompiler-scheduler` Python package with MIT license metadata,
  typed package data, PyPI classifiers, project URLs, and Hatchling build
  configuration.
- Added the `humancompiler_scheduler` import package, including the
  `humancompiler_scheduler.human` namespace for HumanCompiler-oriented daily
  scheduling.
- Added `plan_daily_schedule` and `optimize_human_daily_schedule` as stable
  HumanCompiler adapter entry points.
- Added HumanCompiler daily scheduling fixtures, flexible availability input,
  fixed events, rolling `now` trimming, solver config overrides, review reports,
  and tuning examples.
- Added GitHub Actions workflows for Ruff, pytest, type checking, coverage,
  documentation builds, Dependabot, and PyPI releases.
- Added a tag-triggered release workflow that builds distributions, validates
  package metadata, publishes to PyPI with Trusted Publishing, and creates
  GitHub release notes from this changelog.

### Changed

- Renamed public package artifacts from legacy project naming to
  HumanCompiler-oriented naming before the first PyPI release.
- Declared support for Python `>=3.10, <3.15`.
- Updated examples, tests, docs, and pre-commit hooks to use
  `humancompiler_scheduler`.

### Known Limitations

- Task splitting fields are parsed and preserved, but the solver still schedules
  each task as a single block.
- Breaks are only represented when passed as fixed events; automatic break
  insertion is not implemented yet.
- Rolling reschedule trims future availability with `now`, but frozen prior
  plans and current-task interruptibility are not implemented yet.

### Tests

- Added unit coverage for HumanCompiler daily scheduling models, fixture
  loading, flexible availability compilation, review output, and solver
  behavior.
- Added optional CP-SAT solver coverage under the `cp_sat` pytest marker.
