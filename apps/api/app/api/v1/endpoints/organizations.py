"""The caller's own organization: read it, and let an admin rename it.

There is deliberately no create or delete here. An organization is created as a side effect of
the first user signing up (``handle_new_user()`` in the initial schema), and deleting a tenant
would cascade through every table in the product -- that is an operational action, not a
self-service API.

Writes go through the service-role client rather than the caller's: ``organizations`` has a
SELECT policy for authenticated users but no UPDATE policy, so an RLS-scoped update matches
zero rows and PostgREST reports that as success with an empty body -- the same silent no-op
that the compliance acknowledgment in voice_agents.py works around. ``AdminDep`` is what
actually gates this, and the update is pinned to the caller's own organization id taken from
their profile, never from the request.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import AdminDbDep, AdminDep, DbDep, ProfileDep
from app.core.concurrency import set_etag
from app.schemas.common import ERROR_RESPONSES
from app.schemas.organizations import Organization, OrganizationUpdate

router = APIRouter(prefix="/organizations", tags=["Organizations"])

_SELECT = "id,name,slug,created_at,ai_calling_compliance_ack_at"


@router.get(
    "/me",
    response_model=Organization,
    summary="Get the caller's organization",
    description="Any authenticated member may read it; only a full-access role may change it.",
    responses=ERROR_RESPONSES,
)
async def read_organization(profile: ProfileDep, db: DbDep, response: Response) -> Organization:
    result = await db.select(
        "organizations", params={"select": _SELECT, "id": f"eq.{profile['organization_id']}"}
    )
    row = result.one("Organization")
    set_etag(response, row)
    return Organization.model_validate(row)


@router.patch(
    "/me",
    response_model=Organization,
    summary="Rename the caller's organization",
    description=(
        "Requires a role with full organization access. The workspace name appears on every "
        "AI voice agent's recording disclosure, so changing it changes what callers are told."
    ),
    responses=ERROR_RESPONSES,
)
async def update_organization(
    body: OrganizationUpdate,
    profile: ProfileDep,
    admin_db: AdminDbDep,
    response: Response,
    _admin: AdminDep,
) -> Organization:
    changes = OrganizationUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        db_result = await admin_db.select(
            "organizations", params={"select": _SELECT, "id": f"eq.{profile['organization_id']}"}
        )
        return Organization.model_validate(db_result.one("Organization"))

    result = await admin_db.update(
        "organizations",
        {"id": f"eq.{profile['organization_id']}", "select": _SELECT},
        changes,
    )
    row = result.one("Organization")
    set_etag(response, row)
    return Organization.model_validate(row)
