"""Shared test fixtures."""

from __future__ import annotations

import time
from typing import Any, Iterator

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import settings
from app.core.security import TokenUser
from app.db.supabase import SupabaseClient
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """TestClient as a context manager so the lifespan (HTTP pool) actually runs."""
    with TestClient(app) as test_client:
        yield test_client


class FakeResult:
    """Stand-in for :class:`app.db.supabase.Result`."""

    def __init__(self, data: Any = None, count: int | None = None):
        self.data = data
        self.count = count

    @property
    def rows(self) -> list[dict[str, Any]]:
        if isinstance(self.data, list):
            return self.data
        if self.data is None:
            return []
        return [self.data]

    def first(self) -> dict[str, Any] | None:
        rows = self.rows
        return rows[0] if rows else None

    def one(self, what: str = "Resource") -> dict[str, Any]:
        row = self.first()
        if row is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"{what} not found")
        return row


class FakeDb:
    """Records calls and replays queued responses, so endpoints can be tested without Supabase."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _resolve(self, key: str) -> FakeResult:
        value = self.responses.get(key)
        if isinstance(value, FakeResult):
            return value
        return FakeResult(value)

    async def request(self, method: str, path: str, **kwargs: Any) -> FakeResult:
        self.calls.append((method, path, kwargs))
        return self._resolve(f"{method} {path}")

    async def select(self, table: str, *, params=None, count=False) -> FakeResult:
        self.calls.append(("GET", table, {"params": params, "count": count}))
        return self._resolve(f"GET {table}")

    async def select_one(self, table: str, *, params=None, what=None) -> dict[str, Any]:
        return (await self.select(table, params=params)).one(what or table)

    async def insert(self, table: str, payload: Any) -> FakeResult:
        self.calls.append(("POST", table, {"payload": payload}))
        return self._resolve(f"POST {table}")

    async def update(self, table: str, params: dict[str, str], payload: Any) -> FakeResult:
        self.calls.append(("PATCH", table, {"params": params, "payload": payload}))
        return self._resolve(f"PATCH {table}")

    async def update_counting(self, table: str, params: dict[str, str], payload: Any) -> int:
        self.calls.append(("PATCH", table, {"params": params, "payload": payload}))
        result = self._resolve(f"PATCH {table}")
        # Mirrors the real client: the row count, not the rows.
        return result.count if result.count is not None else len(result.rows)

    async def delete(self, table: str, params: dict[str, str]) -> FakeResult:
        self.calls.append(("DELETE", table, {"params": params}))
        return self._resolve(f"DELETE {table}")

    async def rpc(self, function: str, payload: Any = None) -> FakeResult:
        self.calls.append(("POST", f"rpc/{function}", {"payload": payload}))
        return self._resolve(f"RPC {function}")


@pytest.fixture
def fake_db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def test_user() -> TokenUser:
    return TokenUser(sub="11111111-2222-3333-4444-555555555555", email="agent@example.com")


@pytest.fixture
def authed_client(app, fake_db, test_user) -> Iterator[TestClient]:
    """Client with auth and the database dependency replaced by in-memory fakes.

    ``get_admin_db`` shares the same fake as ``get_db`` -- good enough for testing the shape of
    what a service-role code path writes/reads, without a real SupabaseAdminClient touching the
    network. Endpoints that construct ``SupabaseAdminClient()`` directly (bypassing the
    dependency) are unaffected by this and need their own httpx-level mocking instead -- see
    test_auth_endpoints.py's FakeHttpClient for that pattern.
    """
    app.dependency_overrides[deps.get_current_user] = lambda: test_user
    app.dependency_overrides[deps.get_access_token] = lambda: "test-token"
    app.dependency_overrides[deps.get_db] = lambda: fake_db
    app.dependency_overrides[deps.get_admin_db] = lambda: fake_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_token(secret: str = "test-secret-at-least-32-bytes-long!!", **claims: Any) -> str:
    """Build an HS256 token carrying valid default claims."""
    now = int(time.time())
    payload = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "email": "agent@example.com",
        "aud": "authenticated",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + 3600,
    }
    payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


__all__ = ["FakeDb", "FakeResult", "SupabaseClient", "make_token"]
