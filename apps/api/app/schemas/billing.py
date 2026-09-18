"""Billing schemas: the organization's plan, the plan catalog, and checkout/portal actions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel, StrictAPIModel

PlanId = Literal["starter", "growth", "scale"]


class PlanInfo(APIModel):
    id: PlanId
    name: str
    price_per_seat_usd: int = Field(description="Monthly price per seat, for display.")
    features: list[str]
    description: str
    available: bool = Field(description="False when no Dodo product is configured for it.")


class BillingOverview(APIModel):
    plan: Literal["trial", "starter", "growth", "scale"]
    status: str = Field(description="'trialing', or the subscription's status at Dodo Payments.")
    access: Literal["trial", "paid", "read_only"] = Field(
        description="What the organization can do right now. 'read_only' refuses every write."
    )
    features: list[str] = Field(description="Plan features currently unlocked.")
    trial_ends_at: datetime | None = None
    trial_days_left: int
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    seats: int | None = Field(default=None, description="Paid seats; null while trialing.")
    seat_limit: int = Field(description="Active users allowed right now.")
    seats_used: int = Field(description="Active users in the organization.")
    has_subscription: bool
    can_manage: bool = Field(description="Whether the caller may change the plan.")
    configured: bool = Field(description="Whether billing is configured on this server.")
    plans: list[PlanInfo]


class CheckoutRequest(StrictAPIModel):
    plan: PlanId
    seats: int = Field(ge=1, le=1000)


class CheckoutSession(APIModel):
    checkout_url: str


class ChangePlanRequest(StrictAPIModel):
    plan: PlanId
    seats: int = Field(ge=1, le=1000)


class ChangePlanResult(APIModel):
    accepted: bool = Field(
        description="The change was accepted by the billing provider. The plan shown by "
        "GET /billing updates when its confirming webhook arrives, usually within seconds."
    )


class PortalSession(APIModel):
    url: str


class WebhookAck(APIModel):
    received: bool
