"""Proposal versioning and file upload.

Version numbers are allocated by reading the current maximum and adding one, which races when
two clients submit concurrently. ``proposals`` has a ``UNIQUE (opportunity_id, version)``
constraint, so the loser of that race gets a unique violation rather than a duplicate version;
:func:`create_version` retries on that specific conflict instead of surfacing a 409.
"""

from __future__ import annotations

import logging
from typing import Any


from app.core.config import settings
from app.core.errors import ConflictError
from app.db.supabase import SupabaseClient
from app.services import storage

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
    """Store a proposal document and return its object path.

    A path, not a URL: the bucket is private, so a readable link is signed per response and
    expires. See app.services.storage for why.
    """
    path = storage.object_path(
        f"{opportunity_id}/v{version}", filename, fallback="proposal"
    )
    return await storage.upload(
        bucket=settings.proposals_bucket, path=path, data=data, content_type=content_type
    )
