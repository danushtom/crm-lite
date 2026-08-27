"""Dashboard aggregate endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep, ProfileDep
from app.schemas.common import AUTH_RESPONSES
from app.schemas.dashboard import DashboardMetrics, TrendPoint
from app.schemas.tasks import FollowUpQueues, Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

UPCOMING_WINDOW_DAYS = 14
DEFAULT_TIMEZONE = "Asia/Kolkata"


def _unwrap_rpc(data: Any) -> dict[str, Any]:
    """PostgREST wraps a jsonb-returning RPC as ``[{"dashboard_metrics": {...}}]``."""
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        inner = data.get("dashboard_metrics")
        return inner if isinstance(inner, dict) else data
    return {}


def _zone_for(profile: dict[str, Any]) -> tuple[ZoneInfo, str]:
    """Resolve the caller's timezone, falling back rather than failing their dashboard."""
    name = str(profile.get("timezone") or DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("unknown timezone %r on user %s; using %s", name, profile.get("id"), DEFAULT_TIMEZONE)
        return ZoneInfo(DEFAULT_TIMEZONE), DEFAULT_TIMEZONE


@router.get(
    "",
    response_model=DashboardMetrics,
    summary="Pipeline and activity KPIs",
    description=(
        "Computed by the `dashboard_metrics()` SQL function so aggregation happens in the "
        "database rather than over a full table fetch. Admins see organisation-wide totals; "
        "everyone else sees only what they own. When `mixed_currency` is true the headline "
        "totals add different units -- read `pipeline_by_currency` instead."
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
        "Day boundaries are computed in the caller's own timezone, not the server's. With "
        "agents in IST and a server in UTC those differ for five and a half hours a day, "
        "which is long enough to report a task due today as overdue."
    ),
    responses=AUTH_RESPONSES,
)
async def get_follow_ups(db: DbDep, user: CurrentUserDep, profile: ProfileDep) -> FollowUpQueues:
    tz, tz_name = _zone_for(profile)

    local_now = datetime.now(timezone.utc).astimezone(tz)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    horizon = day_start + timedelta(days=UPCOMING_WINDOW_DAYS + 1)

    owner = f"eq.{user.sub}"

    async def query(**filters: str) -> list[dict[str, Any]]:
        result = await db.select(
            "tasks",
            params={"select": "*", "owner_id": owner, "order": "due_at.asc,id.desc", **filters},
        )
        return result.rows

    overdue = await query(status="eq.pending", due_at=f"lt.{day_start.isoformat()}")
    due_today = await query(
        due_at=f"gte.{day_start.isoformat()}",
        **{"and": f"(due_at.lt.{day_end.isoformat()})"},
    )
    upcoming = await query(
        status="eq.pending",
        due_at=f"gte.{day_end.isoformat()}",
        **{"and": f"(due_at.lt.{horizon.isoformat()})"},
    )

    return FollowUpQueues(
        today=[Task.model_validate(t) for t in due_today],
        overdue=[Task.model_validate(t) for t in overdue],
        upcoming=[Task.model_validate(t) for t in upcoming],
        timezone=tz_name,
    )


@router.get(
    "/trend",
    response_model=list[TrendPoint],
    summary="Monthly won and opened value",
    description=(
        "What actually happened, month by month. The dashboard previously drew this from a "
        "formula over the current pipeline total, which moved plausibly but described nothing. "
        "Won dates come from the audit log where it has them."
    ),
    responses=AUTH_RESPONSES,
)
async def get_trend(
    db: DbDep,
    months: Annotated[int, Query(ge=1, le=24, description="How many months to include.")] = 6,
) -> list[TrendPoint]:
    result = await db.rpc("pipeline_trend", {"months": months})
    data = result.data
    if isinstance(data, list) and data and isinstance(data[0], dict) and "pipeline_trend" in data[0]:
        data = data[0]["pipeline_trend"]
    return [TrendPoint.model_validate(p) for p in (data or [])]
