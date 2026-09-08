"""Voice agent knowledge-base document upload. Mirrors app.services.proposals.upload_file."""

from __future__ import annotations

from app.core.config import settings
from app.services import storage


async def upload_document(
    *,
    voice_agent_id: str,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> str:
    """Store a knowledge-base document and return its object path.

    A path, not a URL: the bucket is private, so a readable link is signed per response and
    expires. These files hold pricing sheets and internal call scripts, which is exactly the
    material that should not sit behind a permanent public link.
    """
    path = storage.object_path(voice_agent_id, filename, fallback="document")
    return await storage.upload(
        bucket=settings.voice_kb_bucket, path=path, data=data, content_type=content_type
    )
