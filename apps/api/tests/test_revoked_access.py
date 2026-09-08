"""A user whose access has been revoked must not get past the profile dependency.

The database is the real authority here -- `current_org_id()` returns NULL and `is_admin()`
returns false for a deactivated user, which makes every RLS policy fail closed, including for
the browser's own direct Supabase queries. This covers the application-layer half: an endpoint
that loads the profile should say plainly that access was revoked rather than returning an
empty collection and leaving the caller to guess.
"""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}


def profile(is_active: bool, test_user):
    return FakeResult(
        [
            {
                "id": test_user.sub,
                "email": "revoked@example.com",
                "role_id": ADMIN_ROLE["id"],
                "roles": ADMIN_ROLE,
                "organization_id": "org-1",
                "is_active": is_active,
            }
        ]
    )


def test_a_revoked_user_is_refused_by_the_profile_dependency(authed_client, fake_db, test_user):
    fake_db.responses["GET users"] = profile(False, test_user)

    response = authed_client.get(f"{V1}/auth/me")

    assert response.status_code == 403
    assert "revoked" in response.json()["detail"].lower()


def test_a_revoked_user_keeps_no_admin_powers(authed_client, fake_db, test_user):
    """The role still says grants_full_access -- revocation is on the user, not the role -- so
    this is the case where checking only the role would let a revoked admin straight through."""
    fake_db.responses["GET users"] = profile(False, test_user)

    response = authed_client.post(f"{V1}/roles", json={"name": "Backdoor", "permission_keys": []})

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "roles"]


def test_an_active_user_is_unaffected(authed_client, fake_db, test_user):
    fake_db.responses["GET users"] = profile(True, test_user)

    response = authed_client.get(f"{V1}/auth/me")

    assert response.status_code == 200


def test_a_missing_is_active_column_is_treated_as_active(authed_client, fake_db, test_user):
    """Defaulting to active matters for the older rows that predate the column: failing closed
    on absence would lock out an entire existing workspace on deploy."""
    fake_db.responses["GET users"] = FakeResult(
        [
            {
                "id": test_user.sub,
                "email": "legacy@example.com",
                "role_id": ADMIN_ROLE["id"],
                "roles": ADMIN_ROLE,
                "organization_id": "org-1",
            }
        ]
    )

    response = authed_client.get(f"{V1}/auth/me")

    assert response.status_code == 200
