"""Opportunity and proposal schemas.

An opportunity is a *pursuit* against a lead: its pipeline stage, commercials, scope and
proposal history. A lead may have several over time -- the build, then the retainer -- of
which at most one is active. Nothing here is mirrored onto the lead.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.domain.enums import (
    LeadSource,
    LeadStage,
    OpportunityStatus,
    ProjectType,
    ProposalStatus,
)
from app.schemas.common import APIModel, Money, PatchModel, StrictAPIModel
from app.schemas.companies import Company


class OpportunityOpen(StrictAPIModel):
    """Body for opening a further pursuit against an existing lead."""

    title: str = Field(min_length=1, max_length=200)
    stage: LeadStage = LeadStage.PROSPECT
    quoted_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    deal_probability: int = Field(default=50, ge=0, le=100)
    timeline_weeks: int | None = Field(default=None, ge=0, le=520)
    tech_stack: str | None = Field(default=None, max_length=5_000)


class OpportunityUpdate(PatchModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    quoted_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(
        default=None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$"
    )
    timeline_weeks: int | None = Field(default=None, ge=0, le=520)
    tech_stack: str | None = Field(default=None, max_length=5_000)
    requirements_doc: str | None = Field(default=None, max_length=50_000)
    architecture_notes: str | None = Field(default=None, max_length=50_000)
    status: OpportunityStatus | None = None
    stage: LeadStage | None = None
    deal_probability: int | None = Field(default=None, ge=0, le=100)
    score_override: int | None = Field(
        default=None, ge=0, le=100, description="Pins priority_score, bypassing the scoring model."
    )
    score_override_reason: str | None = Field(default=None, max_length=500)


class Proposal(APIModel):
    id: str
    opportunity_id: str
    version: int
    title: str
    file_url: str | None = None
    figma_url: str | None = None
    github_url: str | None = None
    loom_url: str | None = None
    quoted_price: Money | None = None
    change_notes: str | None = None
    status: ProposalStatus = ProposalStatus.DRAFT
    sent_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProposalCreate(StrictAPIModel):
    title: str = Field(min_length=1, max_length=200)
    figma_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    loom_url: str | None = Field(default=None, max_length=500)
    quoted_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    change_notes: str | None = Field(default=None, max_length=5_000)
    status: ProposalStatus = ProposalStatus.DRAFT


class Opportunity(APIModel):
    id: str
    lead_id: str
    owner_id: str
    title: str
    stage: LeadStage
    quoted_value: Money | None = None
    currency: str = "INR"
    deal_probability: int = 50
    priority_score: int = 0
    score_override: int | None = None
    score_override_reason: str | None = None
    timeline_weeks: int | None = None
    tech_stack: str | None = None
    requirements_doc: str | None = None
    architecture_notes: str | None = None
    status: OpportunityStatus = OpportunityStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class OpportunityDetail(Opportunity):
    """``GET /opportunities/{id}`` -- includes the full versioned proposal history."""

    proposals: list[Proposal] = Field(default_factory=list)


class OpportunityLead(APIModel):
    """The qualification record behind a pursuit, as embedded in board rows.

    Carries no stage or commercials: those belong to the opportunity itself.
    """

    id: str
    company_id: str
    primary_contact_id: str | None = None
    owner_id: str
    project_type: ProjectType
    lead_source: LeadSource
    last_contact_date: date | None = None
    next_followup_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    companies: Company | None = None


class OpportunityWithLead(Opportunity):
    """Kanban board row: the pursuit plus the lead and company it belongs to."""

    leads: OpportunityLead | None = None


class OpportunitySummary(APIModel):
    """Light projection used for lead -> opportunity deep links."""

    id: str
    lead_id: str
    title: str
    status: OpportunityStatus
    stage: LeadStage
    quoted_value: Money | None = None
    currency: str = "INR"
    deal_probability: int = 50
    priority_score: int = 0
    updated_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )
