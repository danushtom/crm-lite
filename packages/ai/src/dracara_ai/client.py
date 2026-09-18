"""The OpenAI client, built once per process.

``get_openai_client`` is a module-level factory rather than an inline constructor specifically so
tests can monkeypatch it with a fake -- the same pattern the voice-platform adapter uses for its
HTTP client (see ``apps/api/tests/test_voice_platform.py``, which replaces
``get_http_client``). Nothing in this package constructs ``AsyncOpenAI`` directly.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from .config import ai_settings
from .errors import AiNotConfiguredError, AiUpstreamError

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return the shared client, creating it on first use.

    Raises :class:`AiNotConfiguredError` when the feature is switched off or no key is present, so
    callers get one predictable failure instead of an SDK error from somewhere deep in a graph.
    """
    global _client
    if not ai_settings.is_configured:
        raise AiNotConfiguredError(
            "AI features require AI_ENABLED=true and OPENAI_API_KEY to be set"
        )
    if _client is None:
        kwargs: dict[str, Any] = {
            "api_key": ai_settings.openai_api_key,
            "timeout": ai_settings.openai_timeout_seconds,
            "max_retries": ai_settings.openai_max_retries,
        }
        if ai_settings.openai_api_base:
            kwargs["base_url"] = ai_settings.openai_api_base
        _client = AsyncOpenAI(**kwargs)
    return _client


def reset_openai_client() -> None:
    """Drop the cached client. For tests, and for a config reload."""
    global _client
    _client = None


async def complete_json(
    *,
    model: str,
    system: str,
    user: str,
    schema_model: type,
    temperature: float = 0.2,
) -> tuple[Any, Any]:
    """One structured completion: returns ``(parsed_model_instance, usage)``.

    Uses the SDK's schema-parsing helper so the model's reply is validated against
    ``schema_model`` before it reaches a caller -- a graph node should never hand a half-parsed
    dict onward. ``usage`` is the raw usage object; wrap it with
    :func:`dracara_ai.usage.record_from_usage` to persist it.
    """
    client = get_openai_client()
    try:
        response = await client.beta.chat.completions.parse(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=schema_model,
        )
    except (APITimeoutError, RateLimitError) as exc:
        raise AiUpstreamError(f"The model provider is unavailable: {exc.__class__.__name__}") from exc
    except APIError as exc:
        logger.error("openai_api_error model=%s status=%s", model, getattr(exc, "status_code", None))
        raise AiUpstreamError("The model provider rejected the request") from exc

    choice = response.choices[0]
    if choice.message.refusal:
        raise AiUpstreamError(f"The model declined the request: {choice.message.refusal}")
    return choice.message.parsed, response.usage
