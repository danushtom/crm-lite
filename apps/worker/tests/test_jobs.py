"""Scheduled job behaviour, driven against a recording fake of the Supabase client.

The jobs run with the service role and on a timer, so a mistake here is silent and
repeats: it does not surface as a failed request that anyone sees.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import worker_app  # noqa: E402


class FakeSupabase:
    """Records every call and replays canned responses keyed by ``METHOD /path``."""

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, path, *, params=None, json_body=None, prefer=None):
        self.calls.append((method, path, {"params": params or {}, "json_body": json_body}))
        return self.responses.get(f"{method} {path}")

    def writes(self, path=None):
        return [
            c for c in self.calls
            if c[0] in ("PATCH", "POST") and (path is None or c[1] == path)
        ]

    def params_for(self, method, path):
        for m, p, kwargs in self.calls:
            if m == method and p == path:
                return kwargs["params"]
        return None


@pytest.fixture
def fake_sb(monkeypatch):
    sb = FakeSupabase()
    monkeypatch.setattr(worker_app, "_sb", lambda: sb)
    return sb


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    sent: list[dict] = []

    def _record(sb, **kwargs):
        sent.append(kwargs)
        return {"id": "notif-1"}

    monkeypatch.setattr(worker_app, "insert_notification", _record)
    return sent


LEAD = {
    "id": "lead-1",
    "estimated_value": 500000,
    "currency": "INR",
    "deal_probability": 50,
    "stage": "prospect",
    "next_followup_date": None,
    "score_override": None,
    "priority_score": 0,
}


def _score_for(lead):
    from scoring import compute_priority_score

    return compute_priority_score(
        estimated_value=float(lead["estimated_value"]),
        currency=lead["currency"],
        deal_probability=lead["deal_probability"],
        stage=lead["stage"],
        next_followup_date=lead["next_followup_date"],
        intelligence=None,
        score_override=None,
    )


# --- score_recalculate --------------------------------------------------------


def test_unchanged_score_is_not_rewritten(fake_sb):
    """Rewriting bumps updated_at, which puts the row back in the next run's window.

    Unconditional writes made this job self-perpetuating: every lead it touched stayed in
    scope forever, degenerating into an hourly rewrite of the whole table.
    """
    settled = {**LEAD, "priority_score": _score_for(LEAD)}
    fake_sb.responses["GET /leads"] = [settled]
    fake_sb.responses["GET /lead_intelligence"] = []

    result = worker_app.score_recalculate()

    assert fake_sb.writes() == []
    assert result == "scores:0"


def test_changed_score_is_written_to_the_lead(fake_sb):
    fake_sb.responses["GET /leads"] = [{**LEAD, "priority_score": 0}]
    fake_sb.responses["GET /lead_intelligence"] = []
    fake_sb.responses["GET /opportunities"] = []

    worker_app.score_recalculate()

    lead_writes = fake_sb.writes("/leads")
    assert len(lead_writes) == 1
    assert lead_writes[0][2]["json_body"]["priority_score"] == _score_for(LEAD)


def test_score_is_mirrored_onto_the_opportunity(fake_sb):
    """The Kanban reads opportunities.priority_score; updating only the lead left it stale."""
    fake_sb.responses["GET /leads"] = [{**LEAD, "priority_score": 0}]
    fake_sb.responses["GET /lead_intelligence"] = []
    fake_sb.responses["GET /opportunities"] = [{"id": "opp-1", "priority_score": 0}]

    worker_app.score_recalculate()

    opp_writes = fake_sb.writes("/opportunities")
    assert len(opp_writes) == 1
    assert opp_writes[0][2]["json_body"]["priority_score"] == _score_for(LEAD)


def test_opportunity_write_is_skipped_when_already_correct(fake_sb):
    score = _score_for(LEAD)
    fake_sb.responses["GET /leads"] = [{**LEAD, "priority_score": 0}]
    fake_sb.responses["GET /lead_intelligence"] = []
    fake_sb.responses["GET /opportunities"] = [{"id": "opp-1", "priority_score": score}]

    worker_app.score_recalculate()

    assert fake_sb.writes("/opportunities") == []


def test_score_override_is_respected(fake_sb):
    fake_sb.responses["GET /leads"] = [{**LEAD, "score_override": 91, "priority_score": 0}]
    fake_sb.responses["GET /lead_intelligence"] = []
    fake_sb.responses["GET /opportunities"] = []

    worker_app.score_recalculate()

    assert fake_sb.writes("/leads")[0][2]["json_body"]["priority_score"] == 91


# --- no_touch_alert -----------------------------------------------------------


def test_stale_leads_are_filtered_upstream(fake_sb):
    """Previously every lead was fetched and most discarded in Python."""
    fake_sb.responses["GET /leads"] = []

    worker_app.no_touch_alert()

    params = fake_sb.params_for("GET", "/leads")
    assert params["no_touch_alert"] == "is.false"
    assert "last_contact_date.is.null" in params["or"]
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    assert cutoff in params["or"]


def test_stale_lead_is_flagged_and_notified(fake_sb, no_real_notifications):
    fake_sb.responses["GET /leads"] = [
        {"id": "lead-9", "owner_id": "user-1", "last_contact_date": "2026-01-01",
         "no_touch_alert": False}
    ]

    result = worker_app.no_touch_alert()

    assert fake_sb.writes("/leads")[0][2]["json_body"] == {"no_touch_alert": True}
    assert no_real_notifications[0]["notif_type"] == "no_touch"
    assert result == "flagged:1"


# --- post_meeting_prompt ------------------------------------------------------


def test_meeting_scan_is_bounded(fake_sb):
    """The prompt window is 15 minutes after a meeting ends, so old meetings cannot qualify."""
    fake_sb.responses["GET /meetings"] = []

    worker_app.post_meeting_prompt()

    params = fake_sb.params_for("GET", "/meetings")
    assert "scheduled_at" in params, "an unbounded scan grows without limit"
    assert params["scheduled_at"].startswith("gte.")
    assert params["limit"] == "500"


def test_prompt_fires_just_after_a_meeting_ends(fake_sb, no_real_notifications):
    ended = datetime.now(timezone.utc) - timedelta(minutes=35)
    fake_sb.responses["GET /meetings"] = [
        {"id": "m-1", "owner_id": "u-1", "title": "Discovery",
         "scheduled_at": ended.isoformat(), "duration_minutes": 30}
    ]

    worker_app.post_meeting_prompt()

    assert len(no_real_notifications) == 1
    assert no_real_notifications[0]["dedupe_key"] == "post_meeting:m-1"


def test_prompt_does_not_fire_for_a_meeting_still_running(fake_sb, no_real_notifications):
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    fake_sb.responses["GET /meetings"] = [
        {"id": "m-2", "owner_id": "u-1", "title": "In progress",
         "scheduled_at": start.isoformat(), "duration_minutes": 60}
    ]

    worker_app.post_meeting_prompt()

    assert no_real_notifications == []


def test_unparseable_timestamp_is_skipped_not_fatal(fake_sb, no_real_notifications):
    fake_sb.responses["GET /meetings"] = [
        {"id": "m-3", "owner_id": "u-1", "title": "Bad", "scheduled_at": "not-a-date",
         "duration_minutes": 30}
    ]

    assert worker_app.post_meeting_prompt() == "prompts:0"


# --- followup_reminder / overdue_escalation -----------------------------------


def test_followup_reminder_dedupes_per_task_per_day(fake_sb, no_real_notifications):
    fake_sb.responses["GET /tasks"] = [
        {"id": "t-1", "owner_id": "u-1", "title": "Call", "lead_id": "lead-1"}
    ]

    worker_app.followup_reminder()

    key = no_real_notifications[0]["dedupe_key"]
    assert key.startswith("followup_reminder:t-1:")
    assert date.today().isoformat() in key


def test_overdue_escalation_is_bounded(fake_sb):
    fake_sb.responses["GET /tasks"] = []
    fake_sb.responses["GET /users"] = []

    worker_app.overdue_escalation()

    params = fake_sb.params_for("GET", "/tasks")
    assert params["limit"] == "1000"
    assert params["status"] == "eq.pending"


def test_overdue_escalation_notifies_owner_and_admins(fake_sb, no_real_notifications):
    fake_sb.responses["GET /tasks"] = [
        {"id": "t-5", "owner_id": "u-1", "title": "Late", "due_date": "2026-01-01"}
    ]
    fake_sb.responses["GET /users"] = [{"id": "admin-1"}, {"id": "admin-2"}]

    worker_app.overdue_escalation()

    kinds = [n["notif_type"] for n in no_real_notifications]
    assert kinds.count("task_overdue") == 1
    assert kinds.count("task_overdue_admin") == 2


# --- HTTP client reuse --------------------------------------------------------


def test_http_client_is_shared_across_calls():
    """Celery builds a client per task and several jobs issue a request per row."""
    import supabase_admin

    supabase_admin.close_shared_client()
    try:
        first = supabase_admin._shared_client()
        second = supabase_admin._shared_client()
        assert first is second
    finally:
        supabase_admin.close_shared_client()
