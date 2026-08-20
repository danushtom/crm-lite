from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import SupabaseRest, TokenUser, get_current_user, get_sb
from app.rbac import forbid_partner_intel_edit
from app.scoring import compute_priority_score

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadCreate(BaseModel):
    company_id: str
    primary_contact_id: str | None = None
    owner_id: str | None = None
    stage: str | None = Field(default="prospect")
    project_type: str
    lead_source: str
    estimated_value: float | None = None
    currency: str | None = "INR"
    deal_probability: int | None = Field(default=50, ge=0, le=100)
    last_contact_date: str | None = None
    next_followup_date: str | None = None
    tags: list[str] | None = None


class LeadPatch(BaseModel):
    company_id: str | None = None
    primary_contact_id: str | None = None
    owner_id: str | None = None
    stage: str | None = None
    project_type: str | None = None
    lead_source: str | None = None
    estimated_value: float | None = None
    currency: str | None = None
    deal_probability: int | None = Field(default=None, ge=0, le=100)
    last_contact_date: str | None = None
    next_followup_date: str | None = None
    tags: list[str] | None = None
    is_opportunity: bool | None = None
    score_override: int | None = Field(default=None, ge=0, le=100)
    score_override_reason: str | None = None


class StagePatch(BaseModel):
    stage: str


async def _one(sb: SupabaseRest, table: str, id_col: str, id_val: str) -> dict[str, Any]:
    rows = await sb.request("GET", f"/{table}", params={"select": "*", id_col: f"eq.{id_val}"})
    if not rows:
        raise HTTPException(404, f"{table} not found")
    return rows[0]


def _ilike_pattern(q: str) -> str:
    safe = "".join(c for c in q.strip() if c not in "*%")[:200]
    return f"*{safe}*" if safe else ""


async def _maybe_lead_intelligence(sb: SupabaseRest, lead_id: str) -> dict[str, Any] | None:
    rows = await sb.request(
        "GET",
        "/lead_intelligence",
        params={"select": "*", "lead_id": f"eq.{lead_id}"},
    )
    return rows[0] if rows else None


def _score_payload(lead: dict[str, Any], intelligence: dict[str, Any] | None) -> int:
    ov = lead.get("score_override")
    ov_int = int(ov) if ov is not None else None
    return compute_priority_score(
        estimated_value=float(lead["estimated_value"]) if lead.get("estimated_value") is not None else None,
        currency=str(lead.get("currency") or "INR"),
        deal_probability=int(lead.get("deal_probability") or 50),
        stage=str(lead.get("stage")),
        next_followup_date=lead.get("next_followup_date"),
        intelligence=intelligence,
        score_override=ov_int,
    )


PIPELINE_KEYS = frozenset({"stage", "estimated_value", "currency", "deal_probability", "tags"})


async def opportunity_id_for_lead(sb: SupabaseRest, lead_id: str) -> str:
    rows = await sb.request(
        "GET",
        "/opportunities",
        params={"lead_id": f"eq.{lead_id}", "select": "id"},
    )
    if not rows:
        raise HTTPException(404, "Opportunity not found for lead")
    return str(rows[0]["id"])


async def refresh_priority_scores_for_lead(sb: SupabaseRest, lead_id: str) -> dict[str, Any]:
    lead = await _one(sb, "leads", "id", lead_id)
    intelligence = await _maybe_lead_intelligence(sb, lead_id)
    ps = _score_payload(lead, intelligence)
    await sb.request(
        "PATCH",
        "/leads",
        params={"id": f"eq.{lead_id}"},
        json_body={"priority_score": ps},
        prefer="return=representation",
    )
    opp_rows = await sb.request(
        "GET",
        "/opportunities",
        params={"lead_id": f"eq.{lead_id}", "select": "id,priority_score"},
    )
    if opp_rows:
        oid = str(opp_rows[0]["id"])
        cur = int(opp_rows[0].get("priority_score") or 0)
        if cur != int(ps):
            await sb.request(
                "PATCH",
                "/opportunities",
                params={"id": f"eq.{oid}"},
                json_body={"priority_score": ps},
                prefer="return=representation",
            )
    return await _one(sb, "leads", "id", lead_id)


@router.get("")
async def list_leads(
    sb: SupabaseRest = Depends(get_sb),
    stage: str | None = None,
    owner_id: str | None = None,
    lead_source: str | None = None,
    project_type: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    params: dict[str, str] = {
        "select": "*,companies(*)",
        "order": "updated_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if stage:
        params["stage"] = f"eq.{stage}"
    if owner_id:
        params["owner_id"] = f"eq.{owner_id}"
    if lead_source:
        params["lead_source"] = f"eq.{lead_source}"
    if project_type:
        params["project_type"] = f"eq.{project_type}"

    wild = _ilike_pattern(search or "")
    if wild:
        cos = await sb.request(
            "GET",
            "/companies",
            params={"select": "id", "limit": "100", "name": f"ilike.{wild}"},
        )
        company_ids = [str(c["id"]) for c in (cos or [])]
        parts = [
            f"project_type.ilike.{wild}",
            f"lead_source.ilike.{wild}",
        ]
        if company_ids:
            parts.append(f"company_id.in.({','.join(company_ids)})")
        params["or"] = "(" + ",".join(parts) + ")"

    return await sb.request("GET", "/leads", params=params)


@router.post("")
async def create_lead(body: LeadCreate, sb: SupabaseRest = Depends(get_sb), user: TokenUser = Depends(get_current_user)):
    payload = body.model_dump(exclude_none=True)
    payload.setdefault("stage", "prospect")
    payload.setdefault("currency", "INR")
    payload.setdefault("deal_probability", 50)
    payload["owner_id"] = payload.get("owner_id") or user.sub
    payload["priority_score"] = _score_payload(payload, None)
    rows = await sb.request("POST", "/leads", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    sb: SupabaseRest = Depends(get_sb),
    include_related: bool = Query(default=False, description="Embed recent activities and tasks"),
):
    lead = await _one(sb, "leads", "id", lead_id)
    intelligence = await _maybe_lead_intelligence(sb, lead_id)
    out: dict[str, Any] = {"lead": lead, "lead_intelligence": intelligence}
    if include_related:
        activities, recent_tasks = await asyncio.gather(
            sb.request(
                "GET",
                "/activities",
                params={
                    "select": "*",
                    "lead_id": f"eq.{lead_id}",
                    "order": "performed_at.desc",
                    "limit": "50",
                },
            ),
            sb.request(
                "GET",
                "/tasks",
                params={
                    "select": "*",
                    "lead_id": f"eq.{lead_id}",
                    "order": "due_date.asc",
                    "limit": "25",
                },
            ),
        )
        out["activities"] = activities or []
        out["recent_tasks"] = recent_tasks or []
    return out


@router.patch("/{lead_id}")
async def patch_lead(lead_id: str, body: LeadPatch, sb: SupabaseRest = Depends(get_sb)):
    patch = body.model_dump(exclude_none=True)
    if not patch:
        return await _one(sb, "leads", "id", lead_id)

    pipeline_patch = {k: v for k, v in patch.items() if k in PIPELINE_KEYS}
    lead_patch = {k: v for k, v in patch.items() if k not in PIPELINE_KEYS}

    if pipeline_patch:
        oid = await opportunity_id_for_lead(sb, lead_id)
        opp_body: dict[str, Any] = {}
        if "stage" in pipeline_patch:
            opp_body["stage"] = pipeline_patch["stage"]
        if "currency" in pipeline_patch:
            opp_body["currency"] = pipeline_patch["currency"]
        if "deal_probability" in pipeline_patch:
            opp_body["deal_probability"] = pipeline_patch["deal_probability"]
        if "tags" in pipeline_patch:
            opp_body["tags"] = pipeline_patch["tags"]
        if "estimated_value" in pipeline_patch:
            opp_body["quoted_value"] = pipeline_patch["estimated_value"]
        await sb.request(
            "PATCH",
            "/opportunities",
            params={"id": f"eq.{oid}"},
            json_body=opp_body,
            prefer="return=representation",
        )

    current = await _one(sb, "leads", "id", lead_id)
    merged = {**current, **lead_patch}
    intelligence = await _maybe_lead_intelligence(sb, lead_id)
    ps = _score_payload(merged, intelligence)

    update_lead = dict(lead_patch)
    if pipeline_patch or lead_patch:
        update_lead["priority_score"] = ps

    rows = await sb.request(
        "PATCH",
        "/leads",
        params={"id": f"eq.{lead_id}"},
        json_body=update_lead,
        prefer="return=representation",
    )
    opp_rows = await sb.request(
        "GET",
        "/opportunities",
        params={"lead_id": f"eq.{lead_id}", "select": "id,priority_score"},
    )
    if opp_rows:
        oid = str(opp_rows[0]["id"])
        if int(opp_rows[0].get("priority_score") or 0) != int(ps):
            await sb.request(
                "PATCH",
                "/opportunities",
                params={"id": f"eq.{oid}"},
                json_body={"priority_score": ps},
                prefer="return=representation",
            )
    return rows[0] if isinstance(rows, list) else rows


@router.patch("/{lead_id}/stage")
async def patch_stage(lead_id: str, body: StagePatch, sb: SupabaseRest = Depends(get_sb)):
    oid = await opportunity_id_for_lead(sb, lead_id)
    await sb.request(
        "PATCH",
        "/opportunities",
        params={"id": f"eq.{oid}"},
        json_body={"stage": body.stage},
        prefer="return=representation",
    )
    return await refresh_priority_scores_for_lead(sb, lead_id)


class IntelligencePatch(BaseModel):
    pain_points: str | None = None
    tech_stack: str | None = None
    budget_hints: str | None = None
    decision_makers: str | None = None
    competitors_involved: str | None = None
    objections_raised: str | None = None
    strategic_notes: str | None = None
    comm_preference: str | None = None


@router.patch("/{lead_id}/intelligence")
async def patch_intelligence(
    lead_id: str,
    body: IntelligencePatch,
    _: None = Depends(forbid_partner_intel_edit),
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    patch = body.model_dump(exclude_none=True)
    if not patch:
        return await _maybe_lead_intelligence(sb, lead_id)
    patch["updated_by"] = user.sub
    rows = await sb.request(
        "PATCH",
        "/lead_intelligence",
        params={"lead_id": f"eq.{lead_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    intel_after = rows[0] if isinstance(rows, list) and rows else rows
    await refresh_priority_scores_for_lead(sb, lead_id)
    return intel_after


@router.post("/{lead_id}/convert")
async def convert_lead(lead_id: str, sb: SupabaseRest = Depends(get_sb)):
    lead = await _one(sb, "leads", "id", lead_id)
    if lead.get("is_opportunity"):
        raise HTTPException(400, "Lead already converted")
    opp_rows = await sb.request(
        "GET",
        "/opportunities",
        params={"select": "id", "lead_id": f"eq.{lead_id}"},
    )
    if not opp_rows:
        raise HTTPException(404, "Opportunity shell missing for lead")
    oid = str(opp_rows[0]["id"])
    await sb.request(
        "PATCH",
        "/opportunities",
        params={"id": f"eq.{oid}"},
        json_body={
            "title": f"{str(lead.get('project_type', 'Opportunity')).replace('_', ' ').capitalize()}",
            "quoted_value": lead.get("estimated_value"),
            "currency": lead.get("currency") or "INR",
            "status": "active",
        },
        prefer="return=representation",
    )
    rows = await sb.request(
        "PATCH",
        "/leads",
        params={"id": f"eq.{lead_id}"},
        json_body={"is_opportunity": True},
        prefer="return=representation",
    )
    out = rows[0] if isinstance(rows, list) else rows
    opp_full = await sb.request("GET", "/opportunities", params={"select": "*", "id": f"eq.{oid}"})
    return {"opportunity": opp_full[0] if opp_full else {"id": oid}, "lead": out}


@router.get("/{lead_id}/activities")
async def list_activities(lead_id: str, sb: SupabaseRest = Depends(get_sb)):
    await _one(sb, "leads", "id", lead_id)
    return await sb.request(
        "GET",
        "/activities",
        params={"select": "*", "lead_id": f"eq.{lead_id}", "order": "performed_at.desc"},
    )


class ActivityCreate(BaseModel):
    type: str
    description: str
    outcome: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/{lead_id}/activities")
async def create_activity(
    lead_id: str,
    body: ActivityCreate,
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    await _one(sb, "leads", "id", lead_id)
    payload = {
        "lead_id": lead_id,
        "type": body.type,
        "description": body.description,
        "outcome": body.outcome,
        "performed_by": user.sub,
        "metadata": body.metadata,
    }
    rows = await sb.request("POST", "/activities", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("/{lead_id}/tasks")
async def list_tasks(lead_id: str, sb: SupabaseRest = Depends(get_sb)):
    await _one(sb, "leads", "id", lead_id)
    return await sb.request(
        "GET",
        "/tasks",
        params={"select": "*", "lead_id": f"eq.{lead_id}", "order": "due_date.asc"},
    )


class TaskCreate(BaseModel):
    title: str
    notes: str | None = None
    due_date: str
    due_time: str | None = None


@router.post("/{lead_id}/tasks")
async def create_task(
    lead_id: str,
    body: TaskCreate,
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    await _one(sb, "leads", "id", lead_id)
    payload = {
        **body.model_dump(exclude_none=True),
        "lead_id": lead_id,
        "owner_id": user.sub,
        "status": "pending",
    }
    rows = await sb.request("POST", "/tasks", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("/{lead_id}/meetings")
async def list_meetings_for_lead(lead_id: str, sb: SupabaseRest = Depends(get_sb)):
    await _one(sb, "leads", "id", lead_id)
    return await sb.request(
        "GET",
        "/meetings",
        params={"select": "*", "lead_id": f"eq.{lead_id}", "order": "scheduled_at.asc"},
    )


class MeetingCreate(BaseModel):
    title: str
    scheduled_at: str
    duration_minutes: int | None = 30
    google_event_id: str | None = None
    google_meet_link: str | None = None


@router.post("/{lead_id}/meetings")
async def create_meeting_for_lead(
    lead_id: str,
    body: MeetingCreate,
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    await _one(sb, "leads", "id", lead_id)
    payload = {
        **body.model_dump(exclude_none=True),
        "lead_id": lead_id,
        "owner_id": user.sub,
        "status": "scheduled",
    }
    rows = await sb.request("POST", "/meetings", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows
