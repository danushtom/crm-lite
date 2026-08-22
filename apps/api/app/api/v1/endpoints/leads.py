"""Lead endpoints, including the activity / task / meeting sub-resources."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep, NonPartnerDep
from app.core.concurrency import IfMatchDep, set_etag
from app.core.pagination import Page, PageParamsDep
from app.domain.enums import LeadSource, LeadStage, ProjectType
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.leads import (
    Activity,
    ActivityCreate,
    Lead,
    LeadCreate,
    LeadDetail,
    LeadIntelligence,
    LeadIntelligenceUpdate,
    LeadStageUpdate,
    LeadUpdate,
    LeadWithCompany,
)
from app.schemas.meetings import Meeting, MeetingCreate
from app.schemas.opportunities import LeadConversion, LeadRef, Opportunity
from app.schemas.tasks import Task, TaskCreate
from app.services import leads as lead_service

router = APIRouter(prefix="/leads", tags=["Leads"])


def _search_pattern(term: str) -> str:
    """PostgREST treats * as the wildcard; strip characters that would break the filter."""
    cleaned = "".join(c for c in term.strip() if c not in "*%(),")[:200]
    return f"*{cleaned}*" if cleaned else ""


@router.get(
    "",
    response_model=Page[LeadWithCompany],
    summary="List leads",
    description="Filterable, paginated lead list with the company embedded.",
    responses=AUTH_RESPONSES,
)
async def list_leads(
    db: DbDep,
    page: PageParamsDep,
    stage: Annotated[LeadStage | None, Query(description="Exact pipeline stage.")] = None,
    owner_id: Annotated[str | None, Query(description="Restrict to one owner.")] = None,
    lead_source: Annotated[LeadSource | None, Query()] = None,
    project_type: Annotated[ProjectType | None, Query()] = None,
    search: Annotated[
        str | None,
        Query(max_length=200, description="Case-insensitive match on the company name."),
    ] = None,
) -> Page[LeadWithCompany]:
    params: dict[str, str] = {
        "select": "*,companies(*)",
        "order": "updated_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if stage:
        params["stage"] = f"eq.{stage.value}"
    if owner_id:
        params["owner_id"] = f"eq.{owner_id}"
    if lead_source:
        params["lead_source"] = f"eq.{lead_source.value}"
    if project_type:
        params["project_type"] = f"eq.{project_type.value}"

    if search:
        pattern = _search_pattern(search)
        if pattern:
            # Filter on the embedded company with an inner join, so the match happens in one
            # query against the trigram index on companies.name.
            #
            # This previously ran a separate lookup capped at 100 company ids and fed them
            # into an `in.(...)` list: past 100 matching companies their leads silently
            # vanished from the results, and the exact set depended on PostgREST's row order.
            # It also matched `search` against project_type and lead_source, which are enums
            # with a handful of values -- substring matching them is close to meaningless, and
            # both already have dedicated exact filters on this endpoint.
            params["select"] = "*,companies!inner(*)"
            params["companies.name"] = f"ilike.{pattern}"

    result = await db.select("leads", params=params, count=True)
    return Page.build([LeadWithCompany.model_validate(r) for r in result.rows], page, result.count)


@router.post(
    "",
    response_model=Lead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead",
    description=(
        "Creates the lead plus, via database triggers, its intelligence panel and the "
        "opportunity row that carries its pipeline position."
    ),
    responses=ERROR_RESPONSES,
)
async def create_lead(
    body: LeadCreate, db: DbDep, user: CurrentUserDep, response: Response
) -> Lead:
    payload = body.model_dump(exclude_none=True, mode="json")
    created = await lead_service.create_lead(db, payload, owner_id=user.sub)
    lead = Lead.model_validate(created)
    response.headers["Location"] = f"{router.prefix}/{lead.id}"
    return lead


@router.get(
    "/{lead_id}",
    response_model=LeadDetail,
    summary="Get a lead",
    description="Returns the lead with its intelligence panel; optionally embeds recent activity.",
    responses=ERROR_RESPONSES,
)
async def get_lead(
    lead_id: str,
    db: DbDep,
    response: Response,
    include_related: Annotated[
        bool, Query(description="Embed recent activities and tasks.")
    ] = False,
) -> LeadDetail:
    lead = await lead_service.get_lead(db, lead_id)
    set_etag(response, lead)
    intelligence = await lead_service.get_lead_intelligence(db, lead_id)

    detail = LeadDetail(
        lead=Lead.model_validate(lead),
        lead_intelligence=LeadIntelligence.model_validate(intelligence) if intelligence else None,
    )
    if include_related:
        activities = await db.select(
            "activities",
            params={
                "select": "*",
                "lead_id": f"eq.{lead_id}",
                "order": "performed_at.desc,id.desc",
                "limit": "50",
            },
        )
        tasks = await db.select(
            "tasks",
            params={"select": "*", "lead_id": f"eq.{lead_id}", "order": "due_at.asc,id.desc", "limit": "25"},
        )
        detail.activities = [Activity.model_validate(a) for a in activities.rows]
        detail.recent_tasks = tasks.rows
    return detail


@router.patch(
    "/{lead_id}",
    response_model=Lead,
    summary="Update a lead",
    description=(
        "Pipeline fields (stage, value, currency, probability, tags) are written to the lead's "
        "opportunity row and mirrored back by a trigger. The priority score is recomputed."
    ),
    responses=ERROR_RESPONSES,
)
async def update_lead(
    lead_id: str,
    body: LeadUpdate,
    db: DbDep,
    response: Response,
    if_match: IfMatchDep,
) -> Lead:
    changes = LeadUpdate.model_validate(body.changes()).model_dump(exclude_unset=True, mode="json")
    updated = await lead_service.update_lead(db, lead_id, changes, if_match=if_match)
    set_etag(response, updated)
    return Lead.model_validate(updated)


@router.patch(
    "/{lead_id}/stage",
    response_model=Lead,
    summary="Move a lead to another stage",
    description="Writes to the opportunity row, which logs a stage-change activity via trigger.",
    responses=ERROR_RESPONSES,
)
async def move_stage(lead_id: str, body: LeadStageUpdate, db: DbDep) -> Lead:
    updated = await lead_service.set_stage(db, lead_id, body.stage.value)
    return Lead.model_validate(updated)


@router.get(
    "/{lead_id}/intelligence",
    response_model=LeadIntelligence,
    summary="Get the CRM intelligence panel",
    responses=ERROR_RESPONSES,
)
async def get_intelligence(lead_id: str, db: DbDep) -> LeadIntelligence:
    await lead_service.get_lead(db, lead_id)
    intelligence = await lead_service.get_lead_intelligence(db, lead_id)
    return LeadIntelligence.model_validate(intelligence or {"lead_id": lead_id})


@router.patch(
    "/{lead_id}/intelligence",
    response_model=LeadIntelligence,
    summary="Update the CRM intelligence panel",
    description="Partners may read this panel but not edit it.",
    responses=ERROR_RESPONSES,
)
async def update_intelligence(
    lead_id: str,
    body: LeadIntelligenceUpdate,
    db: DbDep,
    user: CurrentUserDep,
    _guard: NonPartnerDep,
) -> LeadIntelligence:
    changes = body.changes()
    if not changes:
        return await get_intelligence(lead_id, db)

    changes["updated_by"] = user.sub
    result = await db.update("lead_intelligence", {"lead_id": f"eq.{lead_id}"}, changes)
    updated = result.one("Lead intelligence")
    await lead_service.sync_priority_score(db, lead_id)
    return LeadIntelligence.model_validate(updated)


@router.post(
    "/{lead_id}/convert",
    response_model=LeadConversion,
    status_code=status.HTTP_201_CREATED,
    summary="Convert a lead into an opportunity",
    description="Idempotency is enforced: converting an already-converted lead returns 409.",
    responses=ERROR_RESPONSES,
)
async def convert_lead(lead_id: str, db: DbDep) -> LeadConversion:
    opportunity, lead = await lead_service.convert_to_opportunity(db, lead_id)
    return LeadConversion(
        opportunity=Opportunity.model_validate(opportunity),
        lead=LeadRef.model_validate(lead),
    )


# --- Activities ----------------------------------------------------------------


@router.get(
    "/{lead_id}/activities",
    response_model=Page[Activity],
    summary="List a lead's activity timeline",
    responses=ERROR_RESPONSES,
)
async def list_activities(lead_id: str, db: DbDep, page: PageParamsDep) -> Page[Activity]:
    await lead_service.get_lead(db, lead_id)
    result = await db.select(
        "activities",
        params={
            "select": "*",
            "lead_id": f"eq.{lead_id}",
            "order": "performed_at.desc,id.desc",
            "limit": str(page.limit),
            "offset": str(page.offset),
        },
        count=True,
    )
    return Page.build([Activity.model_validate(a) for a in result.rows], page, result.count)


@router.post(
    "/{lead_id}/activities",
    response_model=Activity,
    status_code=status.HTTP_201_CREATED,
    summary="Log an activity against a lead",
    responses=ERROR_RESPONSES,
)
async def create_activity(
    lead_id: str, body: ActivityCreate, db: DbDep, user: CurrentUserDep
) -> Activity:
    await lead_service.get_lead(db, lead_id)
    payload = {
        **body.model_dump(exclude_none=True, mode="json"),
        "lead_id": lead_id,
        "performed_by": user.sub,
    }
    result = await db.insert("activities", payload)
    return Activity.model_validate(result.one("Activity"))


# --- Tasks ---------------------------------------------------------------------


@router.get(
    "/{lead_id}/tasks",
    response_model=Page[Task],
    summary="List a lead's follow-up tasks",
    responses=ERROR_RESPONSES,
)
async def list_lead_tasks(lead_id: str, db: DbDep, page: PageParamsDep) -> Page[Task]:
    await lead_service.get_lead(db, lead_id)
    result = await db.select(
        "tasks",
        params={
            "select": "*",
            "lead_id": f"eq.{lead_id}",
            "order": "due_at.asc,id.desc",
            "limit": str(page.limit),
            "offset": str(page.offset),
        },
        count=True,
    )
    return Page.build([Task.model_validate(t) for t in result.rows], page, result.count)


@router.post(
    "/{lead_id}/tasks",
    response_model=Task,
    status_code=status.HTTP_201_CREATED,
    summary="Create a follow-up task on a lead",
    responses=ERROR_RESPONSES,
)
async def create_lead_task(
    lead_id: str, body: TaskCreate, db: DbDep, user: CurrentUserDep
) -> Task:
    await lead_service.get_lead(db, lead_id)
    payload = {
        **body.model_dump(exclude_none=True, mode="json"),
        "lead_id": lead_id,
        "owner_id": user.sub,
        "status": "pending",
    }
    result = await db.insert("tasks", payload)
    return Task.model_validate(result.one("Task"))


# --- Meetings ------------------------------------------------------------------


@router.get(
    "/{lead_id}/meetings",
    response_model=Page[Meeting],
    summary="List a lead's meetings",
    responses=ERROR_RESPONSES,
)
async def list_lead_meetings(lead_id: str, db: DbDep, page: PageParamsDep) -> Page[Meeting]:
    await lead_service.get_lead(db, lead_id)
    result = await db.select(
        "meetings",
        params={
            "select": "*",
            "lead_id": f"eq.{lead_id}",
            "order": "scheduled_at.asc,id.desc",
            "limit": str(page.limit),
            "offset": str(page.offset),
        },
        count=True,
    )
    return Page.build([Meeting.model_validate(m) for m in result.rows], page, result.count)


@router.post(
    "/{lead_id}/meetings",
    response_model=Meeting,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a meeting on a lead",
    responses=ERROR_RESPONSES,
)
async def create_lead_meeting(
    lead_id: str, body: MeetingCreate, db: DbDep, user: CurrentUserDep
) -> Meeting:
    await lead_service.get_lead(db, lead_id)
    payload = {
        **body.model_dump(exclude_none=True, mode="json"),
        "lead_id": lead_id,
        "owner_id": user.sub,
        "status": "scheduled",
    }
    result = await db.insert("meetings", payload)
    return Meeting.model_validate(result.one("Meeting"))
