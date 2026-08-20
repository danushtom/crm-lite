"""RBAC helpers — FastAPI dependencies (tdd.md §16.2)."""

from fastapi import Depends, HTTPException

from app.deps import SupabaseRest, TokenUser, get_current_user, get_sb


async def forbid_partner_intel_edit(
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
) -> None:
    rows = await sb.request("GET", "/users", params={"select": "role", "id": f"eq.{user.sub}"})
    if not rows:
        raise HTTPException(403, "Profile missing")
    if rows[0].get("role") == "partner":
        raise HTTPException(403, "Partners cannot edit CRM intelligence")
