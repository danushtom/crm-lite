"""Gather a deal's context, draft a proposal, persist it as a new draft version.

The graph in ``dracara_ai.graphs.proposal_draft`` is pure -- it cannot read the CRM and cannot
resolve a tenant. This module is the half that can: it reads through the caller's own RLS-scoped
client (so a rep cannot draft against a deal they are not allowed to see), pulls reference
material out of the knowledge base with an explicit organization id, and writes the result back
through the existing ``proposals.create_version`` rather than inventing a second write path.

The output is always a **draft**. `proposal_status` defaults to 'draft', nothing here sets
`sent_at`, and the founder edits before anything reaches a client. That is the whole product
claim: 3x faster to a first draft, not proposals sent without a human reading them.
"""

from __future__ import annotations

import logging
from typing import Any

from dracara_ai.graphs import proposal_draft
from dracara_ai.graphs.proposal_draft import ProposalContext, ProposalDraft
from dracara_ai.usage import UsageRecord

from app.core.errors import NotFoundError
from app.db.supabase import SupabaseClient
from app.services import leads as lead_service
from app.services import proposals as proposal_service
from app.services.ai import knowledge_base

logger = logging.getLogger(__name__)

_OPPORTUNITY_SELECT = (
    "id,lead_id,title,stage,status,quoted_value,currency,timeline_weeks,tech_stack,"
    "requirements_doc,architecture_notes,"
    "leads(id,project_type,company_id,companies(name,industry,segment))"
)


async def _reference_material(
    db: SupabaseClient, organization_id: str, query: str
) -> list[str]:
    """Pull pricing sheets and past scopes out of the knowledge base, if any agent has one.

    Best-effort by design: a proposal drafted without reference material is still useful (the
    prompt is told to leave visible ``[CONFIRM: ...]`` placeholders), whereas failing the whole
    request because Qdrant is down would not be.
    """
    try:
        agents = await db.select(
            "voice_agents",
            params={"select": "id", "deleted_at": "is.null", "limit": "5"},
        )
        passages: list[str] = []
        for agent in agents.rows:
            found = await knowledge_base.search(
                organization_id=organization_id,
                voice_agent_id=agent["id"],
                query=query,
                limit=3,
            )
            passages.extend(p["text"] for p in found)
        return passages[:8]
    except Exception:
        logger.info("proposal_draft_reference_lookup_failed org_id=%s", organization_id)
        return []


async def draft_for_opportunity(
    db: SupabaseClient,
    *,
    opportunity_id: str,
    organization_id: str,
) -> tuple[ProposalDraft, dict[str, Any], UsageRecord]:
    """Draft a proposal for one opportunity. Returns (draft, opportunity row, usage).

    Reads through ``db`` -- the caller's scoped client -- so an opportunity the user cannot see
    resolves to a 404 here rather than being drafted against.
    """
    result = await db.select(
        "opportunities",
        params={
            "select": _OPPORTUNITY_SELECT,
            "id": f"eq.{opportunity_id}",
            "deleted_at": "is.null",
        },
    )
    opportunity = result.first()
    if opportunity is None:
        raise NotFoundError("Opportunity not found")

    lead = opportunity.get("leads") or {}
    company = (lead.get("companies") or {}) if isinstance(lead, dict) else {}
    intelligence = (
        await lead_service.get_lead_intelligence(db, lead["id"]) if lead.get("id") else None
    ) or {}

    # The requirements panel is free text; split it into lines so the model sees a list rather
    # than one wall of prose it has to re-parse.
    requirements = [
        line.strip("-* \t")
        for line in (opportunity.get("requirements_doc") or "").splitlines()
        if line.strip()
    ]

    company_name = company.get("name") if isinstance(company, dict) else None
    reference = await _reference_material(
        db,
        organization_id,
        query=f"pricing and delivery approach for a {lead.get('project_type') or 'software'} project",
    )

    context = ProposalContext(
        company_name=company_name,
        project_type=lead.get("project_type") if isinstance(lead, dict) else None,
        estimated_value=float(opportunity["quoted_value"])
        if opportunity.get("quoted_value") is not None
        else None,
        currency=opportunity.get("currency") or "INR",
        stage=opportunity.get("stage"),
        intelligence={
            k: v
            for k, v in intelligence.items()
            if k not in ("id", "lead_id", "organization_id", "created_at", "updated_at") and v
        },
        requirements=requirements,
        reference_material=reference,
    )

    draft, usage = await proposal_draft.run(context)
    return draft, opportunity, usage


async def persist_draft(
    db: SupabaseClient,
    *,
    opportunity_id: str,
    draft: ProposalDraft,
    created_by: str,
    quoted_price: float | None,
) -> dict[str, Any]:
    """Write the draft as the next proposal version.

    Goes through ``proposals.create_version`` so it inherits that function's unique-violation
    retry: two people pressing "Draft with AI" at once must not collide on a version number.
    """
    return await proposal_service.create_version(
        db,
        opportunity_id,
        {
            "title": draft.title,
            "change_notes": "First draft generated by AI. Review before sending.",
            "quoted_price": quoted_price,
            "ai_generated": True,
            "ai_draft_markdown": draft.to_markdown(),
        },
        created_by,
    )
