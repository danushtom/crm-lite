"""Tools the voice agent can invoke mid-call, dispatched by `tool_name` from the platform's
tool-call webhook (see app/api/v1/endpoints/voice_webhooks.py).

Every function is scoped by `org_id`, which the webhook handler has already resolved from a
trusted, signature-verified, DB-backed lookup -- never from an argument the LLM/platform
payload supplies directly (that argument is hallucination/prompt-injection-controllable in a
way the webhook's own resolved call_id is not). Keep each tool to 1-2 DB round trips: this
runs on the critical path of a live phone call.

`dispatch()` additionally enforces the agent's own data-access policy -- which tools it may
call, and which lead fields it may be told. That check belongs *here* rather than only in the
tool definitions sent to the platform: the declarations are advisory (a tool call can arrive
for a tool that was never declared, whether through a vendor-side edit, a stale assistant
configuration or a model that has been talked into inventing one), while this function is the
only path from a tool call to the database. The policy is read from the `voice_agents` row that
the resolved `calls` row points at -- not from the payload, for the same reason `org_id` is not.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from dracara_ai import voice_script
from dracara_ai.errors import AiError

from app.core.errors import NotFoundError
from app.db.supabase import SupabaseAdminClient
from app.services import leads as lead_service
from app.services.ai import knowledge_base

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


#: Where each shareable field actually lives. A field the organization did not tick is never
#: read into the response, so an agent cannot be told a budget or an internal note by accident.
#: Keys are `dracara_ai.voice_script.LEAD_FIELDS`; the UI offers exactly this vocabulary.
_LEAD_FIELD_SOURCES: dict[str, tuple[str, str]] = {
    "company_name": ("company", "name"),
    "project_type": ("lead", "project_type"),
    "stage": ("opportunity", "stage"),
    "quoted_value": ("opportunity", "quoted_value"),
    "tags": ("lead", "tags"),
    "next_followup_date": ("lead", "next_followup_date"),
    "last_contact_date": ("lead", "last_contact_date"),
    "budget_range": ("intelligence", "budget_range"),
    "timeline": ("intelligence", "timeline"),
    "pain_points": ("intelligence", "pain_points"),
    "decision_makers": ("intelligence", "decision_makers"),
    "tech_stack": ("opportunity", "tech_stack"),
    "notes": ("intelligence", "notes"),
}


async def get_lead_context(
    org_id: str,
    arguments: dict[str, Any],
    admin_db: SupabaseAdminClient,
    *,
    allowed_fields: list[str] | None = None,
) -> dict[str, Any]:
    """What the CRM knows about this lead -- limited to the fields the organization shared.

    `allowed_fields` comes from the agent's policy, resolved in `dispatch`. None means "whatever
    the policy default is", never "everything": an agent with no policy row still gets the
    conservative default set rather than the whole intelligence panel.
    """
    lead_id = arguments.get("lead_id")
    if not lead_id:
        return {"error": "lead_id is required"}
    try:
        lead = await lead_service.get_lead(admin_db, lead_id)
    except NotFoundError:
        return {"error": "lead not found"}
    if lead.get("organization_id") != org_id:
        return {"error": "lead not found"}

    fields = allowed_fields if allowed_fields is not None else list(voice_script.DEFAULT_LEAD_FIELDS)
    wanted = {f for f in fields if f in _LEAD_FIELD_SOURCES}
    if not wanted:
        return {"shared": {}, "note": "This agent has not been given access to CRM lead data."}
    sources = {_LEAD_FIELD_SOURCES[f][0] for f in wanted}

    # Only the rows a chosen field actually needs: three lookups is already a lot to do while
    # someone waits on the phone.
    company: dict[str, Any] = {}
    if "company" in sources and lead.get("company_id"):
        found = await admin_db.select(
            "companies",
            params={"select": "name", "id": f"eq.{lead['company_id']}", "organization_id": f"eq.{org_id}"},
        )
        company = found.first() or {}

    opportunity: dict[str, Any] = {}
    if "opportunity" in sources:
        found = await admin_db.select(
            "opportunities",
            params={
                "select": "stage,quoted_value,tech_stack",
                "lead_id": f"eq.{lead_id}",
                "status": "eq.active",
                "deleted_at": "is.null",
                "limit": "1",
            },
        )
        opportunity = found.first() or {}

    intelligence: dict[str, Any] = {}
    if "intelligence" in sources:
        intelligence = await lead_service.get_lead_intelligence(admin_db, lead_id) or {}

    rows = {"lead": lead, "company": company, "opportunity": opportunity, "intelligence": intelligence}
    shared: dict[str, Any] = {}
    for field in voice_script.LEAD_FIELDS:
        if field not in wanted:
            continue
        source, key = _LEAD_FIELD_SOURCES[field]
        value = rows[source].get(key)
        if value not in (None, "", [], {}):
            shared[field] = value
    return {"shared": shared}


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
        # The worker's `calendar_push` job (every two minutes) forwards CRM-created meetings to
        # the owner's Google Calendar, so this is now true rather than the apology it replaced.
        # It is still asynchronous and it still depends on that rep having connected Google, so
        # the wording promises "shortly", not "already done".
        "note": "Booked. It will appear on the rep's calendar shortly.",
    }


async def search_knowledge_base(org_id: str, arguments: dict[str, Any], admin_db: SupabaseAdminClient) -> dict[str, Any]:
    """Look something up in the agent's uploaded documents (pricing sheets, FAQs, scripts).

    Note which two arguments are *not* taken from `arguments`: `org_id` is the webhook's resolved
    value, and `voice_agent_id` is read from the `calls` row this tool call belongs to. Qdrant has
    no row-level security, so its payload filter is the entire tenant boundary -- accepting either
    from the model's tool-call arguments would let a hallucinated (or injected) id read another
    organization's pricing. The query text is the only thing the model gets to choose.
    """
    query = arguments.get("query")
    if not query:
        return {"error": "query is required"}

    call_id = arguments.get("call_id")
    if not call_id:
        return {"error": "call_id is required"}
    call_result = await admin_db.select(
        "calls",
        params={"select": "voice_agent_id", "id": f"eq.{call_id}", "organization_id": f"eq.{org_id}"},
    )
    call = call_result.first()
    if call is None:
        return {"error": "call not found"}

    try:
        passages = await knowledge_base.search(
            organization_id=org_id,
            voice_agent_id=call["voice_agent_id"],
            query=str(query)[:500],
            limit=int(arguments.get("limit") or 3),
        )
    except AiError as exc:
        # Mid-call, on a live phone line: degrade to "I don't have that to hand" rather than
        # failing the tool call and leaving the agent silent.
        logger.warning("voice_kb_search_failed org_id=%s error=%s", org_id, exc)
        return {"passages": [], "note": "The knowledge base is unavailable right now."}

    if not passages:
        return {
            "passages": [],
            "note": "Nothing in the uploaded documents covers this. Do not guess an answer.",
        }
    return {"passages": passages}


TOOLS: dict[str, ToolFn] = {
    "check_consent": check_consent,
    "get_lead_context": get_lead_context,
    "log_call_outcome": log_call_outcome,
    "update_deal_stage": update_deal_stage,
    "book_appointment": book_appointment,
    "search_knowledge_base": search_knowledge_base,
}


async def _policy(
    org_id: str, voice_agent_id: str | None, admin_db: SupabaseAdminClient
) -> dict[str, Any] | None:
    """The agent's data-access policy, read from its own row and scoped by the resolved org."""
    if not voice_agent_id:
        return None
    result = await admin_db.select(
        "voice_agents",
        params={"select": "data_access", "id": f"eq.{voice_agent_id}", "organization_id": f"eq.{org_id}"},
    )
    row = result.first()
    return (row or {}).get("data_access") or {}


async def dispatch(
    tool_name: str,
    org_id: str,
    arguments: dict[str, Any],
    admin_db: SupabaseAdminClient,
    *,
    voice_agent_id: str | None = None,
) -> dict[str, Any]:
    """Run one mid-call tool, if this agent is allowed to.

    `voice_agent_id` comes from the resolved `calls` row in the webhook, never from the payload.
    Omitting it (an older caller, or a call row without an agent) falls back to the conservative
    default policy rather than to "everything allowed" -- a missing policy must not be a
    privilege escalation.
    """
    tool = TOOLS.get(tool_name)
    if tool is None:
        logger.warning("voice_tool_unknown tool=%s", tool_name)
        return {"error": f"Unknown tool: {tool_name}"}

    data_access = await _policy(org_id, voice_agent_id, admin_db)
    allowed = voice_script.enabled_tools(data_access)
    if tool_name not in allowed:
        # Refused, and said plainly, so the model tells the caller it cannot do that rather
        # than hallucinating that it did. A write tool (booking, stage change) that reached
        # here while switched off is the case this exists for.
        logger.warning(
            "voice_tool_refused tool=%s org_id=%s agent=%s", tool_name, org_id, voice_agent_id
        )
        return {
            "error": f"{tool_name} is not enabled for this agent",
            "note": "Tell the caller you cannot do that on this call and offer a callback.",
        }

    logger.info("voice_tool_call tool=%s org_id=%s", tool_name, org_id)
    if tool_name == "get_lead_context":
        return await get_lead_context(
            org_id,
            arguments,
            admin_db,
            allowed_fields=voice_script.shared_lead_fields(data_access),
        )
    return await tool(org_id, arguments, admin_db)
