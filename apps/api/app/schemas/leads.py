"""Lead, lead-intelligence and activity schemas.

A lead is a *qualification* record: who the prospect is, where they came from, what kind of
work they want, and when to follow up. Pipeline position and commercials belong to its
opportunities (see :mod:`app.schemas.opportunities`), of which a lead may have several.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.domain.enums import ActivityType, CommPreference, LeadSource, LeadStage, ProjectType
from app.schemas.common import APIModel, Money, PatchModel, StrictAPIModel
from app.schemas.companies import Company


class InitialOpportunity(StrictAPIModel):
    """Commercials for the pursuit opened alongside a new lead.

    Creating a lead always opens its first opportunity; this lets the caller populate it in
    the same request instead of following up with a PATCH.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    stage: LeadStage = LeadStage.PROSPECT
    quoted_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    deal_probability: int = Field(default=50, ge=0, le=100)


class LeadCreate(StrictAPIModel):
    company_id: str = Field(description="Company this lead belongs to.")
    project_type: ProjectType
    lead_source: LeadSource
    primary_contact_id: str | None = None
    owner_id: str | None = Field(
        default=None, description="Defaults to the authenticated user when omitted."
    )
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    tags: list[str] = Field(default_factory=list, max_length=25)
    opportunity: InitialOpportunity | None = Field(
        default=None,
        description="Commercials for the initial pursuit. Defaults are used when omitted.",
    )


class LeadUpdate(PatchModel):
    company_id: str | None = None
    primary_contact_id: str | None = None
    owner_id: str | None = None
    project_type: ProjectType | None = None
    lead_source: LeadSource | None = None
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    tags: list[str] | None = Field(default=None, max_length=25)


class Lead(APIModel):
    id: str
    company_id: str
    primary_contact_id: str | None = None
    owner_id: str
    project_type: ProjectType
    lead_source: LeadSource
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    no_touch_alert: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class LeadOpportunity(APIModel):
    """A lead's pursuit, as embedded in lead responses."""

    id: str
    title: str
    stage: LeadStage
    status: str
    quoted_value: Money | None = None
    currency: str = "INR"
    deal_probability: int = 50
    priority_score: int = 0
    updated_at: datetime | None = None


class LeadWithCompany(Lead):
    """List representation: company embedded, plus every pursuit against this lead.

    Pipeline position is read from ``opportunities`` rather than duplicated onto the lead.
    """

    companies: Company | None = None
    opportunities: list[LeadOpportunity] = Field(default_factory=list)


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
    performed_by: str | None = Field(
        default=None, description="Null for actions taken by the system rather than a person."
    )
    actor_type: str = Field(default="user", description="'user' or 'system'.")
    performed_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class ActivityCreate(StrictAPIModel):
    type: ActivityType
    description: str = Field(min_length=1, max_length=5_000)
    outcome: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] | None = None


class LeadDetail(APIModel):
    """``GET /leads/{id}`` -- the lead, its intelligence panel and its pursuits."""

    lead: Lead
    lead_intelligence: LeadIntelligence | None = None
    opportunities: list[LeadOpportunity] = Field(default_factory=list)
    activities: list[Activity] | None = Field(
        default=None, description="Present only when include_related=true."
    )
    recent_tasks: list[dict[str, Any]] | None = Field(
        default=None, description="Present only when include_related=true."
    )
