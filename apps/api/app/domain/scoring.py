"""Weighted opportunity score (tdd.md 12.2).

The implementation lives in the workspace package ``dracara-scoring`` so the API and the
Celery worker share one copy. They previously held separate files that had already drifted,
which meant the same lead could score differently depending on which process last touched it.

Imported here rather than referenced directly throughout the app so the rest of the codebase
keeps depending on ``app.domain``.
"""

from dracara_scoring import (
    clamp01,
    compute_priority_score,
    dimension_authority,
    dimension_budget_fit,
    dimension_probability,
    dimension_project_size,
    dimension_urgency,
)

__all__ = [
    "clamp01",
    "compute_priority_score",
    "dimension_authority",
    "dimension_budget_fit",
    "dimension_probability",
    "dimension_project_size",
    "dimension_urgency",
]
