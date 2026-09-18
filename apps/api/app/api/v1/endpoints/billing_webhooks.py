"""Callbacks from Dodo Payments: subscription lifecycle events.

Like voice_webhooks.py, no user-auth dependency appears here -- the caller is Dodo, not a
logged-in user -- and the route is verified by signature instead (Standard Webhooks, see
app/core/webhook_security.py) and ``@limiter.exempt`` so provider retries never compete with a
user's quota.

The payload's ``metadata`` (which carries the organization id we set at checkout) is never used
to decide which organization an event belongs to. ``apply_subscription_event`` resolves that from
the Dodo customer id this API stored itself when it created the customer.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, Request

from app.api.deps import AdminDbDep
from app.core.config import settings
from app.core.errors import BadRequestError, UnauthorizedError
from app.core.rate_limit import limiter
from app.core.webhook_security import verify_standard_webhook
from app.schemas.billing import WebhookAck
from app.services.billing import apply_subscription_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing-webhooks", tags=["Billing Webhooks"])


@router.post(
    "/dodo",
    response_model=WebhookAck,
    summary="Subscription lifecycle callback from Dodo Payments",
    description=(
        "Signature-verified (Standard Webhooks), not JWT-authenticated. Idempotent on the "
        "webhook-id header; out-of-order deliveries older than the last applied event are ignored."
    ),
)
@limiter.exempt
async def dodo_events(
    request: Request,
    admin_db: AdminDbDep,
    webhook_id: str | None = Header(default=None, alias="webhook-id"),
    webhook_timestamp: str | None = Header(default=None, alias="webhook-timestamp"),
    webhook_signature: str | None = Header(default=None, alias="webhook-signature"),
) -> WebhookAck:
    raw_body = await request.body()
    if not verify_standard_webhook(
        raw_body,
        webhook_id=webhook_id,
        webhook_timestamp=webhook_timestamp,
        webhook_signature=webhook_signature,
        secret=settings.dodo_webhook_secret,
    ):
        logger.warning("billing_webhook_signature_invalid")
        raise UnauthorizedError("Invalid webhook signature")

    try:
        event = json.loads(raw_body)
    except ValueError as exc:
        raise BadRequestError("Webhook body is not JSON") from exc
    event_type = str(event.get("type") or "")

    seen = await admin_db.select(
        "billing_events", params={"select": "webhook_id", "webhook_id": f"eq.{webhook_id}"}
    )
    if seen.first() is not None:
        return WebhookAck(received=True)

    organization_id = None
    if event_type.startswith("subscription."):
        organization_id = await apply_subscription_event(admin_db, event)
    # Everything else (payment.*, refund.*, dispute.*) is acknowledged and recorded but not
    # acted on: subscription events alone carry the state access decisions need.

    await admin_db.insert(
        "billing_events",
        {
            "webhook_id": webhook_id,
            "event_type": event_type,
            "organization_id": organization_id,
            "payload": event,
        },
    )
    logger.info("billing_webhook_applied type=%s org=%s", event_type, organization_id)
    return WebhookAck(received=True)
