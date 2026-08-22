"""Follow-up task schemas."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import Field, model_validator

from app.domain.enums import TaskStatus
from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class Task(APIModel):
    id: str
    lead_id: str
    owner_id: str
    title: str
    notes: str | None = None
    due_date: date
    due_time: time | None = None
    status: TaskStatus = TaskStatus.PENDING
    outcome_note: str | None = None
    snoozed_until: date | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None


class TaskCreate(StrictAPIModel):
    title: str = Field(min_length=1, max_length=300)
    due_date: date
    notes: str | None = Field(default=None, max_length=5_000)
    due_time: time | None = None


class TaskUpdate(PatchModel):
    status: TaskStatus | None = None
    due_date: date | None = None
    due_time: time | None = None
    snoozed_until: date | None = None
    outcome_note: str | None = Field(default=None, max_length=2_000)
    notes: str | None = Field(default=None, max_length=5_000)
    title: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def _snooze_requires_date(self) -> "TaskUpdate":
        fields = self.model_fields_set
        if self.status is TaskStatus.SNOOZED and "snoozed_until" not in fields:
            raise ValueError("snoozed_until is required when setting status to 'snoozed'")
        return self


class FollowUpQueues(APIModel):
    """``GET /dashboard/follow-ups`` -- the three queues the follow-up engine drives."""

    today: list[Task] = Field(description="Pending tasks due today.")
    overdue: list[Task] = Field(description="Pending tasks whose due date has passed.")
    upcoming: list[Task] = Field(description="Tasks due within the next 14 days.")
