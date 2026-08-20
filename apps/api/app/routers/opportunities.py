from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.deps import SupabaseRest, TokenUser, get_current_user, get_sb

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class OpportunityPatch(BaseModel):
    title: str | None = None
    quoted_value: float | None = None
    currency: str | None = None
    timeline_weeks: int | None = None
    tech_stack: str | None = None
    requirements_doc: str | None = None
    architecture_notes: str | None = None
    status: str | None = None
    stage: str | None = None
    deal_probability: int | None = Field(default=None, ge=0, le=100)
    priority_score: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = None


@router.get("")
async def list_opportunities(
    sb: SupabaseRest = Depends(get_sb),
    limit: int = Query(default=500, ge=1, le=500),
    lead_id: str | None = Query(default=None, description="When set, returns at most one row for this lead (light select)."),
):
    """Kanban source: one opportunity per lead with nested lead + company.

    With ``lead_id``, returns a minimal row for lead detail deep-links (no nested joins).
    """
    if lead_id:
        return await sb.request(
            "GET",
            "/opportunities",
            params={
                "select": "id,lead_id,title,status,stage",
                "lead_id": f"eq.{lead_id}",
                "order": "updated_at.desc",
                "limit": "1",
            },
        )
    return await sb.request(
        "GET",
        "/opportunities",
        params={
            "select": "*,leads(*,companies(*))",
            "order": "updated_at.desc",
            "limit": str(limit),
        },
    )


@router.patch("/{opportunity_id}")
async def patch_opportunity(
    opportunity_id: str,
    body: OpportunityPatch,
    sb: SupabaseRest = Depends(get_sb),
):
    patch = body.model_dump(exclude_none=True)
    if not patch:
        rows = await sb.request("GET", "/opportunities", params={"select": "*", "id": f"eq.{opportunity_id}"})
        if not rows:
            raise HTTPException(404, "Opportunity not found")
        return rows[0]
    rows = await sb.request(
        "PATCH",
        "/opportunities",
        params={"id": f"eq.{opportunity_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("/{opportunity_id}")
async def get_opportunity(opportunity_id: str, sb: SupabaseRest = Depends(get_sb)):
    rows = await sb.request(
        "GET",
        "/opportunities",
        params={
            "select": "*,proposals(*)",
            "id": f"eq.{opportunity_id}",
        },
    )
    if not rows:
        raise HTTPException(404, "Opportunity not found")
    return rows[0]


class ProposalCreate(BaseModel):
    title: str
    figma_url: str | None = None
    github_url: str | None = None
    loom_url: str | None = None
    quoted_price: float | None = None
    change_notes: str | None = None
    status: str | None = "draft"


async def _next_proposal_version(sb: SupabaseRest, opportunity_id: str) -> int:
    existing = await sb.request(
        "GET",
        "/proposals",
        params={
            "select": "version",
            "opportunity_id": f"eq.{opportunity_id}",
            "order": "version.desc",
            "limit": "1",
        },
    )
    if existing:
        return int(existing[0]["version"]) + 1
    return 1


@router.post("/{opportunity_id}/proposals")
async def create_proposal_version(
    opportunity_id: str,
    body: ProposalCreate,
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    next_version = await _next_proposal_version(sb, opportunity_id)
    payload = {
        **body.model_dump(exclude_none=True),
        "opportunity_id": opportunity_id,
        "version": next_version,
        "created_by": user.sub,
    }
    rows = await sb.request("POST", "/proposals", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows


@router.post("/{opportunity_id}/proposals/upload")
async def upload_proposal_file(
    opportunity_id: str,
    file: UploadFile = File(...),
    title: str = Form(...),
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    """Upload PDF/binary to Supabase Storage bucket `proposals`, then create proposal row with file_url."""
    if not settings.supabase_service_role_key:
        raise HTTPException(503, "SUPABASE_SERVICE_ROLE_KEY required for uploads")
    bucket = settings.proposals_bucket
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "Max file size 50MB")
    safe_name = (file.filename or "proposal").replace("/", "_")[:200]
    next_version = await _next_proposal_version(sb, opportunity_id)
    storage_path = f"{opportunity_id}/v{next_version}_{uuid.uuid4().hex[:8]}_{safe_name}"
    url_base = settings.supabase_url.rstrip("/")
    storage_url = f"{url_base}/storage/v1/object/{bucket}/{storage_path}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            storage_url,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": file.content_type or "application/octet-stream",
            },
            content=data,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, f"Storage upload failed: {r.text}")
    public_url = f"{url_base}/storage/v1/object/public/{bucket}/{storage_path}"
    payload = {
        "opportunity_id": opportunity_id,
        "version": next_version,
        "title": title,
        "file_url": public_url,
        "created_by": user.sub,
        "status": "draft",
    }
    rows = await sb.request("POST", "/proposals", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows
