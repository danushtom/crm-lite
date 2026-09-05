"""Tools the voice agent can invoke mid-call, dispatched by `tool_name` from the platform's
tool-call webhook (see app/api/v1/endpoints/voice_webhooks.py).

Every function is scoped by `org_id`, which the webhook handler has already resolved from a
trusted, signature-verified, DB-backed lookup -- never from an argument the LLM/platform
payload supplies directly (that argument is hallucination/prompt-injection-controllable in a
way the webhook's own resolved call_id is not). Keep each tool to 1-2 DB round trips: this
runs on the critical path of a live phone call.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from app.core.errors import NotFoundError
from app.db.supabase import SupabaseAdminClient
from app.services import leads as lead_service

logger = logging.getLogger(__name__)

ToolFn = Callable[[str, dict[str, Any], SupabaseAdminClient], Awaitable[dict[str, Any]]]


async def check_consent(org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    contact_id = arguments.get("contact_id")
    if not contact_id:
        return {"error": "contact_id is required"}
    result = await admin_db.select(
        "contacts",
        params={"select": "ai_call_consent", "id": f"eq.{contact_id}", "organization_id": f"eq.{org_id}"},
    )
    row = result.first()
    return {"consented": bool(row and row.get("ai_call_consent"))}


async def get_lead_context(org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    lead_id = arguments.get("lead_id")
    if not lead_id:
        return {"error": "lead_id is required"}
    try:
        lead = await lead_service.get_lead(admin_db, lead_id)
    except NotFoundError:
        return {"error": "lead not found"}
    if lead.get("organization_id") != org_id:
        return {"error": "lead not found"}
    intelligence = await lead_service.get_lead_intelligence(admin_db, lead_id)
    return {
        "lead": {k: lead.get(k) for k in ("id", "company_id", "next_followup_date", "tags")},
        "intelligence": intelligence,
    }


async def log_call_outcome(org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    call_id = arguments.get("call_id")
    outcome = arguments.get("outcome")
    if not call_id or not outcome:
        return {"error": "call_id and outcome are required"}
    await admin_db.update(
        "calls",
        {"id": f"eq.{call_id}", "organization_id": f"eq.{org_id}"},
        {"outcome": outcome, "summary": arguments.get("summary")},
    )
    return {"logged": True}


async def update_deal_stage(org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    opportunity_id = arguments.get("opportunity_id")
    stage = arguments.get("stage")
    if not opportunity_id or not stage:
        return {"error": "opportunity_id and stage are required"}
    existing = await admin_db.select(
        "opportunities",
        params={"select": "id", "id": f"eq.{opportunity_id}", "organization_id": f"eq.{org_id}"},
    )
    if existing.first() is None:
        return {"error": "opportunity not found"}
    updated = await lead_service.set_stage(admin_db, opportunity_id, stage)
    return {"stage": updated.get("stage")}


async def book_appointment(org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    """Unlike the other tools, `lead_id`/`owner_id` here would otherwise flow straight from
    the LLM's tool-call arguments into an INSERT -- the one place in this module where a
    hallucinated or manipulated argument could create a row attributed to another org entirely
    (meetings.organization_id is derived from whichever of lead_id/owner_id is present). Both
    are resolved against org_id before they're trusted, exactly like every other tool here."""
    lead_id = arguments.get("lead_id")
    title = arguments.get("title") or "Meeting booked by AI agent"
    scheduled_at = arguments.get("scheduled_at")
    if not scheduled_at:
        return {"error": "scheduled_at is required"}

    owner_id: str | None = None
    if lead_id:
        lead_result = await admin_db.select(
            "leads", params={"select": "owner_id,organization_id", "id": f"eq.{lead_id}"}
        )
        lead = lead_result.first()
        if lead is None or lead.get("organization_id") != org_id:
            return {"error": "lead not found"}
        owner_id = lead.get("owner_id")
    else:
        requested_owner = arguments.get("owner_id")
        if not requested_owner:
            return {"error": "lead_id or owner_id is required"}
        owner_result = await admin_db.select(
            "users",
            params={"select": "id", "id": f"eq.{requested_owner}", "organization_id": f"eq.{org_id}"},
        )
        if owner_result.first() is None:
            return {"error": "owner not found in this organization"}
        owner_id = requested_owner

    result = await admin_db.insert(
        "meetings",
        {
            "lead_id": lead_id,
            "owner_id": owner_id,
            "title": title,
            "scheduled_at": scheduled_at,
            "duration_minutes": arguments.get("duration_minutes", 30),
        },
    )
    meeting = result.one("Meeting")
    return {
        "meeting_id": meeting["id"],
        # This creates a CRM record only -- calendar_sync only pulls FROM Google Calendar
        # today, there is no push-to-Google path yet. Do not tell the caller it was added to
        # their Google Calendar.
        "note": "Added to the CRM. This will not appear on the rep's Google Calendar automatically.",
    }


TOOLS: dict[str, ToolFn] = {
    "check_consent": check_consent,
    "get_lead_context": get_lead_context,
    "log_call_outcome": log_call_outcome,
    "update_deal_stage": update_deal_stage,
    "book_appointment": book_appointment,
}


async def dispatch(tool_name: str, org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    tool = TOOLS.get(tool_name)
    if tool is None:
        logger.warning("voice_tool_unknown tool=%s", tool_name)
        return {"error": f"Unknown tool: {tool_name}"}
    logger.info("voice_tool_call tool=%s org_id=%s", tool_name, org_id)
    return await tool(org_id, arguments, admin_db)
