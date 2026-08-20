from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import SupabaseRest, get_sb

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("")
async def list_contacts(sb: SupabaseRest = Depends(get_sb)):
    """List contacts with parent company name for CRM modules UI."""
    return await sb.request(
        "GET",
        "/contacts",
        params={
            "select": "*,companies(name)",
            "order": "created_at.desc",
        },
    )


class ContactCreate(BaseModel):
    company_id: str
    full_name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    avatar_url: str | None = None
    source: str | None = None
    is_primary: bool | None = False


class ContactPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    avatar_url: str | None = None
    source: str | None = None
    is_primary: bool | None = None


@router.post("")
async def create_contact(body: ContactCreate, sb: SupabaseRest = Depends(get_sb)):
    payload = body.model_dump(exclude_none=True)
    rows = await sb.request("POST", "/contacts", json_body=payload, prefer="return=representation")
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("/{contact_id}")
async def get_contact(contact_id: str, sb: SupabaseRest = Depends(get_sb)):
    rows = await sb.request("GET", "/contacts", params={"select": "*", "id": f"eq.{contact_id}"})
    if not rows:
        raise HTTPException(404, "Contact not found")
    return rows[0]


@router.patch("/{contact_id}")
async def patch_contact(contact_id: str, body: ContactPatch, sb: SupabaseRest = Depends(get_sb)):
    patch = body.model_dump(exclude_none=True)
    if not patch:
        return await get_contact(contact_id, sb)
    rows = await sb.request(
        "PATCH",
        "/contacts",
        params={"id": f"eq.{contact_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    return rows[0] if isinstance(rows, list) and rows else rows
