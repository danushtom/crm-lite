"""Qdrant-backed knowledge base for voice agents.

READ THIS BEFORE CHANGING ANYTHING HERE.

Every other tenant boundary in this product is enforced by Postgres row-level security: even if
application code forgets a filter, the database still refuses to return another organization's
rows. **Qdrant has no such backstop.** A payload filter is the only thing separating one tenant's
pricing sheets from another's, and a missing filter fails silently and completely -- it returns
results, just the wrong organization's.

So this module gives that filter the same treatment ``app/services/voice_tools.py`` gives
LLM-supplied arguments: ``organization_id`` is a *required keyword-only* parameter on every read
and every delete, and it is applied as a ``must`` condition inside this module rather than by the
caller. There is deliberately no function here that can be called without naming a tenant, and no
"search everything" escape hatch to reach for later.

The other half of that discipline: the ``voice_agent_id`` passed to :func:`search` must come from
the resolved ``calls`` row, never from the model's tool-call arguments -- see the trust-boundary
note in ``voice_tools.py`` for why the two are not the same thing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from .config import ai_settings
from .errors import AiNotConfiguredError, AiUpstreamError

logger = logging.getLogger(__name__)

#: Namespace for deterministic point ids. A re-index of the same document overwrites its own
#: points instead of duplicating them, so the operation is idempotent and a retry is harmless.
_POINT_NAMESPACE = uuid.UUID("6f3a1c52-8d2b-4f1e-9a77-2c4b8d5e1f30")

_client: AsyncQdrantClient | None = None


@dataclass(slots=True)
class KbChunk:
    """One retrieved chunk, with enough provenance to cite it back to the user."""

    text: str
    score: float
    document_id: str
    filename: str
    chunk_index: int


def get_qdrant_client() -> AsyncQdrantClient:
    """Shared client. A module-level factory so tests can replace it, matching ``client.py``."""
    global _client
    if not ai_settings.qdrant_url:
        raise AiNotConfiguredError("QDRANT_URL is not configured")
    if _client is None:
        _client = AsyncQdrantClient(
            url=ai_settings.qdrant_url,
            api_key=ai_settings.qdrant_api_key or None,
            timeout=int(ai_settings.qdrant_timeout_seconds),
        )
    return _client


def reset_qdrant_client() -> None:
    """Drop the cached client. For tests, and for a config reload."""
    global _client
    _client = None


def point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{document_id}:{chunk_index}"))


def _tenant_filter(
    *, organization_id: str, voice_agent_id: str | None = None, document_id: str | None = None
) -> models.Filter:
    """Build the ``must`` conditions -- the single place a filter is constructed in this module.

    ``organization_id`` is not optional and is not defaulted. If you find yourself wanting to make
    it so, re-read the module docstring.
    """
    if not organization_id:
        raise ValueError("organization_id is required: it is the tenant boundary, not a hint")

    conditions: list[models.Condition] = [
        models.FieldCondition(
            key="organization_id", match=models.MatchValue(value=organization_id)
        )
    ]
    if voice_agent_id:
        conditions.append(
            models.FieldCondition(
                key="voice_agent_id", match=models.MatchValue(value=voice_agent_id)
            )
        )
    if document_id:
        conditions.append(
            models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
        )
    return models.Filter(must=conditions)


async def ensure_collection() -> None:
    """Create the collection and its payload indexes if they do not exist.

    The ``organization_id`` payload index is not a nicety: without it Qdrant filters by scanning,
    and the tenant filter -- which sits on the hot path of a live phone call -- gets slower as
    other tenants add documents.
    """
    client = get_qdrant_client()
    name = ai_settings.qdrant_collection
    try:
        if not await client.collection_exists(name):
            await client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=ai_settings.openai_embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created name=%s", name)

        for field in ("organization_id", "voice_agent_id", "document_id"):
            await client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
    except Exception as exc:
        raise AiUpstreamError(f"Could not prepare the Qdrant collection: {exc}") from exc


async def upsert_document_chunks(
    *,
    organization_id: str,
    voice_agent_id: str,
    document_id: str,
    filename: str,
    chunks: list[str],
    vectors: list[list[float]],
) -> int:
    """Replace this document's chunks with the ones given. Returns the number of points written.

    Existing points for the document are removed first, so re-indexing a shortened document does
    not leave the tail of the previous version searchable.
    """
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must be the same length")

    await ensure_collection()
    await delete_document(organization_id=organization_id, document_id=document_id)

    if not chunks:
        return 0

    points = [
        models.PointStruct(
            id=point_id(document_id, index),
            vector=vector,
            payload={
                "organization_id": organization_id,
                "voice_agent_id": voice_agent_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_index": index,
                "text": chunk,
            },
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    client = get_qdrant_client()
    try:
        await client.upsert(
            collection_name=ai_settings.qdrant_collection, points=points, wait=True
        )
    except Exception as exc:
        raise AiUpstreamError(f"Could not write to the knowledge base: {exc}") from exc

    logger.info(
        "kb_document_indexed org_id=%s document_id=%s chunks=%d",
        organization_id,
        document_id,
        len(points),
    )
    return len(points)


async def search(
    *,
    organization_id: str,
    voice_agent_id: str,
    query_vector: list[float],
    limit: int = 5,
    score_threshold: float = 0.25,
) -> list[KbChunk]:
    """Retrieve the most relevant chunks for one agent, within one organization.

    Both scoping arguments are required and keyword-only by design -- see the module docstring.
    """
    await ensure_collection()
    client = get_qdrant_client()
    try:
        response = await client.query_points(
            collection_name=ai_settings.qdrant_collection,
            query=query_vector,
            query_filter=_tenant_filter(
                organization_id=organization_id, voice_agent_id=voice_agent_id
            ),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
    except Exception as exc:
        raise AiUpstreamError(f"Could not search the knowledge base: {exc}") from exc

    results: list[KbChunk] = []
    for point in response.points:
        payload: dict[str, Any] = point.payload or {}
        # Belt and braces: the filter above is the boundary, but a payload coming back with the
        # wrong tenant would mean that filter had silently failed, and that must never be served.
        if payload.get("organization_id") != organization_id:
            logger.error(
                "kb_tenant_mismatch expected=%s got=%s point=%s",
                organization_id,
                payload.get("organization_id"),
                point.id,
            )
            continue
        results.append(
            KbChunk(
                text=str(payload.get("text") or ""),
                score=float(point.score or 0.0),
                document_id=str(payload.get("document_id") or ""),
                filename=str(payload.get("filename") or ""),
                chunk_index=int(payload.get("chunk_index") or 0),
            )
        )
    return results


async def delete_document(*, organization_id: str, document_id: str) -> None:
    """Remove every chunk of one document.

    Scoped by organization so a crafted or stale ``document_id`` cannot delete another tenant's
    points.
    """
    client = get_qdrant_client()
    try:
        await client.delete(
            collection_name=ai_settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=_tenant_filter(organization_id=organization_id, document_id=document_id)
            ),
            wait=True,
        )
    except Exception as exc:
        raise AiUpstreamError(
            f"Could not remove the document from the knowledge base: {exc}"
        ) from exc


async def delete_agent_documents(*, organization_id: str, voice_agent_id: str) -> None:
    """Remove every chunk belonging to one agent.

    Called when the agent is deleted, so the vector store does not outlive Postgres.
    """
    client = get_qdrant_client()
    try:
        await client.delete(
            collection_name=ai_settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=_tenant_filter(
                    organization_id=organization_id, voice_agent_id=voice_agent_id
                )
            ),
            wait=True,
        )
    except Exception as exc:
        raise AiUpstreamError(f"Could not clear the agent's knowledge base: {exc}") from exc
