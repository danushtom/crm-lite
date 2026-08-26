"""Lead and opportunity business logic.

Since leads and opportunities were separated, each fact has exactly one owner: a lead holds
qualification data, an opportunity holds the pursuit. Nothing is mirrored, so an update goes
to one table and stays there -- no splitting the payload, no re-reading to see what a trigger
rewrote. A lead update is now a single round trip where it used to take up to eight.

Priority score is a property of the pursuit (it is derived from value, probability and stage),
so it is computed and stored on the opportunity.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.concurrency import update_guarded
from app.core.errors import ConflictError, NotFoundError
from app.db.supabase import SupabaseClient
from app.domain.scoring import compute_priority_score

logger = logging.getLogger(__name__)

#: Columns selected when embedding a lead's pursuits.
OPPORTUNITY_COLUMNS = (
    "id,title,stage,status,quoted_value,currency,deal_probability,priority_score,updated_at"
)


async def get_lead(db: SupabaseClient, lead_id: str) -> dict[str, Any]:
    result = await db.select("leads", params={"select": "*", "id": f"eq.{lead_id}"})
    return result.one("Lead")


async def get_lead_intelligence(db: SupabaseClient, lead_id: str) -> dict[str, Any] | None:
    result = await db.select(
        "lead_intelligence", params={"select": "*", "lead_id": f"eq.{lead_id}"}
    )
    return result.first()


async def list_opportunities_for_lead(db: SupabaseClient, lead_id: str) -> list[dict[str, Any]]:
    result = await db.select(
        "opportunities",
        params={
            "select": OPPORTUNITY_COLUMNS,
            "lead_id": f"eq.{lead_id}",
            "order": "created_at.desc,id.desc",
        },
    )
    return result.rows


async def get_active_opportunity(db: SupabaseClient, lead_id: str) -> dict[str, Any]:
    """The pursuit currently in play. A partial unique index guarantees at most one."""
    result = await db.select(
        "opportunities",
        params={
            "select": "*",
            "lead_id": f"eq.{lead_id}",
            "status": "eq.active",
            "limit": "1",
        },
    )
    opportunity = result.first()
    if opportunity is None:
        raise NotFoundError("This lead has no active opportunity")
    return opportunity


def score_for(opportunity: dict[str, Any], intelligence: dict[str, Any] | None) -> int:
    """Weighted priority score for a pursuit (tdd.md 12.2)."""
    override = opportunity.get("score_override")
    value = opportunity.get("quoted_value")
    return compute_priority_score(
        estimated_value=float(value) if value is not None else None,
        currency=str(opportunity.get("currency") or "INR"),
        deal_probability=int(opportunity.get("deal_probability") or 50),
        stage=str(opportunity.get("stage") or "prospect"),
        next_followup_date=opportunity.get("next_followup_date"),
        intelligence=intelligence,
        score_override=int(override) if override is not None else None,
    )


async def sync_opportunity_score(
    db: SupabaseClient,
    opportunity: dict[str, Any],
    *,
    intelligence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute and persist a pursuit's score, writing only when it moved."""
    if intelligence is None:
        intelligence = await get_lead_intelligence(db, str(opportunity["lead_id"]))

    score = score_for(opportunity, intelligence)
    if int(opportunity.get("priority_score") or 0) == score:
        return opportunity

    result = await db.update(
        "opportunities", {"id": f"eq.{opportunity['id']}"}, {"priority_score": score}
    )
    return result.first() or {**opportunity, "priority_score": score}


async def create_lead(
    db: SupabaseClient,
    payload: dict[str, Any],
    *,
    owner_id: str,
    opportunity: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create a lead and populate the pursuit its insert trigger opens.

    Returns the lead and its opportunities.
    """
    body = dict(payload)
    body["owner_id"] = body.get("owner_id") or owner_id

    created = (await db.insert("leads", body)).one("Lead")
    lead_id = str(created["id"])

    # ensure_opportunity_for_lead() has already opened the initial pursuit.
    pursuits = await list_opportunities_for_lead(db, lead_id)
    if not pursuits:
        logger.error("lead %s created without an opportunity; trigger missing?", lead_id)
        return created, []

    if opportunity:
        updates = {k: v for k, v in opportunity.items() if v is not None}
        updates.setdefault("title", _default_title(created))
        current = {**pursuits[0], **updates, "lead_id": lead_id}
        updates["priority_score"] = score_for(current, None)
        refreshed = await db.update(
            "opportunities", {"id": f"eq.{pursuits[0]['id']}"}, updates
        )
        row = refreshed.first()
        if row is not None:
            pursuits = [row]

    return created, pursuits


def _default_title(lead: dict[str, Any]) -> str:
    project = str(lead.get("project_type") or "opportunity").replace("_", " ")
    return project.capitalize()


async def update_lead(
    db: SupabaseClient,
    lead_id: str,
    changes: dict[str, Any],
    *,
    if_match: int | None | str = None,
) -> dict[str, Any]:
    """Apply a partial update to the lead itself.

    Every field here belongs to the lead, so this is one conditional statement -- the version
    check and the write are the same round trip, with no window between them.
    """
    if not changes:
        return await get_lead(db, lead_id)

    return await update_guarded(
        db, "leads", record_id=lead_id, changes=changes, if_match=if_match, what="Lead"
    )


async def open_opportunity(
    db: SupabaseClient,
    lead_id: str,
    payload: dict[str, Any],
    *,
    owner_id: str,
) -> dict[str, Any]:
    """Open a further pursuit against an existing lead -- the upsell or follow-on engagement.

    At most one pursuit per lead may be active, enforced by a partial unique index; the
    resulting conflict is translated into a clear 409 rather than a constraint error.
    """
    lead = await get_lead(db, lead_id)

    body = {
        **payload,
        "lead_id": lead_id,
        "owner_id": payload.get("owner_id") or lead.get("owner_id") or owner_id,
    }
    body.setdefault("title", _default_title(lead))
    body.setdefault("status", "active")
    body["priority_score"] = score_for(body, await get_lead_intelligence(db, lead_id))

    try:
        result = await db.insert("opportunities", body)
    except ConflictError as exc:
        raise ConflictError(
            "This lead already has an active opportunity. Close or win it before opening "
            "another, or update the existing one."
        ) from exc

    return result.one("Opportunity")


async def set_stage(db: SupabaseClient, opportunity_id: str, stage: str) -> dict[str, Any]:
    """Move a pursuit through the pipeline. A trigger records the stage change as activity."""
    result = await db.update("opportunities", {"id": f"eq.{opportunity_id}"}, {"stage": stage})
    updated = result.one("Opportunity")
    return await sync_opportunity_score(db, updated)
