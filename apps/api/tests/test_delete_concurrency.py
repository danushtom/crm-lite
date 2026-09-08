"""If-Match on the hard-delete endpoints.

Companies, contacts, leads, opportunities and voice agents are soft-deleted through a database
function that already took an expected version. Meetings, tasks, proposals and roles are
removed outright and their DELETE handlers accepted no precondition at all, so a client holding
a stale copy could delete a row that had changed underneath it -- a task someone else had just
completed, a meeting that had been rescheduled, a proposal that had since been sent.
"""

from __future__ import annotations

import pytest

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}


def as_admin(fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": ADMIN_ROLE["id"], "is_active": True, "roles": ADMIN_ROLE, "organization_id": "org-1"}]
    )


#: (path, table, the row the "someone got there first" branch re-reads)
CASES = [
    (f"{V1}/tasks/task-1", "tasks", {"id": "task-1", "version": 4}),
    (f"{V1}/meetings/meeting-1", "meetings", {"id": "meeting-1", "version": 4}),
    (f"{V1}/roles/role-9", "roles", {"id": "role-9", "version": 4}),
]


@pytest.mark.parametrize("path,table,row", CASES)
def test_the_version_is_pushed_into_the_delete_itself(authed_client, fake_db, test_user, path, table, row):
    """The check and the delete are one statement: a separate read-then-delete would leave a
    window for the row to change in between."""
    as_admin(fake_db, test_user)
    fake_db.responses[f"DELETE {table}"] = FakeResult([row])

    response = authed_client.delete(path, headers={"If-Match": '"4"'})

    assert response.status_code == 204
    params = [c for c in fake_db.calls if c[0] == "DELETE" and c[1] == table][0][2]["params"]
    assert params["version"] == "eq.4"


@pytest.mark.parametrize("path,table,row", CASES)
def test_a_stale_version_is_refused_rather_than_deleting(authed_client, fake_db, test_user, path, table, row):
    as_admin(fake_db, test_user)
    # Nothing matched the conditional delete, and the row is still there on the re-read.
    fake_db.responses[f"DELETE {table}"] = FakeResult([])
    fake_db.responses[f"GET {table}"] = FakeResult([row])

    response = authed_client.delete(path, headers={"If-Match": '"2"'})

    assert response.status_code == 412
    assert response.json()["current_version"] == 4


@pytest.mark.parametrize("path,table,row", CASES)
def test_deleting_a_row_that_is_already_gone_is_a_404(authed_client, fake_db, test_user, path, table, row):
    as_admin(fake_db, test_user)
    fake_db.responses[f"DELETE {table}"] = FakeResult([])
    fake_db.responses[f"GET {table}"] = FakeResult([])

    response = authed_client.delete(path, headers={"If-Match": '"4"'})

    assert response.status_code == 404


@pytest.mark.parametrize("path,table,row", CASES)
def test_omitting_if_match_still_deletes(authed_client, fake_db, test_user, path, table, row):
    """The header stays optional, as it is everywhere else in this API -- sending it is what
    buys protection, not sending it must not break an existing client."""
    as_admin(fake_db, test_user)
    fake_db.responses[f"DELETE {table}"] = FakeResult([row])

    response = authed_client.delete(path)

    assert response.status_code == 204
    params = [c for c in fake_db.calls if c[0] == "DELETE" and c[1] == table][0][2]["params"]
    assert "version" not in params


def test_a_sent_proposal_is_still_refused_before_the_version_is_even_checked(
    authed_client, fake_db, test_user
):
    """The draft-only rule is about the deal record, not about concurrency, so it must not be
    bypassable by supplying a correct If-Match."""
    as_admin(fake_db, test_user)
    fake_db.responses["GET proposals"] = FakeResult(
        [{"id": "prop-1", "status": "sent", "version": 3}]
    )

    response = authed_client.delete(f"{V1}/proposals/prop-1", headers={"If-Match": '"3"'})

    assert response.status_code == 409
    assert not [c for c in fake_db.calls if c[0] == "DELETE" and c[1] == "proposals"]


def test_a_proposals_if_match_speaks_in_row_version_not_the_document_number(
    authed_client, fake_db, test_user
):
    """proposals.version is the number users see -- "Proposal v2" -- and is UNIQUE per
    opportunity. Using it as the concurrency counter meant the bump_version trigger renumbered
    a proposal on every edit; row_version is the counter, and If-Match must filter on that."""
    as_admin(fake_db, test_user)
    fake_db.responses["GET proposals"] = FakeResult(
        [{"id": "prop-1", "status": "draft", "version": 2, "row_version": 7}]
    )
    fake_db.responses["DELETE proposals"] = FakeResult([{"id": "prop-1"}])

    response = authed_client.delete(f"{V1}/proposals/prop-1", headers={"If-Match": '"7"'})

    assert response.status_code == 204
    params = [c for c in fake_db.calls if c[0] == "DELETE" and c[1] == "proposals"][0][2]["params"]
    assert params["row_version"] == "eq.7"
    assert "version" not in params


def test_a_proposals_etag_is_its_row_version(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET proposals"] = FakeResult(
        [{
            "id": "prop-1",
            "opportunity_id": "opp-1",
            "version": 2,
            "row_version": 7,
            "title": "Statement of work",
            "status": "draft",
        }]
    )

    response = authed_client.get(f"{V1}/proposals/prop-1")

    assert response.status_code == 200
    # 7, the concurrency counter -- not 2, the document number.
    assert response.headers["ETag"] == '"7"'
    assert response.json()["version"] == 2
