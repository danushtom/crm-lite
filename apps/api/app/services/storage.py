"""Supabase Storage: uploads, and short-lived signed URLs for reading them back.

Both buckets hold commercially sensitive material -- proposals carry pricing and contract
terms, and a voice agent's knowledge base carries pricing sheets and internal scripts. They are
private, and what is stored on the row is the *object path*, not a URL. A readable link is
minted per response and expires.

The previous shape returned `/object/public/{bucket}/{path}` and stored that string on the row.
That only works with a public bucket, which makes every document readable by anyone who ever
sees the link -- and a link leaks easily: it sits in the database, goes out over the API to
every member of the organization, lands in browser history, and travels in `Referer` the moment
someone opens it and clicks onward. Unguessable is not the same as private.

Two things are deliberately not left to the caller:

  * `download` is forced on the signed link, so a file that claims to be `text/html` is saved
    rather than rendered. Content-Type comes from the uploading client and cannot be trusted;
    without this, an uploaded HTML file would execute on the Storage origin.
  * Object paths are always prefixed with the owning resource's id and a random segment, so a
    guessed or crafted filename cannot address someone else's object.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.core.config import settings
from app.core.errors import NotConfiguredError, PayloadTooLargeError, UpstreamError
from app.db.supabase import get_http_client

logger = logging.getLogger(__name__)

#: How long a generated link stays valid. Long enough to click and download, short enough that a
#: link pasted into a chat is not a lasting grant.
SIGNED_URL_TTL_SECONDS = 300


def _service_key() -> str:
    key = settings.supabase_service_role_key
    if not key:
        raise NotConfiguredError("SUPABASE_SERVICE_ROLE_KEY is required for file storage")
    return key


def object_path(prefix: str, filename: str, *, fallback: str) -> str:
    """`<owning-resource-id>/<random>_<sanitised name>`.

    The random segment is what stops one upload overwriting another with the same filename, and
    the prefix is what keeps each resource's objects in their own folder.
    """
    safe_name = (filename or fallback).replace("/", "_").replace("\\", "_").lstrip(".")[:200]
    return f"{prefix}/{uuid.uuid4().hex[:8]}_{safe_name or fallback}"


async def upload(*, bucket: str, path: str, data: bytes, content_type: str | None) -> str:
    """Store the bytes and return the object path to persist on the row."""
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise PayloadTooLargeError(f"File exceeds the {limit_mb}MB upload limit")

    client = get_http_client()
    try:
        response = await client.post(
            f"{settings.storage_base_url}/object/{bucket}/{path}",
            headers={
                "Authorization": f"Bearer {_service_key()}",
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

    return path


async def signed_url(*, bucket: str, path: str, filename: str | None = None) -> str | None:
    """A time-limited link to one object, or None if a link cannot be produced.

    Returns None rather than raising: these are minted while shaping a response, and a document
    whose link could not be signed should leave the rest of the payload intact rather than
    failing the whole request.
    """
    if not path:
        return None

    # Tolerate rows written before storage moved to private buckets, which hold a full URL
    # rather than a path. Nothing has been uploaded in this project yet, but a deployment that
    # had would otherwise start handing back unusable links.
    if path.startswith("http://") or path.startswith("https://"):
        return path

    client = get_http_client()
    try:
        response = await client.post(
            f"{settings.storage_base_url}/object/sign/{bucket}/{path}",
            headers={"Authorization": f"Bearer {_service_key()}"},
            json={"expiresIn": SIGNED_URL_TTL_SECONDS},
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
    except httpx.HTTPError:
        logger.warning("storage_sign_failed bucket=%s", bucket)
        return None

    if response.status_code >= 400:
        logger.warning(
            "storage_sign_failed bucket=%s status=%s", bucket, response.status_code
        )
        return None

    signed = response.json().get("signedURL") or response.json().get("signedUrl")
    if not signed:
        return None

    # `download` makes the browser save the file instead of rendering it. The Content-Type on
    # the object came from whoever uploaded it, so an HTML file would otherwise run as a page
    # on the Storage origin.
    separator = "&" if "?" in signed else "?"
    suffix = f"{separator}download="
    suffix += (filename or "").replace("/", "_").replace("\\", "_")[:200]
    return f"{settings.storage_base_url}{signed}{suffix}"
