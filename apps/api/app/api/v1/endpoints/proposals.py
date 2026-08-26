"""Proposal endpoints.

Proposals are created under their opportunity (``POST /opportunities/{id}/proposals``) because
the version number is allocated per opportunity. Once created they are addressable in their
own right, which is what this module provides: reading one, moving it through its status, and
removing a draft.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.api.deps import DbDep
from app.core.concurrency import IfMatchDep, set_etag, update_guarded
from app.core.errors import ConflictError
from app.domain.enums import ProposalStatus
from app.schemas.common import ERROR_RESPONSES
from app.schemas.opportunities import Proposal, ProposalUpdate

router = APIRouter(prefix="/proposals", tags=["Proposals"])


@router.get(
    "/{proposal_id}",
    response_model=Proposal,
    summary="Get a proposal",
    responses=ERROR_RESPONSES,
)
async def get_proposal(proposal_id: str, db: DbDep, response: Response) -> Proposal:
    result = await db.select("proposals", params={"select": "*", "id": f"eq.{proposal_id}"})
    row = result.one("Proposal")
    set_etag(response, row)
    return Proposal.model_validate(row)


@router.patch(
    "/{proposal_id}",
    response_model=Proposal,
    summary="Update a proposal",
    description=(
        "Moves a proposal through its lifecycle (draft, sent, under review, accepted, "
        "rejected) and lets its links and price be corrected. Marking one sent stamps "
        "`sent_at` server-side, which is what the dashboard's pending-response count reads."
    ),
    responses=ERROR_RESPONSES,
)
async def update_proposal(
    proposal_id: str,
    body: ProposalUpdate,
    db: DbDep,
    response: Response,
    if_match: IfMatchDep,
) -> Proposal:
    changes = ProposalUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        return await get_proposal(proposal_id, db, response)

    # The moment a proposal goes out is a fact about the deal, not something a client should
    # be able to backdate.
    if changes.get("status") == ProposalStatus.SENT:
        changes.setdefault("sent_at", datetime.now(timezone.utc).isoformat())

    row = await update_guarded(
        db,
        "proposals",
        record_id=proposal_id,
        changes=changes,
        if_match=if_match,
        what="Proposal",
    )
    set_etag(response, row)
    return Proposal.model_validate(row)


@router.delete(
    "/{proposal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft proposal",
    description=(
        "Only a draft can be removed. Once a proposal has been sent it is part of what "
        "happened on the deal, and deleting it would leave a hole in the version history; "
        "mark it rejected instead."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_proposal(proposal_id: str, db: DbDep) -> Response:
    existing = await db.select(
        "proposals", params={"select": "id,status,version", "id": f"eq.{proposal_id}"}
    )
    row = existing.one("Proposal")

    if row.get("status") != ProposalStatus.DRAFT:
        raise ConflictError(
            "Only a draft proposal can be deleted. Mark this one rejected instead, so the "
            "version history stays intact."
        )

    await db.delete("proposals", {"id": f"eq.{proposal_id}"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
