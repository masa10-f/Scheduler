Human Solver Parameters
=======================

``HumanDailySolverConfig`` controls how the experimental
``humancompiler_scheduler.human`` daily solvers score candidate task placements. These
parameters do not represent hard constraints by themselves. They change which
valid candidate the greedy scoring logic prefers.

Most parameters are integer score points. Larger positive scores make a
candidate more likely to be selected, while penalties subtract from the total
score. Minute parameters define thresholds used by those scoring rules.

Parameter Summary
-----------------

.. list-table::
   :header-rows: 1
   :widths: 22 10 10 12 24 28

   * - Parameter
     - Default
     - Unit
     - Valid range
     - Effect
     - When to tune
   * - ``kind_match_score``
     - ``8``
     - Score points
     - Integer ``>= 0``
     - Added when a task's ``work_kind`` matches the slot's ``work_kind``.
     - Increase when focused, study, and light-work slots should be kept more strictly separated. Decrease when the scheduler should be more flexible about slot type.
   * - ``kind_mismatch_score``
     - ``1``
     - Score points
     - Integer ``>= 0``
     - Added when a task's ``work_kind`` does not match the slot's ``work_kind``.
     - Raise when mismatched work is acceptable and avoiding unscheduled tasks matters more than semantic fit. Lower toward ``0`` when mismatches should be a last resort.
   * - ``priority_score_base``
     - ``6``
     - Score points
     - Integer ``>= 1``
     - Computes the priority component as ``max(1, priority_score_base - task.priority)``. Lower numeric task priority receives more score.
     - Increase when high-priority tasks should dominate kind/deadline preferences. Decrease when priority should be a weak tie-breaker.
   * - ``deadline_soon_days``
     - ``2``
     - Days
     - Integer ``>= 0``
     - Defines the due-date window that receives deadline score. A task due today through this many days ahead receives extra score.
     - Increase when the plan should pull upcoming deadlines forward earlier. Decrease when only same-day or near-immediate deadlines should affect scheduling.
   * - ``deadline_score``
     - ``4``
     - Score points per urgency step
     - Integer ``>= 0``
     - Added for tasks due within ``deadline_soon_days``. The score grows as the due date gets closer.
     - Increase when deadlines should outweigh work-kind fit or project continuity. Set to ``0`` when due dates should not affect the score.
   * - ``overdue_score``
     - ``20``
     - Score points
     - Integer ``>= 0``
     - Added once when ``due_at`` is before the schedule date.
     - Increase when overdue tasks should jump ahead of most other work. Lower when overdue tasks should still compete normally with priority and slot fit.
   * - ``fixed_assignment_score``
     - ``100``
     - Score points
     - Integer ``>= 0``
     - Added to score breakdowns for fixed assignments that are accepted.
     - Increase when reports should clearly show fixed placements as dominant choices. Lower when comparing fixed and non-fixed score totals should stay visually closer.
   * - ``dependency_unlock_score``
     - ``3``
     - Score points per unlocked dependent task
     - Integer ``>= 0``
     - Added for each downstream task that becomes unblocked when the current task is scheduled.
     - Increase when prerequisite tasks should be scheduled earlier to unlock follow-up work. Lower when dependency unlocking should not outweigh priority or deadline pressure.
   * - ``min_block_minutes``
     - ``15``
     - Minutes
     - Integer ``> 0``
     - Smallest scheduler-generated block unless the task has less remaining work. Task-level ``min_chunk_minutes`` overrides this value.
     - Raise when tiny task fragments are not useful. Lower when short leftover gaps should be usable.
   * - ``block_granularity_minutes``
     - ``15``
     - Minutes
     - Integer ``> 0``
     - Step size used when generating candidate block durations between the minimum and maximum.
     - Lower for finer packing choices. Raise to reduce candidate count and make block lengths more regular.
   * - ``max_candidate_block_minutes``
     - ``180``
     - Minutes
     - Integer ``>= min_block_minutes``
     - Largest duration considered for one greedy placement. Long tasks can still receive multiple blocks as the solver advances through the day.
     - Lower when one placement should not dominate a slot. Raise when larger uninterrupted sessions should be considered.
   * - ``project_switch_penalty``
     - ``4``
     - Score points
     - Integer ``>= 0``
     - Subtracted when a task starts after a previous task from a different ``project_id`` without a reset gap.
     - Increase to encourage batching by project and reduce context switching. Lower when mixing projects across the day is acceptable.
   * - ``project_switch_reset_gap_minutes``
     - ``30``
     - Minutes
     - Integer ``>= 0``
     - A gap of at least this many minutes clears the project-switch penalty.
     - Increase when only substantial breaks should reset project context. Decrease when short pauses should be enough to switch projects without penalty.
   * - ``long_continuous_threshold_minutes``
     - ``120``
     - Minutes
     - Integer ``>= 0``
     - Maximum continuous work duration before ``long_continuous_penalty`` applies. ``0`` disables this penalty path.
     - Lower when the schedule should insert more variety or shorter work runs. Raise when longer continuous sessions are acceptable.
   * - ``long_continuous_penalty``
     - ``5``
     - Score points
     - Integer ``>= 0``
     - Subtracted when adding a task would exceed ``long_continuous_threshold_minutes``.
     - Increase when long uninterrupted blocks should be discouraged. Set to ``0`` when continuous work length should not affect selection.
   * - ``break_reset_gap_minutes``
     - ``20``
     - Minutes
     - Integer ``>= 0``
     - A gap of at least this many minutes resets the continuous-work counter.
     - Increase when only real breaks should reset fatigue/continuity tracking. Decrease when smaller gaps should break up continuous work.
   * - ``small_gap_minutes``
     - ``15``
     - Minutes
     - Integer ``>= 0``
     - Defines what counts as a small remaining slot gap after placing a task.
     - Increase when the solver should reward using up larger leftover gaps. Decrease when only near-perfect slot fills should receive the gap-fill bonus.
   * - ``small_gap_fill_score``
     - ``2``
     - Score points
     - Integer ``>= 0``
     - Added when placing a task leaves ``0`` through ``small_gap_minutes`` unused minutes in the slot.
     - Increase when compact slot packing matters. Set to ``0`` when gap filling should not influence task choice.

Tuning Guidelines
-----------------

Tune one parameter family at a time and compare the ``score_breakdown`` in
``HumanSolverReport`` before changing another family. The scoring model is
additive, so two small weights can outweigh one large weight when they apply to
the same candidate.

Use these rules of thumb:

* If too many tasks land in the wrong kind of slot, increase
  ``kind_match_score`` or lower ``kind_mismatch_score``.
* If urgent work is being delayed, increase ``deadline_score`` or
  ``overdue_score``. If future deadlines are pulled too early, reduce
  ``deadline_soon_days``.
* If prerequisite work is delayed, increase ``dependency_unlock_score``.
* If long backlog tasks consume too much of the day, lower
  ``max_candidate_block_minutes`` or increase ``long_continuous_penalty``.
* If task fragments are too small or too irregular, raise
  ``min_block_minutes`` or ``block_granularity_minutes``.
* If the plan jumps between projects too often, increase
  ``project_switch_penalty`` or ``project_switch_reset_gap_minutes``.
* If the plan creates long uninterrupted work runs, lower
  ``long_continuous_threshold_minutes`` or increase
  ``long_continuous_penalty``.
* If slots are left with unusable fragments of time, increase
  ``small_gap_fill_score`` or ``small_gap_minutes``.

Standalone Tuning WebUI
-----------------------

Use the local WebUI when you want to tune several parameters against the sample
fixtures without repeatedly editing YAML by hand:

.. code-block:: console

   uv run python examples/human_tuning_webui.py

The command serves ``samples/human/*.yaml`` on ``http://127.0.0.1:8765`` by
default. The UI lets you choose a fixture and solver, adjust every
``HumanDailySolverConfig`` field, rerun the solver, inspect the timeline,
unscheduled tasks, violations, and score breakdown, then copy or download the
current ``solver_config`` YAML. Parameters are grouped behind three visibility
levels: ``Essential`` for the first weights to try, ``Tuning`` for behavior
refinement, and ``Expert`` for lower-level thresholds and report-oriented
weights.

Pass explicit fixture paths to expose a narrower review set:

.. code-block:: console

   uv run python examples/human_tuning_webui.py samples/human/daily_flexible_*.yaml

Example YAML
------------

``solver_config`` can be supplied in a Human daily fixture:

.. code-block:: yaml

   solver_config:
     kind_match_score: 8
     kind_mismatch_score: 1
     priority_score_base: 6
     deadline_soon_days: 2
     deadline_score: 4
     overdue_score: 20
     fixed_assignment_score: 100
     dependency_unlock_score: 5
     min_block_minutes: 15
     block_granularity_minutes: 15
     max_candidate_block_minutes: 180
     project_switch_penalty: 6
     project_switch_reset_gap_minutes: 45
     long_continuous_threshold_minutes: 90
     long_continuous_penalty: 7
     break_reset_gap_minutes: 20
     small_gap_minutes: 15
     small_gap_fill_score: 3
