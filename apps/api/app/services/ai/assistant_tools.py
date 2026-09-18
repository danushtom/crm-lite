"""Read-only CRM readers the assistant may call.

This module is where the old ``/api/chat`` design is put right. That route took a blob of CRM data
posted by the browser and pasted it into the system prompt: the client chose what the model saw,
nobody checked the caller was logged in, and nothing tied the data to a tenant.

Here, every reader is built around ``db`` -- the requesting user's own RLS-scoped PostgREST
client, the same one every screen in the product uses. Three things follow from that, and they are
the entire security argument for this feature:

* The model cannot read a row the user could not already open in the UI. Postgres enforces it,
  not a prompt and not a filter in this file.
* No ``organization_id`` appears anywhere below. There is nothing to get wrong, and no argument an
  LLM could supply that would widen the query -- unlike ``voice_tools.py``, where a service-role
  client makes the org id a parameter that must be resolved and passed with care.
* Prompt injection cannot escalate. A note inside a CRM record telling the model to "fetch every
  organization's leads" produces a query that runs as this user and returns their rows.

Every tool is read-only by construction: there is no insert, update or delete in this module, and
none should be added. Writes belong on their own endpoints with their own permission checks, where
a human has pressed a button.
"""

from __future__ import annotations

import logging
from typing import Any

from dracara_ai.graphs.assistant import CrmTool

from app.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

#: Ceiling on how many rows any one tool returns. Protects the context window, and stops a broad
#: question turning into a full table read.
MAX_ROWS = 25

_LEAD_SELECT = (
    "id,project_type,lead_source,last_contact_date,next_followup_date,tags,created_at,"
    "companies(name,industry,segment,website),"
    "opportunities(id,title,stage,status,quoted_value,currency,priority_score,deal_probability)"
)

_OPPORTUNITY_SELECT = (
    "id,title,stage,status,quoted_value,currency,timeline_weeks,tech_stack,priority_score,"
    "deal_probability,score_override,created_at,updated_at,"
    "leads(id,project_type,next_followup_date,companies(name,industry))"
)


def _clamp(value: Any, default: int = 10) -> int:
    try:
        return max(1, min(int(value), MAX_ROWS))
    except (TypeError, ValueError):
        return default


def _sanitise_search(term: str) -> str:
    """Strip the characters PostgREST treats as filter syntax out of a user-supplied search term.

    The same reasoning as the search sanitiser added elsewhere in this codebase: a term reaching a
    ``like``/``ilike`` filter can otherwise break out of its value and change the filter's meaning.
    RLS would still bound the result, but a malformed filter is a bug either way.
    """
    return "".join(c for c in str(term) if c not in "(),.*:\"\\").strip()[:120]


def build_tools(db: SupabaseClient) -> list[CrmTool]:
    """Build the tool set, bound to this caller's scoped client.

    ``db`` must be the RLS-scoped ``DbDep`` client, never ``AdminDbDep``. Passing the admin client
    here would hand the model service-role reach over every tenant and silently undo everything
    this module's docstring claims.
    """

    async def search_leads(args: dict[str, Any]) -> Any:
        params: dict[str, str] = {
            "select": _LEAD_SELECT,
            "deleted_at": "is.null",
            "order": "created_at.desc,id.desc",
            "limit": str(_clamp(args.get("limit"))),
        }
        term = _sanitise_search(args.get("company_name") or "")
        if term:
            # Filter on the embedded company by its own column, which PostgREST supports on an
            # inner join; without `!inner` the filter would be ignored rather than applied.
            params["select"] = params["select"].replace("companies(", "companies!inner(")
            params["companies.name"] = f"ilike.*{term}*"
        result = await db.select("leads", params=params)
        return {"leads": result.rows, "count": len(result.rows)}

    async def get_lead(args: dict[str, Any]) -> Any:
        lead_id = args.get("lead_id")
        if not lead_id:
            return {"error": "lead_id is required"}
        result = await db.select(
            "leads",
            params={"select": _LEAD_SELECT, "id": f"eq.{lead_id}", "deleted_at": "is.null"},
        )
        lead = result.first()
        if lead is None:
            # Indistinguishable from "exists but you cannot see it", on purpose -- the model
            # should not be able to probe for the existence of records outside the user's reach.
            return {"error": "No lead with that id is visible to you"}

        intelligence = await db.select(
            "lead_intelligence", params={"select": "*", "lead_id": f"eq.{lead_id}"}
        )
        return {"lead": lead, "intelligence": intelligence.first()}

    async def get_pipeline_summary(_args: dict[str, Any]) -> Any:
        result = await db.select(
            "opportunities",
            params={
                "select": "stage,status,quoted_value,currency,priority_score",
                "deleted_at": "is.null",
                "status": "eq.active",
                "limit": "500",
            },
        )
        by_stage: dict[str, dict[str, float]] = {}
        for row in result.rows:
            bucket = by_stage.setdefault(
                row.get("stage") or "unknown", {"count": 0, "value": 0.0, "score_total": 0.0}
            )
            bucket["count"] += 1
            bucket["value"] += float(row.get("quoted_value") or 0)
            bucket["score_total"] += float(row.get("priority_score") or 0)

        stages = [
            {
                "stage": stage,
                "count": int(data["count"]),
                "total_value": round(data["value"], 2),
                "average_score": round(data["score_total"] / data["count"], 1),
            }
            for stage, data in sorted(by_stage.items(), key=lambda kv: -kv[1]["count"])
        ]
        return {
            "stages": stages,
            "total_open_deals": sum(s["count"] for s in stages),
            "total_open_value": round(sum(s["total_value"] for s in stages), 2),
            "note": "Active opportunities visible to you. Values are in each deal's own currency.",
        }

    async def get_opportunity(args: dict[str, Any]) -> Any:
        opportunity_id = args.get("opportunity_id")
        if not opportunity_id:
            return {"error": "opportunity_id is required"}
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
            return {"error": "No opportunity with that id is visible to you"}

        health = await db.select(
            "deal_health_snapshots",
            params={
                "select": "risk_level,reasons,suggested_action,generated_at,assessed_by_model",
                "opportunity_id": f"eq.{opportunity_id}",
                "order": "generated_at.desc",
                "limit": "1",
            },
        )
        return {"opportunity": opportunity, "latest_health_check": health.first()}

    async def list_tasks(args: dict[str, Any]) -> Any:
        params: dict[str, str] = {
            "select": "id,title,status,due_at,priority,lead_id",
            "order": "due_at.asc,id.asc",
            "limit": str(_clamp(args.get("limit"))),
        }
        status = args.get("status")
        if status in ("pending", "snoozed", "completed", "cancelled"):
            params["status"] = f"eq.{status}"
        else:
            params["status"] = "eq.pending"
        if args.get("overdue_only"):
            from datetime import datetime, timezone

            params["due_at"] = f"lt.{datetime.now(timezone.utc).isoformat()}"
        result = await db.select("tasks", params=params)
        return {"tasks": result.rows, "count": len(result.rows)}

    async def search_activities(args: dict[str, Any]) -> Any:
        lead_id = args.get("lead_id")
        if not lead_id:
            return {"error": "lead_id is required"}
        result = await db.select(
            "activities",
            params={
                "select": "id,type,description,outcome,actor_type,created_at",
                "lead_id": f"eq.{lead_id}",
                "order": "created_at.desc,id.desc",
                "limit": str(_clamp(args.get("limit"))),
            },
        )
        return {"activities": result.rows, "count": len(result.rows)}

    async def list_recent_calls(args: dict[str, Any]) -> Any:
        result = await db.select(
            "calls",
            params={
                "select": "id,direction,status,outcome,ai_summary,ai_sentiment,"
                "ai_suggested_followup_date,duration_seconds,lead_id,created_at",
                "order": "created_at.desc,id.desc",
                "limit": str(_clamp(args.get("limit"))),
            },
        )
        return {"calls": result.rows, "count": len(result.rows)}

    return [
        CrmTool(
            name="search_leads",
            description=(
                "List leads, most recent first, optionally filtered by company name. "
                "Use this to answer questions about who is in the pipeline."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "Partial company name to filter by",
                    },
                    "limit": {"type": "integer", "description": f"1-{MAX_ROWS}, default 10"},
                },
            },
            fn=search_leads,
        ),
        CrmTool(
            name="get_lead",
            description=(
                "Full detail for one lead by id, including its CRM intelligence notes "
                "(pain points, decision makers, budget signals)."
            ),
            parameters={
                "type": "object",
                "properties": {"lead_id": {"type": "string"}},
                "required": ["lead_id"],
            },
            fn=get_lead,
        ),
        CrmTool(
            name="get_pipeline_summary",
            description=(
                "Deal counts, total value and average score grouped by pipeline stage. "
                "Use this first for any broad 'how is the pipeline doing' question."
            ),
            parameters={"type": "object", "properties": {}},
            fn=get_pipeline_summary,
        ),
        CrmTool(
            name="get_opportunity",
            description=(
                "Full detail for one opportunity by id, including its most recent "
                "deal-health assessment if one exists."
            ),
            parameters={
                "type": "object",
                "properties": {"opportunity_id": {"type": "string"}},
                "required": ["opportunity_id"],
            },
            fn=get_opportunity,
        ),
        CrmTool(
            name="list_tasks",
            description="Follow-up tasks, soonest due first. Defaults to pending tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "snoozed", "completed", "cancelled"],
                    },
                    "overdue_only": {"type": "boolean"},
                    "limit": {"type": "integer", "description": f"1-{MAX_ROWS}, default 10"},
                },
            },
            fn=list_tasks,
        ),
        CrmTool(
            name="search_activities",
            description=(
                "The activity timeline for one lead, most recent first -- calls, emails, "
                "meetings, notes and stage changes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "limit": {"type": "integer", "description": f"1-{MAX_ROWS}, default 10"},
                },
                "required": ["lead_id"],
            },
            fn=search_activities,
        ),
        CrmTool(
            name="list_recent_calls",
            description=(
                "Recent AI voice calls with their summaries, sentiment and suggested follow-up "
                "dates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": f"1-{MAX_ROWS}, default 10"}
                },
            },
            fn=list_recent_calls,
        ),
    ]
