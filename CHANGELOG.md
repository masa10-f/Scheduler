# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-07-06

### Changed

- Extended weekly task selection to allocate partial task hours and report
  assigned hours per regular and recurring task. Partial assignments snap to
  0.5-hour increments (or the task's full hours), and per-project allocations
  are capped at `target_hours` instead of overshooting above it.

## [0.3.0] - 2026-07-05

### Added

- Added Human weekly task selection models and the stable
  `plan_weekly_selection` / `optimize_weekly_selection` adapter APIs.
- Added project allocation, zero-allocation exclusion, recurring task capacity,
  and priority-weighted weekly selection coverage.

### Fixed

- Counted recurring task hours with `project_id` in weekly project allocation
  constraints, project-level selected-hour summaries, and project priority
  bonuses.
- Rejected duplicate weekly task IDs across regular and recurring task inputs.

## [0.2.0] - 2026-06-25

### Added

- Added timeline solver block-duration candidates so long `remaining_minutes`
  values are scheduled as scored work blocks instead of all-or-nothing tasks.
- Added scheduler-level `min_block_minutes`, `block_granularity_minutes`, and
  `max_candidate_block_minutes` controls for block candidate generation.

### Changed

- Removed the legacy Human daily slot solver and comparison wrapper APIs so the
  Human daily scheduler uses the timeline solver directly.

### Fixed

- Fixed Human daily dependency ordering so dependent work only starts after
  prerequisite work has completed by time, including fixed assignments later in
  the day.

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
- Replaced review fixture task data with fully synthetic public demo data.
- Declared support for Python `>=3.10, <3.15`.
- Updated examples, tests, docs, and pre-commit hooks to use
  `humancompiler_scheduler`.

### Known Limitations

- Long tasks are scheduled as a single block when one compatible slot has enough
  capacity; bounded multi-block placement is not available in the 0.1.0 release.
- Breaks are only represented when passed as fixed events; automatic break
  insertion is not implemented yet.
- Rolling reschedule trims future availability with `now`, but frozen prior
  plans and current-task interruptibility are not implemented yet.

### Tests

- Added unit coverage for HumanCompiler daily scheduling models, fixture
  loading, flexible availability compilation, review output, and solver
  behavior.
- Added optional CP-SAT solver coverage under the `cp_sat` pytest marker.
