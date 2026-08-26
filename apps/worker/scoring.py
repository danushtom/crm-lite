"""Weighted opportunity score -- re-exported from the shared workspace package.

This file used to be a hand-maintained copy of the API's implementation, and the two had
already drifted. It now forwards to ``dracara-scoring`` so there is exactly one.
"""

from dracara_scoring import clamp01, compute_priority_score

__all__ = ["clamp01", "compute_priority_score"]
