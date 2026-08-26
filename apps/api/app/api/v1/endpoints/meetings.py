"""Meeting endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep
from app.core.concurrency import IfMatchDep, set_etag, update_guarded
from app.core.errors import ForbiddenError
from app.core.pagination import Page, PageParamsDep
from app.domain.enums import MeetingStatus
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.meetings import (
    Meeting,
    MeetingOutcomeResult,
    MeetingOutcomeUpdate,
    MeetingUpdate,
)
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
async def get_meeting(meeting_id: str, db: DbDep, response: Response) -> Meeting:
    result = await db.select("meetings", params={"select": "*", "id": f"eq.{meeting_id}"})
    row = result.one("Meeting")
    set_etag(response, row)
    return Meeting.model_validate(row)


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


@router.patch(
    "/{meeting_id}",
    response_model=Meeting,
    summary="Reschedule or amend a meeting",
    description=(
        "For changing when a meeting happens, how long it runs, or cancelling it. Recording "
        "what came *out* of it is a separate action -- see `PATCH /meetings/{id}/outcome` -- "
        "because that one can schedule follow-up work."
    ),
    responses=ERROR_RESPONSES,
)
async def update_meeting(
    meeting_id: str,
    body: MeetingUpdate,
    db: DbDep,
    response: Response,
    if_match: IfMatchDep,
) -> Meeting:
    changes = MeetingUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        return await get_meeting(meeting_id, db, response)

    row = await update_guarded(
        db, "meetings", record_id=meeting_id, changes=changes, if_match=if_match, what="Meeting"
    )
    set_etag(response, row)
    return Meeting.model_validate(row)


@router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a meeting",
    description=(
        "Removes the meeting outright, for one booked in error. To record that a meeting was "
        "called off, set its status to cancelled instead so it stays on the timeline."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_meeting(meeting_id: str, db: DbDep) -> Response:
    existing = await db.select("meetings", params={"select": "id", "id": f"eq.{meeting_id}"})
    existing.one("Meeting")

    deleted = await db.delete("meetings", {"id": f"eq.{meeting_id}"})
    if deleted.first() is None:
        raise ForbiddenError("You do not have permission to delete this meeting")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
