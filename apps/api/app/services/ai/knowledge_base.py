"""Indexing voice-agent documents into Qdrant, and searching them back out.

Closes the gap `tdd.md` §23.4 recorded: uploads worked, but nothing ever read the uploaded file,
so an admin could attach a pricing sheet and the agent would still know nothing about it.

Two rules shape everything here:

* **Indexing failure never fails an upload.** The file is already stored in Supabase Storage and
  the row is already written; if extraction or embedding fails, that is recorded in
  `index_error` and the worker's reindex pass will try again. Rolling back a successful upload
  because a third-party embedding API had a bad minute would be the wrong trade.
* **Postgres is the record; Qdrant is a derived index.** Deleting a document deletes its points,
  and the vector store is rebuildable from Storage at any time. Nothing is only in Qdrant.

The stamping writes use the admin client: `voice_agent_documents` deliberately has no UPDATE
policy for `authenticated` (see the migration), because these columns are system state, not
something a user edits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from dracara_ai import chunking, embeddings, vector_store
from dracara_ai.config import ai_settings
from dracara_ai.errors import AiError
from dracara_ai.extract import extract_text, is_supported
from dracara_ai.usage import UsageRecord

from app.db.supabase import SupabaseAdminClient

logger = logging.getLogger(__name__)

#: Refuse to index absurdly large documents rather than spending a fortune embedding a book. The
#: upload itself is already capped by MAX_UPLOAD_BYTES; this is a second, semantic cap.
MAX_EXTRACTED_CHARS = 400_000


async def index_document(
    admin_db: SupabaseAdminClient,
    *,
    organization_id: str,
    voice_agent_id: str,
    document_id: str,
    filename: str,
    data: bytes,
) -> tuple[int, UsageRecord]:
    """Extract, chunk, embed and store one document. Returns (chunks written, usage).

    Records the outcome on the row either way -- a successful index stamps `indexed_at`, a failed
    one stamps `index_error` and leaves `indexed_at` NULL so the worker retries it.
    """
    usage = UsageRecord(feature="kb_index", model=ai_settings.openai_embedding_model)

    try:
        if not is_supported(filename):
            raise AiError(
                f"{filename} cannot be indexed. Supported types: PDF, Word, text, Markdown, CSV."
            )

        text = extract_text(data, filename)
        if len(text) > MAX_EXTRACTED_CHARS:
            logger.info(
                "kb_document_truncated document_id=%s chars=%d", document_id, len(text)
            )
            text = text[:MAX_EXTRACTED_CHARS]

        chunks = chunking.chunk_text(text)
        if not chunks:
            raise AiError(
                "No readable text was found in this file. A scanned PDF needs OCR before it "
                "can be indexed."
            )

        vectors = await embeddings.embed_texts(chunks, usage=usage)
        written = await vector_store.upsert_document_chunks(
            organization_id=organization_id,
            voice_agent_id=voice_agent_id,
            document_id=document_id,
            filename=filename,
            chunks=chunks,
            vectors=vectors,
        )

        await _stamp(
            admin_db,
            document_id,
            {
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "chunk_count": written,
                "extracted_chars": len(text),
                "index_error": None,
            },
            organization_id=organization_id,
        )
        return written, usage

    except Exception as exc:
        logger.warning(
            "kb_index_failed document_id=%s filename=%s error=%s", document_id, filename, exc
        )
        await _stamp(
            admin_db,
            document_id,
            {"index_error": str(exc)[:500], "indexed_at": None, "chunk_count": 0},
            organization_id=organization_id,
        )
        raise


async def _stamp(
    admin_db: SupabaseAdminClient,
    document_id: str,
    changes: dict[str, Any],
    *,
    organization_id: str,
) -> None:
    """Record indexing state. Best-effort: losing the stamp must not lose the upload.

    The organization clause is defence in depth rather than a load-bearing check -- the
    document id always comes from a row this request just inserted through the caller's own
    RLS-scoped client. But this is a service-role write, which bypasses RLS entirely, and an
    unscoped admin UPDATE keyed on an id is the shape that goes wrong later when someone reuses
    the helper from somewhere the id is less trustworthy.
    """
    try:
        await admin_db.update(
            "voice_agent_documents",
            {"id": f"eq.{document_id}", "organization_id": f"eq.{organization_id}"},
            changes,
        )
    except Exception:
        logger.exception("kb_stamp_failed document_id=%s", document_id)


async def remove_document(*, organization_id: str, document_id: str) -> None:
    """Drop a document's points. Best-effort: a failure here must not block the row's deletion,
    or a user would be unable to delete a document whenever Qdrant was down. The orphaned points
    are unreachable anyway -- nothing references them once the row is gone -- and the worker's
    reconciliation would clear them."""
    try:
        await vector_store.delete_document(
            organization_id=organization_id, document_id=document_id
        )
    except Exception:
        logger.exception(
            "kb_delete_failed org_id=%s document_id=%s", organization_id, document_id
        )


async def remove_agent(*, organization_id: str, voice_agent_id: str) -> None:
    """Drop every point belonging to an agent, when the agent itself is deleted."""
    try:
        await vector_store.delete_agent_documents(
            organization_id=organization_id, voice_agent_id=voice_agent_id
        )
    except Exception:
        logger.exception(
            "kb_agent_delete_failed org_id=%s voice_agent_id=%s", organization_id, voice_agent_id
        )


async def search(
    *, organization_id: str, voice_agent_id: str, query: str, limit: int = 4
) -> list[dict[str, Any]]:
    """Retrieve knowledge-base passages for one agent.

    Both scoping arguments are required by `vector_store.search` and neither may originate from a
    model's tool-call arguments -- see the trust-boundary note in `app/services/voice_tools.py`.
    """
    usage = UsageRecord(feature="kb_search", model=ai_settings.openai_embedding_model)
    vector = await embeddings.embed_query(query, usage=usage)
    chunks = await vector_store.search(
        organization_id=organization_id,
        voice_agent_id=voice_agent_id,
        query_vector=vector,
        limit=limit,
    )
    return [
        {"text": c.text, "source": c.filename, "relevance": round(c.score, 3)} for c in chunks
    ]
