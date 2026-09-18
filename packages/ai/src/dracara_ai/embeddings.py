"""Embedding text for the knowledge base."""

from __future__ import annotations

import logging

from openai import APIError, APITimeoutError, RateLimitError

from .client import get_openai_client
from .config import ai_settings
from .errors import AiUpstreamError
from .usage import UsageRecord

logger = logging.getLogger(__name__)

#: The provider caps inputs per request; batching also keeps one oversized document from
#: producing a single request large enough to time out.
EMBED_BATCH_SIZE = 64


async def embed_texts(texts: list[str], *, usage: UsageRecord | None = None) -> list[list[float]]:
    """Embed ``texts`` in order. Returns one vector per input."""
    if not texts:
        return []

    client = get_openai_client()
    vectors: list[list[float]] = []

    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        try:
            response = await client.embeddings.create(
                model=ai_settings.openai_embedding_model,
                input=batch,
            )
        except (APITimeoutError, RateLimitError) as exc:
            raise AiUpstreamError(
                f"The embedding provider is unavailable: {exc.__class__.__name__}"
            ) from exc
        except APIError as exc:
            logger.error("openai_embedding_error status=%s", getattr(exc, "status_code", None))
            raise AiUpstreamError("The embedding provider rejected the request") from exc

        # The API documents that `data` comes back in input order, but it also carries an
        # explicit index; sorting on it costs nothing and removes the assumption.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)

        if usage is not None:
            usage.add(response.usage)

    return vectors


async def embed_query(text: str, *, usage: UsageRecord | None = None) -> list[float]:
    """Embed a single search query."""
    vectors = await embed_texts([text], usage=usage)
    if not vectors:
        raise AiUpstreamError("The embedding provider returned no vector for the query")
    return vectors[0]
