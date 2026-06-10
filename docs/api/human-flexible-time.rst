Human Flexible Time Adapter
===========================

The experimental ``scheduler.human`` daily planner accepts flexible daily
fixtures in addition to hand-written ``time_slots``. Flexible fixtures describe
the day as broad ``availability_windows``, hard ``fixed_events``, and an
optional ``now`` timestamp. The adapter compiles that input into
``HumanTimeSlot`` values before the existing timeline solver runs.

Implementation Status
---------------------

The v1 adapter is implemented. It:

* subtracts ``fixed_events`` from ``availability_windows``;
* drops generated intervals that end before ``now``;
* trims generated intervals that cross ``now`` to start at ``now``;
* distributes a capped window's ``capacity_minutes`` across generated slots;
* preserves ``task_dependencies`` and ``solver_config``;
* keeps existing fixtures with explicit ``time_slots`` unchanged.

Task split policy fields are parsed and preserved on ``HumanTask``. The solver
does not yet split one task into multiple scheduled blocks.

Usage
-----

Flexible fixtures can be loaded with the same helper used for fixed
``time_slots`` fixtures:

.. code-block:: python

   from scheduler.human import load_human_daily_fixture, solve_human_daily_timeline

   fixture = load_human_daily_fixture("samples/human/daily_flexible_normal.yaml")
   report = solve_human_daily_timeline(fixture)

Use the review command to compare fixture output:

.. code-block:: bash

   uv run python examples/human_daily_review.py samples/human/daily_flexible_*.yaml

Add ``--verbose`` to include solver settings and the full score breakdown.

Compatibility
-------------

The existing ``time_slots`` fixture format remains supported. New flexible-time
inputs are an additive adapter layer, not a breaking replacement. If a fixture
contains both ``time_slots`` and ``availability_windows``, the explicit
``time_slots`` are used.

Input Model
-----------

``availability_windows``
  Broad same-day working windows, such as 09:00-12:00 focused work and
  13:00-18:00 mixed work. Each window can carry a default work kind and
  optional capacity limit. When a capped window is split by fixed events or
  ``now``, the cap is consumed across the generated slots instead of being reset
  for each slot.

``fixed_events``
  Hard blocks that cannot be moved by the solver: meetings, lab reservations,
  travel, meals, and user-pinned breaks. They are subtracted from availability
  before tasks are considered.

``now``
  Optional timestamp for rolling reschedule. Generated intervals ending before
  ``now`` are dropped, and intervals crossing ``now`` are trimmed to begin at
  ``now``. The v1 adapter does not reconstruct already scheduled historical
  blocks.

``split_allowed`` and chunk fields
  Task-level split policy. ``split_allowed``, ``min_chunk_minutes``, and
  ``preferred_chunk_minutes`` are parsed and preserved for future solver
  behavior. The current timeline solver still schedules each task as a single
  block.

Generated Slots
---------------

Flexible input compiles to the current ``HumanDailyFixture`` shape before
calling the existing solvers:

* subtract ``fixed_events`` from ``availability_windows``;
* drop intervals that end before ``now``;
* trim intervals that cross ``now`` to start at ``now``;
* preserve accepted fixed assignments as fixed timeline blocks;
* emit generated ``HumanTimeSlot`` values ordered by start time;
* keep ``task_dependencies`` and ``solver_config`` unchanged.

For v1, generated slots can be coarse intervals split only by fixed events and
``now``. Fine-grained task splitting can follow after review fixtures show that
the broad time model behaves naturally.

Scheduling Rules
----------------

Current hard constraints:

* fixed events and frozen past blocks cannot overlap scheduled work;
* tasks must fit in one generated interval;
* dependency order remains based on concrete block end times.

Future splitting rules:

* non-splittable tasks should stay in one generated interval;
* split chunks should be at least ``min_chunk_minutes``;
* the solver should prefer ``preferred_chunk_minutes`` when splitting long
  tasks.

Soft preferences already handled by the timeline solver include:

* keep focused work in high-energy windows when possible;
* prefer natural breaks around fixed events over filling every small gap;
* avoid changing the project immediately after a short fixed event unless the
  score clearly justifies it.

Review Fixtures
---------------

The following review fixtures are included:

* ``samples/human/daily_flexible_normal.yaml``: a normal day with morning focus,
  lunch, and afternoon mixed availability;
* ``samples/human/daily_flexible_rolling.yaml``: a rolling reschedule after a
  late morning interruption;
* ``samples/human/daily_flexible_fixed_events.yaml``: a day with a lab
  reservation that blocks a large afternoon interval;
* ``samples/human/daily_flexible_split_policy.yaml``: a mixed day containing one
  non-splittable task and several small splittable follow-ups.

Known Limitations
-----------------

The v1 adapter does not yet:

* split a single task across multiple scheduled blocks;
* preserve a previously scheduled plan as frozen timeline blocks;
* model interruptibility for a currently running task.

Those behaviors should be implemented in the solver layer after the flexible
fixture output has been reviewed.
