"""FastAPI dependencies: authentication, database clients and role gates.

Endpoints depend on the annotated aliases at the bottom of this module
(``CurrentUserDep``, ``DbDep``, ``AdminDep`` ...) rather than wiring ``Depends`` by hand, so
security requirements are declared uniformly and show up correctly in the OpenAPI schema.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ForbiddenError, PaymentRequiredError, UnauthorizedError
from app.core.security import TokenUser, decode_access_token_async
from app.db.supabase import SupabaseAdminClient, SupabaseClient
from app.services import billing

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


#: role/permissions live two joins away (users -> roles -> role_permissions -> permissions),
#: not on the users row directly. Anywhere a profile is re-fetched (not just get_current_profile
#: below) needs this same embed, or is_full_access()/has_permission() silently see no role at
#: all rather than an error -- reuse this rather than writing "select": "*" by hand.
PROFILE_SELECT = "*,roles(id,name,grants_full_access,role_permissions(permissions(resource,action))),organizations!users_organization_id_fkey(name)"


async def get_current_profile(db: DbDep, user: CurrentUserDep) -> dict:
    """Load the caller's ``public.users`` row, with their role and its permission grants
    embedded in the same query -- see PROFILE_SELECT.
    """
    result = await db.select(
        "users", params={"select": PROFILE_SELECT, "id": f"eq.{user.sub}"}
    )
    profile = result.first()
    if profile is None:
        raise ForbiddenError("No profile exists for this account")
    # Deactivated users are refused here as well as in RLS. The database is the authority --
    # current_org_id() and is_admin() both require is_active -- but a token that outlives a
    # revocation should get a clear 403 from the API rather than a silently empty collection.
    if not profile.get("is_active", True):
        raise ForbiddenError("This account's access has been revoked")
    return profile


ProfileDep = Annotated[dict, Depends(get_current_profile)]


def is_full_access(profile: dict) -> bool:
    """True when the profile's role bypasses ownership entirely within its organization."""
    role = profile.get("roles") or {}
    return bool(role.get("grants_full_access"))


def has_permission(profile: dict, permission: str) -> bool:
    """``permission`` is a ``'<resource>.<action>'`` key from the permissions catalog."""
    if is_full_access(profile):
        return True
    role = profile.get("roles") or {}
    for grant in role.get("role_permissions") or []:
        perm = grant.get("permissions") or {}
        if f"{perm.get('resource')}.{perm.get('action')}" == permission:
            return True
    return False


async def require_full_access(profile: ProfileDep) -> dict:
    if not is_full_access(profile):
        raise ForbiddenError("This action requires a role with full organization access")
    return profile


require_admin = require_full_access
AdminDep = Annotated[dict, Depends(require_full_access)]


def require_permission(permission: str):
    """Build a dependency asserting the caller's role holds ``permission``.

    A role marked ``grants_full_access`` always passes, same as every other bypass in this
    codebase (see ``is_admin()`` in the database).
    """

    async def _guard(profile: ProfileDep) -> dict:
        if not has_permission(profile, permission):
            raise ForbiddenError(f"This action requires the '{permission}' permission")
        return profile

    return _guard


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def plan_gate(feature: str | None = None):
    """Build a dependency that refuses writes the organization's plan does not cover.

    Attached per router in ``app/api/v1/router.py``. Reads are never gated: a lapsed
    organization keeps full read access to its own data (read-only mode), and a downgraded one
    can still see the voice agents or AI results it already has. ``feature`` additionally
    requires that plan feature (see ``app.services.billing.PLANS``).

    Takes ``DbDep`` rather than ``ProfileDep`` on purpose: RLS already narrows
    ``organization_subscriptions`` to the caller's one row, so no profile lookup is needed.
    """

    async def _guard(request: Request, db: DbDep) -> None:
        if request.method in _SAFE_METHODS:
            return
        row = await billing.load_subscription(db)
        if row is None:
            return  # fail open -- see the module docstring of app.services.billing
        ent = billing.entitlements(row)
        if not ent.writable:
            raise PaymentRequiredError(
                "Your free trial or subscription has ended, so this workspace is read-only. "
                "An admin can choose a plan under Settings → Billing.",
                code="subscription_inactive",
            )
        if feature and feature not in ent.features:
            raise PaymentRequiredError(
                "Your current plan does not include this feature. "
                "An admin can upgrade under Settings → Billing.",
                code="plan_upgrade_required",
            )

    return _guard
