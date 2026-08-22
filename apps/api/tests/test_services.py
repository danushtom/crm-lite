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

BASE_LEAD = {
    "id": LEAD_ID,
    "company_id": "co-1",
    "owner_id": "user-1",
    "stage": "prospect",
    "project_type": "saas",
    "lead_source": "referral",
    "estimated_value": 500000,
    "currency": "INR",
    "deal_probability": 50,
    "priority_score": 0,
    "tags": [],
    "is_opportunity": False,
}


def db_with(**responses) -> FakeDb:
    return FakeDb(responses)


# --- Pipeline field routing ---------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_fields_are_written_to_the_opportunity_not_the_lead():
    """`leads` mirrors the opportunity via trigger; writing stage there would be reverted."""
    db = db_with(**{
        "GET leads": BASE_LEAD,
        "GET opportunities": {"id": OPP_ID, "priority_score": 0},
        "PATCH opportunities": {"id": OPP_ID},
        "PATCH leads": BASE_LEAD,
        "GET lead_intelligence": None,
    })

    await lead_service.update_lead(db, LEAD_ID, {"stage": "negotiation", "estimated_value": 900000})

    opp_writes = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"]
    assert opp_writes, "stage change must be written to the opportunity"
    body = opp_writes[0][2]["payload"]
    assert body["stage"] == "negotiation"
    # estimated_value is named quoted_value on the opportunity.
    assert body["quoted_value"] == 900000
    assert "estimated_value" not in body

    lead_writes = [c for c in db.calls if c[0] == "PATCH" and c[1] == "leads"]
    for _, _, kwargs in lead_writes:
        assert "stage" not in kwargs["payload"], "stage must never be written directly to leads"


@pytest.mark.asyncio
async def test_non_pipeline_fields_go_straight_to_the_lead():
    db = db_with(**{
        "GET leads": BASE_LEAD,
        "PATCH leads": BASE_LEAD,
        "GET opportunities": None,
        "GET lead_intelligence": None,
    })

    await lead_service.update_lead(db, LEAD_ID, {"next_followup_date": "2026-09-01"})

    assert not [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"]
    lead_writes = [c for c in db.calls if c[0] == "PATCH" and c[1] == "leads"]
    assert lead_writes[0][2]["payload"]["next_followup_date"] == "2026-09-01"


@pytest.mark.asyncio
async def test_empty_update_is_a_no_op_read():
    db = db_with(**{"GET leads": BASE_LEAD})
    result = await lead_service.update_lead(db, LEAD_ID, {})
    assert result["id"] == LEAD_ID
    assert not [c for c in db.calls if c[0] in ("PATCH", "POST")]


# --- Scoring propagation ------------------------------------------------------


@pytest.mark.asyncio
async def test_score_is_mirrored_onto_the_opportunity():
    db = db_with(**{
        "GET leads": {**BASE_LEAD, "priority_score": 0, "deal_probability": 90},
        "GET lead_intelligence": {"decision_makers": "CTO"},
        "GET opportunities": {"id": OPP_ID, "priority_score": 0},
        "PATCH leads": BASE_LEAD,
        "PATCH opportunities": {"id": OPP_ID},
    })

    await lead_service.sync_priority_score(db, LEAD_ID)

    opp_patch = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"]
    assert opp_patch, "recomputed score must reach the opportunity the Kanban reads"
    assert opp_patch[0][2]["payload"]["priority_score"] > 0


@pytest.mark.asyncio
async def test_score_write_is_skipped_when_unchanged():
    """Avoid a pointless UPDATE (and the trigger cascade it fires) when nothing moved."""
    lead = {**BASE_LEAD, "priority_score": 0, "deal_probability": 50}
    score = lead_service.score_for(lead, None)
    db = db_with(**{
        "GET leads": {**lead, "priority_score": score},
        "GET lead_intelligence": None,
        "GET opportunities": {"id": OPP_ID, "priority_score": score},
    })

    await lead_service.sync_priority_score(db, LEAD_ID)

    assert not [c for c in db.calls if c[0] == "PATCH"]


# --- Stage moves --------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_stage_targets_the_opportunity():
    db = db_with(**{
        "GET opportunities": {"id": OPP_ID, "priority_score": 10},
        "PATCH opportunities": {"id": OPP_ID},
        "GET leads": BASE_LEAD,
        "GET lead_intelligence": None,
        "PATCH leads": BASE_LEAD,
    })

    await lead_service.set_stage(db, LEAD_ID, "won")

    patch = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"][0]
    assert patch[2]["payload"]["stage"] == "won"


@pytest.mark.asyncio
async def test_missing_opportunity_shell_is_a_404():
    db = db_with(**{"GET opportunities": None})
    with pytest.raises(NotFoundError):
        await lead_service.get_opportunity_for_lead(db, LEAD_ID)


# --- Conversion ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_convert_is_not_repeatable():
    db = db_with(**{"GET leads": {**BASE_LEAD, "is_opportunity": True}})
    with pytest.raises(ConflictError):
        await lead_service.convert_to_opportunity(db, LEAD_ID)


@pytest.mark.asyncio
async def test_convert_copies_commercials_onto_the_opportunity():
    db = db_with(**{
        "GET leads": BASE_LEAD,
        "GET opportunities": {"id": OPP_ID},
        "PATCH opportunities": {"id": OPP_ID, "lead_id": LEAD_ID, "owner_id": "user-1",
                                "title": "Saas", "stage": "prospect"},
        "PATCH leads": {**BASE_LEAD, "is_opportunity": True},
    })

    opportunity, lead = await lead_service.convert_to_opportunity(db, LEAD_ID)

    body = [c for c in db.calls if c[0] == "PATCH" and c[1] == "opportunities"][0][2]["payload"]
    assert body["quoted_value"] == BASE_LEAD["estimated_value"]
    assert body["currency"] == "INR"
    assert body["status"] == "active"
    assert lead["is_opportunity"] is True
    assert opportunity["id"] == OPP_ID


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
