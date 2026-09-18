"""Plans, entitlements, and the Dodo Payments integration.

Three things live here, in the order a request meets them:

1. The plan catalog and :func:`entitlements`, re-exported from ``packages/billing`` (shared
   with the worker) -- the single function that turns an ``organization_subscriptions`` row
   into "may this organization write, which features does it have, how many seats". The API's
   write gate (``deps.plan_gate``), ``GET /billing`` and the worker's AI jobs all call it, so
   they can never disagree.
2. A thin Dodo Payments REST client (customers, checkout sessions, plan changes, portal).
3. :func:`apply_subscription_event` -- how a signature-verified webhook updates the row.

Billing is a commercial gate, not a security boundary: RLS still decides what anyone can see.
That is why a *missing* subscription row fails open (see ``deps.plan_gate``) -- the migration
backfills every organization and a trigger covers new ones, so a missing row means a bug, and
a billing bug should not lock a customer out of their own pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from dracara_billing import (  # noqa: F401 -- re-exported for the API's callers
    ALL_FEATURES,
    FEATURE_AI,
    FEATURE_VOICE_AGENTS,
    PAID_STATUSES,
    PLANS,
    TRIAL_DAYS,
    TRIAL_SEAT_LIMIT,
    Entitlements,
    Plan,
    entitlements,
)
from dracara_billing import parse_instant as _parse_instant

from app.core.config import settings
from app.core.errors import NotConfiguredError, UpstreamError
from app.db.supabase import SupabaseClient, get_http_client

logger = logging.getLogger(__name__)

#: Every Dodo SubscriptionStatus we store verbatim.
DODO_STATUSES = frozenset(
    {"pending", "active", "past_due", "on_hold", "paused", "cancelled", "failed", "expired"}
)


def product_id(plan: Plan) -> str:
    """The Dodo product configured for ``plan`` (``DODO_PRODUCT_<PLAN>``), or ""."""
    return getattr(settings, f"dodo_product_{plan.id}", "")


def plan_for_product(dodo_product_id: str | None) -> Plan | None:
    if not dodo_product_id:
        return None
    for plan in PLANS.values():
        configured = product_id(plan)
        if configured and configured == dodo_product_id:
            return plan
    return None


async def load_subscription(db: SupabaseClient) -> dict[str, Any] | None:
    """The caller's own organization's row. RLS limits the table to exactly that one row, so
    no organization filter is needed (or trusted) here."""
    result = await db.select(
        "organization_subscriptions", params={"select": "*", "limit": "1"}
    )
    return result.first()


# --- Dodo Payments REST client ---------------------------------------------------------------


def _require_configured() -> None:
    if not settings.billing_configured:
        raise NotConfiguredError("Billing is not configured on this server")


async def _dodo(method: str, path: str, *, json: Any = None, params: dict | None = None) -> dict:
    _require_configured()
    client = get_http_client()
    try:
        response = await client.request(
            method,
            f"{settings.dodo_api_base}{path}",
            headers={
                "Authorization": f"Bearer {settings.dodo_payments_api_key}",
                "Content-Type": "application/json",
            },
            json=json,
            params=params,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Could not reach the billing provider") from exc
    if response.status_code >= 400:
        # The body can echo request details; log it server-side only.
        logger.error("dodo_request_failed path=%s status=%s body=%s", path, response.status_code, response.text)
        raise UpstreamError("The billing provider rejected the request")
    return response.json() if response.content else {}


async def create_customer(*, email: str, name: str, organization_id: str) -> str:
    body = await _dodo(
        "POST",
        "/customers",
        json={"email": email, "name": name, "metadata": {"organization_id": organization_id}},
    )
    customer_id = body.get("customer_id")
    if not customer_id:
        raise UpstreamError("The billing provider did not return a customer")
    return customer_id


async def create_checkout(
    *,
    customer_id: str,
    plan: Plan,
    seats: int,
    organization_id: str,
    trial_days: int,
) -> str:
    payload: dict[str, Any] = {
        "product_cart": [{"product_id": product_id(plan), "quantity": seats}],
        "customer": {"customer_id": customer_id},
        "return_url": f"{settings.web_app_origin}/settings/billing?checkout=success",
        # Informational only: the webhook resolves the organization from our own stored
        # customer id, never from this.
        "metadata": {"organization_id": organization_id, "plan": plan.id},
    }
    if trial_days > 0:
        # Subscribing mid-trial keeps the days they have left rather than charging today.
        payload["subscription_data"] = {"trial_period_days": trial_days}
    body = await _dodo("POST", "/checkouts", json=payload)
    url = body.get("checkout_url")
    if not url:
        raise UpstreamError("The billing provider did not return a checkout link")
    return url


async def change_plan(*, subscription_id: str, plan: Plan, seats: int) -> None:
    await _dodo(
        "POST",
        f"/subscriptions/{subscription_id}/change-plan",
        json={
            "product_id": product_id(plan),
            "quantity": seats,
            "proration_billing_mode": "prorated_immediately",
        },
    )


async def portal_link(*, customer_id: str) -> str:
    body = await _dodo(
        "POST",
        f"/customers/{customer_id}/customer-portal/session",
        params={"return_url": f"{settings.web_app_origin}/settings/billing"},
    )
    link = body.get("link")
    if not link:
        raise UpstreamError("The billing provider did not return a portal link")
    return link


# --- Webhook application -----------------------------------------------------------------------


async def apply_subscription_event(admin_db: SupabaseClient, event: dict[str, Any]) -> str | None:
    """Apply one verified ``subscription.*`` event. Returns the organization id it applied to,
    or None when there was nothing to apply (unknown customer, stale or out-of-order event).

    The organization is resolved from ``data.customer.customer_id`` against the customer id this
    API itself stored at checkout -- the same "resolve from our own record, never from the
    payload's claims" rule the voice webhooks follow. ``metadata`` is never consulted.
    """
    data = event.get("data") or {}
    customer_id = (data.get("customer") or {}).get("customer_id")
    if not customer_id:
        return None
    found = await admin_db.select(
        "organization_subscriptions",
        params={"select": "*", "dodo_customer_id": f"eq.{customer_id}"},
    )
    row = found.first()
    if row is None:
        logger.warning("billing_webhook_unknown_customer customer=%s", customer_id)
        return None

    event_at = _parse_instant(event.get("timestamp")) or datetime.now(timezone.utc)
    last_at = _parse_instant(row.get("last_event_at"))
    if last_at is not None and event_at < last_at:
        return None

    status = data.get("status")
    subscription_id = data.get("subscription_id")
    current_id = row.get("dodo_subscription_id")
    # A second, abandoned subscription (say, a duplicate checkout that later failed or
    # expired) must not knock out the one the organization is actually paying for.
    if (
        current_id
        and subscription_id
        and subscription_id != current_id
        and row.get("status") in PAID_STATUSES
        and status not in PAID_STATUSES
    ):
        return None

    changes: dict[str, Any] = {
        "last_event_at": event_at.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if status in DODO_STATUSES:
        changes["status"] = status
    if subscription_id:
        changes["dodo_subscription_id"] = subscription_id
    event_product = data.get("product_id")
    if event_product:
        changes["dodo_product_id"] = event_product
        plan = plan_for_product(event_product)
        if plan is not None:
            changes["plan"] = plan.id
        else:
            logger.warning("billing_webhook_unknown_product product=%s", event_product)
    quantity = data.get("quantity")
    if isinstance(quantity, int) and quantity > 0:
        changes["seats"] = quantity
    if "next_billing_date" in data:
        changes["current_period_end"] = data.get("next_billing_date")
    if "cancel_at_next_billing_date" in data:
        changes["cancel_at_period_end"] = bool(data.get("cancel_at_next_billing_date"))

    organization_id = row["organization_id"]
    await admin_db.update(
        "organization_subscriptions", {"organization_id": f"eq.{organization_id}"}, changes
    )
    return organization_id
