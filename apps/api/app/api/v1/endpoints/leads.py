"""Lead endpoints, including the activity / task / meeting sub-resources.

Pipeline position lives on a lead's opportunities, so stage filtering here joins through to
them rather than reading a mirrored column. Moving a card between stages is a write to the
opportunity (``PATCH /opportunities/{id}``), not to the lead.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep, require_permission
from app.core.concurrency import IfMatchDep, set_etag, soft_delete_guarded, update_guarded
from app.core.pagination import Page, PageParamsDep
from app.core.search import contains_pattern
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
    LeadOpportunity,
    LeadUpdate,
    LeadWithCompany,
)
from app.schemas.meetings import Meeting, MeetingCreate
from app.schemas.opportunities import Opportunity, OpportunityOpen
from app.schemas.tasks import Task, TaskCreate
from app.services import leads as lead_service

router = APIRouter(prefix="/leads", tags=["Leads"])

_EMBED = f"*,companies(*),opportunities({lead_service.OPPORTUNITY_COLUMNS})"


@router.get(
    "",
    response_model=Page[LeadWithCompany],
    summary="List leads",
    description=(
        "Filterable, paginated lead list with the company and every pursuit embedded. "
        "Filtering by stage joins through to the opportunities, since a lead has no stage "
        "of its own."
    ),
    responses=AUTH_RESPONSES,
)
async def list_leads(
    db: DbDep,
    page: PageParamsDep,
    stage: Annotated[
        LeadStage | None, Query(description="Match leads with a pursuit at this stage.")
    ] = None,
    owner_id: Annotated[str | None, Query(description="Restrict to one owner.")] = None,
    lead_source: Annotated[LeadSource | None, Query()] = None,
    project_type: Annotated[ProjectType | None, Query()] = None,
    search: Annotated[
        str | None, Query(max_length=200, description="Case-insensitive match on the company name.")
    ] = None,
) -> Page[LeadWithCompany]:
    params: dict[str, str] = {
        "select": _EMBED,
        "order": "updated_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if owner_id:
        params["owner_id"] = f"eq.{owner_id}"
    if lead_source:
        params["lead_source"] = f"eq.{lead_source.value}"
    if project_type:
        params["project_type"] = f"eq.{project_type.value}"

    if stage:
        # !inner turns the embed into a join, so the filter restricts the leads returned.
        params["select"] = _EMBED.replace("opportunities(", "opportunities!inner(")
        params["opportunities.stage"] = f"eq.{stage.value}"

    if search:
        pattern = contains_pattern(search)
        if pattern:
            params["select"] = params["select"].replace("companies(", "companies!inner(")
            params["companies.name"] = f"ilike.{pattern}"

    result = await db.select("leads", params=params, count=True)
    return Page.build([LeadWithCompany.model_validate(r) for r in result.rows], page, result.count)


@router.post(
    "",
    response_model=LeadDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead",
    description=(
        "Creates the lead, its CRM intelligence panel and its initial pursuit in one call. "
        "Supply `opportunity` to set the pursuit's commercials; defaults are used otherwise."
    ),
    responses=ERROR_RESPONSES,
)
async def create_lead(
    body: LeadCreate, db: DbDep, user: CurrentUserDep, response: Response
) -> LeadDetail:
    payload = body.model_dump(exclude_none=True, mode="json", exclude={"opportunity"})
    initial = body.opportunity.model_dump(mode="json") if body.opportunity else None

    lead, pursuits = await lead_service.create_lead(
        db, payload, owner_id=user.sub, opportunity=initial
    )

    response.headers["Location"] = f"{router.prefix}/{lead['id']}"
    set_etag(response, lead)
    return LeadDetail(
        lead=Lead.model_validate(lead),
        opportunities=[LeadOpportunity.model_validate(o) for o in pursuits],
    )


@router.get(
    "/{lead_id}",
    response_model=LeadDetail,
    summary="Get a lead",
    description="The lead with its intelligence panel and pursuits; optionally recent activity.",
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
    pursuits = await lead_service.list_opportunities_for_lead(db, lead_id)

    detail = LeadDetail(
        lead=Lead.model_validate(lead),
        lead_intelligence=LeadIntelligence.model_validate(intelligence) if intelligence else None,
        opportunities=[LeadOpportunity.model_validate(o) for o in pursuits],
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
            params={
                "select": "*",
                "lead_id": f"eq.{lead_id}",
                "order": "due_at.asc,id.desc",
                "limit": "25",
            },
        )
        detail.activities = [Activity.model_validate(a) for a in activities.rows]
        detail.recent_tasks = tasks.rows
    return detail


@router.patch(
    "/{lead_id}",
    response_model=Lead,
    summary="Update a lead",
    description=(
        "Updates qualification fields. Stage, value and probability belong to the lead's "
        "opportunities -- change those through `PATCH /opportunities/{id}`."
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


# --- Opportunities -------------------------------------------------------------


@router.get(
    "/{lead_id}/opportunities",
    response_model=Page[LeadOpportunity],
    summary="List a lead's pursuits",
    responses=ERROR_RESPONSES,
)
async def list_lead_opportunities(
    lead_id: str, db: DbDep, page: PageParamsDep
) -> Page[LeadOpportunity]:
    await lead_service.get_lead(db, lead_id)
    rows = await lead_service.list_opportunities_for_lead(db, lead_id)
    return Page.build([LeadOpportunity.model_validate(o) for o in rows], page, len(rows))


@router.post(
    "/{lead_id}/opportunities",
    response_model=Opportunity,
    status_code=status.HTTP_201_CREATED,
    summary="Open another pursuit against this lead",
    description=(
        "For the follow-on engagement -- the retainer after the build. Replaces the former "
        "`POST /leads/{id}/convert`, which mutated a row that already existed and set a "
        "boolean, rather than creating anything. At most one pursuit per lead may be active."
    ),
    responses=ERROR_RESPONSES,
)
async def open_opportunity(
    lead_id: str,
    body: OpportunityOpen,
    db: DbDep,
    user: CurrentUserDep,
    response: Response,
) -> Opportunity:
    created = await lead_service.open_opportunity(
        db, lead_id, body.model_dump(exclude_none=True, mode="json"), owner_id=user.sub
    )
    response.headers["Location"] = f"/opportunities/{created['id']}"
    set_etag(response, created)
    return Opportunity.model_validate(created)


# --- Intelligence --------------------------------------------------------------


@router.get(
    "/{lead_id}/intelligence",
    response_model=LeadIntelligence,
    summary="Get the CRM intelligence panel",
    responses=ERROR_RESPONSES,
)
async def get_intelligence(lead_id: str, db: DbDep, response: Response) -> LeadIntelligence:
    await lead_service.get_lead(db, lead_id)
    intelligence = await lead_service.get_lead_intelligence(db, lead_id)
    if intelligence:
        set_etag(response, intelligence)
    return LeadIntelligence.model_validate(intelligence or {"lead_id": lead_id})


@router.patch(
    "/{lead_id}/intelligence",
    response_model=LeadIntelligence,
    summary="Update the CRM intelligence panel",
    description=(
        "Partners may read this panel but not edit it. Decision-maker seniority feeds the "
        "priority score, so the active pursuit is rescored afterwards."
    ),
    responses=ERROR_RESPONSES,
)
async def update_intelligence(
    lead_id: str,
    body: LeadIntelligenceUpdate,
    db: DbDep,
    response: Response,
    user: CurrentUserDep,
    if_match: IfMatchDep,
    _guard: Annotated[dict, Depends(require_permission("lead_intelligence.write"))],
) -> LeadIntelligence:
    changes = body.changes()
    if not changes:
        return await get_intelligence(lead_id, db, response)

    changes["updated_by"] = user.sub
    # Keyed by lead_id, not id: this panel is 1:1 with its lead. Without the guard, two reps
    # editing the free-text strategy notes silently overwrite each other -- the most
    # collision-prone field in the product, and the one this route used to leave unprotected
    # while still advertising a version/ETag.
    updated = await update_guarded(
        db,
        "lead_intelligence",
        record_id=lead_id,
        changes=changes,
        if_match=if_match,
        what="Lead intelligence",
        id_column="lead_id",
    )
    set_etag(response, updated)

    pursuits = await db.select(
        "opportunities",
        params={"select": "*", "lead_id": f"eq.{lead_id}", "status": "eq.active", "limit": "1"},
    )
    active = pursuits.first()
    if active is not None:
        await lead_service.sync_opportunity_score(db, active, intelligence=updated)

    return LeadIntelligence.model_validate(updated)


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
        "actor_type": "user",
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
async def create_lead_task(lead_id: str, body: TaskCreate, db: DbDep, user: CurrentUserDep) -> Task:
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


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a lead",
    description=(
        "A soft delete. The lead and everything hanging off it -- pursuits, activities, "
        "tasks, meetings, proposals -- disappear from queries but are retained: a hard "
        "delete would cascade and erase the deal's entire commercial history."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_lead(lead_id: str, db: DbDep, if_match: IfMatchDep) -> Response:
    await soft_delete_guarded(
        db,
        "leads",
        record_id=lead_id,
        if_match=if_match,
        what="Lead",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
