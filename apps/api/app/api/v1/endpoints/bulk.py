"""Bulk actions on selected leads, contacts and companies.

Everything runs as the caller under row-level security, one statement or function call per
record where the single-record path does the same -- so a bulk action can do exactly what the
caller could do one record at a time, and nothing else. Each id gets its own result: a record
the caller cannot see or change fails on its own without failing the rest.

Deliberately not optimistic-concurrency guarded (no If-Match): a bulk action is a statement
about the selection as it stands, and asking for 200 ETags would make it unusable.
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field, model_validator

from app.api.deps import DbDep, ProfileDep, is_full_access
from app.core.concurrency import soft_delete_guarded
from app.core.errors import APIError, ForbiddenError, UnprocessableError
from app.core.rate_limit import limiter
from app.schemas.common import APIModel, ERROR_RESPONSES, StrictAPIModel

router = APIRouter(prefix="/bulk", tags=["Bulk actions"])

BulkKind = Literal["leads", "contacts", "companies"]
BulkAction = Literal["delete", "reassign", "add_tags", "remove_tags"]

MAX_BULK_IDS = 500
#: Ids are interpolated into an `in.(...)` filter, where `,` and `)` are structural -- so they
#: are held to the UUID shape here rather than trusted to be well-formed.
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CONCURRENCY = 8
_ACTIONS: dict[str, set[str]] = {
    "leads": {"delete", "reassign", "add_tags", "remove_tags"},
    "contacts": {"delete"},
    "companies": {"delete"},
}
_SINGULAR = {"leads": "Lead", "contacts": "Contact", "companies": "Company"}


class BulkRequest(StrictAPIModel):
    action: BulkAction
    ids: list[str] = Field(min_length=1, max_length=MAX_BULK_IDS)
    owner_id: str | None = Field(default=None, description="For reassign: the new owner.")
    tags: list[str] | None = Field(default=None, max_length=25, description="For add_tags / remove_tags.")

    @model_validator(mode="after")
    def _needs(self) -> "BulkRequest":
        if not all(_UUID.match(i) for i in self.ids):
            raise ValueError("every id must be a UUID")
        if self.action == "reassign" and not (self.owner_id and _UUID.match(self.owner_id)):
            raise ValueError("reassign needs owner_id, a UUID")
        if self.action in {"add_tags", "remove_tags"}:
            cleaned = [t.strip()[:50] for t in self.tags or [] if t.strip()]
            if not cleaned:
                raise ValueError(f"{self.action} needs at least one tag")
            self.tags = cleaned
        self.ids = list(dict.fromkeys(self.ids))  # de-duplicate, keep order
        return self


class BulkItemResult(APIModel):
    id: str
    ok: bool
    message: str | None = None


class BulkResult(APIModel):
    action: BulkAction
    succeeded: int
    failed: int
    results: list[BulkItemResult]


async def _each(ids: list[str], work) -> list[BulkItemResult]:
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def run(record_id: str) -> BulkItemResult:
        async with gate:
            try:
                await work(record_id)
                return BulkItemResult(id=record_id, ok=True)
            except APIError as exc:
                return BulkItemResult(id=record_id, ok=False, message=exc.detail)

    return list(await asyncio.gather(*(run(i) for i in ids)))


def _merge_tags(current: list[str], tags: list[str], *, add: bool) -> list[str]:
    lowered = {t.lower() for t in tags}
    if add:
        merged = list(current)
        for tag in tags:
            if tag.lower() not in {m.lower() for m in merged}:
                merged.append(tag)
        return merged[:25]
    return [t for t in current if t.lower() not in lowered]


@router.post(
    "/{kind}",
    response_model=BulkResult,
    summary="Apply one action to many records",
    description=(
        f"Up to {MAX_BULK_IDS} ids. Leads support delete, reassign (full-access roles only), "
        "add_tags and remove_tags; contacts and companies support delete. Runs as the caller; "
        "every id gets its own result, and one failure does not stop the rest."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def bulk_action(
    request: Request,
    response: Response,
    kind: BulkKind,
    body: BulkRequest,
    db: DbDep,
    profile: ProfileDep,
) -> BulkResult:
    if body.action not in _ACTIONS[kind]:
        raise UnprocessableError(f"{body.action} is not available for {kind}")
    what = _SINGULAR[kind]

    if body.action == "delete":
        results = await _each(
            body.ids,
            lambda record_id: soft_delete_guarded(db, kind, record_id=record_id, if_match=None, what=what),
        )

    elif body.action == "reassign":
        if not is_full_access(profile):
            raise ForbiddenError("Only a role with full organization access can reassign leads")
        owner = await db.select(
            "users", params={"select": "id", "id": f"eq.{body.owner_id}", "is_active": "eq.true"}
        )
        if owner.first() is None:
            raise UnprocessableError("The new owner is not an active member of this organization")
        updated = await db.update(
            "leads", {"id": f"in.({','.join(body.ids)})", "select": "id"}, {"owner_id": body.owner_id}
        )
        done = {str(r["id"]) for r in updated.rows}
        results = [
            BulkItemResult(id=i, ok=i in done, message=None if i in done else f"{what} not found")
            for i in body.ids
        ]

    else:
        found = await db.select(
            "leads", params={"select": "id,tags", "id": f"in.({','.join(body.ids)})"}
        )
        current: dict[str, list[str]] = {str(r["id"]): list(r.get("tags") or []) for r in found.rows}
        add = body.action == "add_tags"

        async def retag(record_id: str) -> None:
            if record_id not in current:
                raise UnprocessableError(f"{what} not found")
            merged = _merge_tags(current[record_id], body.tags or [], add=add)
            if merged != current[record_id]:
                await db.update("leads", {"id": f"eq.{record_id}"}, {"tags": merged})

        results = await _each(body.ids, retag)

    ok = sum(1 for r in results if r.ok)
    return BulkResult(action=body.action, succeeded=ok, failed=len(results) - ok, results=results)
