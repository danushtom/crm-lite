"""Bulk actions: per-record results, the admin gate on reassign, and input hardening."""

from __future__ import annotations

import pytest

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult
from tests.test_imports import ADMIN_ROLE, AGENT_ROLE, ME, TableDb

L1 = "aaaaaaaa-0000-4000-8000-000000000001"
L2 = "aaaaaaaa-0000-4000-8000-000000000002"
HIDDEN = "aaaaaaaa-0000-4000-8000-000000000009"
SAM = "bbbbbbbb-0000-4000-8000-000000000002"


def _db(role=ADMIN_ROLE) -> TableDb:
    return TableDb(
        users=[
            {"id": ME, "email": "me@example.com", "is_active": True, "organization_id": "org-1", "roles": role},
            {"id": SAM, "email": "sam@example.com", "is_active": True, "organization_id": "org-1"},
        ],
        leads=[
            {"id": L1, "owner_id": ME, "tags": ["warm"]},
            {"id": L2, "owner_id": ME, "tags": []},
        ],
    )


@pytest.fixture
def fake_db():
    return _db()


def _post(client, kind, **body):
    return client.post(f"{V1}/bulk/{kind}", json=body)


def test_reassign_moves_the_visible_leads_and_reports_the_rest(authed_client, fake_db):
    response = _post(authed_client, "leads", action="reassign", ids=[L1, L2, HIDDEN], owner_id=SAM)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["succeeded"], body["failed"]) == (2, 1)
    assert {r["id"]: r["ok"] for r in body["results"]} == {L1: True, L2: True, HIDDEN: False}
    assert all(lead["owner_id"] == SAM for lead in fake_db.tables["leads"])


def test_only_full_access_roles_can_reassign(authed_client, fake_db):
    fake_db.tables["users"][0]["roles"] = AGENT_ROLE

    response = _post(authed_client, "leads", action="reassign", ids=[L1], owner_id=SAM)

    assert response.status_code == 403
    assert fake_db.tables["leads"][0]["owner_id"] == ME


def test_reassign_to_someone_outside_the_organization_is_refused(authed_client, fake_db):
    response = _post(
        authed_client, "leads", action="reassign", ids=[L1], owner_id="cccccccc-0000-4000-8000-000000000003"
    )

    assert response.status_code == 422
    assert fake_db.tables["leads"][0]["owner_id"] == ME


def test_tags_are_added_without_duplicates_and_removed_case_insensitively(authed_client, fake_db):
    _post(authed_client, "leads", action="add_tags", ids=[L1, L2], tags=["Warm", "q4"])
    assert fake_db.tables["leads"][0]["tags"] == ["warm", "q4"]
    assert fake_db.tables["leads"][1]["tags"] == ["Warm", "q4"]

    _post(authed_client, "leads", action="remove_tags", ids=[L1, L2], tags=["WARM"])
    assert fake_db.tables["leads"][0]["tags"] == ["q4"]
    assert fake_db.tables["leads"][1]["tags"] == ["q4"]


def test_delete_reports_each_record_through_the_soft_delete_function(authed_client, fake_db):
    outcomes = iter([{"status": "deleted"}, {"status": "referenced"}])

    async def rpc(function, payload=None):
        fake_db.calls.append(("POST", f"rpc/{function}", {"payload": payload}))
        return FakeResult(next(outcomes))

    fake_db.rpc = rpc  # type: ignore[method-assign]
    response = _post(authed_client, "companies", action="delete", ids=[L1, L2])

    body = response.json()
    assert (body["succeeded"], body["failed"]) == (1, 1)
    failed = next(r for r in body["results"] if not r["ok"])
    assert "active leads" in failed["message"]
    assert {c[1] for c in fake_db.calls if c[1].startswith("rpc/")} == {"rpc/soft_delete_company"}


@pytest.mark.parametrize(
    "body",
    [
        {"action": "delete", "ids": ["1),or(owner_id.neq.x"]},  # filter injection attempt
        {"action": "delete", "ids": []},
        {"action": "reassign", "ids": [L1]},  # no owner
        {"action": "add_tags", "ids": [L1], "tags": ["  "]},
    ],
)
def test_malformed_requests_are_rejected_before_any_query(authed_client, fake_db, body):
    response = authed_client.post(f"{V1}/bulk/leads", json=body)

    assert response.status_code == 422
    assert not any(c[0] in ("PATCH", "POST") for c in fake_db.calls)


def test_actions_are_limited_per_kind(authed_client):
    response = _post(authed_client, "contacts", action="add_tags", ids=[L1], tags=["x"])

    assert response.status_code == 422
