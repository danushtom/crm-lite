"""Mid-call tools invoked from the voice platform's tool-call webhook.

Every tool must scope its writes/reads by the resolved org_id -- these are the only functions
in the codebase that act on arguments an LLM generated, not on validated request bodies.
`book_appointment` is the one that previously trusted `owner_id`/`lead_id` straight from those
arguments; the tests below pin down that it now validates both against org_id first.
"""

from __future__ import annotations

import pytest

from dracara_ai import voice_script

from app.services import voice_tools
from tests.conftest import FakeDb, FakeResult

ORG_ID = "org-1"
OTHER_ORG_ID = "org-2"
AGENT_ID = "va-real"


@pytest.fixture(autouse=True)
def _agent_allows_everything(fake_db: FakeDb):
    """dispatch() reads the agent's data-access policy before running a tool. These tests are
    about each tool's own org scoping, so the policy is wide open here; the policy gate itself
    is tested separately below."""
    fake_db.responses["GET voice_agents"] = FakeResult(
        {
            "data_access": {
                "tools": {name: True for name in voice_tools.TOOLS},
                "lead_fields": list(voice_script.LEAD_FIELDS),
            }
        }
    )


@pytest.mark.asyncio
async def test_check_consent_scopes_the_query_by_org(fake_db: FakeDb):
    fake_db.responses["GET contacts"] = FakeResult({"ai_call_consent": True})

    result = await voice_tools.dispatch("check_consent", ORG_ID, {"contact_id": "c-1"}, fake_db, voice_agent_id=AGENT_ID)

    assert result == {"consented": True}
    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "contacts"][0][2]["params"]
    assert params["organization_id"] == f"eq.{ORG_ID}"


@pytest.mark.asyncio
async def test_get_lead_context_rejects_a_lead_from_another_org(fake_db: FakeDb):
    fake_db.responses["GET leads"] = FakeResult({"id": "lead-1", "organization_id": OTHER_ORG_ID})

    result = await voice_tools.dispatch("get_lead_context", ORG_ID, {"lead_id": "lead-1"}, fake_db, voice_agent_id=AGENT_ID)

    assert result == {"error": "lead not found"}


@pytest.mark.asyncio
async def test_update_deal_stage_rejects_an_opportunity_from_another_org(fake_db: FakeDb):
    fake_db.responses["GET opportunities"] = FakeResult(None)

    result = await voice_tools.dispatch(
        "update_deal_stage",
        ORG_ID,
        {"opportunity_id": "opp-1", "stage": "won"},
        fake_db,
        voice_agent_id=AGENT_ID,
    )

    assert result == {"error": "opportunity not found"}
    assert not [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "opportunities"]


@pytest.mark.asyncio
async def test_book_appointment_rejects_a_lead_from_another_org(fake_db: FakeDb):
    fake_db.responses["GET leads"] = FakeResult({"owner_id": "u-1", "organization_id": OTHER_ORG_ID})

    result = await voice_tools.dispatch(
        "book_appointment",
        ORG_ID,
        {"lead_id": "lead-1", "scheduled_at": "2026-09-10T10:00:00Z"},
        fake_db,
        voice_agent_id=AGENT_ID,
    )

    assert result == {"error": "lead not found"}
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "meetings"]


@pytest.mark.asyncio
async def test_book_appointment_derives_owner_from_the_lead_not_the_argument(fake_db: FakeDb):
    """owner_id must come from CRM data, never straight from the tool-call arguments -- an
    LLM-hallucinated owner_id would otherwise create a meeting for an arbitrary user."""
    fake_db.responses["GET leads"] = FakeResult({"owner_id": "real-owner", "organization_id": ORG_ID})
    fake_db.responses["POST meetings"] = FakeResult({"id": "m-1"})

    await voice_tools.dispatch(
        "book_appointment",
        ORG_ID,
        {"lead_id": "lead-1", "owner_id": "attacker-supplied-owner", "scheduled_at": "2026-09-10T10:00:00Z"},
        fake_db,
        voice_agent_id=AGENT_ID,
    )

    payload = [c for c in fake_db.calls if c[0] == "POST" and c[1] == "meetings"][0][2]["payload"]
    assert payload["owner_id"] == "real-owner"


@pytest.mark.asyncio
async def test_book_appointment_without_a_lead_requires_a_valid_org_member_as_owner(fake_db: FakeDb):
    fake_db.responses["GET users"] = FakeResult(None)  # not a member of this org

    result = await voice_tools.dispatch(
        "book_appointment",
        ORG_ID,
        {"owner_id": "not-a-member", "scheduled_at": "2026-09-10T10:00:00Z"},
        fake_db,
        voice_agent_id=AGENT_ID,
    )

    assert result == {"error": "owner not found in this organization"}
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "meetings"]


@pytest.mark.asyncio
async def test_unknown_tool_name_is_reported_not_raised(fake_db: FakeDb):
    result = await voice_tools.dispatch("delete_everything", ORG_ID, {}, fake_db, voice_agent_id=AGENT_ID)
    assert "error" in result


# --- search_knowledge_base ------------------------------------------------------------
#
# The knowledge-base tool is the one that reaches a store with no row-level security behind it,
# so it has one extra obligation the others do not: neither scoping argument may originate from
# the model's tool-call arguments. org_id comes from the webhook's resolved call; voice_agent_id
# is read back off the `calls` row here.


@pytest.mark.asyncio
async def test_search_knowledge_base_takes_the_agent_from_the_call_not_the_arguments(
    fake_db: FakeDb, monkeypatch
):
    fake_db.responses["GET calls"] = FakeResult({"voice_agent_id": "va-real"})
    captured: dict = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return [{"text": "MVP from 5,00,000 INR", "source": "pricing.pdf", "relevance": 0.9}]

    monkeypatch.setattr(voice_tools.knowledge_base, "search", fake_search)

    result = await voice_tools.dispatch(
        "search_knowledge_base",
        ORG_ID,
        {
            "call_id": "call-1",
            "query": "what does an MVP cost",
            # A hallucinated or injected agent id, which must be ignored entirely.
            "voice_agent_id": "va-belonging-to-someone-else",
            "organization_id": OTHER_ORG_ID,
        },
        fake_db,
        voice_agent_id=AGENT_ID,
    )

    assert captured["organization_id"] == ORG_ID
    assert captured["voice_agent_id"] == "va-real"
    assert result["passages"][0]["source"] == "pricing.pdf"


@pytest.mark.asyncio
async def test_search_knowledge_base_scopes_the_call_lookup_by_org(fake_db: FakeDb, monkeypatch):
    fake_db.responses["GET calls"] = FakeResult(None)

    result = await voice_tools.dispatch(
        "search_knowledge_base", ORG_ID, {"call_id": "call-from-another-org", "query": "pricing"}, fake_db
    )

    assert result == {"error": "call not found"}
    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "calls"][0][2]["params"]
    assert params["organization_id"] == f"eq.{ORG_ID}"


@pytest.mark.asyncio
async def test_search_knowledge_base_tells_the_agent_not_to_guess_when_nothing_matches(
    fake_db: FakeDb, monkeypatch
):
    """Mid-call, an empty result is the moment an LLM is most likely to invent a price."""
    fake_db.responses["GET calls"] = FakeResult({"voice_agent_id": "va-1"})

    async def empty(**_kwargs):
        return []

    monkeypatch.setattr(voice_tools.knowledge_base, "search", empty)

    result = await voice_tools.dispatch(
        "search_knowledge_base", ORG_ID, {"call_id": "call-1", "query": "discounts"}, fake_db
    )

    assert result["passages"] == []
    assert "Do not guess" in result["note"]


@pytest.mark.asyncio
async def test_search_knowledge_base_degrades_instead_of_failing_the_live_call(
    fake_db: FakeDb, monkeypatch
):
    """A vector store outage must not leave the agent silent on a live phone line."""
    from dracara_ai.errors import AiUpstreamError

    fake_db.responses["GET calls"] = FakeResult({"voice_agent_id": "va-1"})

    async def broken(**_kwargs):
        raise AiUpstreamError("qdrant unreachable")

    monkeypatch.setattr(voice_tools.knowledge_base, "search", broken)

    result = await voice_tools.dispatch(
        "search_knowledge_base", ORG_ID, {"call_id": "call-1", "query": "pricing"}, fake_db
    )

    assert result["passages"] == []
    assert "unavailable" in result["note"]


def test_every_dispatchable_tool_is_declared_to_the_platform():
    """The dispatcher and the assistant's declared tool list are two halves of one bridge. A tool
    added to only one half is either never callable or fails when called -- which is exactly the
    state the whole feature was in before TOOL_DEFINITIONS existed."""
    from app.services.voice_platform import TOOL_DEFINITIONS

    declared = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert declared == set(voice_tools.TOOLS)


def test_no_declared_tool_asks_the_model_for_a_call_id():
    """call_id is injected by the webhook from the resolved call row. Declaring it would invite
    the model to supply a pointer into another organization's data."""
    from app.services.voice_platform import TOOL_DEFINITIONS

    for tool in TOOL_DEFINITIONS:
        properties = tool["function"]["parameters"].get("properties", {})
        assert "call_id" not in properties, tool["function"]["name"]
        assert "organization_id" not in properties, tool["function"]["name"]


# --- The data-access policy ---------------------------------------------------------------
#
# An organization decides which CRM data and which actions its agent gets. The declarations
# sent to the voice platform are advisory -- a tool call can arrive for a tool that was never
# declared -- so these assert the dispatcher refuses the work, not just that it was not offered.


def _policy(fake_db: FakeDb, **tools: bool) -> None:
    fake_db.responses["GET voice_agents"] = FakeResult(
        {"data_access": {"tools": tools, "lead_fields": []}}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments", "table"),
    [
        ("book_appointment", {"lead_id": "lead-1", "scheduled_at": "2026-09-10T10:00:00Z"}, "meetings"),
        ("update_deal_stage", {"opportunity_id": "opp-1", "stage": "won"}, "opportunities"),
    ],
)
async def test_a_switched_off_write_tool_is_refused_before_it_writes(
    fake_db: FakeDb, tool, arguments, table
):
    _policy(fake_db, book_appointment=False, update_deal_stage=False)
    fake_db.responses["GET leads"] = FakeResult({"owner_id": "u-1", "organization_id": ORG_ID})
    fake_db.responses["GET opportunities"] = FakeResult({"id": "opp-1"})

    result = await voice_tools.dispatch(tool, ORG_ID, arguments, fake_db, voice_agent_id=AGENT_ID)

    assert "not enabled" in result["error"]
    # It is told what to say instead, so it offers a callback rather than claiming it booked.
    assert "callback" in result["note"]
    assert not [c for c in fake_db.calls if c[0] in ("POST", "PATCH") and c[1] == table]


@pytest.mark.asyncio
async def test_a_policy_lookup_is_scoped_to_the_resolved_organization(fake_db: FakeDb):
    """The policy decides what the agent may do, so reading it with an unscoped id would let a
    call in one organization be governed by another organization's agent."""
    await voice_tools.dispatch("log_call_outcome", ORG_ID, {"call_id": "c", "outcome": "x"}, fake_db, voice_agent_id=AGENT_ID)

    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "voice_agents"][0][2]["params"]
    assert params["id"] == f"eq.{AGENT_ID}"
    assert params["organization_id"] == f"eq.{ORG_ID}"


@pytest.mark.asyncio
async def test_an_agent_with_no_policy_does_not_get_the_write_tools(fake_db: FakeDb):
    """A missing policy row must not be a privilege escalation."""
    fake_db.responses["GET voice_agents"] = FakeResult(None)
    fake_db.responses["GET leads"] = FakeResult({"owner_id": "u-1", "organization_id": ORG_ID})

    result = await voice_tools.dispatch(
        "book_appointment",
        ORG_ID,
        {"lead_id": "lead-1", "scheduled_at": "2026-09-10T10:00:00Z"},
        fake_db,
        voice_agent_id=AGENT_ID,
    )

    assert "not enabled" in result["error"]


@pytest.mark.asyncio
async def test_lead_context_returns_only_the_fields_the_organization_shared(fake_db: FakeDb):
    fake_db.responses["GET voice_agents"] = FakeResult(
        {"data_access": {"tools": {"get_lead_context": True}, "lead_fields": ["company_name", "project_type"]}}
    )
    fake_db.responses["GET leads"] = FakeResult(
        {"id": "lead-1", "organization_id": ORG_ID, "company_id": "co-1", "project_type": "saas", "tags": ["vip"]}
    )
    fake_db.responses["GET companies"] = FakeResult({"name": "Acme"})

    result = await voice_tools.dispatch(
        "get_lead_context", ORG_ID, {"lead_id": "lead-1"}, fake_db, voice_agent_id=AGENT_ID
    )

    assert result["shared"] == {"company_name": "Acme", "project_type": "saas"}
    # A field that was not shared is never even read, so it cannot leak through a log or an error.
    assert not [c for c in fake_db.calls if c[1] == "lead_intelligence"]


@pytest.mark.asyncio
async def test_lead_context_says_so_when_no_crm_data_is_shared_at_all(fake_db: FakeDb):
    """The inbound receptionist template ships this way: it answers the main line to strangers,
    so it is given no pipeline data. The agent needs to know that, or it will improvise."""
    fake_db.responses["GET voice_agents"] = FakeResult(
        {"data_access": {"tools": {"get_lead_context": True}, "lead_fields": []}}
    )
    fake_db.responses["GET leads"] = FakeResult({"id": "lead-1", "organization_id": ORG_ID})

    result = await voice_tools.dispatch(
        "get_lead_context", ORG_ID, {"lead_id": "lead-1"}, fake_db, voice_agent_id=AGENT_ID
    )

    assert result["shared"] == {}
    assert "not been given access" in result["note"]


def test_only_the_safety_tools_are_beyond_an_organizations_control():
    """If this list grows, an organization has lost a choice it used to have -- so it is pinned."""
    assert set(voice_script.ALWAYS_ON_TOOLS) == {"check_consent", "log_call_outcome"}
    assert set(voice_script.TOOL_BRIEFS) == set(voice_tools.TOOLS)
