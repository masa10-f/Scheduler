Quickstart
==========

Installation
------------

Install the package from PyPI after the first release:

.. code-block:: console

   uv add humancompiler-scheduler

Or install the package from the repository root:

.. code-block:: console

   uv pip install -e .

Install the optional CP-SAT solver support when you want to use OR-Tools:

.. code-block:: console

   uv pip install -e ".[cp-sat]"

Build these docs with the documentation extra:

.. code-block:: console

   uv run --extra docs sphinx-build -b html docs docs/_build/html

Generic Scheduling
------------------

The generic API models tasks, resources, precedences, and assignments in
discrete time slots.

.. code-block:: python

   from humancompiler_scheduler import Problem, Resource, Task, solve_greedy

   problem = Problem(
       tasks={
           "write": Task(id="write", duration=2, earliest_start=0),
           "review": Task(id="review", duration=1, earliest_start=0),
       },
       resources={
           "person": Resource(id="person", capacity=1, availability=[(0, 8)]),
       },
       time_horizon=8,
   )

   result = solve_greedy(problem)
   print(result.status)
   print(result.schedule.assignments)

YAML Input
----------

Use ``load_problem_yaml`` to load a scheduling problem from YAML:

.. code-block:: python

   from humancompiler_scheduler import load_problem_yaml, solve_greedy

   problem = load_problem_yaml("samples/sample.yaml")
   result = solve_greedy(problem)

Human Daily Scheduling
----------------------

The ``humancompiler_scheduler.human`` namespace is experimental. It keeps HumanCompiler daily
scheduling concepts separate from the generic solver API.

.. code-block:: python

   from humancompiler_scheduler.human import (
       format_human_daily_compact,
       load_human_daily_fixture,
       plan_daily_schedule,
   )

   fixture = load_human_daily_fixture("samples/human/daily_basic.yaml")
   report = plan_daily_schedule(fixture)
   print(report.plan.status)
   print(format_human_daily_compact(fixture, report))
