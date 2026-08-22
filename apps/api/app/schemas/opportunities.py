"""Opportunity and proposal schemas.

The pipeline (Kanban) lives on ``opportunities`` -- one row per lead -- with ``leads`` kept in
sync by a database trigger. See ``supabase/migrations/20260429140000_opportunities_pipeline.sql``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.domain.enums import LeadStage, OpportunityStatus, ProposalStatus
from app.schemas.common import APIModel, Money, PatchModel, StrictAPIModel
from app.schemas.leads import LeadWithCompany


class OpportunityUpdate(PatchModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    quoted_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timeline_weeks: int | None = Field(default=None, ge=0, le=520)
    tech_stack: str | None = Field(default=None, max_length=5_000)
    requirements_doc: str | None = Field(default=None, max_length=50_000)
    architecture_notes: str | None = Field(default=None, max_length=50_000)
    status: OpportunityStatus | None = None
    stage: LeadStage | None = None
    deal_probability: int | None = Field(default=None, ge=0, le=100)
    priority_score: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = Field(default=None, max_length=25)


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
    tags: list[str] = Field(default_factory=list)
    timeline_weeks: int | None = None
    tech_stack: str | None = None
    requirements_doc: str | None = None
    architecture_notes: str | None = None
    status: OpportunityStatus = OpportunityStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OpportunityDetail(Opportunity):
    """``GET /opportunities/{id}`` -- includes the full versioned proposal history."""

    proposals: list[Proposal] = Field(default_factory=list)


class OpportunityWithLead(Opportunity):
    """Kanban board row: opportunity plus its lead and that lead's company."""

    leads: LeadWithCompany | None = None


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


class LeadConversion(APIModel):
    """Result of promoting a lead to a tracked opportunity."""

    opportunity: Opportunity
    lead: "LeadRef"


class LeadRef(APIModel):
    id: str
    is_opportunity: bool = True
    stage: LeadStage | None = None


LeadConversion.model_rebuild()
