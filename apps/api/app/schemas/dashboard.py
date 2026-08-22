"""Dashboard and health schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel, Money


class WinLossRatio(APIModel):
    wins: int = 0
    losses: int = 0


class DashboardMetrics(APIModel):
    """Aggregates computed by the ``dashboard_metrics()`` SQL function, scoped by RLS.

    Admins see organisation-wide totals; everyone else sees only what they own.
    """

    pipeline_total: Money = Field(description="Sum of estimated value across visible leads.")
    weighted_forecast: Money = Field(description="Pipeline weighted by each lead's probability.")
    stage_values: dict[str, Money] = Field(
        default_factory=dict, description="Estimated value bucketed by pipeline stage."
    )
    pipeline_by_currency: dict[str, Money] = Field(
        default_factory=dict,
        description="Pipeline value grouped by currency. Always correct, unlike the totals above.",
    )
    mixed_currency: bool = Field(
        default=False,
        description=(
            "True when the visible pipeline spans more than one currency, in which case "
            "pipeline_total and weighted_forecast add different units and are meaningless. "
            "Read pipeline_by_currency instead."
        ),
    )
    followups_today_count: int = 0
    overdue_tasks_count: int = 0
    proposals_pending_response: int = 0
    hot_leads_needing_action: list[str] = Field(
        default_factory=list,
        description="Ids of leads scoring >= 80 with no contact in the last 3 days.",
    )
    win_loss_ratio_30d: WinLossRatio = Field(default_factory=WinLossRatio)


class HealthStatus(APIModel):
    status: str = "ok"


class LivenessStatus(APIModel):
    live: bool = True


class ReadinessStatus(APIModel):
    ready: bool
    supabase_rest_reachable: bool | None = None
    jwks_reachable: bool | None = None
    hs256_secret_configured: bool | None = None
    missing: list[str] | None = Field(default=None, description="Unset required settings.")
    detail: str | None = None


class ServiceInfo(APIModel):
    service: str
    version: str
    environment: str
    docs_url: str
    api_versions: list[str]
