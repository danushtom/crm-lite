"""Mid-call tools invoked from the voice platform's tool-call webhook.

Every tool must scope its writes/reads by the resolved org_id -- these are the only functions
in the codebase that act on arguments an LLM generated, not on validated request bodies.
`book_appointment` is the one that previously trusted `owner_id`/`lead_id` straight from those
arguments; the tests below pin down that it now validates both against org_id first.
"""

from __future__ import annotations

import pytest

from app.services import voice_tools
from tests.conftest import FakeDb, FakeResult

ORG_ID = "org-1"
OTHER_ORG_ID = "org-2"


@pytest.mark.asyncio
async def test_check_consent_scopes_the_query_by_org(fake_db: FakeDb):
    fake_db.responses["GET contacts"] = FakeResult({"ai_call_consent": True})

    result = await voice_tools.dispatch("check_consent", ORG_ID, {"contact_id": "c-1"}, fake_db)

    assert result == {"consented": True}
    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "contacts"][0][2]["params"]
    assert params["organization_id"] == f"eq.{ORG_ID}"


@pytest.mark.asyncio
async def test_get_lead_context_rejects_a_lead_from_another_org(fake_db: FakeDb):
    fake_db.responses["GET leads"] = FakeResult({"id": "lead-1", "organization_id": OTHER_ORG_ID})

    result = await voice_tools.dispatch("get_lead_context", ORG_ID, {"lead_id": "lead-1"}, fake_db)

    assert result == {"error": "lead not found"}


@pytest.mark.asyncio
async def test_update_deal_stage_rejects_an_opportunity_from_another_org(fake_db: FakeDb):
    fake_db.responses["GET opportunities"] = FakeResult(None)

    result = await voice_tools.dispatch(
        "update_deal_stage", ORG_ID, {"opportunity_id": "opp-1", "stage": "won"}, fake_db
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
    )

    assert result == {"error": "owner not found in this organization"}
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "meetings"]


@pytest.mark.asyncio
async def test_unknown_tool_name_is_reported_not_raised(fake_db: FakeDb):
    result = await voice_tools.dispatch("delete_everything", ORG_ID, {}, fake_db)
    assert "error" in result
