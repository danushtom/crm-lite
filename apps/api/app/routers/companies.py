from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import SupabaseRest, TokenUser, get_current_user, get_sb

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyCreate(BaseModel):
    name: str
    industry: str | None = None
    size: str | None = None
    website: str | None = None
    location: str | None = None
    logo_url: str | None = None
    linkedin_url: str | None = None
    segment: str | None = None  # sme | startup | enterprise (company_segment enum)


class CompanyPatch(BaseModel):
    name: str | None = None
    industry: str | None = None
    size: str | None = None
    website: str | None = None
    location: str | None = None
    logo_url: str | None = None
    linkedin_url: str | None = None
    segment: str | None = None


@router.post("")
async def create_company(body: CompanyCreate, sb: SupabaseRest = Depends(get_sb), user: TokenUser = Depends(get_current_user)):
    payload = body.model_dump(exclude_none=True)
    payload["created_by"] = user.sub
    rows = await sb.request("POST", "/companies", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("")
async def list_companies(sb: SupabaseRest = Depends(get_sb)):
    return await sb.request("GET", "/companies", params={"select": "*", "order": "created_at.desc"})


@router.get("/{company_id}")
async def get_company(company_id: str, sb: SupabaseRest = Depends(get_sb)):
    rows = await sb.request("GET", "/companies", params={"select": "*", "id": f"eq.{company_id}"})
    if not rows:
        raise HTTPException(404, "Company not found")
    return rows[0]


@router.patch("/{company_id}")
async def patch_company(company_id: str, body: CompanyPatch, sb: SupabaseRest = Depends(get_sb)):
    patch = body.model_dump(exclude_none=True)
    if not patch:
        return await get_company(company_id, sb)
    rows = await sb.request(
        "PATCH",
        "/companies",
        params={"id": f"eq.{company_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    return rows[0] if isinstance(rows, list) and rows else rows
