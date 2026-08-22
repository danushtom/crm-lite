"""Lead business logic: scoring propagation, pipeline writes and conversion.

The pipeline lives on ``opportunities`` while ``leads`` carries mirrored columns kept current
by the ``opportunities_sync_lead`` trigger. Callers therefore must write pipeline fields to the
opportunity, never to the lead -- :func:`update_lead` encapsulates that split so endpoints do
not have to know about it.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.errors import ConflictError, NotFoundError
from app.db.supabase import SupabaseClient
from app.domain.scoring import compute_priority_score

logger = logging.getLogger(__name__)

#: Columns owned by the opportunity row; writing them to ``leads`` would be reverted by the trigger.
PIPELINE_FIELDS = frozenset({"stage", "estimated_value", "currency", "deal_probability", "tags"})

#: lead column -> opportunity column, where the names differ.
_LEAD_TO_OPPORTUNITY = {"estimated_value": "quoted_value"}


async def get_lead(db: SupabaseClient, lead_id: str) -> dict[str, Any]:
    result = await db.select("leads", params={"select": "*", "id": f"eq.{lead_id}"})
    return result.one("Lead")


async def get_lead_intelligence(db: SupabaseClient, lead_id: str) -> dict[str, Any] | None:
    result = await db.select(
        "lead_intelligence", params={"select": "*", "lead_id": f"eq.{lead_id}"}
    )
    return result.first()


async def get_opportunity_for_lead(db: SupabaseClient, lead_id: str) -> dict[str, Any]:
    """Every lead gets an opportunity shell from a trigger; its absence is a data-integrity fault."""
    result = await db.select(
        "opportunities", params={"select": "*", "lead_id": f"eq.{lead_id}", "limit": "1"}
    )
    opportunity = result.first()
    if opportunity is None:
        raise NotFoundError("No opportunity exists for this lead")
    return opportunity


def score_for(lead: dict[str, Any], intelligence: dict[str, Any] | None) -> int:
    override = lead.get("score_override")
    estimated = lead.get("estimated_value")
    return compute_priority_score(
        estimated_value=float(estimated) if estimated is not None else None,
        currency=str(lead.get("currency") or "INR"),
        deal_probability=int(lead.get("deal_probability") or 50),
        stage=str(lead.get("stage") or "prospect"),
        next_followup_date=lead.get("next_followup_date"),
        intelligence=intelligence,
        score_override=int(override) if override is not None else None,
    )


async def sync_priority_score(db: SupabaseClient, lead_id: str) -> dict[str, Any]:
    """Recompute the lead's score and mirror it onto its opportunity."""
    lead = await get_lead(db, lead_id)
    intelligence = await get_lead_intelligence(db, lead_id)
    score = score_for(lead, intelligence)

    if int(lead.get("priority_score") or 0) != score:
        await db.update("leads", {"id": f"eq.{lead_id}"}, {"priority_score": score})
        lead["priority_score"] = score

    opportunity = await db.select(
        "opportunities", params={"select": "id,priority_score", "lead_id": f"eq.{lead_id}"}
    )
    row = opportunity.first()
    if row is not None and int(row.get("priority_score") or 0) != score:
        await db.update("opportunities", {"id": f"eq.{row['id']}"}, {"priority_score": score})

    return lead


async def set_stage(db: SupabaseClient, lead_id: str, stage: str) -> dict[str, Any]:
    """Move a lead through the pipeline by writing to its opportunity row."""
    opportunity = await get_opportunity_for_lead(db, lead_id)
    await db.update("opportunities", {"id": f"eq.{opportunity['id']}"}, {"stage": stage})
    return await sync_priority_score(db, lead_id)


async def create_lead(db: SupabaseClient, payload: dict[str, Any], owner_id: str) -> dict[str, Any]:
    body = dict(payload)
    body.setdefault("owner_id", owner_id)
    if not body.get("owner_id"):
        body["owner_id"] = owner_id
    body["priority_score"] = score_for(body, None)
    result = await db.insert("leads", body)
    return result.one("Lead")


async def update_lead(db: SupabaseClient, lead_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial update, routing pipeline fields to the opportunity row."""
    if not changes:
        return await get_lead(db, lead_id)

    pipeline_changes = {k: v for k, v in changes.items() if k in PIPELINE_FIELDS}
    lead_changes = {k: v for k, v in changes.items() if k not in PIPELINE_FIELDS}

    if pipeline_changes:
        opportunity = await get_opportunity_for_lead(db, lead_id)
        opportunity_body = {
            _LEAD_TO_OPPORTUNITY.get(key, key): value for key, value in pipeline_changes.items()
        }
        await db.update("opportunities", {"id": f"eq.{opportunity['id']}"}, opportunity_body)

    if lead_changes:
        await db.update("leads", {"id": f"eq.{lead_id}"}, lead_changes)

    # Read back after both writes so the score reflects trigger-synced values.
    return await sync_priority_score(db, lead_id)


async def convert_to_opportunity(db: SupabaseClient, lead_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Promote a qualified lead into a tracked opportunity."""
    lead = await get_lead(db, lead_id)
    if lead.get("is_opportunity"):
        raise ConflictError("Lead has already been converted to an opportunity")

    opportunity = await get_opportunity_for_lead(db, lead_id)
    project_type = str(lead.get("project_type") or "opportunity").replace("_", " ").capitalize()

    updated = await db.update(
        "opportunities",
        {"id": f"eq.{opportunity['id']}"},
        {
            "title": project_type,
            "quoted_value": lead.get("estimated_value"),
            "currency": lead.get("currency") or "INR",
            "status": "active",
        },
    )
    lead_result = await db.update("leads", {"id": f"eq.{lead_id}"}, {"is_opportunity": True})

    return updated.one("Opportunity"), lead_result.one("Lead")
