"""Idempotent creates via the ``Idempotency-Key`` header.

A POST retried after a timeout used to create a second record: nothing distinguished a retry
from a genuine second request. Clients can now send::

    POST /api/v1/leads
    Idempotency-Key: 6f1c2b7e-...

The first response is recorded against that key and replayed for any repeat, so the retry is
safe. The request body is fingerprinted alongside it, so reusing a key with different content
is reported as a conflict rather than silently returning someone else's response.

Scope is deliberately narrow: only POST, only when the header is present, and only for
successful responses. A failed create leaves no record, so the client is free to retry it
with the same key.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.errors import problem_response
from app.db.supabase import SupabaseAdminClient

logger = logging.getLogger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 255
REPLAYED_HEADER = "Idempotent-Replay"


def _fingerprint(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _caller_hash(request: Request) -> str:
    """Identify the caller without storing their credentials.

    The key is recorded before authentication has necessarily resolved a profile, so this
    hashes the bearer token itself; anonymous callers fall back to their address.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return "t:" + hashlib.sha256(token.encode()).hexdigest()
    client = request.client.host if request.client else "unknown"
    return "a:" + hashlib.sha256(client.encode()).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not self.enabled or request.method != "POST" or not key:
            return await call_next(request)

        key = key.strip()[:MAX_KEY_LENGTH]
        if not key:
            return await call_next(request)

        body = await request.body()
        request_hash = _fingerprint(body)
        caller = _caller_hash(request)
        endpoint = request.url.path

        try:
            store = SupabaseAdminClient()
        except Exception as exc:
            # Without a service-role key we cannot record anything. Failing the request would
            # be worse than processing it normally, so log and carry on.
            logger.warning("idempotency store unavailable: %s", exc)
            return await call_next(request)

        existing = await self._lookup(store, caller, key)
        if existing is not None:
            if existing.get("request_hash") != request_hash:
                return problem_response(
                    request,
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used with a different request body. "
                        "Use a fresh key for a different request."
                    ),
                    code="idempotency_key_reused",
                )
            return self._replay(existing)

        response = await call_next(request)

        # Only successful creates are worth replaying; a failure should be retryable.
        if 200 <= response.status_code < 300:
            payload = await self._capture(response)
            await self._record(
                store,
                caller=caller,
                key=key,
                endpoint=endpoint,
                request_hash=request_hash,
                status_code=response.status_code,
                body=payload,
            )
            return self._rebuild(response, payload)

        return response

    async def _lookup(
        self, store: SupabaseAdminClient, caller: str, key: str
    ) -> dict[str, Any] | None:
        try:
            result = await store.select(
                "idempotency_keys",
                params={
                    "select": "*",
                    "caller_hash": f"eq.{caller}",
                    "idempotency_key": f"eq.{key}",
                    "limit": "1",
                },
            )
            return result.first()
        except Exception as exc:
            logger.warning("idempotency lookup failed: %s", exc)
            return None

    async def _record(
        self,
        store: SupabaseAdminClient,
        *,
        caller: str,
        key: str,
        endpoint: str,
        request_hash: str,
        status_code: int,
        body: bytes,
    ) -> None:
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        try:
            await store.insert(
                "idempotency_keys",
                {
                    "caller_hash": caller,
                    "idempotency_key": key,
                    "endpoint": endpoint,
                    "request_hash": request_hash,
                    "status_code": status_code,
                    "response_body": parsed,
                },
            )
        except Exception as exc:
            # A concurrent duplicate lost the race to the unique index. The work is already
            # done and the caller has their response; nothing here is worth failing over.
            logger.info("idempotency record skipped for %s: %s", endpoint, exc)

    @staticmethod
    async def _capture(response: Response) -> bytes:
        chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
        return b"".join(chunks)

    @staticmethod
    def _rebuild(response: Response, body: bytes) -> Response:
        """The body stream was consumed to record it, so hand back an equivalent response."""
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    @staticmethod
    def _replay(record: dict[str, Any]) -> Response:
        response = JSONResponse(
            record.get("response_body"),
            status_code=int(record.get("status_code") or 200),
        )
        response.headers[REPLAYED_HEADER] = "true"
        return response
