"""Request and response shapes for the AI endpoints.

See supabase/migrations/20260918000000_ai_features.sql. Nothing here accepts CRM data from the
client: the assistant reads the CRM itself, through the caller's own RLS-scoped connection. That
is deliberate -- the previous Next.js implementation took a context blob from the browser, which
let the caller choose what the model saw. See app/services/ai/assistant_tools.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel, StrictAPIModel


class ChatMessage(StrictAPIModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class ChatRequest(StrictAPIModel):
    """A conversation so far. There is no `context` field, and that is the point."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ProposalDraftRequest(StrictAPIModel):
    #: Overrides the price the model would otherwise leave as a placeholder. The founder usually
    #: knows the number before the prose.
    quoted_price: float | None = Field(default=None, ge=0)


class ProposalDraftResponse(APIModel):
    proposal_id: str
    version: int
    title: str
    markdown: str = Field(description="The full draft, for the editor to load")
    tokens_used: int


class AiUsageEntry(APIModel):
    feature: str
    model: str
    total_tokens: int
    cost_usd: float
    created_at: datetime | None = None


class AiUsageSummary(APIModel):
    """This organization's month-to-date spend."""

    month_start: datetime
    total_tokens: int
    total_cost_usd: float
    monthly_token_budget: int = Field(
        description="0 means no ceiling is configured (AI_MONTHLY_TOKEN_BUDGET)"
    )
    budget_remaining: int | None = Field(
        default=None, description="Null when no ceiling is configured"
    )
    by_feature: list[AiUsageEntry] = Field(default_factory=list)


class AiStatus(APIModel):
    """Whether AI features can do real work in this deployment."""

    enabled: bool
    configured: bool
    research_configured: bool = Field(
        default=False, description="Web research needs EXA_API_KEY in addition to the AI settings"
    )
    detail: str


class DealHealthSnapshot(APIModel):
    """One opportunity's most recent at-risk assessment."""

    opportunity_id: str
    opportunity_title: str | None = None
    company_name: str | None = None
    risk_level: Literal["low", "medium", "high"]
    reasons: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    assessed_by_model: bool = Field(
        default=False,
        description=(
            "False means the deterministic gate cleared it without a model call -- "
            "'nothing looked wrong', not 'a model considered this and cleared it'"
        ),
    )
    generated_at: datetime | None = None


class CitedFact(APIModel):
    value: str
    source_url: str


class ResearchSource(APIModel):
    index: int
    title: str
    url: str
    published_date: str | None = None


class CompanyProfileOut(APIModel):
    """What research found. Every fact carries the URL it came from."""

    description: CitedFact | None = None
    industry: CitedFact | None = None
    size: CitedFact | None = None
    segment: CitedFact | None = None
    location: CitedFact | None = None
    linkedin_url: CitedFact | None = None
    recent_news: list[CitedFact] = Field(default_factory=list)
    tech_signals: list[CitedFact] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    suspicious_content: bool = False
    note: str | None = None


class FieldSuggestion(APIModel):
    field: Literal["industry", "size", "segment", "location", "linkedin_url"]
    current: str | None = None
    suggested: str
    source_url: str
    overwrites: bool = Field(description="True if accepting this replaces a value a person entered")


class CompanyResearchOut(APIModel):
    """Research plus suggested edits. Nothing here has been written to the company -- applying
    a suggestion goes through PATCH /companies/{id}, with its version check."""

    research_id: str
    company_id: str
    company_version: int = Field(description="Send back as If-Match when applying suggestions")
    profile: CompanyProfileOut
    suggestions: list[FieldSuggestion] = Field(default_factory=list)
    researched_at: datetime | None = None
    from_cache: bool = False


class ResearchRequest(StrictAPIModel):
    force: bool = Field(default=False, description="Re-run even if recent research exists")


class LeadBriefBody(APIModel):
    summary: str
    why_now: str = ""
    talking_points: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class LeadBriefOut(APIModel):
    brief_id: str
    lead_id: str
    brief: LeadBriefBody
    research_id: str | None = None
    created_at: datetime | None = None
