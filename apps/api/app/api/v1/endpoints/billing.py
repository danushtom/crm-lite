"""The organization's subscription: read it, start a checkout, change plan or seats, and open
the Dodo customer portal (invoices, payment method, cancellation).

Reads are open to every member -- the UI needs the plan to decide what to show. Every action
needs a full-access role. All writes to ``organization_subscriptions`` go through the service
role because the table has no write policies at all (see the billing migration); the one
written here is the Dodo customer id, pinned to the caller's own organization from their
profile. Plan and status only ever change from the signature-verified webhook.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, status

from app.api.deps import AdminDbDep, AdminDep, DbDep, ProfileDep, is_full_access
from app.core.config import settings
from app.core.errors import ConflictError, NotConfiguredError, UnprocessableError
from app.core.rate_limit import limiter
from app.schemas.billing import (
    BillingOverview,
    ChangePlanRequest,
    ChangePlanResult,
    CheckoutRequest,
    CheckoutSession,
    PlanInfo,
    PortalSession,
)
from app.schemas.common import ERROR_RESPONSES
from app.services import billing

router = APIRouter(prefix="/billing", tags=["Billing"])


async def _seats_used(db: DbDep) -> int:
    result = await db.select(
        "users", params={"select": "id", "is_active": "eq.true", "limit": "1"}, count=True
    )
    return result.count if result.count is not None else len(result.rows)


async def _own_subscription(admin_db: AdminDbDep, organization_id: str) -> dict:
    result = await admin_db.select(
        "organization_subscriptions",
        params={"select": "*", "organization_id": f"eq.{organization_id}"},
    )
    return result.one("Subscription")


def _plan(plan_id: str) -> billing.Plan:
    plan = billing.PLANS[plan_id]
    if not billing.product_id(plan):
        raise NotConfiguredError(f"The {plan.name} plan is not configured on this server")
    return plan


@router.get(
    "",
    response_model=BillingOverview,
    summary="Get the organization's plan, trial and seat usage",
    description="Any member may read it; changing it requires a role with full organization access.",
    responses=ERROR_RESPONSES,
)
async def read_billing(db: DbDep, profile: ProfileDep) -> BillingOverview:
    row = await billing.load_subscription(db) or {
        "plan": "trial",
        "status": "trialing",
        "trial_ends_at": None,
    }
    ent = billing.entitlements(row)
    return BillingOverview(
        plan=row.get("plan") or "trial",
        status=row.get("status") or "trialing",
        access=ent.access,
        features=sorted(ent.features),
        trial_ends_at=row.get("trial_ends_at"),
        trial_days_left=ent.trial_days_left,
        current_period_end=row.get("current_period_end"),
        cancel_at_period_end=bool(row.get("cancel_at_period_end")),
        seats=row.get("seats"),
        seat_limit=ent.seat_limit,
        seats_used=await _seats_used(db),
        has_subscription=bool(row.get("dodo_subscription_id"))
        and row.get("status") in billing.PAID_STATUSES,
        can_manage=is_full_access(profile),
        configured=settings.billing_configured,
        plans=[
            PlanInfo(
                id=plan.id,
                name=plan.name,
                price_per_seat_usd=plan.price_per_seat_usd,
                features=sorted(plan.features),
                description=plan.description,
                available=bool(billing.product_id(plan)),
            )
            for plan in billing.PLANS.values()
        ],
    )


@router.post(
    "/checkout",
    response_model=CheckoutSession,
    summary="Start a Dodo Payments checkout for a plan",
    description=(
        "Returns a hosted checkout URL to redirect the admin to. Days left on the free trial "
        "carry over as a trial on the subscription. Refused when a subscription is already "
        "active -- use change-plan instead."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def start_checkout(
    request: Request,
    response: Response,
    body: CheckoutRequest,
    db: DbDep,
    admin_db: AdminDbDep,
    admin: AdminDep,
) -> CheckoutSession:
    plan = _plan(body.plan)
    organization_id = admin["organization_id"]
    row = await _own_subscription(admin_db, organization_id)
    if row.get("dodo_subscription_id") and row.get("status") in billing.PAID_STATUSES:
        raise ConflictError("This organization already has an active subscription; change its plan instead")

    used = await _seats_used(db)
    if body.seats < used:
        raise UnprocessableError(f"This organization has {used} active users; buy at least {used} seats")

    customer_id = row.get("dodo_customer_id")
    if not customer_id:
        org_name = (admin.get("organizations") or {}).get("name") or "Workspace"
        customer_id = await billing.create_customer(
            email=admin.get("email") or "", name=org_name, organization_id=organization_id
        )
        await admin_db.update(
            "organization_subscriptions",
            {"organization_id": f"eq.{organization_id}"},
            {"dodo_customer_id": customer_id},
        )

    ent = billing.entitlements(row, now=datetime.now(timezone.utc))
    url = await billing.create_checkout(
        customer_id=customer_id,
        plan=plan,
        seats=body.seats,
        organization_id=organization_id,
        trial_days=ent.trial_days_left if ent.access == "trial" else 0,
    )
    return CheckoutSession(checkout_url=url)


@router.post(
    "/change-plan",
    response_model=ChangePlanResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Change the active subscription's plan or seat count",
    description="Prorated immediately against the saved payment method.",
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def change_plan(
    request: Request,
    response: Response,
    body: ChangePlanRequest,
    db: DbDep,
    admin_db: AdminDbDep,
    admin: AdminDep,
) -> ChangePlanResult:
    plan = _plan(body.plan)
    row = await _own_subscription(admin_db, admin["organization_id"])
    subscription_id = row.get("dodo_subscription_id")
    if not subscription_id or row.get("status") not in billing.PAID_STATUSES:
        raise ConflictError("There is no active subscription to change; start a checkout instead")

    used = await _seats_used(db)
    if body.seats < used:
        raise UnprocessableError(
            f"This organization has {used} active users; deactivate some before dropping to {body.seats} seats"
        )

    await billing.change_plan(subscription_id=subscription_id, plan=plan, seats=body.seats)
    return ChangePlanResult(accepted=True)


@router.post(
    "/portal",
    response_model=PortalSession,
    summary="Open the Dodo Payments customer portal",
    description="Invoices, payment method and cancellation. Returns a short-lived link.",
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def open_portal(
    request: Request, response: Response, admin_db: AdminDbDep, admin: AdminDep
) -> PortalSession:
    row = await _own_subscription(admin_db, admin["organization_id"])
    customer_id = row.get("dodo_customer_id")
    if not customer_id:
        raise ConflictError("This organization has not subscribed yet")
    return PortalSession(url=await billing.portal_link(customer_id=customer_id))
