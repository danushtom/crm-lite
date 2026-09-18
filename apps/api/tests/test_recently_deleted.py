"""Recently deleted: listing and restoring.

The permission rule lives in the database functions (restore_deleted migration); what is
tested here is that the API calls them as the caller, passes paging through, and turns each
function status into the right response.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

ROW = {
    "id": "lead-1",
    "label": "Acme",
    "detail": "Saas · Asha Rao",
    "deleted_at": "2026-09-18T10:00:00+00:00",
    "deleted_by_name": "Sam",
    "blocked_by": None,
}


def test_lists_one_kind_through_the_definer_function(authed_client, fake_db):
    fake_db.responses["RPC recently_deleted"] = FakeResult([ROW])

    response = authed_client.get(f"{V1}/recently-deleted", params={"kind": "leads", "limit": 20, "offset": 40})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"][0]["label"] == "Acme"
    assert body["page"]["has_more"] is False
    method, path, kwargs = fake_db.calls[-1]
    assert path == "rpc/recently_deleted"
    assert kwargs["payload"] == {"p_kind": "leads", "p_limit": 20, "p_offset": 40}


def test_an_unknown_kind_is_rejected_before_reaching_the_database(authed_client, fake_db):
    response = authed_client.get(f"{V1}/recently-deleted", params={"kind": "users"})

    assert response.status_code == 422
    assert not any(c[1].startswith("rpc/") for c in fake_db.calls)


def test_restoring_reports_success(authed_client, fake_db):
    fake_db.responses["RPC restore_record"] = FakeResult({"status": "restored"})

    response = authed_client.post(f"{V1}/recently-deleted/contacts/ct-1/restore")

    assert response.status_code == 200
    assert response.json() == {"id": "ct-1", "restored": True}
    assert fake_db.calls[-1][2]["payload"] == {"p_kind": "contacts", "p_id": "ct-1"}


@pytest.mark.parametrize(
    ("outcome", "status", "code", "detail"),
    [
        ({"status": "parent_deleted", "parent": "company"}, 409, "parent_deleted", "restore the company first"),
        ({"status": "conflict"}, 409, "active_opportunity_exists", "another active opportunity"),
        ({"status": "not_found"}, 404, "not_found", "not found"),
        (None, 404, "not_found", "not found"),
    ],
)
def test_restore_failures_explain_what_to_do(authed_client, fake_db, outcome, status, code, detail):
    fake_db.responses["RPC restore_record"] = FakeResult(outcome)

    response = authed_client.post(f"{V1}/recently-deleted/leads/lead-1/restore")

    assert response.status_code == status
    assert response.json()["code"] == code
    assert detail in response.json()["detail"]


def test_restoring_is_a_write_and_so_is_refused_in_a_read_only_workspace(authed_client, fake_db):
    fake_db.responses["GET organization_subscriptions"] = {
        "plan": "trial",
        "status": "trialing",
        "trial_ends_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }

    response = authed_client.post(f"{V1}/recently-deleted/leads/lead-1/restore")

    assert response.status_code == 402
    assert not any(c[1] == "rpc/restore_record" for c in fake_db.calls)
