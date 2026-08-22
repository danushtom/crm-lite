"""Core plumbing: error translation, pagination maths, middleware and rate-limit keying."""

from __future__ import annotations

import pytest

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
    UpstreamError,
)
from app.core.pagination import Page, PageParams
from app.core.rate_limit import rate_limit_key
from app.db.supabase import Result, _parse_content_range, _translate_error


# --- PostgREST error translation ---------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("23505", ConflictError),        # unique violation
        ("23503", ConflictError),        # foreign key violation
        ("23502", UnprocessableError),   # not-null violation
        ("23514", UnprocessableError),   # check violation
        ("22P02", UnprocessableError),   # invalid text representation
        ("42501", ForbiddenError),       # RLS violation
    ],
)
def test_postgres_error_codes_map_to_api_errors(code, expected):
    err = _translate_error(400, {"code": code, "message": "boom"}, "/leads")
    assert isinstance(err, expected)


def test_rls_violation_is_403_not_400():
    """PostgREST reports RLS denials with a 400; surfacing that as 400 misleads clients."""
    err = _translate_error(400, {"code": "42501", "message": "row-level security"}, "/leads")
    assert isinstance(err, ForbiddenError)
    assert err.status_code == 403


def test_unknown_upstream_failure_does_not_leak_details():
    err = _translate_error(500, {"code": "XX000", "message": "internal db path /var/lib/pg"}, "/leads")
    assert isinstance(err, UpstreamError)
    assert "var/lib" not in err.detail


def test_upstream_404_maps_to_not_found():
    assert isinstance(_translate_error(404, {}, "/leads"), NotFoundError)


# --- Content-Range parsing ----------------------------------------------------


@pytest.mark.parametrize(
    "header,expected",
    [
        ("0-24/231", 231),
        ("items 0-24/231", 231),
        ("0-0/1", 1),
        ("*/0", 0),
        ("0-24/*", None),   # count not requested
        (None, None),
        ("garbage", None),
        ("0-24/notanumber", None),
    ],
)
def test_content_range_parsing(header, expected):
    assert _parse_content_range(header) == expected


# --- Result helpers -----------------------------------------------------------


def test_result_one_raises_not_found_on_empty():
    with pytest.raises(NotFoundError):
        Result(data=[]).one("Lead")


def test_result_normalises_a_single_object_to_rows():
    assert Result(data={"id": "x"}).rows == [{"id": "x"}]


def test_result_first_is_none_when_empty():
    assert Result(data=None).first() is None


# --- Pagination ---------------------------------------------------------------


def test_has_more_uses_the_total_when_known():
    page = Page.build([1, 2, 3], PageParams(limit=3, offset=0), total=10)
    assert page.page.has_more is True
    assert page.page.total == 10


def test_has_more_is_false_on_the_final_page():
    page = Page.build([1, 2], PageParams(limit=3, offset=8), total=10)
    assert page.page.has_more is False


def test_has_more_is_inferred_from_a_full_page_without_a_count():
    assert Page.build([1, 2, 3], PageParams(limit=3, offset=0)).page.has_more is True
    assert Page.build([1, 2], PageParams(limit=3, offset=0)).page.has_more is False


def test_empty_page_reports_no_more():
    page = Page.build([], PageParams(limit=50, offset=0), total=0)
    assert page.page.has_more is False
    assert page.items == []


# --- Rate-limit keying --------------------------------------------------------


class _FakeRequest:
    def __init__(self, headers=None, user=None, client_host="1.2.3.4"):
        self.headers = headers or {}
        self.state = type("S", (), {})()
        if user is not None:
            self.state.user = user
        self.client = type("C", (), {"host": client_host})()
        self.scope = {"client": (client_host, 1234), "headers": []}


def test_authenticated_requests_key_by_user():
    user = type("U", (), {"sub": "user-9"})()
    assert rate_limit_key(_FakeRequest(user=user)) == "user:user-9"


def test_bearer_token_is_hashed_not_stored_verbatim():
    """The limiter's key ends up in storage and logs; raw credentials must not."""
    token = "secret-access-token"
    key = rate_limit_key(_FakeRequest(headers={"authorization": f"Bearer {token}"}))
    assert key.startswith("token:")
    assert token not in key


def test_same_token_yields_a_stable_bucket():
    req = lambda: _FakeRequest(headers={"authorization": "Bearer abc"})  # noqa: E731
    assert rate_limit_key(req()) == rate_limit_key(req())


def test_different_tokens_get_different_buckets():
    a = rate_limit_key(_FakeRequest(headers={"authorization": "Bearer aaa"}))
    b = rate_limit_key(_FakeRequest(headers={"authorization": "Bearer bbb"}))
    assert a != b


def test_anonymous_requests_fall_back_to_ip():
    assert rate_limit_key(_FakeRequest()).startswith("ip:")


# --- Middleware ---------------------------------------------------------------


def test_probes_are_exempt_from_rate_limiting(client):
    """An orchestrator that receives a 429 on a probe will cycle the instance."""
    for _ in range(30):
        assert client.get("/health/live").status_code == 200


def test_oversized_body_is_rejected_with_problem_details(client):
    from app.core.config import settings

    response = client.post(
        "/api/v1/companies",
        content=b"x",
        headers={
            "Content-Length": str(settings.max_upload_bytes + 1),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_request_id_reaches_the_access_log(client, caplog):
    """The id must still be set when the access line is emitted, not reset beforehand."""
    import logging

    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/", headers={"X-Request-ID": "corr-42"})

    access_records = [r for r in caplog.records if r.name == "app.access"]
    assert access_records, "expected an access log record"
    assert getattr(access_records[-1], "request_id", None) == "corr-42"


def test_client_supplied_request_id_is_truncated(client):
    response = client.get("/health", headers={"X-Request-ID": "A" * 500})
    assert len(response.headers["X-Request-ID"]) <= 64


def test_probe_requests_are_not_access_logged(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/health")
    assert not [r for r in caplog.records if r.name == "app.access"]
