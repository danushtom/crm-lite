"""Tenant (organization) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel, PatchModel


class Organization(APIModel):
    id: str
    name: str
    slug: str | None = None
    created_at: datetime | None = None
    ai_calling_compliance_ack_at: datetime | None = Field(
        default=None,
        description="Set once an admin has acknowledged the AI calling compliance terms.",
    )


class OrganizationUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
