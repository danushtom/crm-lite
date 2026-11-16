"""Two-factor enforcement, as the API sees it.

The enforcement itself is in the database (20260920010000_enforce_mfa.sql): for a session below
aal2 whose user has a verified factor, current_org_id() is NULL and a restrictive policy hides
every row -- including the caller's own users row. These tests pin what the API does with that.
"""

from __future__ import annotations

from app.api import deps
from app.core.config import API_V1_PREFIX as V1
from app.core.security import TokenUser
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin", "name": "Admin", "grants_full_access": True, "role_permissions": []}


def _as(app, user: TokenUser):
    app.dependency_overrides[deps.get_current_user] = lambda: user


def test_an_unverified_session_is_told_to_enter_its_code(app, authed_client, fake_db, test_user):
    _as(app, TokenUser(sub=test_user.sub, email=test_user.email, aal="aal1"))
    fake_db.responses["GET users"] = FakeResult([])  # what RLS returns to that session

    response = authed_client.get(f"{V1}/auth/me")

    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_a_verified_session_with_no_profile_is_still_a_plain_403(app, authed_client, fake_db, test_user):
    _as(app, TokenUser(sub=test_user.sub, email=test_user.email, aal="aal2"))
    fake_db.responses["GET users"] = FakeResult([])

    response = authed_client.get(f"{V1}/auth/me")

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_a_session_that_can_read_its_profile_proceeds_at_either_level(app, authed_client, fake_db, test_user):
    _as(app, TokenUser(sub=test_user.sub, email=test_user.email, aal="aal1"))
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "email": test_user.email, "full_name": "A", "is_active": True,
          "organization_id": "org-1", "role_id": "role-admin", "roles": ADMIN_ROLE, "timezone": "UTC"}]
    )

    assert authed_client.get(f"{V1}/auth/me").status_code == 200
