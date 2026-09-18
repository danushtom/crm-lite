"""The daily brief, and the admin lookup it shares with overdue_escalation.

The existing FakeSupabase answers by path, ignoring params -- which is exactly how a query on
the dropped ``users.role`` column survived: the fake returned admins no matter what was asked.
These tests pin the query itself.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import worker_app  # noqa: E402
from tests.test_jobs import FakeSupabase, fake_sb, no_real_notifications  # noqa: E402,F401 -- fixtures

_FUTURE = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
_PAST = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()


class SentEmails:
    def __init__(self):
        self.sent: list[dict] = []

    def post(self, url, *, headers, json, timeout):
        self.sent.append({"url": url, "headers": headers, "json": json})

        class _Ok:
            def raise_for_status(self):
                return None

        return _Ok()


@pytest.fixture
def outbox(monkeypatch):
    box = SentEmails()
    monkeypatch.setattr(worker_app.httpx, "post", box.post)
    monkeypatch.setattr(worker_app.ENV, "resend_api_key", "re_test")
    return box


def _responses(**extra):
    return {
        "GET /organization_subscriptions": [
            {"organization_id": "org-a", "plan": "trial", "status": "trialing", "trial_ends_at": _FUTURE},
            {"organization_id": "org-b", "plan": "growth", "status": "active", "seats": 2},
            {"organization_id": "org-lapsed", "plan": "trial", "status": "trialing", "trial_ends_at": _PAST},
        ],
        "GET /users": [
            {"id": "admin-a", "email": "a@example.com", "full_name": "Asha", "organization_id": "org-a"},
            {"id": "admin-b", "email": "b@example.com", "full_name": "Ben", "organization_id": "org-b"},
            {"id": "admin-x", "email": "x@example.com", "full_name": "Xi", "organization_id": "org-lapsed"},
        ],
        "GET /tasks": [
            {"organization_id": "org-a"},
            {"organization_id": "org-a"},
            {"organization_id": "org-b"},
        ],
        "GET /leads": [{"organization_id": "org-b"}],
        "GET /organizations": [
            {"id": "org-a", "name": "Acme <Agency>"},
            {"id": "org-b", "name": "Beta"},
        ],
        **extra,
    }


def test_admins_are_found_by_full_access_role_not_the_dropped_role_column(fake_sb):
    fake_sb.responses["GET /tasks"] = []
    fake_sb.responses["GET /users"] = []

    worker_app.overdue_escalation()

    params = fake_sb.params_for("GET", "/users")
    assert "role" not in params
    assert "roles!inner(grants_full_access)" in params["select"]
    assert params["roles.grants_full_access"] == "eq.true"
    assert params["is_active"] == "eq.true"


def test_each_admin_gets_only_their_own_organizations_numbers(fake_sb, outbox):
    fake_sb.responses.update(_responses())

    assert worker_app.daily_brief() == "sent:2"

    by_recipient = {e["json"]["to"][0]: e["json"]["html"] for e in outbox.sent}
    # Both /tasks queries share one canned response here, so due-today and overdue both read 2
    # for org-a and 1 for org-b -- what matters is that org-b's numbers never reach org-a.
    assert "Acme &lt;Agency&gt;" in by_recipient["a@example.com"]
    assert "Beta" not in by_recipient["a@example.com"]
    assert "Acme" not in by_recipient["b@example.com"]


def test_lapsed_organizations_are_not_emailed(fake_sb, outbox):
    fake_sb.responses.update(_responses())

    worker_app.daily_brief()

    assert "x@example.com" not in [e["json"]["to"][0] for e in outbox.sent]


def test_a_retry_cannot_send_the_same_brief_twice(fake_sb, outbox):
    fake_sb.responses.update(_responses())

    worker_app.daily_brief()

    keys = [e["headers"]["Idempotency-Key"] for e in outbox.sent]
    assert len(keys) == len(set(keys))
    assert all(k.startswith("daily-brief/") for k in keys)


def test_the_brief_is_skipped_without_an_email_provider(fake_sb, monkeypatch):
    monkeypatch.setattr(worker_app.ENV, "resend_api_key", "")

    assert worker_app.daily_brief() == "skip:no_resend"
    assert fake_sb.calls == []
