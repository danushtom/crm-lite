"""Role and permission management: GET /roles/catalog, and CRUD on /roles.

Reading roles and the permission catalog is open to any authenticated user (the UI needs role
names wherever a person is listed). Creating, editing or deleting a role requires a role with
full organization access -- the same gate as everything under /agents.
"""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}
AGENT_ROLE = {"id": "role-agent-1", "name": "Agent", "grants_full_access": False, "role_permissions": []}

PERMISSIONS_CATALOG = [
    {"id": "perm-leads-read", "resource": "leads", "action": "read", "description": "View leads."},
    {"id": "perm-leads-write", "resource": "leads", "action": "write", "description": "Edit leads."},
]

SALES_LEAD_ROLE_ROW = {
    "id": "role-sales-lead-1",
    "name": "Sales Lead",
    "grants_full_access": False,
    "is_system": False,
    "role_permissions": [{"permissions": {"resource": "leads", "action": "read"}}],
    "created_at": "2026-09-05T00:00:00Z",
    "updated_at": "2026-09-05T00:00:00Z",
}


def as_admin(fake_db, test_user):
    """The role gate reads the caller's profile row, with the role embedded."""
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": ADMIN_ROLE["id"], "is_active": True, "roles": ADMIN_ROLE}]
    )


def as_agent(fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": AGENT_ROLE["id"], "is_active": True, "roles": AGENT_ROLE}]
    )


# --- Catalog --------------------------------------------------------------------


def test_any_authenticated_user_can_read_the_permission_catalog(authed_client, fake_db):
    fake_db.responses["GET permissions"] = FakeResult(PERMISSIONS_CATALOG)

    response = authed_client.get(f"{V1}/roles/catalog")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {p["resource"] for p in body} == {"leads"}


# --- List -------------------------------------------------------------------------


def test_any_authenticated_user_can_list_roles(authed_client, fake_db):
    fake_db.responses["GET roles"] = FakeResult([SALES_LEAD_ROLE_ROW])
    fake_db.responses["GET users"] = FakeResult(
        [{"role_id": SALES_LEAD_ROLE_ROW["id"]}, {"role_id": SALES_LEAD_ROLE_ROW["id"]}]
    )

    response = authed_client.get(f"{V1}/roles")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["name"] == "Sales Lead"
    assert body[0]["permissions"] == ["leads.read"]
    assert body[0]["user_count"] == 2


# --- Create -----------------------------------------------------------------------


def test_an_admin_can_create_a_role(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET permissions"] = FakeResult(PERMISSIONS_CATALOG)
    fake_db.responses["POST roles"] = FakeResult({"id": "role-new-1"})
    fake_db.responses["GET roles"] = FakeResult(
        {**SALES_LEAD_ROLE_ROW, "id": "role-new-1"}
    )

    response = authed_client.post(
        f"{V1}/roles",
        json={"name": "Sales Lead", "grants_full_access": False, "permission_keys": ["leads.read"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sales Lead"
    assert body["permissions"] == ["leads.read"]
    grants = [c for c in fake_db.calls if c[0] == "POST" and c[1] == "role_permissions"][0]
    assert grants[2]["payload"] == [{"role_id": "role-new-1", "permission_id": "perm-leads-read"}]


def test_a_non_admin_cannot_create_a_role(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)

    response = authed_client.post(
        f"{V1}/roles",
        json={"name": "Should Not Exist", "grants_full_access": False, "permission_keys": []},
    )

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "roles"]


def test_creating_a_role_with_an_unknown_permission_key_is_rejected(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET permissions"] = FakeResult(PERMISSIONS_CATALOG)

    response = authed_client.post(
        f"{V1}/roles",
        json={"name": "Bad Role", "grants_full_access": False, "permission_keys": ["not_a_real.permission"]},
    )

    assert response.status_code == 422
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "roles"]


# --- Update -----------------------------------------------------------------------


def test_an_admin_can_rename_a_role(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    updated = {**SALES_LEAD_ROLE_ROW, "name": "Renamed"}
    fake_db.responses["PATCH roles"] = FakeResult(updated)
    fake_db.responses["GET roles"] = FakeResult(updated)

    response = authed_client.patch(f"{V1}/roles/{SALES_LEAD_ROLE_ROW['id']}", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    payload = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "roles"][0][2]["payload"]
    assert payload == {"name": "Renamed"}


def test_an_admin_can_replace_a_roles_permissions(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET permissions"] = FakeResult(PERMISSIONS_CATALOG)
    updated_row = {
        **SALES_LEAD_ROLE_ROW,
        "role_permissions": [{"permissions": {"resource": "leads", "action": "write"}}],
    }
    fake_db.responses["GET roles"] = FakeResult(updated_row)

    response = authed_client.patch(
        f"{V1}/roles/{SALES_LEAD_ROLE_ROW['id']}", json={"permission_keys": ["leads.write"]}
    )

    assert response.status_code == 200
    assert response.json()["permissions"] == ["leads.write"]
    assert [c for c in fake_db.calls if c[0] == "DELETE" and c[1] == "role_permissions"]
    insert = [c for c in fake_db.calls if c[0] == "POST" and c[1] == "role_permissions"][0]
    assert insert[2]["payload"] == [
        {"role_id": SALES_LEAD_ROLE_ROW["id"], "permission_id": "perm-leads-write"}
    ]


def test_a_non_admin_cannot_update_a_role(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)

    response = authed_client.patch(f"{V1}/roles/{SALES_LEAD_ROLE_ROW['id']}", json={"name": "Hacked"})

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "roles"]


# --- Delete -----------------------------------------------------------------------


def test_an_admin_can_delete_a_role(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET roles"] = FakeResult([{"id": SALES_LEAD_ROLE_ROW["id"]}])
    fake_db.responses["DELETE roles"] = FakeResult([{"id": SALES_LEAD_ROLE_ROW["id"]}])

    response = authed_client.delete(f"{V1}/roles/{SALES_LEAD_ROLE_ROW['id']}")

    assert response.status_code == 204


def test_deleting_an_unknown_role_is_404(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET roles"] = FakeResult([])

    response = authed_client.delete(f"{V1}/roles/does-not-exist")

    assert response.status_code == 404


def test_a_non_admin_cannot_delete_a_role(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)

    response = authed_client.delete(f"{V1}/roles/{SALES_LEAD_ROLE_ROW['id']}")

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "DELETE"]


def test_deleting_a_role_still_assigned_to_users_is_rejected(authed_client, fake_db, test_user):
    """The database refuses the delete (still referenced or the org's last full-access role);
    PostgREST reports zero rows affected either way, which the endpoint treats as forbidden."""
    as_admin(fake_db, test_user)
    fake_db.responses["GET roles"] = FakeResult([{"id": SALES_LEAD_ROLE_ROW["id"]}])
    fake_db.responses["DELETE roles"] = FakeResult([])

    response = authed_client.delete(f"{V1}/roles/{SALES_LEAD_ROLE_ROW['id']}")

    assert response.status_code == 403
