"""Voice agent knowledge-base document upload. Mirrors app.services.proposals.upload_file."""

from __future__ import annotations

import logging
import uuid

import httpx

from app.core.config import settings
from app.core.errors import NotConfiguredError, PayloadTooLargeError, UpstreamError
from app.db.supabase import get_http_client

logger = logging.getLogger(__name__)


async def upload_document(
    *,
    voice_agent_id: str,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> str:
    """Upload a knowledge-base document to Supabase Storage and return its public URL."""
    if not settings.supabase_service_role_key:
        raise NotConfiguredError("SUPABASE_SERVICE_ROLE_KEY is required for document uploads")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise PayloadTooLargeError(f"File exceeds the {limit_mb}MB upload limit")

    safe_name = (filename or "document").replace("/", "_").replace("\\", "_")[:200]
    object_path = f"{voice_agent_id}/{uuid.uuid4().hex[:8]}_{safe_name}"
    bucket = settings.voice_kb_bucket

    client = get_http_client()
    try:
        response = await client.post(
            f"{settings.storage_base_url}/object/{bucket}/{object_path}",
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": content_type or "application/octet-stream",
            },
            content=data,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Storage upload failed") from exc

    if response.status_code >= 400:
        logger.error("storage_upload_failed status=%s body=%s", response.status_code, response.text)
        raise UpstreamError("Storage rejected the upload")

    return f"{settings.storage_base_url}/object/public/{bucket}/{object_path}"
