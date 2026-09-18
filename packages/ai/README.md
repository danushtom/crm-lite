# @dracara/ai (`dracara_ai`)

Every LLM call in Dracara Growth OS goes through this package. It exists for the same reason
`packages/scoring` does: the API (`apps/api`) and the Celery worker (`apps/worker`) both need this
logic, and two copies of a prompt drift apart silently. Both install it from the workspace with
`-e ../../packages/ai`.

## The rule that keeps this package honest

**Graphs are pure.** A graph takes plain data in and returns a Pydantic model out. It holds no
database handle, resolves no `organization_id`, and performs no writes — exactly like
`compute_priority_score` in `packages/scoring`. All database I/O and all tenant scoping stay in the
caller (an API service, or a worker task).

The single exception is `graphs/assistant.py`, which cannot read anything on its own: it is handed
already-bound, already-RLS-scoped reader callables as its tools. It still never sees a DB client.

This matters because the worker runs as service role with no per-request user token. Keeping
tenancy decisions out of this package means a graph has nothing to leak even if a prompt is
manipulated into asking for it.

## Tenancy in the vector store

`vector_store.py` is the one place here that touches a datastore, and Qdrant has no row-level
security. Read its module docstring before changing it — the payload filter *is* the tenant
boundary, and `organization_id` is a required keyword-only argument on every call for that reason.
