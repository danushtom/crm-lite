"""Opportunity and proposal endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUserDep, DbDep
from app.core.concurrency import IfMatchDep, set_etag, update_guarded
from app.core.pagination import Page, PageParamsDep
from app.domain.enums import LeadStage, OpportunityStatus
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.opportunities import (
    Opportunity,
    OpportunityDetail,
    OpportunitySummary,
    OpportunityUpdate,
    OpportunityWithLead,
    Proposal,
    ProposalCreate,
)
from app.services import proposals as proposal_service

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])

_SUMMARY_COLUMNS = "id,lead_id,title,status,stage,quoted_value,currency,deal_probability,priority_score,updated_at"


@router.get(
    "",
    response_model=Page[OpportunityWithLead],
    summary="List opportunities",
    description="The Kanban board source: one opportunity per lead, with lead and company embedded.",
    responses=AUTH_RESPONSES,
)
async def list_opportunities(
    db: DbDep,
    page: PageParamsDep,
    stage: Annotated[LeadStage | None, Query(description="Exact pipeline stage.")] = None,
    opportunity_status: Annotated[
        OpportunityStatus | None, Query(alias="status", description="Commercial status.")
    ] = None,
) -> Page[OpportunityWithLead]:
    params: dict[str, str] = {
        "select": "*,leads(*,companies(*))",
        "order": "updated_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if stage:
        params["stage"] = f"eq.{stage.value}"
    if opportunity_status:
        params["status"] = f"eq.{opportunity_status.value}"

    result = await db.select("opportunities", params=params, count=True)
    return Page.build(
        [OpportunityWithLead.model_validate(o) for o in result.rows], page, result.count
    )


@router.get(
    "/by-lead/{lead_id}",
    response_model=OpportunitySummary,
    summary="Get the opportunity for a lead",
    description=(
        "Light projection for lead -> opportunity deep links. Replaces the previous "
        "`GET /opportunities?lead_id=` filter, which returned a list for a one-to-one relation."
    ),
    responses=ERROR_RESPONSES,
)
async def get_opportunity_by_lead(lead_id: str, db: DbDep) -> OpportunitySummary:
    result = await db.select(
        "opportunities",
        params={"select": _SUMMARY_COLUMNS, "lead_id": f"eq.{lead_id}", "limit": "1"},
    )
    return OpportunitySummary.model_validate(result.one("Opportunity"))


@router.get(
    "/{opportunity_id}",
    response_model=OpportunityDetail,
    summary="Get an opportunity",
    description="Includes the full versioned proposal history.",
    responses=ERROR_RESPONSES,
)
async def get_opportunity(
    opportunity_id: str, db: DbDep, response: Response
) -> OpportunityDetail:
    result = await db.select(
        "opportunities",
        params={"select": "*,proposals(*)", "id": f"eq.{opportunity_id}"},
    )
    row = result.one("Opportunity")
    set_etag(response, row)
    return OpportunityDetail.model_validate(row)


@router.patch(
    "/{opportunity_id}",
    response_model=Opportunity,
    summary="Update an opportunity",
    description="Stage and commercial changes here propagate to the lead via a database trigger.",
    responses=ERROR_RESPONSES,
)
async def update_opportunity(
    opportunity_id: str,
    body: OpportunityUpdate,
    db: DbDep,
    response: Response,
    if_match: IfMatchDep,
) -> Opportunity:
    changes = OpportunityUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        result = await db.select(
            "opportunities", params={"select": "*", "id": f"eq.{opportunity_id}"}
        )
        row = result.one("Opportunity")
        set_etag(response, row)
        return Opportunity.model_validate(row)

    row = await update_guarded(
        db,
        "opportunities",
        record_id=opportunity_id,
        changes=changes,
        if_match=if_match,
        what="Opportunity",
    )
    set_etag(response, row)
    return Opportunity.model_validate(row)


# --- Proposals -----------------------------------------------------------------


@router.get(
    "/{opportunity_id}/proposals",
    response_model=Page[Proposal],
    summary="List proposal versions",
    responses=ERROR_RESPONSES,
)
async def list_proposals(
    opportunity_id: str, db: DbDep, page: PageParamsDep
) -> Page[Proposal]:
    result = await db.select(
        "proposals",
        params={
            "select": "*",
            "opportunity_id": f"eq.{opportunity_id}",
            "order": "version.desc,id.desc",
            "limit": str(page.limit),
            "offset": str(page.offset),
        },
        count=True,
    )
    return Page.build([Proposal.model_validate(p) for p in result.rows], page, result.count)


@router.post(
    "/{opportunity_id}/proposals",
    response_model=Proposal,
    status_code=status.HTTP_201_CREATED,
    summary="Create the next proposal version",
    description="The version number is allocated server-side; concurrent submissions are retried.",
    responses=ERROR_RESPONSES,
)
async def create_proposal(
    opportunity_id: str,
    body: ProposalCreate,
    db: DbDep,
    user: CurrentUserDep,
    response: Response,
) -> Proposal:
    created = await proposal_service.create_version(
        db, opportunity_id, body.model_dump(exclude_none=True, mode="json"), created_by=user.sub
    )
    proposal = Proposal.model_validate(created)
    response.headers["Location"] = f"{router.prefix}/{opportunity_id}/proposals/{proposal.id}"
    return proposal


@router.post(
    "/{opportunity_id}/proposals/upload",
    response_model=Proposal,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a proposal document",
    description="Stores the file in Supabase Storage, then records it as the next version.",
    responses=ERROR_RESPONSES,
)
async def upload_proposal(
    opportunity_id: str,
    db: DbDep,
    user: CurrentUserDep,
    file: Annotated[UploadFile, File(description="Proposal document (PDF or similar).")],
    title: Annotated[str, Form(min_length=1, max_length=200)],
) -> Proposal:
    version = await proposal_service.next_version(db, opportunity_id)
    data = await file.read()
    public_url = await proposal_service.upload_file(
        opportunity_id=opportunity_id,
        version=version,
        filename=file.filename or "proposal",
        content_type=file.content_type,
        data=data,
    )
    created = await proposal_service.create_version(
        db,
        opportunity_id,
        {"title": title, "file_url": public_url, "status": "draft"},
        created_by=user.sub,
    )
    return Proposal.model_validate(created)
