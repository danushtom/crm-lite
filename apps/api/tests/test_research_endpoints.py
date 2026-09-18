"""Company research and pre-call brief endpoints.

The property that matters most: a company or lead the caller cannot see is a 404 *before* anything
is sent to the search provider. Otherwise research would leak which companies another tenant is
pursuing -- by name, to a third party -- and bill the wrong organization for it.
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import API_V1_PREFIX as V1
from app.core.config import settings
from app.services.ai import research as research_service
from tests.conftest import FakeResult

AGENT_ROLE = {
    "id": "role-agent-1",
    "name": "Agent",
    "grants_full_access": False,
    "role_permissions": [{"permissions": {"resource": "ai", "action": "read"}}],
}
PARTNER_ROLE = {
    "id": "role-partner-1",
    "name": "Partner",
    "grants_full_access": False,
    "role_permissions": [{"permissions": {"resource": "leads", "action": "read"}}],
}
COMPANY = {
    "id": "co-1",
    "name": "Acme Robotics",
    "website": "https://acme.io",
    "industry": None,
    "size": "11-50",
    "segment": None,
    "location": None,
    "linkedin_url": None,
    "version": 3,
}


def _as(fake_db, test_user, role=AGENT_ROLE):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": role["id"], "is_active": True, "roles": role, "organization_id": "org-1"}]
    )


@pytest.fixture
def research_on(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "exa_api_key", "exa-test")
    monkeypatch.setattr(settings, "ai_monthly_token_budget", 0)


@pytest.fixture
def searches(monkeypatch):
    """Record every call into the research graph -- i.e. every time something would be sent to
    the search provider."""
    from dracara_ai.graphs import research as graph

    calls: list[dict] = []

    async def fake_research_company(**kwargs):
        calls.append(kwargs)
        profile = graph.CompanyProfile(
            industry=graph.CitedFact(value="Robotics", source_url="https://acme.io/about"),
            size=graph.CitedFact(value="51-200", source_url="https://acme.io/about"),
            sources=[graph.Source(index=1, title="About", url="https://acme.io/about")],
        )
        from dracara_ai.usage import UsageRecord

        return profile, UsageRecord(feature="company_research", model="gpt-4o-mini", prompt_tokens=10)

    monkeypatch.setattr(graph, "research_company", fake_research_company)
    return calls


# --- Access is proven before anything is searched --------------------------------


def test_an_invisible_company_is_a_404_and_nothing_is_searched(
    authed_client, fake_db, test_user, research_on, searches
):
    _as(fake_db, test_user)
    fake_db.responses["GET companies"] = FakeResult(None)  # RLS returned nothing

    response = authed_client.post(f"{V1}/ai/companies/someone-elses-company/research", json={})

    assert response.status_code == 404
    assert searches == []


def test_only_the_name_and_website_reach_the_search_step(
    authed_client, fake_db, test_user, research_on, searches
):
    _as(fake_db, test_user)
    fake_db.responses["GET companies"] = FakeResult([COMPANY])
    fake_db.responses["GET company_research"] = FakeResult(None)
    fake_db.responses["POST company_research"] = FakeResult(
        [{"id": "r-1", "profile": {}, "created_at": "2026-09-18T00:00:00Z"}]
    )

    response = authed_client.post(f"{V1}/ai/companies/co-1/research", json={})

    assert response.status_code == 200, response.text
    assert searches == [{"company_name": "Acme Robotics", "website": "https://acme.io"}]


def test_research_is_stored_with_the_service_role_and_never_edits_the_company(
    authed_client, fake_db, test_user, research_on, searches
):
    _as(fake_db, test_user)
    fake_db.responses["GET companies"] = FakeResult([COMPANY])
    fake_db.responses["GET company_research"] = FakeResult(None)
    fake_db.responses["POST company_research"] = FakeResult(
        [{"id": "r-1", "profile": {}, "created_at": "2026-09-18T00:00:00Z"}]
    )

    authed_client.post(f"{V1}/ai/companies/co-1/research", json={})

    assert not [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "companies"]
    insert = [c for c in fake_db.calls if c[0] == "POST" and c[1] == "company_research"][0][2]["payload"]
    # The org is derived by trigger from the company; the payload does not assert one.
    assert "organization_id" not in insert


def test_suggestions_fill_blanks_and_flag_overwrites(authed_client, fake_db, test_user, research_on, searches):
    _as(fake_db, test_user)
    fake_db.responses["GET companies"] = FakeResult([COMPANY])
    fake_db.responses["GET company_research"] = FakeResult(None)
    fake_db.responses["POST company_research"] = FakeResult(
        [{"id": "r-1", "profile": {}, "created_at": "2026-09-18T00:00:00Z"}]
    )

    body = authed_client.post(f"{V1}/ai/companies/co-1/research", json={}).json()

    # The stored row's profile is what's returned; the fake stores {} so re-derive directly.
    from dracara_ai.graphs import research as graph

    profile = graph.CompanyProfile(
        industry=graph.CitedFact(value="Robotics", source_url="https://acme.io/about"),
        size=graph.CitedFact(value="51-200", source_url="https://acme.io/about"),
    )
    s = {x["field"]: x for x in research_service.suggestions(COMPANY, profile)}
    assert s["industry"]["overwrites"] is False  # was blank
    assert s["size"]["overwrites"] is True  # "11-50" was typed by a person
    assert body["company_version"] == 3  # handed back for If-Match on the PATCH


def test_recent_research_is_served_without_searching_again(
    authed_client, fake_db, test_user, research_on, searches
):
    _as(fake_db, test_user)
    fake_db.responses["GET companies"] = FakeResult([COMPANY])
    fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    fake_db.responses["GET company_research"] = FakeResult(
        [{"id": "r-old", "profile": {}, "created_at": fresh}]
    )

    body = authed_client.post(f"{V1}/ai/companies/co-1/research", json={}).json()

    assert body["from_cache"] is True
    assert searches == []


def test_force_re_runs_research_even_when_recent(authed_client, fake_db, test_user, research_on, searches):
    _as(fake_db, test_user)
    fake_db.responses["GET companies"] = FakeResult([COMPANY])
    fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    fake_db.responses["GET company_research"] = FakeResult([{"id": "r-old", "profile": {}, "created_at": fresh}])
    fake_db.responses["POST company_research"] = FakeResult(
        [{"id": "r-new", "profile": {}, "created_at": fresh}]
    )

    authed_client.post(f"{V1}/ai/companies/co-1/research", json={"force": True})

    assert len(searches) == 1


def test_an_invisible_lead_gets_no_brief_and_nothing_is_searched(
    authed_client, fake_db, test_user, research_on, searches
):
    _as(fake_db, test_user)
    fake_db.responses["GET leads"] = FakeResult(None)

    response = authed_client.post(f"{V1}/ai/leads/someone-elses-lead/brief")

    assert response.status_code == 404
    assert searches == []


# --- Gates ------------------------------------------------------------------------


def test_research_needs_the_ai_read_permission(authed_client, fake_db, test_user, research_on, searches):
    _as(fake_db, test_user, PARTNER_ROLE)

    response = authed_client.post(f"{V1}/ai/companies/co-1/research", json={})

    assert response.status_code == 403
    assert searches == []


def test_research_reports_not_configured_without_an_exa_key(
    authed_client, fake_db, test_user, research_on, monkeypatch
):
    monkeypatch.setattr(settings, "exa_api_key", "")
    _as(fake_db, test_user)

    response = authed_client.post(f"{V1}/ai/companies/co-1/research", json={})

    assert response.status_code == 501


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", f"{V1}/ai/companies/co-1/research"),
        ("get", f"{V1}/ai/companies/co-1/research"),
        ("post", f"{V1}/ai/leads/lead-1/brief"),
        ("get", f"{V1}/ai/leads/lead-1/brief"),
    ],
)
def test_research_endpoints_reject_an_anonymous_caller(client, method, path):
    response = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert response.status_code == 401


# --- The SQL side ---------------------------------------------------------------------

MIGRATION = pathlib.Path("../../supabase/migrations/20260918010000_ai_research.sql")


def test_research_tables_accept_no_writes_from_users():
    """A user who could write here could plant 'sourced' text and links a colleague would trust."""
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("company_research", "lead_briefs"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        for verb in ("INSERT", "UPDATE", "DELETE"):
            assert not re.search(rf"CREATE POLICY \w+ ON public\.{table} FOR {verb}", sql)


def test_research_tables_derive_their_organization():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "set_parent_organization('companies', 'company_id')" in sql
    assert "set_parent_organization('leads', 'lead_id')" in sql


def test_brief_visibility_goes_through_the_lead_chokepoint():
    """A brief contains CRM facts, so it is exactly as private as the lead."""
    sql = MIGRATION.read_text(encoding="utf-8")
    policy = re.search(r"CREATE POLICY lead_briefs_select.*?;\n", sql, re.S).group(0)
    assert "current_org_id(auth.uid())" in policy
    assert "can_access_lead(auth.uid(), lead_briefs.lead_id)" in policy
