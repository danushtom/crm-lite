"""Meeting endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep
from app.core.pagination import Page, PageParamsDep
from app.domain.enums import MeetingStatus
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.meetings import Meeting, MeetingOutcomeResult, MeetingOutcomeUpdate
from app.services import meetings as meeting_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


@router.get(
    "",
    response_model=Page[Meeting],
    summary="List meetings",
    description="Meetings visible to the caller, soonest first.",
    responses=AUTH_RESPONSES,
)
async def list_meetings(
    db: DbDep,
    page: PageParamsDep,
    meeting_status: Annotated[MeetingStatus | None, Query(alias="status")] = None,
    scheduled_from: Annotated[
        str | None, Query(description="ISO timestamp lower bound on scheduled_at.")
    ] = None,
    scheduled_to: Annotated[
        str | None, Query(description="ISO timestamp upper bound on scheduled_at.")
    ] = None,
) -> Page[Meeting]:
    params: dict[str, str] = {
        "select": "*",
        "order": "scheduled_at.asc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if meeting_status:
        params["status"] = f"eq.{meeting_status.value}"
    if scheduled_from:
        params["scheduled_at"] = f"gte.{scheduled_from}"
    if scheduled_to:
        # PostgREST needs distinct keys for two bounds on one column.
        params["and"] = f"(scheduled_at.lte.{scheduled_to})"

    result = await db.select("meetings", params=params, count=True)
    return Page.build([Meeting.model_validate(m) for m in result.rows], page, result.count)


@router.get(
    "/{meeting_id}",
    response_model=Meeting,
    summary="Get a meeting",
    responses=ERROR_RESPONSES,
)
async def get_meeting(meeting_id: str, db: DbDep) -> Meeting:
    result = await db.select("meetings", params={"select": "*", "id": f"eq.{meeting_id}"})
    return Meeting.model_validate(result.one("Meeting"))


@router.patch(
    "/{meeting_id}/outcome",
    response_model=MeetingOutcomeResult,
    summary="Record a meeting outcome",
    description=(
        "Outcomes of 'needs_proposal' or 'followup_later' automatically schedule a follow-up "
        "task two days out; the created task id is returned."
    ),
    responses=ERROR_RESPONSES,
)
async def record_outcome(
    meeting_id: str,
    body: MeetingOutcomeUpdate,
    db: DbDep,
    user: CurrentUserDep,
) -> MeetingOutcomeResult:
    changes = body.model_dump(exclude_none=True, mode="json")
    meeting, task_id = await meeting_service.record_outcome(
        db, meeting_id, changes, owner_id=user.sub
    )
    return MeetingOutcomeResult(meeting=Meeting.model_validate(meeting), followup_task_id=task_id)
