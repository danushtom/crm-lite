"""Supabase (PostgREST / Auth / Storage) access layer.

Two things this module exists to guarantee:

1. **Connection reuse.** A single :class:`httpx.AsyncClient` is created at application startup
   and shared by every request. The previous implementation opened a fresh client -- and
   therefore a fresh TLS handshake and connection pool -- for every upstream call.
2. **Uniform error translation.** PostgREST error payloads are mapped onto the API's
   :mod:`app.core.errors` hierarchy, so a unique-violation surfaces as 409 rather than a
   pass-through 400, and no upstream body ever leaks verbatim to the client.

Two credentials are modelled explicitly:

* :class:`SupabaseClient` -- acts *as the calling user*; every query is subject to RLS.
* :class:`SupabaseAdminClient` -- service role; **bypasses RLS**. Use only where a privileged
  operation is genuinely required, and never with user-supplied filters.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableError,
    UpstreamError,
)

logger = logging.getLogger(__name__)

Method = Literal["GET", "POST", "PATCH", "PUT", "DELETE"]

# PostgreSQL SQLSTATE codes PostgREST forwards in its error payloads.
_PG_UNIQUE_VIOLATION = "23505"
_PG_FOREIGN_KEY_VIOLATION = "23503"
_PG_NOT_NULL_VIOLATION = "23502"
_PG_CHECK_VIOLATION = "23514"
_PG_INVALID_TEXT_REPRESENTATION = "22P02"
_PG_RLS_VIOLATION = "42501"

_shared_client: httpx.AsyncClient | None = None


async def open_http_client() -> httpx.AsyncClient:
    """Create the process-wide HTTP client. Called once from the app lifespan."""
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_seconds, connect=10.0),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
            headers={"User-Agent": "dracara-growth-os-api"},
        )
    return _shared_client


async def close_http_client() -> None:
    """Dispose of the shared client. Called once from the app lifespan."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


def get_http_client() -> httpx.AsyncClient:
    if _shared_client is None:
        raise ServiceUnavailableError("HTTP client is not initialised")
    return _shared_client


@dataclass(slots=True)
class Result:
    """A PostgREST response: rows plus the exact count when one was requested."""

    data: Any
    count: int | None = None

    @property
    def rows(self) -> list[dict[str, Any]]:
        if isinstance(self.data, list):
            return self.data
        if self.data is None:
            return []
        return [self.data]

    def first(self) -> dict[str, Any] | None:
        rows = self.rows
        return rows[0] if rows else None

    def one(self, what: str = "Resource") -> dict[str, Any]:
        row = self.first()
        if row is None:
            raise NotFoundError(f"{what} not found")
        return row


def _parse_content_range(header: str | None) -> int | None:
    """``items 0-24/231`` -> ``231``. Returns None when the count is unknown (``*``)."""
    if not header or "/" not in header:
        return None
    total = header.rsplit("/", 1)[1].strip()
    if not total or total == "*":
        return None
    try:
        return int(total)
    except ValueError:
        return None


def _translate_error(status_code: int, payload: Any, path: str) -> Exception:
    """Map a PostgREST failure onto the API's error hierarchy."""
    code = ""
    message = ""
    if isinstance(payload, dict):
        code = str(payload.get("code") or "")
        message = str(payload.get("message") or payload.get("hint") or "")

    if code == _PG_UNIQUE_VIOLATION:
        return ConflictError(message or "Resource already exists")
    if code == _PG_FOREIGN_KEY_VIOLATION:
        return ConflictError(message or "Referenced record is still in use")
    if code in (_PG_NOT_NULL_VIOLATION, _PG_CHECK_VIOLATION, _PG_INVALID_TEXT_REPRESENTATION):
        return UnprocessableError(message or "Request violates a database constraint")
    if code == _PG_RLS_VIOLATION or status_code in (401, 403):
        return ForbiddenError("You do not have access to this resource")
    if status_code == 404:
        return NotFoundError("Resource not found")
    if status_code == 409:
        return ConflictError(message or "Conflict")
    if status_code in (400, 422):
        return UnprocessableError(message or "Upstream rejected the request")

    # Anything else is a genuine upstream fault: log the detail, return a generic message.
    logger.error(
        "supabase_error status=%s path=%s code=%s message=%s",
        status_code,
        path,
        code or "-",
        message or payload,
    )
    return UpstreamError("The data service returned an unexpected error")


class SupabaseClient:
    """PostgREST client scoped to a caller's credentials (RLS applies)."""

    __slots__ = ("_headers", "_base")

    def __init__(self, access_token: str, *, apikey: str | None = None) -> None:
        self._base = settings.rest_base_url
        self._headers = {
            "apikey": apikey or settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def request(
        self,
        method: Method,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str | None = None,
        count: bool = False,
    ) -> Result:
        headers = dict(self._headers)
        prefer_parts = [prefer] if prefer else ["return=representation"]
        if count:
            prefer_parts.append("count=exact")
        headers["Prefer"] = ",".join(prefer_parts)

        client = get_http_client()
        try:
            response = await client.request(
                method,
                f"{self._base}{path}",
                params=params,
                content=json.dumps(json_body) if json_body is not None else None,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            logger.warning("supabase_timeout path=%s", path)
            raise ServiceUnavailableError("The data service timed out") from exc
        except httpx.HTTPError as exc:
            logger.warning("supabase_transport_error path=%s error=%s", path, exc)
            raise ServiceUnavailableError("The data service is unreachable") from exc

        if response.status_code >= 400:
            payload: Any = response.text
            try:
                payload = response.json()
            except (json.JSONDecodeError, ValueError):
                pass
            raise _translate_error(response.status_code, payload, path)

        total = _parse_content_range(response.headers.get("content-range")) if count else None

        if response.status_code == 204 or not response.content:
            return Result(data=None, count=total)
        if "application/json" in response.headers.get("content-type", ""):
            return Result(data=response.json(), count=total)
        return Result(data=response.text, count=total)

    # -- Convenience wrappers ------------------------------------------------

    async def select(
        self,
        table: str,
        *,
        params: dict[str, str] | None = None,
        count: bool = False,
    ) -> Result:
        return await self.request("GET", f"/{table}", params=params, count=count)

    async def select_one(
        self,
        table: str,
        *,
        params: dict[str, str] | None = None,
        what: str | None = None,
    ) -> dict[str, Any]:
        result = await self.request("GET", f"/{table}", params={**(params or {}), "limit": "1"})
        return result.one(what or table.rstrip("s").replace("_", " ").capitalize())

    async def insert(self, table: str, payload: Any) -> Result:
        return await self.request("POST", f"/{table}", json_body=payload)

    async def update(self, table: str, params: dict[str, str], payload: Any) -> Result:
        return await self.request("PATCH", f"/{table}", params=params, json_body=payload)

    async def delete(self, table: str, params: dict[str, str]) -> Result:
        return await self.request("DELETE", f"/{table}", params=params)

    async def rpc(self, function: str, payload: Any = None) -> Result:
        return await self.request("POST", f"/rpc/{function}", json_body=payload or {})


class SupabaseAdminClient(SupabaseClient):
    """Service-role client. **Bypasses RLS** -- use sparingly and never with caller-supplied filters."""

    def __init__(self) -> None:
        key = settings.supabase_service_role_key
        if not key:
            raise ServiceUnavailableError("SUPABASE_SERVICE_ROLE_KEY is not configured")
        super().__init__(key, apikey=key)
