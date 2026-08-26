"""Authentication endpoints: current user, and the Google Calendar OAuth exchange."""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUserDep, DbDep, ProfileDep
from app.core.concurrency import set_etag
from app.core.config import settings
from app.core.errors import NotConfiguredError, UpstreamError
from app.core.rate_limit import limiter
from app.db.supabase import SupabaseAdminClient, get_http_client
from app.schemas.auth import (
    CurrentUser,
    CurrentUserUpdate,
    GoogleAuthorizeUrl,
    GoogleOAuthExchange,
    GoogleOAuthResult,
)
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
        timezone=str(profile.get("timezone") or "Asia/Kolkata"),
        # Never return the tokens themselves -- only whether the connection exists.
        calendar_connected=bool(profile.get("google_refresh_token")),
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


@router.patch(
    "/me",
    response_model=CurrentUser,
    summary="Update your own profile",
    description=(
        "Name, avatar and timezone. Role and access are administrative and cannot be changed "
        "here -- see `PATCH /agents/{id}`. Timezone decides when your follow-up queue rolls "
        "over to the next day, so it is the one setting worth getting right."
    ),
    responses=ERROR_RESPONSES,
)
async def update_current_user(
    body: CurrentUserUpdate,
    db: DbDep,
    user: CurrentUserDep,
    response: Response,
) -> CurrentUser:
    changes = CurrentUserUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        profile = await db.select("users", params={"select": "*", "id": f"eq.{user.sub}"})
        return await read_current_user(profile.one("Profile"), user)

    result = await db.update("users", {"id": f"eq.{user.sub}"}, changes)
    updated = result.one("Profile")
    set_etag(response, updated)
    return await read_current_user(updated, user)


@router.get(
    "/google/authorize-url",
    response_model=GoogleAuthorizeUrl,
    summary="Start the Google Calendar consent flow",
    description=(
        "Returns the URL to send the browser to. Built server-side so the client id and the "
        "scope list stay in one place -- a frontend that assembles this itself will drift "
        "from what the callback expects."
    ),
    responses=ERROR_RESPONSES,
)
async def google_authorize_url(user: CurrentUserDep) -> GoogleAuthorizeUrl:
    if not settings.google_client_id:
        raise NotConfiguredError(
            "Google Calendar is not configured on this server (GOOGLE_CLIENT_ID)."
        )
    if not settings.google_redirect_uri:
        raise NotConfiguredError("GOOGLE_REDIRECT_URI is not configured on this server.")

    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(
                [
                    "https://www.googleapis.com/auth/calendar.events",
                    "https://www.googleapis.com/auth/calendar.readonly",
                ]
            ),
            # Without these Google returns no refresh token on a repeat consent, and the
            # worker's nightly sync silently stops working a week later.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return GoogleAuthorizeUrl(
        authorize_url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
        state=state,
    )


@router.delete(
    "/google",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect Google Calendar",
    description="Clears the stored tokens. Meetings already synced are kept.",
    responses=ERROR_RESPONSES,
)
async def disconnect_google(user: CurrentUserDep) -> Response:
    # Written with the service role: the token columns are deliberately not user-writable.
    admin = SupabaseAdminClient()
    await admin.update(
        "users",
        {"id": f"eq.{user.sub}"},
        {"google_access_token": None, "google_refresh_token": None},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
