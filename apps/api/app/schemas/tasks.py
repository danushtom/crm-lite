"""Follow-up task schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.domain.enums import TaskStatus
from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class Task(APIModel):
    id: str
    lead_id: str
    owner_id: str
    title: str
    notes: str | None = None
    due_at: datetime = Field(
        description="When the follow-up is due, as an absolute instant. Render in the owner's timezone."
    )
    status: TaskStatus = TaskStatus.PENDING
    outcome_note: str | None = None
    snoozed_to: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class TaskCreate(StrictAPIModel):
    title: str = Field(min_length=1, max_length=300)
    due_at: datetime = Field(description="Absolute instant the follow-up falls due.")
    notes: str | None = Field(default=None, max_length=5_000)


class TaskUpdate(PatchModel):
    status: TaskStatus | None = None
    due_at: datetime | None = None
    snoozed_to: datetime | None = None
    outcome_note: str | None = Field(default=None, max_length=2_000)
    notes: str | None = Field(default=None, max_length=5_000)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    owner_id: str | None = Field(
        default=None,
        description=(
            "Reassign the follow-up to another teammate. Leads are reassignable, so without "
            "this, deactivating someone moved their pipeline but stranded every task they "
            "owned -- invisible in every queue, since the follow-up queues are owner-scoped."
        ),
    )

    @model_validator(mode="after")
    def _snooze_requires_date(self) -> "TaskUpdate":
        fields = self.model_fields_set
        if self.status is TaskStatus.SNOOZED and "snoozed_to" not in fields:
            raise ValueError("snoozed_to is required when setting status to 'snoozed'")
        return self


class FollowUpQueues(APIModel):
    """``GET /dashboard/follow-ups`` -- the three queues the follow-up engine drives."""

    today: list[Task] = Field(description="Tasks due today in the caller's timezone.")
    overdue: list[Task] = Field(
        description="Pending tasks whose due instant is before today began, in the caller's timezone."
    )
    upcoming: list[Task] = Field(
        description="Pending tasks due from tomorrow through the next 14 days."
    )
    timezone: str = Field(description="IANA zone these day boundaries were computed in.")
