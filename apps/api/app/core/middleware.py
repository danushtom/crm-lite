"""Cross-cutting HTTP middleware: request correlation, access logs, security headers, body limits."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.errors import problem_response
from app.core.logging import request_id_ctx

logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
API_VERSION_HEADER = "X-API-Version"

#: Probe endpoints fire constantly; logging each one buries real traffic.
QUIET_PATHS = frozenset({"/health", "/health/live", "/health/ready"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request id and emit one structured access log per request."""

    def __init__(self, app: ASGIApp, api_version: str = "v1") -> None:
        super().__init__(app)
        self.api_version = api_version

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        # Never echo an unbounded client-supplied value straight into logs and responses.
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        request.state.request_id = request_id

        # The ContextVar must stay set until *after* the access log is emitted, otherwise
        # that line is written with no correlation id attached.
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "%s %s -> unhandled exception (%.1fms)",
                request.method,
                request.url.path,
                (time.perf_counter() - started) * 1000,
                extra={"http_method": request.method, "http_path": request.url.path},
            )
            raise
        else:
            duration_ms = (time.perf_counter() - started) * 1000
            response.headers[REQUEST_ID_HEADER] = request_id
            response.headers[API_VERSION_HEADER] = self.api_version
            response.headers["Server-Timing"] = f"app;dur={duration_ms:.1f}"

            if request.url.path not in QUIET_PATHS:
                logger.info(
                    "%s %s -> %s (%.1fms)",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": response.status_code,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
            return response
        finally:
            request_id_ctx.reset(token)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they are buffered into memory.

    File uploads are checked separately against ``MAX_UPLOAD_BYTES``; this guards the JSON
    endpoints, which would otherwise accept an unbounded body.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    return problem_response(
                        request,
                        status_code=413,
                        detail=f"Request body exceeds the {self.max_bytes} byte limit",
                        code="payload_too_large",
                    )
            except ValueError:
                return problem_response(
                    request,
                    status_code=400,
                    detail="Invalid Content-Length header",
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline hardening headers.

    This service returns JSON only, so the CSP is deliberately restrictive; the interactive
    docs are exempted because Swagger UI loads its own assets.
    """

    _DOC_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect", "/openapi.json"})

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

        if request.url.path not in self._DOC_PATHS:
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )

        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
