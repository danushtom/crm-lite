"""Errors raised by this package.

Deliberately defined here rather than imported from ``apps/api/app/core/errors.py``: this package
is also installed into the Celery worker, which has no FastAPI dependency and no problem-details
machinery. The API maps these onto its own RFC 9457 responses at the edge (see
``app/api/v1/endpoints/ai.py``); the worker just logs them.
"""

from __future__ import annotations


class AiError(Exception):
    """Base class, so a caller can catch everything this package raises in one clause."""


class AiNotConfiguredError(AiError):
    """No ``OPENAI_API_KEY`` (or no ``QDRANT_URL``) is set.

    A configuration problem, not a runtime failure -- the caller should surface it as "this
    feature is not set up" rather than retrying.
    """


class AiUpstreamError(AiError):
    """The model provider or vector store rejected the request, or could not be reached."""


class AiBudgetExceededError(AiError):
    """This organization has spent past its configured monthly token budget.

    Raised by the caller, not by this package -- it lives here so the API and the worker agree on
    one exception type rather than inventing two.
    """
