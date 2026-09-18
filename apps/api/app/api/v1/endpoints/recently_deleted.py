"""Recently deleted records, and restoring them.

Deleted rows are hidden by every SELECT policy, so neither listing nor restoring can go through
ordinary PostgREST reads and writes -- the same reason deletes go through ``soft_delete_*``.
Both calls here use SECURITY DEFINER functions (``recently_deleted``, ``restore_record``, in
the 20260920000000 migration) that apply exactly the permission rule the matching delete
function applies: you can see and restore what you could have deleted. The caller's own
client is used, so ``auth.uid()`` inside those functions is the caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Page, PageParamsDep
from app.schemas.common import APIModel, ERROR_RESPONSES

router = APIRouter(prefix="/recently-deleted", tags=["Recently deleted"])

DeletedKind = Literal["companies", "contacts", "leads", "opportunities"]

_SINGULAR = {"companies": "company", "contacts": "contact", "leads": "lead", "opportunities": "opportunity"}
_PARENT_HINT = {
    "company": "Its company is deleted too; restore the company first.",
    "contact": "Its primary contact is deleted too; restore the contact first.",
    "lead": "Its lead is deleted too; restore the lead first.",
}


class DeletedRecord(APIModel):
    id: str
    label: str
    detail: str | None = None
    deleted_at: datetime
    deleted_by_name: str | None = None
    blocked_by: Literal["company", "contact", "lead"] | None = None


class RestoreResult(APIModel):
    id: str
    restored: bool


@router.get(
    "",
    response_model=Page[DeletedRecord],
    summary="List recently deleted records of one kind",
    description=(
        "Newest first. Only records the caller could have deleted are listed. `blocked_by` names "
        "a deleted parent that must be restored first."
    ),
    responses=ERROR_RESPONSES,
)
async def list_deleted(
    db: DbDep,
    page: PageParamsDep,
    kind: Annotated[DeletedKind, Query(description="Which kind of record to list.")],
) -> Page[DeletedRecord]:
    result = await db.rpc(
        "recently_deleted", {"p_kind": kind, "p_limit": page.limit, "p_offset": page.offset}
    )
    return Page.build([DeletedRecord.model_validate(r) for r in result.rows], page)


@router.post(
    "/{kind}/{record_id}/restore",
    response_model=RestoreResult,
    summary="Restore a deleted record",
    description=(
        "409 when a deleted parent must be restored first, or when restoring an opportunity would "
        "give its lead a second active pursuit."
    ),
    responses=ERROR_RESPONSES,
)
async def restore(kind: DeletedKind, record_id: str, db: DbDep) -> RestoreResult:
    result = await db.rpc("restore_record", {"p_kind": kind, "p_id": record_id})
    outcome = result.data
    if isinstance(outcome, list):
        outcome = outcome[0] if outcome else None
    status = (outcome or {}).get("status") if isinstance(outcome, dict) else None

    what = _SINGULAR[kind].capitalize()
    if status == "restored":
        return RestoreResult(id=record_id, restored=True)
    if status == "parent_deleted":
        raise ConflictError(
            _PARENT_HINT.get(outcome.get("parent"), "Restore its parent record first."),
            code="parent_deleted",
        )
    if status == "conflict":
        raise ConflictError(
            "This lead already has another active opportunity; close that one before restoring this.",
            code="active_opportunity_exists",
        )
    raise NotFoundError(f"{what} not found in recently deleted")
