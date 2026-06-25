Human Flexible Time Adapter
===========================

The experimental ``humancompiler_scheduler.human`` daily planner accepts flexible daily
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
* preserves generated slot indexes when rolling ``now`` drops past slots;
* distributes a capped window's ``capacity_minutes`` across generated slots;
* preserves ``task_dependencies`` and ``solver_config``;
* keeps existing fixtures with explicit ``time_slots`` unchanged.

The timeline solver treats ``remaining_minutes`` as available task backlog for
planning. It generates scheduler-level block-duration candidates for the current
slot and scores those candidates with the same work-kind, priority, deadline,
project-switch, continuous-work, and gap-fill rules used for task choice. Long
tasks can therefore receive one or more work blocks in the day when they remain
good candidates.

Usage
-----

Flexible fixtures can be loaded with the same helper used for fixed
``time_slots`` fixtures:

.. code-block:: python

   from humancompiler_scheduler.human import load_human_daily_fixture, solve_human_daily_timeline

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
  blocks. Slot indexes are assigned before ``now`` filtering, so rolling
  fixtures can contain index gaps when past slots are dropped.

Chunk sizing fields
  The timeline solver emits one concrete block at a time from scheduler-level
  block candidates. ``min_chunk_minutes`` overrides the scheduler's
  ``min_block_minutes`` for that task, and ``preferred_chunk_minutes`` adds a
  natural task-specific duration to the candidate set.

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

Generated slots can be coarse intervals split by fixed events and ``now``.
Tasks may produce multiple scheduled blocks across those generated slots.

Scheduling Rules
----------------

Current hard constraints:

* fixed events and frozen past blocks cannot overlap scheduled work;
* each emitted task block must fit in one generated interval;
* dependency order is evaluated from the blocks in the generated plan, so a
  dependent task waits until its prerequisites have enough planned work blocks
  ahead of it.

Candidate generation rules:

* generated blocks use ``min_block_minutes``, ``block_granularity_minutes``, and
  ``max_candidate_block_minutes`` from ``solver_config``;
* task-level ``min_chunk_minutes`` can raise or lower the minimum block for one
  task;
* task-level ``preferred_chunk_minutes`` adds a preferred duration candidate;
* long tasks can contribute bounded blocks without needing to occupy every
  available minute in the day.

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
* ``samples/human/daily_flexible_block_candidates.yaml``: a mixed day showing
  long task backlog being cut into scored scheduler blocks while leaving room
  for other work.

Known Limitations
-----------------

The v1 adapter does not yet:

* preserve a previously scheduled plan as frozen timeline blocks;
* model interruptibility for a currently running task.

Those behaviors should be implemented in the solver layer after the flexible
fixture output has been reviewed.
