"""The tenant row's own read/update endpoints.

The important behaviour here is that the organization id is taken from the caller's profile,
never from the request: the update runs on the service-role client (organizations has no UPDATE
policy for authenticated users), so RLS is not there to catch a mistake.
"""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}
AGENT_ROLE = {"id": "role-agent-1", "name": "Agent", "grants_full_access": False, "role_permissions": []}

ORG_ROW = {"id": "org-1", "name": "Acme Inc", "slug": "acme", "created_at": None}


def as_role(fake_db, test_user, role):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": role["id"], "is_active": True, "roles": role, "organization_id": "org-1"}]
    )


def test_any_member_can_read_their_organization(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, AGENT_ROLE)
    fake_db.responses["GET organizations"] = FakeResult([ORG_ROW])

    response = authed_client.get(f"{V1}/organizations/me")

    assert response.status_code == 200
    assert response.json()["name"] == "Acme Inc"


def test_a_non_admin_cannot_rename_the_organization(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, AGENT_ROLE)

    response = authed_client.patch(f"{V1}/organizations/me", json={"name": "Renamed"})

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "organizations"]


def test_an_admin_renames_only_their_own_organization(authed_client, fake_db, test_user):
    """The write is service-role, so nothing downstream would stop it touching another tenant
    if the filter came from anywhere but the caller's own profile."""
    as_role(fake_db, test_user, ADMIN_ROLE)
    fake_db.responses["PATCH organizations"] = FakeResult({**ORG_ROW, "name": "Renamed"})

    response = authed_client.patch(f"{V1}/organizations/me", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    patch = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "organizations"][0]
    assert patch[2]["params"]["id"] == "eq.org-1"
    assert patch[2]["payload"] == {"name": "Renamed"}


def test_an_empty_name_is_rejected(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE)

    response = authed_client.patch(f"{V1}/organizations/me", json={"name": ""})

    assert response.status_code == 422
    assert not [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "organizations"]
