"""Company research and pre-call briefs: the parts that need a database and a tenant.

The graphs in ``dracara_ai.graphs.research`` are pure. This module:

* **Proves access before spending anything.** Every entry point first reads the company or lead
  through ``db`` -- the caller's own RLS-scoped client. A record the caller cannot see resolves to
  404 here, before a single search is billed, and its name never reaches the search provider.
* **Sends only public identifiers out.** The company's name and website go to web search; nothing
  else from the CRM does. CRM facts go to the model provider for the brief, as they already do for
  every other AI feature, but never to the search provider.
* **Writes with the service role, org derived by trigger.** ``company_research`` and
  ``lead_briefs`` have no write policy for ``authenticated``; their ``organization_id`` is set by
  ``set_parent_organization()`` from the company or lead, overwriting whatever was sent.
* **Never edits the company.** Research returns *suggestions*. Applying one goes through the
  ordinary ``PATCH /companies/{id}`` endpoint with its version check, pressed by a person.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from dracara_ai.config import ai_settings
from dracara_ai.graphs import research as research_graph
from dracara_ai.graphs.research import BriefInput, CompanyProfile, LeadBrief
from dracara_ai.usage import UsageRecord

from app.core.errors import NotFoundError
from app.db.supabase import SupabaseAdminClient, SupabaseClient

logger = logging.getLogger(__name__)

#: Profile fields that map one-to-one onto a `companies` column, and so can be offered as a
#: suggested edit. `description`, news and tech signals are shown but have no column to fill.
SUGGESTIBLE_FIELDS = ("industry", "size", "segment", "location", "linkedin_url")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _visible_company(db: SupabaseClient, company_id: str) -> dict[str, Any]:
    result = await db.select(
        "companies",
        params={
            "select": "id,name,website,industry,size,segment,location,linkedin_url,version",
            "id": f"eq.{company_id}",
            "deleted_at": "is.null",
        },
    )
    company = result.first()
    if company is None:
        raise NotFoundError("Company not found")
    return company


async def latest_research(db: SupabaseClient, company_id: str) -> dict[str, Any] | None:
    """Newest stored research, read through the caller's RLS (visibility follows the company)."""
    result = await db.select(
        "company_research",
        params={
            "select": "id,profile,suspicious_content,created_at",
            "company_id": f"eq.{company_id}",
            "order": "created_at.desc,id.desc",
            "limit": "1",
        },
    )
    return result.first()


def suggestions(company: dict[str, Any], profile: CompanyProfile) -> list[dict[str, Any]]:
    """Fields research could fill or would change, for a person to accept or ignore."""
    out = []
    for field in SUGGESTIBLE_FIELDS:
        fact = getattr(profile, field)
        if fact is None:
            continue
        current = company.get(field)
        if current and str(current).strip().lower() == fact.value.strip().lower():
            continue
        out.append(
            {
                "field": field,
                "current": current,
                "suggested": fact.value,
                "source_url": fact.source_url,
                # Filling a blank is low-risk; overwriting something a person typed is not, and
                # the UI defaults the checkbox accordingly.
                "overwrites": bool(current),
            }
        )
    return out


async def research_company(
    db: SupabaseClient,
    admin_db: SupabaseAdminClient,
    *,
    company_id: str,
    requested_by: str,
    force: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], UsageRecord | None]:
    """Return (company, stored research row, usage-or-None-if-served-from-cache)."""
    company = await _visible_company(db, company_id)

    if not force:
        existing = await latest_research(db, company_id)
        created = _parse(existing.get("created_at")) if existing else None
        if created and datetime.now(timezone.utc) - created < timedelta(days=ai_settings.research_ttl_days):
            return company, existing, None

    # Name and website only -- see the module docstring.
    profile, usage = await research_graph.research_company(
        company_name=company["name"], website=company.get("website")
    )

    inserted = await admin_db.insert(
        "company_research",
        {
            "company_id": company_id,
            "profile": profile.model_dump(),
            "suspicious_content": profile.suspicious_content,
            "requested_by": requested_by,
        },
    )
    row = inserted.one("Company research")
    if profile.suspicious_content:
        logger.warning("research_suspicious_content company_id=%s", company_id)
    return company, row, usage


async def brief_lead(
    db: SupabaseClient,
    admin_db: SupabaseAdminClient,
    *,
    lead_id: str,
    requested_by: str,
) -> tuple[dict[str, Any], list[UsageRecord]]:
    """Write a pre-call brief for a lead the caller can see. Returns (stored row, usages)."""
    lead_result = await db.select(
        "leads",
        params={
            "select": "id,project_type,company_id,primary_contact_id,"
            "opportunities(stage,status,quoted_value,currency,deleted_at)",
            "id": f"eq.{lead_id}",
            "deleted_at": "is.null",
        },
    )
    lead = lead_result.first()
    if lead is None:
        raise NotFoundError("Lead not found")

    usages: list[UsageRecord] = []
    company, research_row, research_usage = await research_company(
        db, admin_db, company_id=lead["company_id"], requested_by=requested_by
    )
    if research_usage is not None:
        usages.append(research_usage)

    contact = None
    if lead.get("primary_contact_id"):
        contact = (
            await db.select(
                "contacts",
                params={"select": "full_name,role", "id": f"eq.{lead['primary_contact_id']}"},
            )
        ).first()

    intelligence = (
        await db.select("lead_intelligence", params={"select": "*", "lead_id": f"eq.{lead_id}"})
    ).first() or {}
    activities = (
        await db.select(
            "activities",
            params={
                "select": "type,description,created_at",
                "lead_id": f"eq.{lead_id}",
                "order": "created_at.desc,id.desc",
                "limit": "8",
            },
        )
    ).rows

    live = [o for o in (lead.get("opportunities") or []) if not o.get("deleted_at")]
    active = next((o for o in live if o.get("status") == "active"), live[0] if live else None)
    deal_value = None
    if active and active.get("quoted_value") is not None:
        deal_value = f"{float(active['quoted_value']):,.0f} {active.get('currency') or 'INR'}"

    data = BriefInput(
        company_name=company["name"],
        contact_name=(contact or {}).get("full_name"),
        contact_role=(contact or {}).get("role"),
        stage=(active or {}).get("stage"),
        deal_value=deal_value,
        project_type=lead.get("project_type"),
        intelligence={
            k: v
            for k, v in intelligence.items()
            if k not in ("id", "lead_id", "organization_id", "created_at", "updated_at", "version")
            and v
        },
        recent_activity=[
            f"{(a.get('created_at') or '')[:10]} {a.get('type')}: {(a.get('description') or '')[:200]}"
            for a in activities
        ],
        research=CompanyProfile.model_validate(research_row["profile"]),
    )
    brief, brief_usage = await research_graph.brief_lead(data)
    usages.append(brief_usage)

    inserted = await admin_db.insert(
        "lead_briefs",
        {
            "lead_id": lead_id,
            "brief": brief.model_dump(),
            "research_id": research_row.get("id"),
            "requested_by": requested_by,
        },
    )
    return inserted.one("Lead brief"), usages


async def latest_brief(db: SupabaseClient, lead_id: str) -> dict[str, Any] | None:
    result = await db.select(
        "lead_briefs",
        params={
            "select": "id,brief,research_id,created_at",
            "lead_id": f"eq.{lead_id}",
            "order": "created_at.desc,id.desc",
            "limit": "1",
        },
    )
    return result.first()


__all__ = [
    "LeadBrief",
    "brief_lead",
    "latest_brief",
    "latest_research",
    "research_company",
    "suggestions",
]
