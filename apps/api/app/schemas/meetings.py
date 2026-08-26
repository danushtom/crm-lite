"""Meeting schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import MeetingOutcome, MeetingStatus
from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class Meeting(APIModel):
    id: str
    lead_id: str | None = None
    owner_id: str
    title: str
    google_event_id: str | None = None
    google_meet_link: str | None = None
    scheduled_at: datetime
    duration_minutes: int = 30
    status: MeetingStatus = MeetingStatus.SCHEDULED
    outcome: MeetingOutcome | None = None
    outcome_notes: str | None = None
    created_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class MeetingCreate(StrictAPIModel):
    title: str = Field(min_length=1, max_length=300)
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=8 * 60)
    google_event_id: str | None = Field(default=None, max_length=200)
    google_meet_link: str | None = Field(default=None, max_length=500)


class MeetingOutcomeUpdate(StrictAPIModel):
    """Recording an outcome may auto-create a follow-up task (see tdd.md 14.2)."""

    outcome: MeetingOutcome
    outcome_notes: str | None = Field(default=None, max_length=5_000)
    status: MeetingStatus = MeetingStatus.COMPLETED


class MeetingOutcomeResult(APIModel):
    meeting: Meeting
    followup_task_id: str | None = Field(
        default=None,
        description="Id of the follow-up task created by this outcome, when one was triggered.",
    )


class MeetingUpdate(PatchModel):
    """Reschedule or amend a meeting. Recording an *outcome* has its own endpoint."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=8 * 60)
    status: MeetingStatus | None = None
    google_meet_link: str | None = Field(default=None, max_length=500)
