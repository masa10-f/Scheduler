Human Flexible Fixture Review
=============================

This note records the first review checkpoint after the flexible time adapter
v1 implementation. It is intentionally a human-readability checkpoint, not a
runtime integration step for HumanCompiler.

Command
-------

.. code-block:: bash

   uv run python examples/human_daily_review.py samples/human/daily_flexible_*.yaml --format markdown

Result
------

The command completed successfully for all four flexible fixtures:

* ``daily_flexible_normal``: 微妙. Morning focused work is used naturally, but
  afternoon ``light_work`` capacity still accepts heavier research tasks. This
  looks like weight tuning around work-kind mismatch and deadline pressure.
* ``daily_flexible_fixed_events``: 微妙. Fixed events are subtracted correctly
  and the timeline resumes after the blocked interval, but heavy tasks still
  land in light slots. This is likely weight tuning, not an adapter bug.
* ``daily_flexible_rolling``: 微妙. ``now`` trimming works and past slots are
  dropped, but the review needs a clearer distinction between "lower score" and
  truly blocked dependency outcomes. This may need report/model wording before
  solver changes.
* ``daily_flexible_split_policy``: 自然 for v1. Split policy fields are parsed
  and preserved, and the solver keeps one block per task as documented. The
  next solver phase should implement actual task splitting before using this as
  real operational behavior.

Tuning Versus Model Work
------------------------

Weight/config tuning candidates:

* Increase the penalty for placing focused work into light slots.
* Rebalance deadline/dependency scores so urgent tasks do not overwhelm energy
  matching unless the due date is genuinely close.
* Review long-work and project-switch penalties after the kind mismatch tuning.

Model/report candidates:

* Add clearer unscheduled reasons for score-based omissions.
* Preserve previously scheduled historical blocks before full rolling
  reschedule support.
* Implement actual split behavior for ``split_allowed`` tasks, respecting
  ``min_chunk_minutes`` and ``preferred_chunk_minutes``.

Next Checkpoint
---------------

Before integrating the external package into HumanCompiler runtime behavior,
export explicitly reviewed, non-sensitive HumanCompiler data into Scheduler
fixture shape and run the same review command against those generated fixtures.
