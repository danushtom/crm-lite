"""RFC 9457 (Problem Details) error model and the handlers that render it.

Every error response from this API -- expected or not -- is a single predictable JSON shape
served as ``application/problem+json``::

    {
      "type": "https://docs.dracara.dev/errors/not-found",
      "title": "Not Found",
      "status": 404,
      "detail": "Lead not found",
      "instance": "/api/v1/leads/123",
      "code": "not_found",
      "request_id": "5f0c..."
    }

Validation failures add an ``errors`` array describing each offending field.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_DOC_BASE = "https://docs.dracara.dev/errors"


class APIError(Exception):
    """Base class for errors this API raises deliberately."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    title: str = "Internal Server Error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        title: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.title
        if code:
            self.code = code
        if title:
            self.title = title
        if status_code:
            self.status_code = status_code
        self.extra = extra or {}
        super().__init__(self.detail)


class BadRequestError(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"
    title = "Bad Request"


class UnauthorizedError(APIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    title = "Unauthorized"


class ForbiddenError(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    title = "Forbidden"


class NotFoundError(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    title = "Not Found"


class ConflictError(APIError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    title = "Conflict"


class PayloadTooLargeError(APIError):
    status_code = 413  # Content Too Large (constant name differs across Starlette versions)
    code = "payload_too_large"
    title = "Payload Too Large"


class UnprocessableError(APIError):
    status_code = 422  # Unprocessable Content
    code = "unprocessable_entity"
    title = "Unprocessable Entity"


class UpstreamError(APIError):
    """Supabase (PostgREST / Auth / Storage) returned an error or was unreachable."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_error"
    title = "Upstream Error"


class ServiceUnavailableError(APIError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    title = "Service Unavailable"


class NotConfiguredError(APIError):
    """A dependency this endpoint needs has not been configured on the server."""

    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "not_configured"
    title = "Not Implemented"


_TITLE_BY_STATUS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Payload Too Large",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
}

_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "unprocessable_entity",
    429: "rate_limit_exceeded",
    500: "internal_error",
    501: "not_configured",
    502: "upstream_error",
    503: "service_unavailable",
}


def problem_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    code: str | None = None,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build an ``application/problem+json`` response."""
    resolved_code = code or _CODE_BY_STATUS.get(status_code, "error")
    slug = resolved_code.replace("_", "-")
    body: dict[str, Any] = {
        "type": ERROR_DOC_BASE + "/" + slug,
        "title": title or _TITLE_BY_STATUS.get(status_code, "Error"),
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "code": resolved_code,
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    body.update({k: v for k, v in extra.items() if v is not None})

    response_headers = dict(headers or {})
    if request_id:
        response_headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        body,
        status_code=status_code,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=response_headers,
    )


def _stringify(detail: Any) -> str:
    """PostgREST and Starlette hand us details in several shapes; normalise to a sentence."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        for key in ("message", "detail", "hint", "error_description", "error"):
            value = detail.get(key)
            if isinstance(value, str) and value:
                return value
    return str(detail)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so no code path can leak a non-Problem error body."""

    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("api_error code=%s detail=%s", exc.code, exc.detail, exc_info=exc)
        return problem_response(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
            code=exc.code,
            title=exc.title,
            **exc.extra,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        headers = dict(getattr(exc, "headers", None) or {})
        return problem_response(
            request,
            status_code=exc.status_code,
            detail=_stringify(exc.detail),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ()) if p != "body") or "body",
                "message": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return problem_response(
            request,
            status_code=422,
            detail="Request validation failed",
            errors=errors,
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return problem_response(
            request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: " + str(exc.detail),
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", exc_info=exc)
        return problem_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )
