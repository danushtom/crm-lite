"""Billing: entitlements, the plan gate, checkout, the seat cap, and the Dodo webhook."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import API_V1_PREFIX as V1
from app.core.config import settings
from app.core.webhook_security import verify_standard_webhook
from app.services import billing
from tests.conftest import FakeResult

SECRET_BYTES = b"super-secret-signing-key-32bytes!"
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode()

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}
AGENT_ROLE = {"id": "role-agent-1", "name": "Agent", "grants_full_access": False, "role_permissions": []}

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def as_role(fake_db, test_user, role, *, active_users: int = 1):
    """The same "GET users" response answers both the profile lookup and the seat count."""
    fake_db.responses["GET users"] = FakeResult(
        [
            {
                "id": test_user.sub,
                "email": "founder@acme.test",
                "role_id": role["id"],
                "is_active": True,
                "roles": role,
                "organization_id": "org-1",
                "organizations": {"name": "Acme"},
            }
        ],
        count=active_users,
    )


def trial_row(*, days_left: float = 10, **extra):
    return {
        "organization_id": "org-1",
        "plan": "trial",
        "status": "trialing",
        "seats": None,
        "trial_ends_at": _iso(datetime.now(timezone.utc) + timedelta(days=days_left)),
        **extra,
    }


def paid_row(plan: str, *, seats: int = 5, status: str = "active", **extra):
    return {
        "organization_id": "org-1",
        "plan": plan,
        "status": status,
        "seats": seats,
        "trial_ends_at": _iso(datetime.now(timezone.utc) - timedelta(days=30)),
        "dodo_customer_id": "cus_1",
        "dodo_subscription_id": "sub_1",
        **extra,
    }


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "dodo_payments_api_key", "test-key")
    monkeypatch.setattr(settings, "dodo_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "dodo_product_starter", "prod_starter")
    monkeypatch.setattr(settings, "dodo_product_growth", "prod_growth")
    monkeypatch.setattr(settings, "dodo_product_scale", "prod_scale")


class FakeResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class SequenceHttpClient:
    """Answers each request with the next queued response, recording what was sent."""

    def __init__(self, *responses: FakeResponse):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)


# --- entitlements -------------------------------------------------------------------------------


def test_an_unexpired_trial_unlocks_everything_with_the_trial_seat_cap():
    ent = billing.entitlements(
        {"plan": "trial", "status": "trialing", "trial_ends_at": _iso(NOW + timedelta(days=3, hours=1))},
        now=NOW,
    )
    assert ent.access == "trial" and ent.writable
    assert ent.features == billing.ALL_FEATURES
    assert ent.seat_limit == billing.TRIAL_SEAT_LIMIT
    assert ent.trial_days_left == 4


def test_an_expired_trial_without_a_subscription_is_read_only():
    ent = billing.entitlements(
        {"plan": "trial", "status": "trialing", "trial_ends_at": _iso(NOW - timedelta(seconds=1))},
        now=NOW,
    )
    assert ent.access == "read_only" and not ent.writable
    assert ent.seat_limit == 0


@pytest.mark.parametrize("status", ["active", "past_due"])
def test_a_paid_plan_in_good_standing_gets_its_own_features_and_seats(status):
    ent = billing.entitlements(paid_row("growth", seats=7, status=status), now=NOW)
    assert ent.access == "paid" and ent.writable
    assert ent.features == {billing.FEATURE_AI}
    assert ent.seat_limit == 7


def test_a_cancelled_plan_keeps_access_until_the_paid_period_ends():
    row = paid_row("starter", status="cancelled", current_period_end=_iso(NOW + timedelta(days=2)))
    assert billing.entitlements(row, now=NOW).writable
    row["current_period_end"] = _iso(NOW - timedelta(days=1))
    assert not billing.entitlements(row, now=NOW).writable


@pytest.mark.parametrize("status", ["on_hold", "failed", "expired", "paused"])
def test_a_lapsed_subscription_is_read_only(status):
    assert not billing.entitlements(paid_row("scale", status=status), now=NOW).writable


# --- Standard Webhooks signature ---------------------------------------------------------------


def sign(body: bytes, *, webhook_id: str = "msg_1", timestamp: int | None = None, secret: bytes = SECRET_BYTES):
    ts = str(timestamp if timestamp is not None else int(time.time()))
    digest = hmac.new(secret, f"{webhook_id}.{ts}.".encode() + body, hashlib.sha256).digest()
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": ts,
        "webhook-signature": "v1," + base64.b64encode(digest).decode(),
    }


def _verify(body: bytes, headers: dict, secret: str = SECRET) -> bool:
    return verify_standard_webhook(
        body,
        webhook_id=headers["webhook-id"],
        webhook_timestamp=headers["webhook-timestamp"],
        webhook_signature=headers["webhook-signature"],
        secret=secret,
    )


def test_a_correctly_signed_webhook_verifies():
    body = b'{"type":"subscription.active"}'
    assert _verify(body, sign(body))


def test_any_matching_signature_in_a_rotation_list_verifies():
    body = b"{}"
    headers = sign(body)
    headers["webhook-signature"] = "v1,bm90LXRoZS1yaWdodC1vbmU= " + headers["webhook-signature"]
    assert _verify(body, headers)


def test_a_tampered_body_fails_verification():
    headers = sign(b'{"quantity":1}')
    assert not _verify(b'{"quantity":999}', headers)


def test_a_replayed_old_delivery_fails_verification():
    body = b"{}"
    assert not _verify(body, sign(body, timestamp=int(time.time()) - 3600))


def test_verification_fails_closed_without_a_secret():
    body = b"{}"
    assert not _verify(body, sign(body), secret="")


# --- plan gate ---------------------------------------------------------------------------------


def test_writes_are_refused_once_the_trial_has_ended(authed_client, fake_db):
    fake_db.responses["GET organization_subscriptions"] = trial_row(days_left=-1)

    response = authed_client.post(f"{V1}/companies", json={"name": "Globex"})

    assert response.status_code == 402
    assert response.json()["code"] == "subscription_inactive"
    assert not any(call[0] == "POST" and call[1] == "companies" for call in fake_db.calls)


def test_reads_still_work_in_read_only_mode(authed_client, fake_db):
    fake_db.responses["GET organization_subscriptions"] = trial_row(days_left=-1)
    fake_db.responses["GET companies"] = FakeResult([], count=0)

    response = authed_client.get(f"{V1}/companies")

    assert response.status_code == 200


def test_a_feature_outside_the_plan_is_refused(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE)
    fake_db.responses["GET organization_subscriptions"] = paid_row("starter")

    response = authed_client.post(f"{V1}/voice-agents", json={"name": "Ava", "system_prompt": "Hi"})

    assert response.status_code == 402
    assert response.json()["code"] == "plan_upgrade_required"


# --- GET /billing --------------------------------------------------------------------------------


def test_any_member_can_read_the_plan(authed_client, fake_db, test_user, configured):
    as_role(fake_db, test_user, AGENT_ROLE, active_users=3)
    fake_db.responses["GET organization_subscriptions"] = trial_row(days_left=5)

    body = authed_client.get(f"{V1}/billing").json()

    assert body["access"] == "trial"
    assert body["seats_used"] == 3
    assert body["seat_limit"] == billing.TRIAL_SEAT_LIMIT
    assert body["can_manage"] is False
    assert [p["id"] for p in body["plans"]] == ["starter", "growth", "scale"]
    # The provider's ids are an implementation detail the browser never needs.
    assert "dodo_customer_id" not in body


# --- checkout ------------------------------------------------------------------------------------


def test_checkout_creates_a_customer_and_carries_the_remaining_trial(
    authed_client, fake_db, test_user, configured, monkeypatch
):
    as_role(fake_db, test_user, ADMIN_ROLE, active_users=2)
    fake_db.responses["GET organization_subscriptions"] = trial_row(days_left=6.5)
    http = SequenceHttpClient(
        FakeResponse(body={"customer_id": "cus_new"}),
        FakeResponse(body={"session_id": "cks_1", "checkout_url": "https://checkout.dodo/cks_1"}),
    )
    monkeypatch.setattr(billing, "get_http_client", lambda: http)

    response = authed_client.post(f"{V1}/billing/checkout", json={"plan": "growth", "seats": 4})

    assert response.status_code == 200, response.text
    assert response.json() == {"checkout_url": "https://checkout.dodo/cks_1"}
    stored = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "organization_subscriptions"]
    assert stored[0][2]["payload"] == {"dodo_customer_id": "cus_new"}
    assert stored[0][2]["params"] == {"organization_id": "eq.org-1"}
    checkout = http.calls[1][2]["json"]
    assert checkout["product_cart"] == [{"product_id": "prod_growth", "quantity": 4}]
    assert checkout["customer"] == {"customer_id": "cus_new"}
    assert checkout["subscription_data"] == {"trial_period_days": 7}


def test_checkout_refuses_fewer_seats_than_active_users(
    authed_client, fake_db, test_user, configured, monkeypatch
):
    as_role(fake_db, test_user, ADMIN_ROLE, active_users=4)
    fake_db.responses["GET organization_subscriptions"] = trial_row()
    monkeypatch.setattr(billing, "get_http_client", lambda: SequenceHttpClient())

    response = authed_client.post(f"{V1}/billing/checkout", json={"plan": "starter", "seats": 3})

    assert response.status_code == 422


def test_checkout_is_refused_while_already_subscribed(authed_client, fake_db, test_user, configured):
    as_role(fake_db, test_user, ADMIN_ROLE)
    fake_db.responses["GET organization_subscriptions"] = paid_row("starter")

    response = authed_client.post(f"{V1}/billing/checkout", json={"plan": "growth", "seats": 5})

    assert response.status_code == 409


def test_only_a_full_access_role_can_start_a_checkout(authed_client, fake_db, test_user, configured):
    as_role(fake_db, test_user, AGENT_ROLE)
    fake_db.responses["GET organization_subscriptions"] = trial_row()

    response = authed_client.post(f"{V1}/billing/checkout", json={"plan": "growth", "seats": 5})

    assert response.status_code == 403


def test_checkout_reports_unconfigured_billing(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE)
    fake_db.responses["GET organization_subscriptions"] = trial_row()

    response = authed_client.post(f"{V1}/billing/checkout", json={"plan": "growth", "seats": 5})

    assert response.status_code == 501


def test_change_plan_sends_the_new_product_and_quantity(
    authed_client, fake_db, test_user, configured, monkeypatch
):
    as_role(fake_db, test_user, ADMIN_ROLE, active_users=3)
    fake_db.responses["GET organization_subscriptions"] = paid_row("starter", seats=3)
    http = SequenceHttpClient(FakeResponse(body={}))
    monkeypatch.setattr(billing, "get_http_client", lambda: http)

    response = authed_client.post(f"{V1}/billing/change-plan", json={"plan": "scale", "seats": 6})

    assert response.status_code == 202
    method, url, kwargs = http.calls[0]
    assert url.endswith("/subscriptions/sub_1/change-plan")
    assert kwargs["json"]["product_id"] == "prod_scale"
    assert kwargs["json"]["quantity"] == 6


# --- seat cap on invites ------------------------------------------------------------------------


def test_invite_is_refused_when_every_seat_is_taken(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE, active_users=billing.TRIAL_SEAT_LIMIT)
    fake_db.responses["GET organization_subscriptions"] = trial_row()

    response = authed_client.post(
        f"{V1}/agents/invite", json={"email": "new@example.com", "role_id": "role-agent-1"}
    )

    assert response.status_code == 402
    assert response.json()["code"] == "seat_limit_reached"
    assert not any(call[1] == "org_invites" for call in fake_db.calls)


def test_invite_links_land_on_the_confirm_page_then_set_password(
    authed_client, fake_db, test_user, monkeypatch
):
    as_role(fake_db, test_user, ADMIN_ROLE, active_users=1)
    fake_db.responses["GET organization_subscriptions"] = trial_row()
    fake_db.responses["POST org_invites"] = {"id": "5b1f7c3e-0000-4000-8000-000000000001"}
    http = SequenceHttpClient(FakeResponse(body={"id": "user-2"}))
    monkeypatch.setattr("app.api.v1.endpoints.agents.get_http_client", lambda: http)
    monkeypatch.setattr(settings, "web_app_url", "https://app.dracara.test/")

    response = authed_client.post(
        f"{V1}/agents/invite", json={"email": "new@example.com", "role_id": "role-agent-1"}
    )

    assert response.status_code == 202, response.text
    redirect = http.calls[0][2]["params"]["redirect_to"]
    assert redirect.startswith("https://app.dracara.test/auth/confirm?next=")
    assert "set-password" in redirect


# --- webhook -------------------------------------------------------------------------------------


def _event(**data):
    return {
        "business_id": "biz_1",
        "type": data.pop("type", "subscription.active"),
        "timestamp": data.pop("timestamp", "2026-09-19T12:00:00Z"),
        "data": {
            "subscription_id": "sub_1",
            "status": "active",
            "product_id": "prod_growth",
            "quantity": 3,
            "next_billing_date": "2026-10-19T12:00:00Z",
            "cancel_at_next_billing_date": False,
            "customer": {"customer_id": "cus_1", "email": "founder@acme.test"},
            # A forged claim: the webhook must never route by this.
            "metadata": {"organization_id": "org-evil"},
            **data,
        },
    }


def _post_webhook(client, event, **sign_kwargs):
    body = json.dumps(event).encode()
    return client.post(
        f"{V1}/billing-webhooks/dodo",
        content=body,
        headers={"content-type": "application/json", **sign(body, **sign_kwargs)},
    )


def test_an_activated_subscription_updates_the_resolved_organization(authed_client, fake_db, configured):
    fake_db.responses["GET organization_subscriptions"] = trial_row(dodo_customer_id="cus_1")

    response = _post_webhook(authed_client, _event())

    assert response.status_code == 200
    lookup = next(c for c in fake_db.calls if c[0] == "GET" and c[1] == "organization_subscriptions")
    assert lookup[2]["params"]["dodo_customer_id"] == "eq.cus_1"
    patch = next(c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "organization_subscriptions")
    assert patch[2]["params"] == {"organization_id": "eq.org-1"}
    payload = patch[2]["payload"]
    assert payload["plan"] == "growth"
    assert payload["status"] == "active"
    assert payload["seats"] == 3
    assert payload["dodo_subscription_id"] == "sub_1"
    recorded = next(c for c in fake_db.calls if c[0] == "POST" and c[1] == "billing_events")
    assert recorded[2]["payload"]["organization_id"] == "org-1"


def test_a_badly_signed_webhook_is_rejected(authed_client, fake_db, configured):
    response = _post_webhook(authed_client, _event(), secret=b"wrong-secret")

    assert response.status_code == 401
    assert not any(c[0] == "PATCH" for c in fake_db.calls)


def test_a_redelivered_webhook_is_not_applied_twice(authed_client, fake_db, configured):
    fake_db.responses["GET billing_events"] = {"webhook_id": "msg_1"}
    fake_db.responses["GET organization_subscriptions"] = trial_row(dodo_customer_id="cus_1")

    response = _post_webhook(authed_client, _event())

    assert response.status_code == 200
    assert not any(c[0] == "PATCH" for c in fake_db.calls)


def test_an_older_event_arriving_late_does_not_roll_the_plan_back(authed_client, fake_db, configured):
    fake_db.responses["GET organization_subscriptions"] = paid_row(
        "scale", last_event_at="2026-09-19T13:00:00+00:00"
    )

    response = _post_webhook(authed_client, _event(timestamp="2026-09-19T12:00:00Z"))

    assert response.status_code == 200
    assert not any(c[0] == "PATCH" and c[1] == "organization_subscriptions" for c in fake_db.calls)


def test_a_failed_duplicate_subscription_does_not_cancel_the_paying_one(
    authed_client, fake_db, configured
):
    fake_db.responses["GET organization_subscriptions"] = paid_row("growth")

    response = _post_webhook(
        authed_client, _event(type="subscription.failed", subscription_id="sub_2", status="failed")
    )

    assert response.status_code == 200
    assert not any(c[0] == "PATCH" and c[1] == "organization_subscriptions" for c in fake_db.calls)


def test_an_event_for_an_unknown_customer_is_acknowledged_and_ignored(authed_client, fake_db, configured):
    response = _post_webhook(authed_client, _event())

    assert response.status_code == 200
    assert not any(c[0] == "PATCH" for c in fake_db.calls)
