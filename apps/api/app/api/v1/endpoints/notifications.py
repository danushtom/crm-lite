"""In-app notification endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep
from app.core.pagination import Page, PageParamsDep
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.notifications import (
    Notification,
    NotificationReadResult,
    NotificationUnreadCount,
    NotificationUpdate,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=Page[Notification],
    summary="List the caller's notifications",
    description="Row-level security restricts results to the authenticated user.",
    responses=AUTH_RESPONSES,
)
async def list_notifications(
    db: DbDep,
    page: PageParamsDep,
    unread_only: Annotated[bool, Query(description="Return only unread notifications.")] = False,
) -> Page[Notification]:
    params: dict[str, str] = {
        "select": "*",
        "order": "created_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if unread_only:
        params["read_at"] = "is.null"

    result = await db.select("notifications", params=params, count=True)
    return Page.build([Notification.model_validate(n) for n in result.rows], page, result.count)


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCount,
    summary="Count unread notifications",
    description="Cheap poll target for the notification bell; avoids fetching full rows.",
    responses=AUTH_RESPONSES,
)
async def unread_count(db: DbDep) -> NotificationUnreadCount:
    result = await db.select(
        "notifications",
        params={"select": "id", "read_at": "is.null", "limit": "1"},
        count=True,
    )
    return NotificationUnreadCount(unread=result.count or 0)


@router.post(
    "/read-all",
    response_model=NotificationReadResult,
    summary="Mark every notification read",
    description=(
        "POST rather than PATCH: this acts on the whole collection rather than partially "
        "updating one addressable resource."
    ),
    responses=AUTH_RESPONSES,
)
async def mark_all_read(db: DbDep, user: CurrentUserDep) -> NotificationReadResult:
    now = datetime.now(timezone.utc).isoformat()
    result = await db.update(
        "notifications",
        {"read_at": "is.null", "user_id": f"eq.{user.sub}"},
        {"read_at": now},
    )
    return NotificationReadResult(updated=len(result.rows))


@router.patch(
    "/{notification_id}",
    response_model=Notification,
    summary="Mark one notification read or unread",
    responses=ERROR_RESPONSES,
)
async def update_notification(
    notification_id: str, body: NotificationUpdate, db: DbDep
) -> Notification:
    read_at = datetime.now(timezone.utc).isoformat() if body.read else None
    result = await db.update(
        "notifications", {"id": f"eq.{notification_id}"}, {"read_at": read_at}
    )
    return Notification.model_validate(result.one("Notification"))


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dismiss a notification",
    responses=ERROR_RESPONSES,
)
async def delete_notification(notification_id: str, db: DbDep) -> Response:
    existing = await db.select(
        "notifications", params={"select": "id", "id": f"eq.{notification_id}"}
    )
    existing.one("Notification")

    await db.delete("notifications", {"id": f"eq.{notification_id}"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
