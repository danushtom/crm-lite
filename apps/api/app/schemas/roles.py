"""Role and permission schemas -- see supabase/migrations/20260905160000_dynamic_roles.sql."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class Permission(APIModel):
    resource: str
    action: str
    description: str


class Role(APIModel):
    id: str
    name: str
    grants_full_access: bool = Field(
        description="Bypasses row-level ownership entirely within this organization."
    )
    is_system: bool = Field(description="One of the four roles every organization is seeded with.")
    permissions: list[str] = Field(
        description="'<resource>.<action>' keys this role holds, e.g. 'leads.write'."
    )
    user_count: int = Field(description="Active users currently assigned this role.")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleCreate(StrictAPIModel):
    name: str = Field(min_length=1, max_length=100)
    grants_full_access: bool = False
    permission_keys: list[str] = Field(
        default_factory=list,
        description="'<resource>.<action>' keys from GET /roles/catalog to grant this role.",
    )


class RoleUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    grants_full_access: bool | None = None
    permission_keys: list[str] | None = Field(
        default=None,
        description="Replaces the role's entire permission set when present.",
    )
