"""Authentication / OAuth schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class GoogleOAuthExchange(StrictAPIModel):
    code: str = Field(min_length=1, max_length=2048, description="Authorization code from Google.")
    redirect_uri: str | None = Field(
        default=None,
        max_length=2048,
        description="Overrides GOOGLE_REDIRECT_URI when the client used a different callback.",
    )


class GoogleOAuthResult(APIModel):
    connected: bool = Field(description="True once Calendar tokens are stored for the user.")
    scope: str | None = Field(default=None, description="Scopes Google granted.")
    expires_in: int | None = Field(default=None, description="Access-token lifetime in seconds.")


class CurrentUser(APIModel):
    """The authenticated caller's profile, as the API sees it."""

    id: str
    email: str | None = None
    full_name: str = ""
    role_id: str
    role_name: str
    grants_full_access: bool = Field(
        description="True when this user's role bypasses row ownership within the organization."
    )
    permissions: list[str] = Field(
        description="'<resource>.<action>' keys this user's role holds, e.g. 'leads.write'."
    )
    organization_id: str
    avatar_url: str | None = None
    is_active: bool = True

    calendar_connected: bool = Field(
        default=False, description="True once Google Calendar tokens are stored for this user."
    )
    timezone: str = Field(
        default="Asia/Kolkata",
        description="IANA zone deciding when this user's follow-up queue rolls over.",
    )


class CurrentUserUpdate(PatchModel):
    """What a user may change about themselves.

    Deliberately excludes role and is_active: those are administrative, and letting someone
    edit their own row would otherwise be a privilege-escalation path. The database enforces
    the same rule independently.
    """

    full_name: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=1000)
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="IANA zone, e.g. 'Asia/Kolkata'. Rejected if Postgres cannot resolve it.",
    )


class GoogleAuthorizeUrl(APIModel):
    """Where to send the browser to begin the Calendar consent flow."""

    authorize_url: str
    state: str = Field(description="Echo this back on the callback to prove the flow is yours.")
