"""Create/update/delete coverage, and the guards that make deletion safe.

Every resource except the deliberately append-only ones now supports the full lifecycle.
What matters is less that the verbs exist than that each one refuses the case it should:
deleting a company that still has leads, a proposal that has already gone out, or the last
admin an organisation has.
"""

from __future__ import annotations

import pytest

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

PROPOSAL = {
    "id": "prop-1",
    "opportunity_id": "opp-1",
    "version": 1,
    "title": "Scope v1",
    "status": "draft",
    "quoted_price": 450000,
    "sent_at": None,
}

MEETING = {
    "id": "m-1",
    "lead_id": "lead-1",
    "owner_id": "11111111-2222-3333-4444-555555555555",
    "title": "Discovery",
    "scheduled_at": "2026-09-01T10:00:00Z",
    "duration_minutes": 30,
    "status": "scheduled",
    "version": 1,
}

AGENT = {
    "id": "agent-1",
    "email": "agent@example.com",
    "full_name": "Sam Agent",
    "role": "agent",
    "is_active": True,
    "version": 1,
}


def as_admin(fake_db, test_user):
    """The role gate reads the caller's profile row."""
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role": "admin", "is_active": True}]
    )


# --- Proposals ----------------------------------------------------------------


def test_marking_a_proposal_sent_stamps_sent_at(authed_client, fake_db):
    """The moment a proposal went out is a fact about the deal, not a client-supplied value."""
    fake_db.responses["PATCH proposals"] = FakeResult({**PROPOSAL, "status": "sent"})

    authed_client.patch(f"{V1}/proposals/prop-1", json={"status": "sent"})

    payload = [c for c in fake_db.calls if c[0] == "PATCH"][0][2]["payload"]
    assert payload["sent_at"] is not None


def test_client_cannot_backdate_sent_at(authed_client):
    response = authed_client.patch(
        f"{V1}/proposals/prop-1", json={"status": "sent", "sent_at": "2020-01-01T00:00:00Z"}
    )
    assert response.status_code == 422


def test_a_draft_proposal_can_be_deleted(authed_client, fake_db):
    fake_db.responses["GET proposals"] = FakeResult([PROPOSAL])
    fake_db.responses["DELETE proposals"] = FakeResult([PROPOSAL])

    assert authed_client.delete(f"{V1}/proposals/prop-1").status_code == 204


@pytest.mark.parametrize("status_value", ["sent", "under_review", "accepted", "rejected"])
def test_a_proposal_that_has_gone_out_cannot_be_deleted(authed_client, fake_db, status_value):
    """Deleting one would leave a hole in the version history of what the client was sent."""
    fake_db.responses["GET proposals"] = FakeResult([{**PROPOSAL, "status": status_value}])

    response = authed_client.delete(f"{V1}/proposals/prop-1")

    assert response.status_code == 409
    assert not [c for c in fake_db.calls if c[0] == "DELETE"]


# --- Meetings -----------------------------------------------------------------


def test_a_meeting_can_be_rescheduled(authed_client, fake_db):
    fake_db.responses["PATCH meetings"] = FakeResult(
        {**MEETING, "scheduled_at": "2026-09-05T14:00:00Z"}
    )

    response = authed_client.patch(
        f"{V1}/meetings/m-1", json={"scheduled_at": "2026-09-05T14:00:00Z"}
    )

    assert response.status_code == 200
    assert [c for c in fake_db.calls if c[0] == "PATCH"][0][2]["payload"]["scheduled_at"]


def test_rescheduling_does_not_touch_the_outcome(authed_client):
    """Recording what came out of a meeting is a separate action; it can schedule follow-ups."""
    response = authed_client.patch(f"{V1}/meetings/m-1", json={"outcome": "needs_proposal"})
    assert response.status_code == 422


def test_a_meeting_can_be_deleted(authed_client, fake_db):
    fake_db.responses["GET meetings"] = FakeResult([MEETING])
    fake_db.responses["DELETE meetings"] = FakeResult([MEETING])

    assert authed_client.delete(f"{V1}/meetings/m-1").status_code == 204


def test_a_delete_filtered_by_rls_is_not_reported_as_success(authed_client, fake_db):
    fake_db.responses["GET meetings"] = FakeResult([MEETING])
    fake_db.responses["DELETE meetings"] = FakeResult([])

    assert authed_client.delete(f"{V1}/meetings/m-1").status_code == 403


# --- Tasks --------------------------------------------------------------------


def test_a_task_can_be_deleted(authed_client, fake_db):
    fake_db.responses["GET tasks"] = FakeResult([{"id": "task-1"}])
    fake_db.responses["DELETE tasks"] = FakeResult([{"id": "task-1"}])

    assert authed_client.delete(f"{V1}/tasks/task-1").status_code == 204


# --- Soft deletes go through the database function -----------------------------


@pytest.mark.parametrize(
    "resource,function",
    [
        ("companies/co-1", "soft_delete_company"),
        ("opportunities/opp-1", "soft_delete_opportunity"),
    ],
)
def test_soft_deletes_use_the_function_not_a_delete(authed_client, fake_db, resource, function):
    """A PATCH cannot do this: the row it writes is one the SELECT policy then hides."""
    fake_db.responses[f"RPC {function}"] = FakeResult({"status": "deleted"})

    response = authed_client.delete(f"{V1}/{resource}")

    assert response.status_code == 204
    assert not [c for c in fake_db.calls if c[0] == "DELETE"]


def test_a_company_with_live_leads_cannot_be_deleted(authed_client, fake_db):
    """Removing it would strand them."""
    fake_db.responses["RPC soft_delete_company"] = FakeResult({"status": "referenced"})

    assert authed_client.delete(f"{V1}/companies/co-1").status_code == 409


# --- Agents -------------------------------------------------------------------


def test_an_admin_can_change_a_role(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["PATCH users"] = FakeResult({**AGENT, "role": "sdr"})

    response = authed_client.patch(f"{V1}/agents/agent-1", json={"role": "sdr"})

    assert response.status_code == 200
    assert response.json()["role"] == "sdr"


def test_a_non_admin_cannot_change_a_role(authed_client, fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role": "agent", "is_active": True}]
    )

    response = authed_client.patch(f"{V1}/agents/agent-1", json={"role": "admin"})

    assert response.status_code == 403


def test_an_agent_can_be_deactivated_rather_than_deleted(authed_client, fake_db, test_user):
    """People who leave keep their history; access is revoked instead."""
    as_admin(fake_db, test_user)
    fake_db.responses["PATCH users"] = FakeResult({**AGENT, "is_active": False})

    response = authed_client.patch(f"{V1}/agents/agent-1", json={"is_active": False})

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_agents_cannot_be_deleted_outright(client):
    """There is deliberately no DELETE: removing a user would orphan everything they own."""
    response = client.delete(f"{V1}/agents/agent-1")
    assert response.status_code in (404, 405)


def test_an_unknown_timezone_is_rejected_at_the_edge(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    response = authed_client.patch(
        f"{V1}/agents/agent-1", json={"timezone": "x" * 100}
    )
    assert response.status_code == 422


# --- Notifications ------------------------------------------------------------


def test_a_notification_can_be_dismissed(authed_client, fake_db):
    fake_db.responses["GET notifications"] = FakeResult([{"id": "n-1"}])
    fake_db.responses["DELETE notifications"] = FakeResult([{"id": "n-1"}])

    assert authed_client.delete(f"{V1}/notifications/n-1").status_code == 204


# --- The append-only timeline stays that way -----------------------------------


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_activities_cannot_be_edited_or_removed(client, method):
    """An audit trail you can rewrite is not an audit trail."""
    response = getattr(client, method)(f"{V1}/leads/lead-1/activities/act-1")
    assert response.status_code in (404, 405)
