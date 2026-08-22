"""In-app notification schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel, StrictAPIModel


class Notification(APIModel):
    id: str
    user_id: str
    type: str = Field(description="Producer-defined category, e.g. 'followup_reminder'.")
    title: str
    body: str | None = None
    metadata: dict[str, Any] | None = None
    read_at: datetime | None = Field(default=None, description="Null while unread.")
    created_at: datetime | None = None
    source_task_id: str | None = None
    meeting_id: str | None = None


class NotificationUpdate(StrictAPIModel):
    read: bool = Field(default=True, description="Set true to mark the notification read.")


class NotificationReadResult(APIModel):
    updated: int = Field(description="Number of notifications transitioned to read.")
