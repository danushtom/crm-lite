"""Shared AI layer for Dracara Growth OS.

Installed from the workspace into both ``apps/api`` and ``apps/worker`` so the two never run two
copies of a prompt that can drift -- the same reason ``packages/scoring`` exists for the
opportunity-scoring formula.

See ``packages/ai/README.md`` for the rule that keeps this package safe to share: graphs are pure,
and tenancy lives in the caller.
"""

from .config import ai_settings, get_ai_settings
from .errors import AiBudgetExceededError, AiError, AiNotConfiguredError, AiUpstreamError
from .usage import UsageRecord, estimate_cost_usd

__all__ = [
    "ai_settings",
    "get_ai_settings",
    "AiError",
    "AiNotConfiguredError",
    "AiUpstreamError",
    "AiBudgetExceededError",
    "UsageRecord",
    "estimate_cost_usd",
]
