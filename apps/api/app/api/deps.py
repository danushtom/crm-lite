"""FastAPI dependencies: authentication, database clients and role gates.

Endpoints depend on the annotated aliases at the bottom of this module
(``CurrentUserDep``, ``DbDep``, ``AdminDep`` ...) rather than wiring ``Depends`` by hand, so
security requirements are declared uniformly and show up correctly in the OpenAPI schema.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import TokenUser, decode_access_token_async
from app.db.supabase import SupabaseAdminClient, SupabaseClient
from app.domain.enums import UserRole

bearer_scheme = HTTPBearer(
    scheme_name="SupabaseAccessToken",
    description="Supabase access token (JWT) issued to the signed-in user.",
    auto_error=False,
)

BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def get_access_token(credentials: BearerDep) -> str:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authorization header with a bearer token is required")
    if (credentials.scheme or "").lower() != "bearer":
        raise UnauthorizedError("Authorization scheme must be Bearer")
    return credentials.credentials


AccessTokenDep = Annotated[str, Depends(get_access_token)]


async def get_current_user(request: Request, token: AccessTokenDep) -> TokenUser:
    """Verify the caller's token and expose it for rate-limit keying and logging."""
    user = await decode_access_token_async(token)
    request.state.user = user
    return user


CurrentUserDep = Annotated[TokenUser, Depends(get_current_user)]


async def get_db(token: AccessTokenDep, _user: CurrentUserDep) -> SupabaseClient:
    """PostgREST client bound to the caller's token, so every query is RLS-scoped.

    Depending on ``get_current_user`` here is deliberate: it guarantees the token is verified
    before it is ever forwarded upstream.
    """
    return SupabaseClient(token)


DbDep = Annotated[SupabaseClient, Depends(get_db)]


async def get_admin_db() -> SupabaseAdminClient:
    """Service-role client. Bypasses RLS -- only for privileged, well-audited operations."""
    return SupabaseAdminClient()


AdminDbDep = Annotated[SupabaseAdminClient, Depends(get_admin_db)]


async def get_current_profile(db: DbDep, user: CurrentUserDep) -> dict:
    """Load the caller's ``public.users`` row (their role lives there, not in the token)."""
    result = await db.select("users", params={"select": "*", "id": f"eq.{user.sub}"})
    profile = result.first()
    if profile is None:
        raise ForbiddenError("No profile exists for this account")
    return profile


ProfileDep = Annotated[dict, Depends(get_current_profile)]


def require_roles(*allowed: UserRole):
    """Build a dependency asserting the caller holds one of ``allowed``."""
    allowed_values = {str(role) for role in allowed}

    async def _guard(profile: ProfileDep) -> dict:
        if str(profile.get("role")) not in allowed_values:
            raise ForbiddenError(
                "This action requires one of the following roles: "
                + ", ".join(sorted(allowed_values))
            )
        return profile

    return _guard


require_admin = require_roles(UserRole.ADMIN)
AdminDep = Annotated[dict, Depends(require_admin)]


async def forbid_partner(profile: ProfileDep) -> dict:
    """Partners are external collaborators: they may read, but not edit CRM intelligence."""
    if str(profile.get("role")) == UserRole.PARTNER:
        raise ForbiddenError("Partners cannot edit CRM intelligence")
    return profile


NonPartnerDep = Annotated[dict, Depends(forbid_partner)]
