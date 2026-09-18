"""Plan catalog and entitlements -- see this package's README."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

#: Feature flags a plan can grant. Everything not listed here (the whole core CRM, calendar
#: sync, lead capture, reports, RBAC) is in every plan.
FEATURE_AI = "ai"
FEATURE_VOICE_AGENTS = "voice_agents"
ALL_FEATURES = frozenset({FEATURE_AI, FEATURE_VOICE_AGENTS})

TRIAL_DAYS = 14
TRIAL_SEAT_LIMIT = 5

#: Statuses in which a paid plan's features apply. past_due is the provider's dunning window:
#: it is still retrying the card, so access continues.
PAID_STATUSES = frozenset({"active", "past_due"})


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    #: Display only. The amount actually charged is whatever the payment provider's product is
    #: priced at -- keep these in step with its dashboard.
    price_per_seat_usd: int
    features: frozenset[str]
    description: str


PLANS: dict[str, Plan] = {
    "starter": Plan(
        id="starter",
        name="Starter",
        price_per_seat_usd=19,
        features=frozenset(),
        description="The full pipeline: leads, opportunities, proposals, follow-ups, calendar sync.",
    ),
    "growth": Plan(
        id="growth",
        name="Growth",
        price_per_seat_usd=49,
        features=frozenset({FEATURE_AI}),
        description="Everything in Starter, plus the AI assistant, call notes, proposal drafting, "
        "deal health and company research.",
    ),
    "scale": Plan(
        id="scale",
        name="Scale",
        price_per_seat_usd=99,
        features=frozenset({FEATURE_AI, FEATURE_VOICE_AGENTS}),
        description="Everything in Growth, plus AI voice agents with a document knowledge base.",
    ),
}


def parse_instant(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class Entitlements:
    #: "trial", "paid", or "read_only".
    access: str
    writable: bool
    features: frozenset[str]
    #: Maximum active users; 0 when read-only.
    seat_limit: int
    trial_days_left: int

    def has(self, feature: str) -> bool:
        return feature in self.features


def entitlements(row: dict[str, Any], *, now: datetime | None = None) -> Entitlements:
    """What an ``organization_subscriptions`` row allows right now."""
    now = now or datetime.now(timezone.utc)
    status = row.get("status")
    plan = PLANS.get(row.get("plan") or "")
    period_end = parse_instant(row.get("current_period_end"))

    # A paid tier in good standing, or cancelled with time left on a period already paid for.
    paid = plan is not None and (
        status in PAID_STATUSES
        or (status == "cancelled" and period_end is not None and period_end > now)
    )
    trial_end = parse_instant(row.get("trial_ends_at"))
    trial_days_left = (
        max(0, math.ceil((trial_end - now).total_seconds() / 86400)) if trial_end else 0
    )

    if paid:
        return Entitlements(
            access="paid",
            writable=True,
            features=plan.features,
            seat_limit=int(row.get("seats") or 1),
            trial_days_left=0,
        )
    if trial_end is not None and trial_end > now:
        return Entitlements(
            access="trial",
            writable=True,
            features=ALL_FEATURES,
            seat_limit=TRIAL_SEAT_LIMIT,
            trial_days_left=trial_days_left,
        )
    return Entitlements(
        access="read_only", writable=False, features=frozenset(), seat_limit=0, trial_days_left=0
    )
