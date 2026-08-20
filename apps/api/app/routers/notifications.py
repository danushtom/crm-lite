from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import SupabaseRest, get_sb

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationPatch(BaseModel):
    read: bool = True


@router.get("")
async def list_notifications(
    sb: SupabaseRest = Depends(get_sb),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = False,
):
    params: dict[str, str] = {
        "select": "*",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if unread_only:
        params["read_at"] = "is.null"
    return await sb.request("GET", "/notifications", params=params)


@router.patch("/read-all")
async def mark_all_read(sb: SupabaseRest = Depends(get_sb)):
    """Mark all notifications as read for current user."""
    ts = datetime.now(timezone.utc).isoformat()
    await sb.request(
        "PATCH",
        "/notifications",
        params={"read_at": "is.null"},
        json_body={"read_at": ts},
        prefer="return=minimal",
    )
    return {"ok": True}


@router.patch("/{notification_id}")
async def patch_notification(
    notification_id: str,
    body: NotificationPatch,
    sb: SupabaseRest = Depends(get_sb),
):
    patch: dict[str, Any] = {}
    if body.read:
        patch["read_at"] = datetime.now(timezone.utc).isoformat()
    rows = await sb.request(
        "PATCH",
        "/notifications",
        params={"id": f"eq.{notification_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    if not rows:
        raise HTTPException(404, "Notification not found")
    return rows[0] if isinstance(rows, list) else rows
