"""LangGraph workflows.

Each module exposes ``run(...)`` (or ``run_stream(...)``) returning its result plus a
:class:`dracara_ai.usage.UsageRecord`. Graphs are pure -- no database handle, no tenant
resolution. See the package README for why.

Imported lazily by name rather than re-exported here: the API needs the assistant and the proposal
drafter, the worker needs call notes and deal health, and neither should pay to import the other's
dependencies at startup.
"""
