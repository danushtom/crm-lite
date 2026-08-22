"""Endpoint behaviour, exercised through the real ASGI stack with a fake database."""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

LEAD = {
    "id": "lead-1",
    "company_id": "co-1",
    "owner_id": "11111111-2222-3333-4444-555555555555",
    "stage": "prospect",
    "project_type": "saas",
    "lead_source": "referral",
    "estimated_value": 250000,
    "currency": "INR",
    "deal_probability": 50,
    "priority_score": 42,
    "tags": ["inbound"],
    "is_opportunity": False,
}

TASK = {
    "id": "task-1",
    "lead_id": "lead-1",
    "owner_id": "11111111-2222-3333-4444-555555555555",
    "title": "Call back",
    "due_at": "2026-09-01T09:00:00+00:00",
    "status": "pending",
}

CONTACT = {"id": "c-1", "company_id": "co-1", "full_name": "Jane Doe", "is_primary": False}


# --- Collection envelope ------------------------------------------------------


def test_collection_returns_envelope_with_total(authed_client, fake_db):
    fake_db.responses["GET leads"] = FakeResult([LEAD], count=137)

    body = authed_client.get(f"{V1}/leads").json()

    assert body["items"][0]["id"] == "lead-1"
    assert body["page"] == {"limit": 50, "offset": 0, "total": 137, "has_more": True}


def test_has_more_is_false_on_the_last_page(authed_client, fake_db):
    fake_db.responses["GET leads"] = FakeResult([LEAD], count=1)
    body = authed_client.get(f"{V1}/leads").json()
    assert body["page"]["has_more"] is False


def test_limit_and_offset_reach_the_query(authed_client, fake_db):
    fake_db.responses["GET leads"] = FakeResult([], count=0)
    authed_client.get(f"{V1}/leads", params={"limit": 10, "offset": 30})
    params = fake_db.calls[-1][2]["params"]
    assert params["limit"] == "10"
    assert params["offset"] == "30"


def test_money_is_serialised_as_a_json_number(authed_client, fake_db):
    """Pydantic renders Decimal as a string by default, which breaks number-typed clients."""
    fake_db.responses["GET leads"] = FakeResult([LEAD], count=1)
    raw = authed_client.get(f"{V1}/leads").text
    assert '"estimated_value":"' not in raw
    value = authed_client.get(f"{V1}/leads").json()["items"][0]["estimated_value"]
    assert isinstance(value, (int, float))


# --- Filters ------------------------------------------------------------------


def test_stage_filter_is_passed_through(authed_client, fake_db):
    fake_db.responses["GET leads"] = FakeResult([], count=0)
    authed_client.get(f"{V1}/leads", params={"stage": "negotiation"})
    assert fake_db.calls[-1][2]["params"]["stage"] == "eq.negotiation"


def test_search_strips_postgrest_wildcards(authed_client, fake_db):
    """Unescaped *, % or , would let a caller alter the filter expression."""
    fake_db.responses["GET leads"] = FakeResult([], count=0)

    authed_client.get(f"{V1}/leads", params={"search": "ac*me,(x)"})

    name_filter = fake_db.calls[-1][2]["params"]["companies.name"]
    # Only the wrapping wildcards this endpoint adds should survive.
    assert name_filter == "ilike.*acmex*"


# --- Creation semantics -------------------------------------------------------


def test_create_lead_returns_201_with_location(authed_client, fake_db):
    fake_db.responses["POST leads"] = FakeResult(LEAD)

    response = authed_client.post(
        f"{V1}/leads",
        json={"company_id": "co-1", "project_type": "saas", "lead_source": "referral"},
    )

    assert response.status_code == 201
    assert response.headers["location"] == "/leads/lead-1"


def test_create_lead_defaults_owner_to_the_caller(authed_client, fake_db, test_user):
    fake_db.responses["POST leads"] = FakeResult(LEAD)
    authed_client.post(
        f"{V1}/leads",
        json={"company_id": "co-1", "project_type": "saas", "lead_source": "referral"},
    )
    payload = [c for c in fake_db.calls if c[0] == "POST"][0][2]["payload"]
    assert payload["owner_id"] == test_user.sub
    assert "priority_score" in payload, "score must be computed server-side, not trusted from input"


def test_create_lead_rejects_an_invalid_enum(authed_client):
    response = authed_client.post(
        f"{V1}/leads",
        json={"company_id": "co-1", "project_type": "telepathy", "lead_source": "referral"},
    )
    assert response.status_code == 422
    assert any(e["field"] == "project_type" for e in response.json()["errors"])


def test_create_lead_rejects_out_of_range_probability(authed_client):
    response = authed_client.post(
        f"{V1}/leads",
        json={
            "company_id": "co-1",
            "project_type": "saas",
            "lead_source": "referral",
            "deal_probability": 150,
        },
    )
    assert response.status_code == 422


def test_client_cannot_set_priority_score_directly(authed_client):
    """priority_score is derived; accepting it from the client would let callers fake ranking."""
    response = authed_client.post(
        f"{V1}/leads",
        json={
            "company_id": "co-1",
            "project_type": "saas",
            "lead_source": "referral",
            "priority_score": 100,
        },
    )
    assert response.status_code == 422


# --- Task lifecycle -----------------------------------------------------------


def test_completing_a_task_stamps_completed_at(authed_client, fake_db):
    fake_db.responses["PATCH tasks"] = FakeResult({**TASK, "status": "completed"})
    authed_client.patch(f"{V1}/tasks/task-1", json={"status": "completed"})
    payload = fake_db.calls[-1][2]["payload"]
    assert payload["completed_at"] is not None


def test_reopening_a_task_clears_completed_at(authed_client, fake_db):
    """A reopened task showing a completion timestamp misreports the follow-up queue."""
    fake_db.responses["PATCH tasks"] = FakeResult(TASK)
    authed_client.patch(f"{V1}/tasks/task-1", json={"status": "pending"})
    assert fake_db.calls[-1][2]["payload"]["completed_at"] is None


def test_snoozing_requires_a_date(authed_client):
    response = authed_client.patch(f"{V1}/tasks/task-1", json={"status": "snoozed"})
    assert response.status_code == 422


def test_snoozing_with_a_date_is_accepted(authed_client, fake_db):
    fake_db.responses["PATCH tasks"] = FakeResult({**TASK, "status": "snoozed"})
    response = authed_client.patch(
        f"{V1}/tasks/task-1", json={"status": "snoozed", "snoozed_to": "2026-09-05T09:00:00+00:00"}
    )
    assert response.status_code == 200


# --- Contact deletion guards --------------------------------------------------


def test_delete_contact_returns_204(authed_client, fake_db):
    fake_db.responses["GET contacts"] = FakeResult([CONTACT])
    fake_db.responses["GET leads"] = FakeResult([])
    fake_db.responses["DELETE contacts"] = FakeResult([CONTACT])

    assert authed_client.delete(f"{V1}/contacts/c-1").status_code == 204


def test_delete_contact_referenced_by_a_lead_is_a_409(authed_client, fake_db):
    fake_db.responses["GET contacts"] = FakeResult([CONTACT])
    fake_db.responses["GET leads"] = FakeResult([{"id": "lead-1"}])

    response = authed_client.delete(f"{V1}/contacts/c-1")

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


def test_delete_contact_filtered_by_rls_is_a_403_not_a_silent_204(authed_client, fake_db):
    """A DELETE that removes zero rows means the policy denied it; do not report success."""
    fake_db.responses["GET contacts"] = FakeResult([CONTACT])
    fake_db.responses["GET leads"] = FakeResult([])
    fake_db.responses["DELETE contacts"] = FakeResult([])

    response = authed_client.delete(f"{V1}/contacts/c-1")

    assert response.status_code == 403


def test_delete_missing_contact_is_a_404(authed_client, fake_db):
    fake_db.responses["GET contacts"] = FakeResult([])
    assert authed_client.delete(f"{V1}/contacts/c-1").status_code == 404


# --- Notifications ------------------------------------------------------------


def test_mark_all_read_is_scoped_to_the_caller(authed_client, fake_db, test_user):
    """Without the user_id filter this would clear every user's notifications."""
    fake_db.responses["PATCH notifications"] = FakeResult([{"id": "n-1"}, {"id": "n-2"}])

    body = authed_client.post(f"{V1}/notifications/read-all", json={}).json()

    params = fake_db.calls[-1][2]["params"]
    assert params["user_id"] == f"eq.{test_user.sub}"
    assert params["read_at"] == "is.null"
    assert body["updated"] == 2


def test_unread_only_filter(authed_client, fake_db):
    fake_db.responses["GET notifications"] = FakeResult([], count=0)
    authed_client.get(f"{V1}/notifications", params={"unread_only": True})
    assert fake_db.calls[-1][2]["params"]["read_at"] == "is.null"


def test_marking_unread_clears_the_timestamp(authed_client, fake_db):
    fake_db.responses["PATCH notifications"] = FakeResult(
        [{"id": "n-1", "user_id": "u", "type": "x", "title": "t", "read_at": None}]
    )
    authed_client.patch(f"{V1}/notifications/n-1", json={"read": False})
    assert fake_db.calls[-1][2]["payload"]["read_at"] is None


# --- Follow-up queues ---------------------------------------------------------


def test_follow_up_queues_filter_in_the_database(authed_client, fake_db, test_user):
    """The previous implementation fetched every task and partitioned in Python."""
    fake_db.responses["GET tasks"] = FakeResult([TASK])
    fake_db.responses["GET users"] = FakeResult([{"id": test_user.sub, "role": "agent",
                                                  "timezone": "Asia/Kolkata"}])

    body = authed_client.get(f"{V1}/dashboard/follow-ups").json()

    assert set(body) == {"today", "overdue", "upcoming", "timezone"}
    queries = [c for c in fake_db.calls if c[1] == "tasks"]
    assert len(queries) == 3, "each queue should be its own filtered query"
    for _, _, kwargs in queries:
        assert kwargs["params"]["owner_id"] == f"eq.{test_user.sub}"
        assert "due_at" in kwargs["params"]


def test_follow_up_day_boundaries_use_the_callers_timezone(authed_client, fake_db, test_user):
    """A server in UTC and an agent in IST disagree about "today" for 5.5 hours a day."""
    from datetime import datetime, timezone as dt_timezone
    from zoneinfo import ZoneInfo

    fake_db.responses["GET tasks"] = FakeResult([])
    fake_db.responses["GET users"] = FakeResult([{"id": test_user.sub, "role": "agent",
                                                  "timezone": "Asia/Kolkata"}])

    body = authed_client.get(f"{V1}/dashboard/follow-ups").json()
    assert body["timezone"] == "Asia/Kolkata"

    overdue_query = [c for c in fake_db.calls if c[1] == "tasks"][0]
    boundary = overdue_query[2]["params"]["due_at"].removeprefix("lt.")
    parsed = datetime.fromisoformat(boundary)

    expected = datetime.now(dt_timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    assert parsed == expected, "midnight must be local midnight, not the server's"


def test_unknown_timezone_falls_back_rather_than_failing(authed_client, fake_db, test_user):
    fake_db.responses["GET tasks"] = FakeResult([])
    fake_db.responses["GET users"] = FakeResult([{"id": test_user.sub, "role": "agent",
                                                  "timezone": "Mars/Olympus_Mons"}])

    response = authed_client.get(f"{V1}/dashboard/follow-ups")

    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Kolkata"


# --- Dashboard ----------------------------------------------------------------


def test_dashboard_unwraps_the_rpc_envelope(authed_client, fake_db):
    """PostgREST wraps a jsonb-returning function as [{"dashboard_metrics": {...}}]."""
    fake_db.responses["RPC dashboard_metrics"] = FakeResult(
        [{"dashboard_metrics": {
            "pipeline_total": 1000,
            "weighted_forecast": 500,
            "stage_values": {"won": 400},
            "hot_leads_needing_action": ["lead-1"],
            "win_loss_ratio_30d": {"wins": 2, "losses": 1},
        }}]
    )

    body = authed_client.get(f"{V1}/dashboard").json()

    assert body["pipeline_total"] == 1000
    assert body["win_loss_ratio_30d"]["wins"] == 2
    assert body["hot_leads_needing_action"] == ["lead-1"]


def test_dashboard_reports_currency_composition(authed_client, fake_db):
    """pipeline_total sums estimated_value across currencies, so callers need to know."""
    fake_db.responses["RPC dashboard_metrics"] = FakeResult(
        [{"dashboard_metrics": {
            "pipeline_total": 1500,
            "weighted_forecast": 700,
            "pipeline_by_currency": {"INR": 1000, "USD": 500},
            "mixed_currency": True,
            "stage_values": {},
            "hot_leads_needing_action": [],
            "win_loss_ratio_30d": {"wins": 0, "losses": 0},
        }}]
    )

    body = authed_client.get(f"{V1}/dashboard").json()

    assert body["mixed_currency"] is True
    assert body["pipeline_by_currency"] == {"INR": 1000, "USD": 500}


def test_lead_search_is_a_single_joined_query(authed_client, fake_db):
    """It used to resolve company ids in a separate call capped at 100, silently dropping
    the leads of every company past that cap."""
    fake_db.responses["GET leads"] = FakeResult([], count=0)

    authed_client.get(f"{V1}/leads", params={"search": "acme"})

    queries = [c for c in fake_db.calls if c[1] in ("leads", "companies")]
    assert len(queries) == 1, f"search should not need a second lookup: {queries}"

    params = queries[0][2]["params"]
    assert params["select"] == "*,companies!inner(*)"
    assert params["companies.name"] == "ilike.*acme*"
    assert "limit" not in str(params.get("companies.name", ""))
