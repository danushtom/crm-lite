"""AI feature services.

The split from ``packages/ai`` is deliberate and worth keeping: ``packages/ai`` holds the model
calls, prompts and graphs and is shared with the worker; this package holds the parts that need a
database, a tenant and a permission check, and belongs to the API alone.
"""
