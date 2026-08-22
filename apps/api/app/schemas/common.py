"""Shared schema primitives."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer


#: Monetary amount. Held as ``Decimal`` server-side so arithmetic stays exact, but serialised
#: as a JSON number -- Pydantic's default is a *string*, which would silently break every
#: client typing these fields as ``number``.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: float(v) if v is not None else None, return_type=float, when_used="json"),
]


class APIModel(BaseModel):
    """Base for every request/response model.

    ``extra="ignore"`` matters on the response side: PostgREST ``select=*`` returns columns we
    do not model, and the API should not break the moment a migration adds one. On the request
    side ``forbid`` is used instead (see :class:`StrictAPIModel`) so typos are caught loudly.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)


class StrictAPIModel(APIModel):
    """Request bodies: reject unknown fields so client typos surface as 422, not silence."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class PatchModel(StrictAPIModel):
    """Base for PATCH bodies.

    Every field is optional, so ``model_dump(exclude_unset=True)`` yields exactly the fields
    the caller actually sent -- letting an explicit ``null`` clear a column, which
    ``exclude_none`` (the previous approach) silently made impossible.
    """

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class Message(APIModel):
    """Generic acknowledgement body."""

    message: str = Field(description="Human-readable result description.")


class ErrorResponse(APIModel):
    """RFC 9457 Problem Details. Documented here so it appears in the OpenAPI schema."""

    type: str = Field(description="URI identifying the error category.")
    title: str = Field(description="Short, human-readable summary of the error type.")
    status: int = Field(description="HTTP status code.")
    detail: str = Field(description="Explanation specific to this occurrence.")
    instance: str = Field(description="Path of the request that produced the error.")
    code: str = Field(description="Stable machine-readable error code.")
    request_id: str | None = Field(default=None, description="Correlation id for this request.")
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Per-field details, present on validation failures."
    )


class TimestampedModel(APIModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None


#: Reusable OpenAPI ``responses`` fragments so error shapes are documented per-route.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Malformed request"},
    401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
    403: {"model": ErrorResponse, "description": "Authenticated but not permitted"},
    404: {"model": ErrorResponse, "description": "Resource does not exist or is not visible"},
    409: {"model": ErrorResponse, "description": "Conflicts with current state"},
    422: {"model": ErrorResponse, "description": "Request failed validation"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    503: {"model": ErrorResponse, "description": "Upstream data service unavailable"},
}

AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    k: v for k, v in ERROR_RESPONSES.items() if k in (401, 403, 429, 503)
}
