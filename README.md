# Scheduler
A general purpose scheduling solver

## HumanCompiler experimental API

HumanCompiler-oriented scheduling models live under `scheduler.human`.
This namespace is experimental and exists to keep HumanCompiler domain concepts
separate from the generic `Task` / `Resource` / `Problem` solver API.

Use this layer for adapter-facing concepts such as human tasks, daily time
slots, fixed assignments, and timeline blocks. The models intentionally do not
depend on HumanCompiler database types.
