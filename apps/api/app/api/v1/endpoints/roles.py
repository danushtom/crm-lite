"""Role management: create/edit/delete organization-owned roles and their permission grants.

Row-level visibility is untouched by any of this -- see supabase/migrations/
20260905160000_dynamic_roles.sql. A role's permissions are feature gates (checked via
app.api.deps.require_permission); the only thing that changes what a user can *see* is
`grants_full_access`, which bypasses row ownership entirely within the organization.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Response, status

from app.api.deps import AdminDep, DbDep
from app.core.concurrency import IfMatchDep, set_etag, update_guarded
from app.core.errors import ForbiddenError, UnprocessableError
from app.schemas.common import ERROR_RESPONSES
from app.schemas.roles import Permission, Role, RoleCreate, RoleUpdate

router = APIRouter(prefix="/roles", tags=["Roles"])


def _role_from_row(row: dict[str, Any], user_counts: Counter[str]) -> Role:
    grants = row.get("role_permissions") or []
    permissions = [
        f"{g['permissions']['resource']}.{g['permissions']['action']}"
        for g in grants
        if g.get("permissions")
    ]
    return Role(
        id=row["id"],
        name=row["name"],
        grants_full_access=row["grants_full_access"],
        is_system=row["is_system"],
        permissions=sorted(permissions),
        user_count=user_counts.get(row["id"], 0),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


async def _resolve_permission_ids(db: DbDep, keys: list[str]) -> list[str]:
    if not keys:
        return []
    result = await db.select("permissions", params={"select": "id,resource,action"})
    by_key = {f"{p['resource']}.{p['action']}": p["id"] for p in result.rows}
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise UnprocessableError(f"Unknown permission key(s): {', '.join(sorted(unknown))}")
    return [by_key[k] for k in keys]


@router.get(
    "/catalog",
    response_model=list[Permission],
    summary="List every permission a role can be granted",
    responses=ERROR_RESPONSES,
)
async def list_permission_catalog(db: DbDep) -> list[Permission]:
    result = await db.select(
        "permissions", params={"select": "*", "order": "resource.asc,action.asc,id.asc"}
    )
    return [Permission(resource=p["resource"], action=p["action"], description=p["description"]) for p in result.rows]


@router.get(
    "",
    response_model=list[Role],
    summary="List this organization's roles",
    responses=ERROR_RESPONSES,
)
async def list_roles(db: DbDep) -> list[Role]:
    roles_result = await db.select(
        "roles",
        params={
            "select": "*,role_permissions(permissions(resource,action))",
            "order": "created_at.asc,id.asc",
        },
    )
    users_result = await db.select("users", params={"select": "role_id"})
    user_counts: Counter[str] = Counter(u["role_id"] for u in users_result.rows)
    return [_role_from_row(row, user_counts) for row in roles_result.rows]


@router.post(
    "",
    response_model=Role,
    status_code=status.HTTP_201_CREATED,
    summary="Create a role",
    description="Requires a role with full organization access.",
    responses=ERROR_RESPONSES,
)
async def create_role(body: RoleCreate, db: DbDep, _admin: AdminDep, response: Response) -> Role:
    permission_ids = await _resolve_permission_ids(db, body.permission_keys)

    inserted = await db.insert(
        "roles", {"name": body.name, "grants_full_access": body.grants_full_access}
    )
    role = inserted.one("Role")

    if permission_ids:
        await db.insert(
            "role_permissions",
            [{"role_id": role["id"], "permission_id": pid} for pid in permission_ids],
        )

    full = await db.select(
        "roles",
        params={
            "select": "*,role_permissions(permissions(resource,action))",
            "id": f"eq.{role['id']}",
        },
    )
    row = full.one("Role")
    set_etag(response, row)
    return _role_from_row(row, Counter())


@router.patch(
    "/{role_id}",
    response_model=Role,
    summary="Rename, re-grant, or toggle full access on a role",
    description=(
        "Requires a role with full organization access. Removing full access from, or "
        "deleting, the organization's last full-access role is rejected by the database."
    ),
    responses=ERROR_RESPONSES,
)
async def update_role(
    role_id: str,
    body: RoleUpdate,
    db: DbDep,
    _admin: AdminDep,
    response: Response,
    if_match: IfMatchDep,
) -> Role:
    changes = body.changes()
    permission_keys = changes.pop("permission_keys", None)

    if changes:
        row = await update_guarded(db, "roles", record_id=role_id, changes=changes, if_match=if_match, what="Role")
    else:
        existing = await db.select("roles", params={"select": "*", "id": f"eq.{role_id}"})
        row = existing.one("Role")

    if permission_keys is not None:
        permission_ids = await _resolve_permission_ids(db, permission_keys)
        await db.delete("role_permissions", {"role_id": f"eq.{role_id}"})
        if permission_ids:
            await db.insert(
                "role_permissions",
                [{"role_id": role_id, "permission_id": pid} for pid in permission_ids],
            )

    full = await db.select(
        "roles",
        params={
            "select": "*,role_permissions(permissions(resource,action))",
            "id": f"eq.{role_id}",
        },
    )
    users_result = await db.select("users", params={"select": "role_id", "role_id": f"eq.{role_id}"})
    user_counts: Counter[str] = Counter(u["role_id"] for u in users_result.rows)
    final_row = full.one("Role")
    set_etag(response, row)
    return _role_from_row(final_row, user_counts)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a role",
    description=(
        "Requires a role with full organization access. Rejected while any user is still "
        "assigned this role, or if it is the organization's last full-access role."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_role(role_id: str, db: DbDep, _admin: AdminDep) -> Response:
    existing = await db.select("roles", params={"select": "id", "id": f"eq.{role_id}"})
    existing.one("Role")

    deleted = await db.delete("roles", {"id": f"eq.{role_id}"})
    if deleted.first() is None:
        raise ForbiddenError("You do not have permission to delete this role")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
