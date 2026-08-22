"""Dashboard aggregate endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.schemas.common import AUTH_RESPONSES
from app.schemas.dashboard import DashboardMetrics
from app.schemas.tasks import FollowUpQueues, Task

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

UPCOMING_WINDOW_DAYS = 14


def _unwrap_rpc(data: Any) -> dict[str, Any]:
    """PostgREST wraps a jsonb-returning RPC as ``[{"dashboard_metrics": {...}}]``."""
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        inner = data.get("dashboard_metrics")
        return inner if isinstance(inner, dict) else data
    return {}


@router.get(
    "",
    response_model=DashboardMetrics,
    summary="Pipeline and activity KPIs",
    description=(
        "Computed by the `dashboard_metrics()` SQL function so aggregation happens in the "
        "database rather than over a full table fetch. Admins see organisation-wide totals; "
        "everyone else sees only what they own."
    ),
    responses=AUTH_RESPONSES,
)
async def get_dashboard(db: DbDep) -> DashboardMetrics:
    result = await db.rpc("dashboard_metrics")
    payload = _unwrap_rpc(result.data)
    hot = payload.get("hot_leads_needing_action")
    if isinstance(hot, list):
        payload["hot_leads_needing_action"] = [str(item) for item in hot]
    return DashboardMetrics.model_validate(payload)


@router.get(
    "/follow-ups",
    response_model=FollowUpQueues,
    summary="Today, overdue and upcoming follow-up queues",
    description=(
        "Drives the follow-up engine. Queues are computed with database-side filters rather "
        "than by fetching every task and partitioning in Python."
    ),
    responses=AUTH_RESPONSES,
)
async def get_follow_ups(db: DbDep, user: CurrentUserDep) -> FollowUpQueues:
    today = date.today()
    today_iso = today.isoformat()
    horizon = (today + timedelta(days=UPCOMING_WINDOW_DAYS)).isoformat()
    owner = f"eq.{user.sub}"

    overdue = await db.select(
        "tasks",
        params={
            "select": "*",
            "owner_id": owner,
            "status": "eq.pending",
            "due_date": f"lt.{today_iso}",
            "order": "due_date.asc,id.desc",
        },
    )
    due_today = await db.select(
        "tasks",
        params={
            "select": "*",
            "owner_id": owner,
            "due_date": f"eq.{today_iso}",
            "order": "due_date.asc,id.desc",
        },
    )
    upcoming = await db.select(
        "tasks",
        params={
            "select": "*",
            "owner_id": owner,
            "status": "eq.pending",
            "due_date": f"gt.{today_iso}",
            "and": f"(due_date.lte.{horizon})",
            "order": "due_date.asc,id.desc",
        },
    )

    return FollowUpQueues(
        today=[Task.model_validate(t) for t in due_today.rows],
        overdue=[Task.model_validate(t) for t in overdue.rows],
        upcoming=[Task.model_validate(t) for t in upcoming.rows],
    )
