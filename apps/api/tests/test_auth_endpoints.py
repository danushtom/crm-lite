"""The /auth router: the caller's own profile, and the Google Calendar OAuth exchange.

Token verification itself is covered by test_auth.py; this file exercises the endpoints in
app/api/v1/endpoints/auth.py -- reading and updating your own profile, and the three-step
Google Calendar connect/disconnect flow, none of which had any test coverage before.
"""

from __future__ import annotations

import json

import httpx

from app.core.config import API_V1_PREFIX as V1
from app.core.config import settings
from tests.conftest import FakeResult

PROFILE_ROLE = {
    "id": "role-agent-1",
    "name": "Agent",
    "grants_full_access": False,
    "role_permissions": [
        {"permissions": {"resource": "leads", "action": "read"}},
        {"permissions": {"resource": "leads", "action": "write"}},
    ],
}

PROFILE_ROW = {
    "id": "11111111-2222-3333-4444-555555555555",
    "email": "agent@example.com",
    "full_name": "Sam Agent",
    "role_id": PROFILE_ROLE["id"],
    "roles": PROFILE_ROLE,
    "organization_id": "org-1",
    "avatar_url": None,
    "is_active": True,
    "timezone": "Asia/Kolkata",
    "google_refresh_token": None,
}


class FakeResponse:
    """Stands in for an httpx.Response returned by an external HTTP call."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = json.dumps(self._json).encode()
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(self._json)

    def json(self):
        return self._json


class FakeHttpClient:
    """Stands in for the process-wide httpx.AsyncClient for tests that reach an external service."""

    def __init__(self, post_response: FakeResponse | None = None, request_response: FakeResponse | None = None):
        self.post_response = post_response or FakeResponse()
        self.request_response = request_response or FakeResponse()
        self.calls: list[tuple[str, str, dict]] = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.post_response

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.request_response


# --- GET /auth/me -------------------------------------------------------------------


def test_read_current_user_exposes_role_and_permissions(authed_client, fake_db):
    fake_db.responses["GET users"] = FakeResult([PROFILE_ROW])

    response = authed_client.get(f"{V1}/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["role_name"] == "Agent"
    assert body["grants_full_access"] is False
    assert body["permissions"] == ["leads.read", "leads.write"]
    assert body["calendar_connected"] is False


def test_read_current_user_reports_calendar_connected_once_a_refresh_token_exists(authed_client, fake_db):
    fake_db.responses["GET users"] = FakeResult([{**PROFILE_ROW, "google_refresh_token": "refresh-token"}])

    response = authed_client.get(f"{V1}/auth/me")

    assert response.json()["calendar_connected"] is True


# --- PATCH /auth/me -----------------------------------------------------------------


def test_updating_your_own_profile(authed_client, fake_db):
    fake_db.responses["PATCH users"] = FakeResult({**PROFILE_ROW, "full_name": "New Name"})

    response = authed_client.patch(f"{V1}/auth/me", json={"full_name": "New Name"})

    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


def test_updating_your_profile_with_no_changes_just_refetches_it(authed_client, fake_db):
    fake_db.responses["GET users"] = FakeResult([PROFILE_ROW])

    response = authed_client.patch(f"{V1}/auth/me", json={})

    assert response.status_code == 200
    assert response.json()["id"] == PROFILE_ROW["id"]


def test_role_and_access_cannot_be_changed_through_self_service_update(authed_client):
    """CurrentUserUpdate forbids unknown fields -- role/is_active are administrative only, see
    PATCH /agents/{id}."""
    response = authed_client.patch(f"{V1}/auth/me", json={"role_id": "role-admin-1"})
    assert response.status_code == 422


# --- POST /auth/google/callback -------------------------------------------------------


def test_google_oauth_not_configured_is_501(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "", raising=False)
    monkeypatch.setattr(settings, "google_client_secret", "", raising=False)

    response = authed_client.post(f"{V1}/auth/google/callback", json={"code": "abc123"})

    assert response.status_code == 501


def test_google_oauth_exchange_stores_the_tokens(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id", raising=False)
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret", raising=False)
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:3000/oauth/callback", raising=False)
    monkeypatch.setattr(settings, "supabase_service_role_key", "test-service-role-key", raising=False)

    fake_client = FakeHttpClient(
        post_response=FakeResponse(
            200,
            {"access_token": "goog-access", "refresh_token": "goog-refresh", "scope": "calendar", "expires_in": 3600},
        )
    )
    monkeypatch.setattr("app.api.v1.endpoints.auth.get_http_client", lambda: fake_client)
    monkeypatch.setattr("app.db.supabase.get_http_client", lambda: fake_client)

    response = authed_client.post(f"{V1}/auth/google/callback", json={"code": "abc123"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"connected": True, "scope": "calendar", "expires_in": 3600}

    # The refresh + access tokens are written with the service-role client, not the caller's.
    method, _url, kwargs = [c for c in fake_client.calls if c[0] == "PATCH"][0]
    payload = json.loads(kwargs["content"])
    assert payload == {"google_access_token": "goog-access", "google_refresh_token": "goog-refresh"}


def test_google_rejecting_the_code_is_upstream_error(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id", raising=False)
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret", raising=False)
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:3000/oauth/callback", raising=False)

    fake_client = FakeHttpClient(post_response=FakeResponse(400, {"error": "invalid_grant"}))
    monkeypatch.setattr("app.api.v1.endpoints.auth.get_http_client", lambda: fake_client)

    response = authed_client.post(f"{V1}/auth/google/callback", json={"code": "bad-code"})

    assert response.status_code == 502


def test_google_unreachable_is_upstream_error(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id", raising=False)
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret", raising=False)
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:3000/oauth/callback", raising=False)

    class UnreachableClient:
        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.api.v1.endpoints.auth.get_http_client", lambda: UnreachableClient())

    response = authed_client.post(f"{V1}/auth/google/callback", json={"code": "abc123"})

    assert response.status_code == 502


# --- GET /auth/google/authorize-url ---------------------------------------------------


def test_authorize_url_requests_offline_access_and_consent(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id", raising=False)
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:3000/oauth/callback", raising=False)

    response = authed_client.get(f"{V1}/auth/google/authorize-url")

    assert response.status_code == 200
    body = response.json()
    assert "access_type=offline" in body["authorize_url"]
    assert "prompt=consent" in body["authorize_url"]
    assert body["state"]


def test_authorize_url_not_configured_is_501(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "", raising=False)

    response = authed_client.get(f"{V1}/auth/google/authorize-url")

    assert response.status_code == 501


# --- DELETE /auth/google -------------------------------------------------------------


def test_disconnecting_google_clears_stored_tokens(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", "test-service-role-key", raising=False)
    fake_client = FakeHttpClient()
    monkeypatch.setattr("app.db.supabase.get_http_client", lambda: fake_client)

    response = authed_client.delete(f"{V1}/auth/google")

    assert response.status_code == 204
    method, _url, kwargs = fake_client.calls[-1]
    assert method == "PATCH"
    payload = json.loads(kwargs["content"])
    assert payload == {"google_access_token": None, "google_refresh_token": None}


def test_disconnecting_google_without_a_service_role_key_is_503(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_role_key", "", raising=False)

    response = authed_client.delete(f"{V1}/auth/google")

    assert response.status_code == 503
