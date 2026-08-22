"""Cursorless offset pagination with a consistent envelope.

Every collection endpoint returns the same shape::

    {"items": [...], "page": {"limit": 50, "offset": 0, "total": 231, "has_more": true}}

``total`` comes from PostgREST's ``Content-Range`` header when the caller opts in with
``Prefer: count=exact``; it is ``None`` when the count was not requested.
"""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class PageParams(BaseModel):
    """Validated ``limit``/``offset`` pair shared by all list endpoints."""

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(default=0, ge=0)


def page_params(
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT, description="Maximum number of items to return."),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip before collecting results."),
    ] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


PageParamsDep = Annotated[PageParams, Depends(page_params)]


class PageMeta(BaseModel):
    """Pagination metadata returned alongside every collection."""

    limit: int = Field(description="Maximum number of items requested.")
    offset: int = Field(description="Number of items skipped.")
    total: int | None = Field(
        default=None, description="Total matching rows, when the upstream count was available."
    )
    has_more: bool = Field(description="True when further pages exist after this one.")


class Page(BaseModel, Generic[T]):
    """Envelope for a page of results."""

    items: list[T]
    page: PageMeta

    @classmethod
    def build(cls, items: list[T], params: PageParams, total: int | None = None) -> "Page[T]":
        if total is not None:
            has_more = params.offset + len(items) < total
        else:
            # Without a count we can only infer: a full page implies there may be more.
            has_more = len(items) == params.limit
        return cls(
            items=items,
            page=PageMeta(
                limit=params.limit,
                offset=params.offset,
                total=total,
                has_more=has_more,
            ),
        )
