"""Contract-level guarantees: versioning, documentation, error shape and pagination.

These assert the conventions the API promises, so a regression in any of them fails CI
rather than reaching a client.
"""

from __future__ import annotations

import pytest

from app.core.config import API_V1_PREFIX

UNVERSIONED_ALLOWED = {"/", "/health", "/health/live", "/health/ready"}


def test_service_root_advertises_versions(client):
    body = client.get("/").json()
    assert body["service"] == "dracara-growth-os-api"
    assert "v1" in body["api_versions"]


def test_health_endpoints_are_unversioned(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/live").json() == {"live": True}


def test_every_resource_route_is_versioned(app):
    unversioned = [
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/")
        and not route.path.startswith(API_V1_PREFIX)
        and route.path not in UNVERSIONED_ALLOWED
        and route.path not in {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}
    ]
    assert unversioned == [], f"routes outside {API_V1_PREFIX}: {unversioned}"


def test_openapi_documents_metadata(client):
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"]
    assert spec["info"]["version"]
    assert spec["info"]["description"]
    assert {tag["name"] for tag in spec["tags"]} >= {"Leads", "Opportunities", "Health"}


def test_every_operation_declares_a_summary_and_success_schema(client):
    """An endpoint with no declared response model produces a useless client SDK."""
    spec = client.get("/openapi.json").json()
    missing_summary: list[str] = []
    missing_schema: list[str] = []

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            label = f"{method.upper()} {path}"
            if not operation.get("summary"):
                missing_summary.append(label)

            success = [c for c in operation.get("responses", {}) if c.startswith("2")]
            assert success, f"{label} declares no success response"
            # 204 legitimately has no body.
            if success == ["204"]:
                continue
            content = operation["responses"][success[0]].get("content", {})
            schema = content.get("application/json", {}).get("schema")
            if not schema:
                missing_schema.append(label)

    assert not missing_summary, f"operations without a summary: {missing_summary}"
    assert not missing_schema, f"operations without a response schema: {missing_schema}"


def test_protected_routes_declare_security(client):
    """Every non-probe operation must advertise the bearer scheme in the schema."""
    spec = client.get("/openapi.json").json()
    unsecured = []
    for path, operations in spec["paths"].items():
        if path in UNVERSIONED_ALLOWED:
            continue
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            if not operation.get("security"):
                unsecured.append(f"{method.upper()} {path}")
    assert unsecured == [], f"operations missing a security requirement: {unsecured}"


@pytest.mark.parametrize(
    "path",
    [f"{API_V1_PREFIX}/leads", f"{API_V1_PREFIX}/companies", f"{API_V1_PREFIX}/contacts"],
)
def test_missing_token_returns_problem_details(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")

    body = response.json()
    assert body["status"] == 401
    assert body["code"] == "unauthorized"
    assert body["instance"] == path
    assert body["type"].endswith("/unauthorized")
    assert body["request_id"]


def test_request_id_is_echoed_when_supplied(client):
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_request_id_is_generated_when_absent(client):
    response = client.get("/health")
    assert response.headers["X-Request-ID"]
    assert response.headers["X-API-Version"] == "v1"


def test_validation_failure_lists_offending_fields(authed_client):
    response = authed_client.post(f"{API_V1_PREFIX}/companies", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unprocessable_entity"
    assert any(err["field"] == "name" for err in body["errors"])


def test_unknown_request_field_is_rejected(authed_client):
    response = authed_client.post(
        f"{API_V1_PREFIX}/companies", json={"name": "Acme", "nmae": "typo"}
    )
    assert response.status_code == 422


def test_invalid_enum_value_is_rejected_at_the_edge(authed_client):
    """Bad enums must 422 at the boundary, not reach Postgres and surface as a 500."""
    response = authed_client.get(f"{API_V1_PREFIX}/leads", params={"stage": "not_a_stage"})
    assert response.status_code == 422


def test_pagination_limit_is_capped(authed_client):
    response = authed_client.get(f"{API_V1_PREFIX}/leads", params={"limit": 5000})
    assert response.status_code == 422


def test_security_headers_are_present(client):
    headers = client.get("/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_every_list_orders_by_a_unique_tiebreaker():
    """OFFSET pagination over a non-unique sort key is non-deterministic.

    Rows sharing the sort value can be returned on two consecutive pages, or skipped
    entirely. Any batch UPDATE gives many rows an identical updated_at, so this is not
    hypothetical -- it is just invisible until the data makes it visible.
    """
    import pathlib
    import re

    endpoints = pathlib.Path("app/api/v1/endpoints")
    offenders = []
    for module in endpoints.glob("*.py"):
        for match in re.finditer(r'"order":\s*"([^"]+)"', module.read_text(encoding="utf-8")):
            clause = match.group(1)
            if not clause.split(",")[-1].startswith("id."):
                offenders.append(f"{module.name}: {clause}")

    assert offenders == [], f"ordering without a unique tiebreaker: {offenders}"
