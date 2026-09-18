"""Usage accounting and the per-organization spend ceiling.

One OpenAI key serves every tenant in this deployment. That makes token spend a shared resource
with no natural back-pressure: a single organization looping the assistant, or uploading a
thousand-page PDF, spends money that was not theirs to spend. Postgres cannot help here -- RLS
governs rows, not cost -- so the ceiling is enforced in application code, before the model call.

Two deliberate choices:

* **Check before, record after.** The check reads the month to date; the record is written when
  the work completes. A request that is already in flight is never killed mid-stream -- a user
  watching a half-written answer disappear is worse than a few thousand tokens of overshoot.
* **Recording never fails the request.** If the usage insert fails, the user still gets their
  answer and the failure is logged. Accounting is important; it is not more important than the
  feature working.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from dracara_ai.usage import UsageRecord

from app.core.config import settings
from app.core.errors import APIError
from app.db.supabase import SupabaseAdminClient

logger = logging.getLogger(__name__)


class BudgetExceededError(APIError):
    """This organization is over its monthly token allowance.

    429 rather than 402: the condition is temporary (it clears at the start of the next month)
    and "slow down" is the right client behaviour.
    """

    status_code = 429
    code = "ai_budget_exceeded"


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


async def tokens_used_this_month(admin_db: SupabaseAdminClient, organization_id: str) -> int:
    """Total tokens this organization has spent since the 1st, UTC.

    Uses the admin client deliberately: `ai_usage` has no INSERT policy and its SELECT policy
    requires `ai.manage`, but the budget applies to every user regardless of whether they may
    *see* the spend. Reading it as the caller would let a rep past the ceiling.
    """
    result = await admin_db.select(
        "ai_usage",
        params={
            "select": "total_tokens",
            "organization_id": f"eq.{organization_id}",
            "created_at": f"gte.{_month_start_iso()}",
        },
    )
    return sum(int(row.get("total_tokens") or 0) for row in result.rows)


async def assert_within_budget(admin_db: SupabaseAdminClient, organization_id: str) -> None:
    """Raise :class:`BudgetExceededError` if this organization is over its allowance."""
    limit = settings.ai_monthly_token_budget
    if limit <= 0:
        return

    used = await tokens_used_this_month(admin_db, organization_id)
    if used >= limit:
        logger.warning(
            "ai_budget_exceeded org_id=%s used=%d limit=%d", organization_id, used, limit
        )
        raise BudgetExceededError(
            "This organization has reached its AI usage limit for the month. "
            "It resets on the 1st, or an admin can raise AI_MONTHLY_TOKEN_BUDGET."
        )


async def record(
    admin_db: SupabaseAdminClient,
    *,
    organization_id: str,
    usage: UsageRecord,
    user_id: str | None = None,
) -> None:
    """Persist one usage record. Never raises -- see the module docstring."""
    if usage.total_tokens <= 0 and usage.extra_cost_usd <= 0:
        # A graph whose deterministic gate short-circuited before any model or search call.
        # (Web search bills in dollars with zero tokens, so tokens alone is not the test.)
        return
    try:
        row = usage.to_row(organization_id)
        row["user_id"] = user_id
        await admin_db.insert("ai_usage", row)
    except Exception:
        logger.exception(
            "ai_usage_record_failed org_id=%s feature=%s tokens=%d",
            organization_id,
            usage.feature,
            usage.total_tokens,
        )
