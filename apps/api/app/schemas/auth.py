"""Authentication / OAuth schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel, StrictAPIModel


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
    role: str
    avatar_url: str | None = None
    is_active: bool = True
