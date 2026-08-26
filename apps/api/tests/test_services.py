"""Service-layer behaviour: the rules that live between the endpoints and the database."""

from __future__ import annotations

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.services import leads as lead_service
from app.services import meetings as meeting_service
from app.services import proposals as proposal_service
from tests.conftest import FakeDb, FakeResult

LEAD_ID = "lead-1"
OPP_ID = "opp-1"

# A lead is now purely a qualification record: no stage, no money, no score.
BASE_LEAD = {
    "id": LEAD_ID,
    "company_id": "co-1",
    "owner_id": "user-1",
    "project_type": "saas",
    "lead_source": "referral",
    "tags": [],
    "version": 1,
}

BASE_OPPORTUNITY = {
    "id": OPP_ID,
    "lead_id": LEAD_ID,
    "owner_id": "user-1",
    "title": "Saas",
    "stage": "prospect",
    "status": "active",
    "quoted_value": 500000,
    "currency": "INR",
    "deal_probability": 50,
    "priority_score": 0,
    "version": 1,
}


def db_with(**responses) -> FakeDb:
    return FakeDb(responses)


# --- Ownership of fields ------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_update_is_a_single_write():
    """Before the tables were separated this split the payload across two tables and
    re-read, costing up to eight round trips. Every field here belongs to the lead."""
    db = db_with(**{
        "GET leads": BASE_LEAD,
        "PATCH leads": {**BASE_LEAD, "next_followup_date": "2026-09-01"},
    })

    await lead_service.update_lead(db, LEAD_ID, {"next_followup_date": "2026-09-01"})

    writes = [c for c in db.calls if c[0] == "PATCH"]
    assert len(writes) == 1
    assert writes[0][1] == "leads"
    assert not [c for c in db.calls if c[1] == "opportunities"]


@pytest.mark.asyncio
async def test_empty_update_is_a_no_op_read():
    db = db_with(**{"GET leads": BASE_LEAD})
    result = await lead_service.update_lead(db, LEAD_ID, {})
    assert result["id"] == LEAD_ID
    assert not [c for c in db.calls if c[0] in ("PATCH", "POST")]


# --- Scoring belongs to the pursuit -------------------------------------------


@pytest.mark.asyncio
async def test_score_is_written_to_the_opportunity():
    db = db_with(**{
        "GET lead_intelligence": {"decision_makers": "CTO"},
        "PATCH opportunities": {**BASE_OPPORTUNITY, "priority_score": 70},
    })

    await lead_service.sync_opportunity_score(db, dict(BASE_OPPORTUNITY))

    writes = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"]
    assert writes, "a recomputed score must be persisted on the pursuit"
    assert writes[0][2]["payload"]["priority_score"] > 0


@pytest.mark.asyncio
async def test_score_write_is_skipped_when_unchanged():
    """Avoid a pointless UPDATE, and the trigger cascade it fires, when nothing moved."""
    settled = dict(BASE_OPPORTUNITY)
    settled["priority_score"] = lead_service.score_for(settled, None)
    db = db_with(**{"GET lead_intelligence": None})

    await lead_service.sync_opportunity_score(db, settled)

    assert not [c for c in db.calls if c[0] == "PATCH"]


@pytest.mark.asyncio
async def test_score_override_pins_the_result():
    pinned = {**BASE_OPPORTUNITY, "score_override": 91}
    assert lead_service.score_for(pinned, None) == 91


# --- Stage moves --------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_stage_writes_to_the_opportunity():
    db = db_with(**{
        "PATCH opportunities": {**BASE_OPPORTUNITY, "stage": "won"},
        "GET lead_intelligence": None,
    })

    await lead_service.set_stage(db, OPP_ID, "won")

    patch = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"][0]
    assert patch[2]["payload"]["stage"] == "won"


@pytest.mark.asyncio
async def test_missing_active_opportunity_is_a_404():
    db = db_with(**{"GET opportunities": None})
    with pytest.raises(NotFoundError):
        await lead_service.get_active_opportunity(db, LEAD_ID)


# --- Creation -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_creating_a_lead_populates_the_pursuit_its_trigger_opened():
    db = db_with(**{
        "POST leads": BASE_LEAD,
        "GET opportunities": [BASE_OPPORTUNITY],
        "PATCH opportunities": {**BASE_OPPORTUNITY, "quoted_value": 900000},
    })

    lead, pursuits = await lead_service.create_lead(
        db,
        {"company_id": "co-1", "project_type": "saas", "lead_source": "referral"},
        owner_id="user-1",
        opportunity={"quoted_value": 900000, "stage": "contacting", "deal_probability": 70},
    )

    assert lead["id"] == LEAD_ID
    body = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"][0][2]["payload"]
    assert body["quoted_value"] == 900000
    assert body["stage"] == "contacting"
    assert "priority_score" in body, "score must be derived server-side at creation"
    assert pursuits[0]["quoted_value"] == 900000


@pytest.mark.asyncio
async def test_lead_creation_defaults_owner_to_the_caller():
    db = db_with(**{"POST leads": BASE_LEAD, "GET opportunities": [BASE_OPPORTUNITY]})

    await lead_service.create_lead(
        db, {"company_id": "co-1", "project_type": "saas", "lead_source": "referral"},
        owner_id="user-9",
    )

    payload = [c for c in db.calls if c[0] == "POST"][0][2]["payload"]
    assert payload["owner_id"] == "user-9"


# --- A lead may have several pursuits -----------------------------------------


@pytest.mark.asyncio
async def test_opening_a_second_pursuit_is_allowed():
    """The build, then the retainer. The old UNIQUE(lead_id) made this impossible."""
    db = db_with(**{
        "GET leads": BASE_LEAD,
        "GET lead_intelligence": None,
        "POST opportunities": {**BASE_OPPORTUNITY, "id": "opp-2", "title": "Retainer"},
    })

    created = await lead_service.open_opportunity(
        db, LEAD_ID, {"title": "Retainer", "quoted_value": 250000}, owner_id="user-1"
    )

    assert created["id"] == "opp-2"
    payload = [c for c in db.calls if c[0] == "POST"][0][2]["payload"]
    assert payload["lead_id"] == LEAD_ID
    assert payload["status"] == "active"
    assert "priority_score" in payload


@pytest.mark.asyncio
async def test_a_second_active_pursuit_is_rejected_clearly():
    """A partial unique index allows only one active pursuit; surface that as guidance."""

    class Conflicting(FakeDb):
        async def insert(self, table, payload):
            raise ConflictError("duplicate key value violates unique constraint")

    db = Conflicting({"GET leads": BASE_LEAD, "GET lead_intelligence": None})

    with pytest.raises(ConflictError) as excinfo:
        await lead_service.open_opportunity(
            db, LEAD_ID, {"title": "Second"}, owner_id="user-1"
        )

    assert "already has an active opportunity" in str(excinfo.value)


# --- Meeting outcomes ---------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["needs_proposal", "followup_later"])
async def test_outcome_requiring_next_step_schedules_a_task(outcome):
    db = db_with(**{
        "GET meetings": {"id": "m-1", "lead_id": LEAD_ID},
        "PATCH meetings": {"id": "m-1", "lead_id": LEAD_ID, "owner_id": "user-1",
                           "title": "Call", "scheduled_at": "2026-08-01T10:00:00Z"},
        "POST tasks": {"id": "task-9"},
    })

    _, task_id = await meeting_service.record_outcome(
        db, "m-1", {"outcome": outcome, "status": "completed"}, owner_id="user-1"
    )

    assert task_id == "task-9"
    payload = [c for c in db.calls if c[0] == "POST" and c[1] == "tasks"][0][2]["payload"]
    assert payload["lead_id"] == LEAD_ID
    assert payload["status"] == "pending"
    assert "due_at" in payload, "follow-ups are scheduled as absolute instants"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["not_interested", "budget_issue", "interested"])
async def test_other_outcomes_schedule_nothing(outcome):
    db = db_with(**{
        "GET meetings": {"id": "m-1", "lead_id": LEAD_ID},
        "PATCH meetings": {"id": "m-1", "lead_id": LEAD_ID, "owner_id": "user-1",
                           "title": "Call", "scheduled_at": "2026-08-01T10:00:00Z"},
    })

    _, task_id = await meeting_service.record_outcome(
        db, "m-1", {"outcome": outcome}, owner_id="user-1"
    )

    assert task_id is None
    assert not [c for c in db.calls if c[0] == "POST" and c[1] == "tasks"]


@pytest.mark.asyncio
async def test_calendar_meeting_without_a_lead_schedules_nothing():
    """Google-synced meetings may have no lead; there is nothing to follow up on."""
    db = db_with(**{
        "GET meetings": {"id": "m-1", "lead_id": None},
        "PATCH meetings": {"id": "m-1", "lead_id": None, "owner_id": "user-1",
                           "title": "Sync", "scheduled_at": "2026-08-01T10:00:00Z"},
    })

    _, task_id = await meeting_service.record_outcome(
        db, "m-1", {"outcome": "needs_proposal"}, owner_id="user-1"
    )

    assert task_id is None


# --- Proposal versioning ------------------------------------------------------


@pytest.mark.asyncio
async def test_first_proposal_is_version_one():
    db = db_with(**{"GET proposals": None, "POST proposals": {"id": "p-1", "version": 1}})
    await proposal_service.create_version(db, OPP_ID, {"title": "Draft"}, created_by="user-1")
    payload = [c for c in db.calls if c[0] == "POST"][0][2]["payload"]
    assert payload["version"] == 1
    assert payload["created_by"] == "user-1"


@pytest.mark.asyncio
async def test_next_version_increments_from_the_highest():
    db = db_with(**{"GET proposals": {"version": 7}, "POST proposals": {"id": "p-8", "version": 8}})
    await proposal_service.create_version(db, OPP_ID, {"title": "v8"}, created_by="user-1")
    assert [c for c in db.calls if c[0] == "POST"][0][2]["payload"]["version"] == 8


@pytest.mark.asyncio
async def test_concurrent_version_collision_is_retried():
    """Two writers can read the same max version; the unique index rejects the loser."""
    attempts = {"n": 0}

    class RacyDb(FakeDb):
        async def insert(self, table, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ConflictError("duplicate key value violates unique constraint")
            return FakeResult({"id": "p-2", "version": payload["version"]})

    db = RacyDb({"GET proposals": {"version": 1}})
    result = await proposal_service.create_version(db, OPP_ID, {"title": "v2"}, created_by="u")

    assert attempts["n"] == 2, "the conflicting insert should have been retried"
    assert result["version"] == 2


@pytest.mark.asyncio
async def test_retries_are_bounded():
    class AlwaysConflicts(FakeDb):
        async def insert(self, table, payload):
            raise ConflictError("duplicate key")

    db = AlwaysConflicts({"GET proposals": {"version": 1}})
    with pytest.raises(ConflictError):
        await proposal_service.create_version(db, OPP_ID, {"title": "x"}, created_by="u")
