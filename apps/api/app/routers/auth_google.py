"""Exchange Google OAuth authorization code; persist Calendar tokens on users (service role)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.deps import TokenUser, get_current_user
from app.limits import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


async def _patch_user_google_tokens(user_id: str, access_token: str, refresh_token: str | None) -> None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "SUPABASE_SERVICE_ROLE_KEY required to store Google tokens")
    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/users"
    body: dict = {"google_access_token": access_token}
    if refresh_token:
        body["google_refresh_token"] = refresh_token
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.patch(
            url,
            params={"id": f"eq.{user_id}"},
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=body,
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)


class GoogleCodeBody(BaseModel):
    code: str


@router.post("/google")
@limiter.limit("30/minute")
async def exchange_google_oauth(
    request: Request,
    body: GoogleCodeBody,
    user: TokenUser = Depends(get_current_user),
):
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        raise HTTPException(
            501,
            "Google OAuth not configured (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI)",
        )
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": body.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    tok = r.json()
    access = tok.get("access_token")
    refresh = tok.get("refresh_token")
    if not access:
        raise HTTPException(502, "Google token response missing access_token")
    await _patch_user_google_tokens(user.sub, access, refresh)
    return {"ok": True, "scope": tok.get("scope")}
