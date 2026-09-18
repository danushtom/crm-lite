"""The assistant's read-only CRM readers.

The security claim these tests protect: the assistant reads through the *caller's* RLS-scoped
client, so it can never see a row the caller could not open in the UI, and no argument the model
supplies can widen that. If someone later swaps `db` for the admin client, or adds a write tool,
these fail.
"""

from __future__ import annotations

import pytest

from app.services.ai import assistant_tools
from tests.conftest import FakeDb, FakeResult


def _tools(fake_db):
    return {t.name: t for t in assistant_tools.build_tools(fake_db)}


# --- Read-only by construction ---------------------------------------------------


@pytest.mark.asyncio
async def test_no_tool_writes_to_the_database(fake_db: FakeDb):
    """Every tool runs; none of them may produce a POST, PATCH or DELETE."""
    fake_db.responses["GET leads"] = FakeResult([{"id": "lead-1"}])
    fake_db.responses["GET opportunities"] = FakeResult([{"id": "opp-1", "stage": "negotiation"}])
    fake_db.responses["GET tasks"] = FakeResult([])
    fake_db.responses["GET activities"] = FakeResult([])
    fake_db.responses["GET calls"] = FakeResult([])
    fake_db.responses["GET lead_intelligence"] = FakeResult(None)
    fake_db.responses["GET deal_health_snapshots"] = FakeResult(None)

    for tool in assistant_tools.build_tools(fake_db):
        await tool.fn({"lead_id": "lead-1", "opportunity_id": "opp-1"})

    assert [c for c in fake_db.calls if c[0] != "GET"] == []


def test_the_tool_set_exposes_no_mutating_verb():
    """A guard against a future 'just let it update the stage' tool arriving without its own
    permission check and a human pressing a button."""
    names = {t.name for t in assistant_tools.build_tools(FakeDb())}
    forbidden = ("create", "update", "delete", "set_", "send", "place_call")
    assert not [n for n in names if n.startswith(forbidden)]


# --- Scoping comes from the connection, not from arguments ------------------------


@pytest.mark.asyncio
async def test_no_tool_accepts_an_organization_argument(fake_db: FakeDb):
    """Unlike voice_tools, there is no org id to pass here -- the connection carries it. A tool
    declaring one would mean someone had reintroduced a way to ask for another tenant."""
    for tool in assistant_tools.build_tools(fake_db):
        assert "organization_id" not in tool.parameters.get("properties", {})


@pytest.mark.asyncio
async def test_an_injected_organization_argument_is_simply_ignored(fake_db: FakeDb):
    fake_db.responses["GET leads"] = FakeResult([{"id": "lead-1"}])

    await _tools(fake_db)["search_leads"].fn({"organization_id": "someone-elses-org"})

    params = [c for c in fake_db.calls if c[1] == "leads"][0][2]["params"]
    assert "organization_id" not in params


@pytest.mark.asyncio
async def test_an_invisible_lead_is_reported_as_not_visible_not_as_forbidden(fake_db: FakeDb):
    """RLS returns nothing for a lead in another organization. The wording must not let the model
    distinguish 'does not exist' from 'exists but is not yours'."""
    fake_db.responses["GET leads"] = FakeResult(None)

    result = await _tools(fake_db)["get_lead"].fn({"lead_id": "lead-in-another-org"})

    assert result == {"error": "No lead with that id is visible to you"}


# --- Input handling ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_search_term_cannot_break_out_of_its_filter(fake_db: FakeDb):
    """PostgREST reads `,` `.` `(` `)` `*` as filter syntax, so a term carrying them could change
    what the filter means. RLS still bounds the result, but a filter that does not mean what it
    says is a bug regardless."""
    fake_db.responses["GET leads"] = FakeResult([])

    await _tools(fake_db)["search_leads"].fn({"company_name": "Acme*,id.eq.(evil)"})

    params = [c for c in fake_db.calls if c[1] == "leads"][0][2]["params"]
    # Every syntax character is stripped; only the letters survive.
    assert params["companies.name"] == "ilike.*Acmeideqevil*"


@pytest.mark.asyncio
async def test_a_model_supplied_limit_is_clamped(fake_db: FakeDb):
    """A model asking for 10,000 rows would blow the context window and read most of a table."""
    fake_db.responses["GET leads"] = FakeResult([])

    await _tools(fake_db)["search_leads"].fn({"limit": 10_000})

    params = [c for c in fake_db.calls if c[1] == "leads"][0][2]["params"]
    assert params["limit"] == str(assistant_tools.MAX_ROWS)


@pytest.mark.asyncio
async def test_a_nonsense_limit_falls_back_to_the_default(fake_db: FakeDb):
    fake_db.responses["GET tasks"] = FakeResult([])

    await _tools(fake_db)["list_tasks"].fn({"limit": "lots please"})

    params = [c for c in fake_db.calls if c[1] == "tasks"][0][2]["params"]
    assert params["limit"] == "10"


@pytest.mark.asyncio
async def test_an_unknown_task_status_falls_back_to_pending(fake_db: FakeDb):
    fake_db.responses["GET tasks"] = FakeResult([])

    await _tools(fake_db)["list_tasks"].fn({"status": "eq.anything.or.(1=1)"})

    params = [c for c in fake_db.calls if c[1] == "tasks"][0][2]["params"]
    assert params["status"] == "eq.pending"


# --- Aggregation ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_summary_groups_by_stage(fake_db: FakeDb):
    fake_db.responses["GET opportunities"] = FakeResult(
        [
            {"stage": "negotiation", "quoted_value": 100, "priority_score": 80},
            {"stage": "negotiation", "quoted_value": 200, "priority_score": 60},
            {"stage": "prospect", "quoted_value": 50, "priority_score": 20},
        ]
    )

    result = await _tools(fake_db)["get_pipeline_summary"].fn({})

    negotiation = next(s for s in result["stages"] if s["stage"] == "negotiation")
    assert negotiation == {
        "stage": "negotiation",
        "count": 2,
        "total_value": 300.0,
        "average_score": 70.0,
    }
    assert result["total_open_deals"] == 3
    assert result["total_open_value"] == 350.0
