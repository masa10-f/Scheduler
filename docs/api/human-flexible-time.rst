Human Flexible Time Design
==========================

This design records the Phase 3.3 direction for moving the experimental
``scheduler.human`` daily planner beyond hand-written ``time_slots`` while
keeping the existing fixtures and review command stable.

Goals
-----

The next scheduler iteration should accept a user's real day as broad
availability windows plus fixed events, then generate internal work intervals
for the existing timeline solver. The design must support rolling reschedule:
work before ``now`` stays frozen, fixed events remain hard blocks, and only the
remaining schedulable time is rebuilt.

The existing ``time_slots`` fixture format remains supported. New flexible-time
inputs should be an additive adapter layer, not a breaking replacement.

Input Model
-----------

``availability_windows``
  Broad same-day working windows, such as 09:00-12:00 focused work and
  13:00-18:00 mixed work. Each window can carry a default work kind and
  optional capacity limit.

``fixed_events``
  Hard blocks that cannot be moved by the solver: meetings, lab reservations,
  travel, meals, and user-pinned breaks. They are subtracted from availability
  before tasks are considered.

``now``
  Optional timestamp for rolling reschedule. Blocks ending before ``now`` are
  frozen. A currently running block is either frozen through its planned end or
  converted into remaining work, depending on task interruptibility.

``split_allowed`` and chunk fields
  Task-level split policy. ``split_allowed`` controls whether a task can be
  divided across intervals. ``min_chunk_minutes`` is the smallest useful block,
  and ``preferred_chunk_minutes`` is the chunk size the planner should try
  first.

Compatibility Plan
------------------

Flexible input should compile to the current ``HumanDailyFixture`` shape before
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

Hard constraints:

* fixed events and frozen past blocks cannot overlap scheduled work;
* non-splittable tasks must fit in one generated interval;
* split chunks must be at least ``min_chunk_minutes``;
* dependency order remains based on concrete block end times.

Soft preferences:

* use ``preferred_chunk_minutes`` when splitting long tasks;
* keep focused work in high-energy windows when possible;
* prefer natural breaks around fixed events over filling every small gap;
* avoid changing the project immediately after a short fixed event unless the
  score clearly justifies it.

Review Fixtures
---------------

Add review fixtures before HumanCompiler integration:

* a normal day with morning focus, lunch, and afternoon mixed availability;
* a rolling reschedule after a late morning interruption;
* a day with a lab reservation that blocks a large afternoon interval;
* a mixed day containing one non-splittable task and several small splittable
  follow-ups.

Acceptance Criteria
-------------------

The flexible-time adapter is ready for implementation when:

* existing ``time_slots`` fixtures still produce the same review command shape;
* generated intervals are explainable from availability, fixed events, and
  ``now``;
* no task is scheduled before ``now`` or inside a fixed event;
* non-splittable tasks are never divided;
* review output makes rolling changes easy to compare with the previous plan.
