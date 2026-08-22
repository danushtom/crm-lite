"""Authentication endpoints: current user, and the Google Calendar OAuth exchange."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request

from app.api.deps import CurrentUserDep, DbDep, ProfileDep
from app.core.config import settings
from app.core.errors import NotConfiguredError, UpstreamError
from app.core.rate_limit import limiter
from app.db.supabase import SupabaseAdminClient, get_http_client
from app.schemas.auth import CurrentUser, GoogleOAuthExchange, GoogleOAuthResult
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Get the authenticated user's profile",
    description="Resolves the caller's role, which lives on the profile row rather than the token.",
    responses=AUTH_RESPONSES,
)
async def read_current_user(profile: ProfileDep, user: CurrentUserDep) -> CurrentUser:
    return CurrentUser(
        id=str(profile.get("id") or user.sub),
        email=profile.get("email") or user.email,
        full_name=profile.get("full_name") or "",
        role=str(profile.get("role") or "agent"),
        avatar_url=profile.get("avatar_url"),
        is_active=bool(profile.get("is_active", True)),
    )


@router.post(
    "/google/callback",
    response_model=GoogleOAuthResult,
    summary="Exchange a Google authorization code for Calendar tokens",
    description=(
        "Completes the Calendar OAuth flow and stores the refresh token against the caller's "
        "profile. Tokens are written with the service role because the column is not "
        "user-writable under RLS."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    body: GoogleOAuthExchange,
    user: CurrentUserDep,
    _db: DbDep,
) -> GoogleOAuthResult:
    if not (settings.google_client_id and settings.google_client_secret):
        raise NotConfiguredError(
            "Google OAuth is not configured (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)"
        )
    redirect_uri = body.redirect_uri or settings.google_redirect_uri
    if not redirect_uri:
        raise NotConfiguredError("GOOGLE_REDIRECT_URI is not configured")

    client = get_http_client()
    try:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": body.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Could not reach Google's token endpoint") from exc

    if response.status_code >= 400:
        # Google echoes the client_secret context in errors; never forward the body.
        logger.error("google_token_exchange_failed status=%s", response.status_code)
        raise UpstreamError("Google rejected the authorization code")

    tokens = response.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise UpstreamError("Google's token response contained no access token")

    updates = {"google_access_token": access_token}
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        updates["google_refresh_token"] = refresh_token

    admin = SupabaseAdminClient()
    await admin.update("users", {"id": f"eq.{user.sub}"}, updates)

    return GoogleOAuthResult(
        connected=True,
        scope=tokens.get("scope"),
        expires_in=tokens.get("expires_in"),
    )
