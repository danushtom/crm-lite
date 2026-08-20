from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.deps import SupabaseRest, TokenUser, assert_roles, get_current_user, get_sb
from app.limits import limiter

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents(
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    await assert_roles(sb, user, {"admin"})
    return await sb.request("GET", "/users", params={"select": "*", "order": "created_at.desc"})


class InviteBody(BaseModel):
    email: str
    full_name: str | None = None
    role: str | None = "agent"


@router.post("/invite")
@limiter.limit("30/minute")
async def invite_agent(
    request: Request,
    body: InviteBody,
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    await assert_roles(sb, user, {"admin"})
    if not settings.supabase_service_role_key:
        raise HTTPException(501, "SUPABASE_SERVICE_ROLE_KEY required for invites")
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/invite",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": body.email,
                "data": {"full_name": body.full_name or "", "role": body.role or "agent"},
            },
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()


@router.get("/{agent_id}/performance")
async def agent_performance(agent_id: str, sb: SupabaseRest = Depends(get_sb), user: TokenUser = Depends(get_current_user)):
    await assert_roles(sb, user, {"admin"})
    leads_moved = await sb.request(
        "GET",
        "/activities",
        params={
            "select": "id",
            "performed_by": f"eq.{agent_id}",
            "type": "eq.stage_change",
        },
    )
    meetings = await sb.request(
        "GET",
        "/meetings",
        params={"select": "id", "owner_id": f"eq.{agent_id}"},
    )
    leads_owned = await sb.request(
        "GET",
        "/leads",
        params={"select": "id", "owner_id": f"eq.{agent_id}"},
    )
    won = await sb.request(
        "GET",
        "/leads",
        params={"select": "id", "owner_id": f"eq.{agent_id}", "stage": "eq.won"},
    )
    return {
        "agent_id": agent_id,
        "stage_moves_logged": len(leads_moved or []),
        "meetings_count": len(meetings or []),
        "assigned_leads": len(leads_owned or []),
        "wins": len(won or []),
    }
