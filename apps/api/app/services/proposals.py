"""Proposal versioning and file upload.

Version numbers are allocated by reading the current maximum and adding one, which races when
two clients submit concurrently. ``proposals`` has a ``UNIQUE (opportunity_id, version)``
constraint, so the loser of that race gets a unique violation rather than a duplicate version;
:func:`create_version` retries on that specific conflict instead of surfacing a 409.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ConflictError, NotConfiguredError, PayloadTooLargeError, UpstreamError
from app.db.supabase import SupabaseClient, get_http_client

logger = logging.getLogger(__name__)

MAX_VERSION_ATTEMPTS = 5


async def next_version(db: SupabaseClient, opportunity_id: str) -> int:
    result = await db.select(
        "proposals",
        params={
            "select": "version",
            "opportunity_id": f"eq.{opportunity_id}",
            "order": "version.desc",
            "limit": "1",
        },
    )
    latest = result.first()
    return int(latest["version"]) + 1 if latest else 1


async def create_version(
    db: SupabaseClient,
    opportunity_id: str,
    payload: dict[str, Any],
    created_by: str,
) -> dict[str, Any]:
    """Insert the next proposal version, retrying if another writer claimed the number first."""
    last_error: Exception | None = None
    for attempt in range(MAX_VERSION_ATTEMPTS):
        version = await next_version(db, opportunity_id)
        body = {
            **payload,
            "opportunity_id": opportunity_id,
            "version": version,
            "created_by": created_by,
        }
        try:
            result = await db.insert("proposals", body)
            return result.one("Proposal")
        except ConflictError as exc:
            last_error = exc
            logger.info(
                "proposal version %s taken for opportunity %s, retrying (attempt %s)",
                version,
                opportunity_id,
                attempt + 1,
            )
    raise ConflictError(
        "Could not allocate a proposal version; too many concurrent submissions"
    ) from last_error


async def upload_file(
    *,
    opportunity_id: str,
    version: int,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> str:
    """Upload a proposal document to Supabase Storage and return its public URL."""
    if not settings.supabase_service_role_key:
        raise NotConfiguredError("SUPABASE_SERVICE_ROLE_KEY is required for proposal uploads")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise PayloadTooLargeError(f"File exceeds the {limit_mb}MB upload limit")

    safe_name = (filename or "proposal").replace("/", "_").replace("\\", "_")[:200]
    object_path = f"{opportunity_id}/v{version}_{uuid.uuid4().hex[:8]}_{safe_name}"
    bucket = settings.proposals_bucket

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
