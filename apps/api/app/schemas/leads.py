"""Lead, lead-intelligence and activity schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.domain.enums import ActivityType, CommPreference, LeadSource, LeadStage, ProjectType
from app.schemas.common import APIModel, Money, PatchModel, StrictAPIModel
from app.schemas.companies import Company


class LeadCreate(StrictAPIModel):
    company_id: str = Field(description="Company this lead belongs to.")
    project_type: ProjectType
    lead_source: LeadSource
    primary_contact_id: str | None = None
    owner_id: str | None = Field(
        default=None, description="Defaults to the authenticated user when omitted."
    )
    stage: LeadStage = LeadStage.PROSPECT
    estimated_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    deal_probability: int = Field(default=50, ge=0, le=100)
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    tags: list[str] = Field(default_factory=list, max_length=25)


class LeadUpdate(PatchModel):
    company_id: str | None = None
    primary_contact_id: str | None = None
    owner_id: str | None = None
    stage: LeadStage | None = None
    project_type: ProjectType | None = None
    lead_source: LeadSource | None = None
    estimated_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    deal_probability: int | None = Field(default=None, ge=0, le=100)
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    tags: list[str] | None = Field(default=None, max_length=25)
    is_opportunity: bool | None = None
    score_override: int | None = Field(
        default=None, ge=0, le=100, description="Pins priority_score, bypassing the scoring model."
    )
    score_override_reason: str | None = Field(default=None, max_length=500)


class LeadStageUpdate(StrictAPIModel):
    stage: LeadStage = Field(description="Target pipeline stage.")


class Lead(APIModel):
    id: str
    company_id: str
    primary_contact_id: str | None = None
    owner_id: str
    stage: LeadStage
    project_type: ProjectType
    lead_source: LeadSource
    estimated_value: Money | None = None
    currency: str = "INR"
    deal_probability: int = 50
    priority_score: int = 0
    score_override: int | None = None
    score_override_reason: str | None = None
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    is_opportunity: bool = False
    tags: list[str] = Field(default_factory=list)
    no_touch_alert: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class LeadWithCompany(Lead):
    """List representation with the company embedded."""

    companies: Company | None = None


class LeadIntelligence(APIModel):
    id: str | None = None
    lead_id: str
    pain_points: str | None = None
    tech_stack: str | None = None
    budget_hints: str | None = None
    decision_makers: str | None = None
    competitors_involved: str | None = None
    objections_raised: str | None = None
    strategic_notes: str | None = None
    comm_preference: CommPreference | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class LeadIntelligenceUpdate(PatchModel):
    pain_points: str | None = Field(default=None, max_length=10_000)
    tech_stack: str | None = Field(default=None, max_length=5_000)
    budget_hints: str | None = Field(default=None, max_length=5_000)
    decision_makers: str | None = Field(default=None, max_length=5_000)
    competitors_involved: str | None = Field(default=None, max_length=5_000)
    objections_raised: str | None = Field(default=None, max_length=10_000)
    strategic_notes: str | None = Field(default=None, max_length=20_000)
    comm_preference: CommPreference | None = None


class Activity(APIModel):
    id: str
    lead_id: str
    type: ActivityType
    description: str
    outcome: str | None = None
    performed_by: str
    performed_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class ActivityCreate(StrictAPIModel):
    type: ActivityType
    description: str = Field(min_length=1, max_length=5_000)
    outcome: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] | None = None


class LeadDetail(APIModel):
    """``GET /leads/{id}`` -- the lead plus its intelligence panel and, optionally, related records."""

    lead: Lead
    lead_intelligence: LeadIntelligence | None = None
    activities: list[Activity] | None = Field(
        default=None, description="Present only when include_related=true."
    )
    recent_tasks: list[dict[str, Any]] | None = Field(
        default=None, description="Present only when include_related=true."
    )
