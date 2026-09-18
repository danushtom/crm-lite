"""The scheduled AI jobs.

Same stakes as the other worker tests: these run with the service role, on a timer, across every
organization at once. A tenant-routing mistake here is silent and repeats nightly.

The model itself is stubbed throughout -- what is under test is the batching, the stamping that
makes a job idempotent, and the fact that every write is routed by the row's own
``organization_id``/``owner_id`` rather than by anything ambient.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_jobs  # noqa: E402
from tests.test_jobs import FakeSupabase  # noqa: E402


class FakeNotes:
    summary = "Priya wants an MVP quote by Friday."
    sentiment = "positive"
    outcome = "interested"
    suggested_next_action = "Send the MVP quote."
    suggested_followup_date = (date.today() + timedelta(days=2)).isoformat()

    class _Item:
        title = "Send the MVP quote"
        detail = "Fixed price, 8 weeks"
        priority = "high"

        def model_dump(self):
            return {"title": self.title, "detail": self.detail, "priority": self.priority}

    action_items = [_Item()]


class FakeUsage:
    total_tokens = 1200

    def to_row(self, organization_id):
        return {
            "organization_id": organization_id,
            "feature": "call_notes",
            "model": "gpt-4o-mini",
            "total_tokens": self.total_tokens,
        }


CALL_ROW = {
    "id": "call-1",
    "organization_id": "org-a",
    "lead_id": "lead-1",
    "transcript": "Hello, this is Priya from Acme...",
    "duration_seconds": 240,
    "ended_at": "2026-09-18T10:00:00+00:00",
}


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(ai_jobs.ENV, "ai_enabled", True)
    monkeypatch.setattr(ai_jobs.ENV, "ai_batch_limit", 25)
    monkeypatch.setattr(ai_jobs.ENV, "supabase_url", "http://localhost")
    monkeypatch.setattr(ai_jobs.ENV, "supabase_service_role_key", "service-key")


def _returning(value):
    """Replace ai_jobs._run with a stub that returns `value`.

    It closes the coroutine it was handed: ai_jobs builds one before calling _run, and silently
    dropping it makes pytest report "coroutine was never awaited" on every test here.
    """

    def _stub(coro):
        coro.close()
        return value

    return _stub


# --- The feature switch -----------------------------------------------------------


def test_every_ai_job_is_a_no_op_when_ai_is_disabled(monkeypatch):
    """A deployment without an API key must not have three jobs failing every few minutes."""
    monkeypatch.setattr(ai_jobs.ENV, "ai_enabled", False)

    assert ai_jobs.run_call_notes() == "skip:ai_disabled"
    assert ai_jobs.run_deal_health() == "skip:ai_disabled"
    assert ai_jobs.run_reindex_knowledge_base() == "skip:ai_disabled"


# --- Call notes -------------------------------------------------------------------


def test_call_notes_only_picks_up_completed_calls_that_have_a_transcript(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /calls": []})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_call_notes()

    params = sb.params_for("GET", "/calls")
    assert params["status"] == "eq.completed"
    assert params["transcript"] == "not.is.null"
    assert params["ai_notes_generated_at"] == "is.null"
    # Bounded, so a backlog cannot become one enormous batch of model calls.
    assert params["limit"] == "25"


def test_call_notes_writes_the_summary_and_stamps_the_row(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    assert ai_jobs.run_call_notes() == "call_notes:1"

    patch = [c for c in sb.writes("/calls")][0][2]["json_body"]
    assert patch["ai_summary"] == FakeNotes.summary
    assert patch["ai_sentiment"] == "positive"
    assert patch["suggested_next_action"] == "Send the MVP quote."
    # The stamp is what stops the same call being summarised (and billed) again next tick.
    assert patch["ai_notes_generated_at"]
    assert patch["ai_notes_error"] is None


def test_call_notes_never_overwrites_the_platforms_own_summary(monkeypatch, ai_on):
    """`summary` is the voice platform's record of what its model said at the time; ours lands
    beside it in `ai_summary` so the two stay distinguishable."""
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    ai_jobs.run_call_notes()

    patch = [c for c in sb.writes("/calls")][0][2]["json_body"]
    assert "summary" not in patch
    assert "outcome" not in patch


def test_call_notes_attributes_tokens_to_the_calls_own_organization(monkeypatch, ai_on):
    """The worker sees every organization at once; spend must follow the row, not a default."""
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    ai_jobs.run_call_notes()

    usage = [c for c in sb.writes("/ai_usage")][0][2]["json_body"]
    assert usage["organization_id"] == "org-a"


def test_call_notes_creates_tasks_owned_by_the_lead_owner(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    ai_jobs.run_call_notes()

    task = [c for c in sb.writes("/tasks")][0][2]["json_body"]
    assert task["owner_id"] == "user-1"
    assert task["lead_id"] == "lead-1"
    assert task["title"] == "Send the MVP quote"
    assert task["due_at"].startswith(FakeNotes.suggested_followup_date)


def test_call_notes_logs_the_summary_on_the_timeline_as_a_system_actor(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    ai_jobs.run_call_notes()

    activity = [c for c in sb.writes("/activities")][0][2]["json_body"]
    assert activity["actor_type"] == "system"
    assert activity["performed_by"] is None
    assert activity["metadata"]["source"] == "ai_call_notes"


def test_a_failed_summarisation_is_recorded_and_left_for_retry(monkeypatch, ai_on):
    """`ai_notes_generated_at` stays NULL, so the next tick tries again -- and the age cutoff in
    the query stops it retrying forever."""
    sb = FakeSupabase({"GET /calls": [CALL_ROW]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    def boom(coro):
        coro.close()
        raise RuntimeError("model timeout")

    monkeypatch.setattr(ai_jobs, "_run", boom)

    assert ai_jobs.run_call_notes() == "call_notes:0"

    patch = [c for c in sb.writes("/calls")][0][2]["json_body"]
    assert patch == {"ai_notes_error": "model timeout"}


def test_a_call_with_no_lead_still_gets_its_summary(monkeypatch, ai_on):
    """An inbound call from an unknown number has no lead. It should still be summarised; there
    is simply no timeline to write it to."""
    sb = FakeSupabase({"GET /calls": [{**CALL_ROW, "lead_id": None}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    assert ai_jobs.run_call_notes() == "call_notes:1"
    assert sb.writes("/calls")
    assert not sb.writes("/activities")
    assert not sb.writes("/tasks")


# --- Deal health ------------------------------------------------------------------


def test_deal_health_only_looks_at_active_undeleted_opportunities(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /opportunities": []})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_deal_health()

    params = sb.params_for("GET", "/opportunities")
    assert params["status"] == "eq.active"
    assert params["deleted_at"] == "is.null"


def test_deal_health_notifies_only_the_owner_of_a_high_risk_deal(monkeypatch, ai_on):
    sb = FakeSupabase(
        {
            "GET /opportunities": [
                {
                    "id": "opp-1",
                    "organization_id": "org-a",
                    "owner_id": "user-1",
                    "lead_id": "lead-1",
                    "title": "Acme rebuild",
                    "stage": "negotiation",
                    "quoted_value": 500000,
                    "currency": "INR",
                    "priority_score": 30,
                    "updated_at": "2026-08-01T00:00:00+00:00",
                }
            ],
            "GET /activities": [],
            "GET /tasks": [],
        }
    )
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    class Health:
        risk_level = "high"
        reasons = ["No contact in 40 days"]
        suggested_action = "Call the CTO this week."
        assessed_by_model = True

    monkeypatch.setattr(ai_jobs, "_run", _returning((Health(), FakeUsage())))

    result = ai_jobs.run_deal_health()

    assert "flagged=1" in result
    snapshot = [c for c in sb.writes("/deal_health_snapshots")][0][2]["json_body"]
    assert snapshot["organization_id"] == "org-a"
    assert snapshot["risk_level"] == "high"

    notification = [c for c in sb.writes("/notifications")][0][2]["json_body"]
    assert notification["user_id"] == "user-1"
    # Keyed to the day: a deal that stays stalled nags once a day, not once a run.
    assert notification["dedupe_key"].startswith("deal_at_risk:opp-1:")


def test_a_low_risk_deal_writes_a_snapshot_but_no_notification(monkeypatch, ai_on):
    sb = FakeSupabase(
        {
            "GET /opportunities": [
                {
                    "id": "opp-1",
                    "organization_id": "org-a",
                    "owner_id": "user-1",
                    "lead_id": "lead-1",
                    "stage": "won",
                    "updated_at": "2026-09-18T00:00:00+00:00",
                }
            ],
            "GET /activities": [],
            "GET /tasks": [],
        }
    )
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    class Health:
        risk_level = "low"
        reasons = []
        suggested_action = ""
        assessed_by_model = False

    monkeypatch.setattr(ai_jobs, "_run", _returning((Health(), FakeUsage())))

    ai_jobs.run_deal_health()

    assert sb.writes("/deal_health_snapshots")
    assert not sb.writes("/notifications")


# --- Reindex ----------------------------------------------------------------------


def test_reindex_only_looks_at_documents_that_were_never_indexed(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /voice_agent_documents": []})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_reindex_knowledge_base()

    assert sb.params_for("GET", "/voice_agent_documents")["indexed_at"] == "is.null"


def test_a_permanently_unindexable_file_is_stamped_so_it_stops_being_retried(monkeypatch, ai_on):
    sb = FakeSupabase(
        {
            "GET /voice_agent_documents": [
                {
                    "id": "doc-1",
                    "organization_id": "org-a",
                    "voice_agent_id": "va-1",
                    "filename": "logo.png",
                    "file_url": "va-1/abc_logo.png",
                }
            ]
        }
    )
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_reindex_knowledge_base()

    patch = [c for c in sb.writes("/voice_agent_documents")][0][2]["json_body"]
    assert patch["indexed_at"]
    assert patch["chunk_count"] == 0
    assert "cannot be indexed" in patch["index_error"]


# --- Tenant scoping of service-role writes ----------------------------------------
#
# These jobs run with the service role, which bypasses RLS entirely. Every write therefore has
# to be pinned to the row's own organization by the query itself -- there is no database
# backstop here, only these filters.


def test_every_write_the_call_notes_job_makes_is_scoped_to_the_calls_organization(
    monkeypatch, ai_on
):
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    ai_jobs.run_call_notes()

    for method, path, kwargs in sb.calls:
        if path == "/calls" and method == "PATCH":
            assert kwargs["params"]["organization_id"] == "eq.org-a", kwargs


def test_the_lead_lookup_is_scoped_so_a_cross_tenant_lead_id_cannot_route_a_task(
    monkeypatch, ai_on
):
    """calls.lead_id is a plain FK with no cross-organization constraint. Without the filter, a
    bad lead_id would hand another tenant's rep a task carrying this call's summary."""
    sb = FakeSupabase({"GET /calls": [CALL_ROW], "GET /leads": [{"owner_id": "user-1"}]})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)
    monkeypatch.setattr(ai_jobs, "_run", _returning((FakeNotes(), FakeUsage())))

    ai_jobs.run_call_notes()

    assert sb.params_for("GET", "/leads")["organization_id"] == "eq.org-a"


def test_the_reindex_job_scopes_its_stamps_to_the_documents_organization(monkeypatch, ai_on):
    sb = FakeSupabase(
        {
            "GET /voice_agent_documents": [
                {
                    "id": "doc-1",
                    "organization_id": "org-b",
                    "voice_agent_id": "va-1",
                    "filename": "logo.png",
                    "file_url": "va-1/abc_logo.png",
                }
            ]
        }
    )
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_reindex_knowledge_base()

    params = [c for c in sb.writes("/voice_agent_documents")][0][2]["params"]
    assert params["organization_id"] == "eq.org-b"


def test_the_daily_snapshot_upsert_names_its_conflict_columns(monkeypatch, ai_on):
    """PostgREST infers an upsert's conflict target from the primary key unless told otherwise.
    The PK here is a fresh uuid per insert, so without an explicit on_conflict the daily unique
    index raises instead of updating and a same-day re-run fails for every deal."""
    sb = FakeSupabase(
        {
            "GET /opportunities": [
                {
                    "id": "opp-1",
                    "organization_id": "org-a",
                    "owner_id": "user-1",
                    "lead_id": "lead-1",
                    "stage": "negotiation",
                    "updated_at": "2026-08-01T00:00:00+00:00",
                }
            ],
            "GET /activities": [],
            "GET /tasks": [],
        }
    )
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    class Health:
        risk_level = "medium"
        reasons = ["stale"]
        suggested_action = "Call them."
        assessed_by_model = True

    monkeypatch.setattr(ai_jobs, "_run", _returning((Health(), FakeUsage())))

    ai_jobs.run_deal_health()

    call = [c for c in sb.writes("/deal_health_snapshots")][0]
    assert call[2]["params"]["on_conflict"] == "opportunity_id,snapshot_date"
    assert call[2]["json_body"]["snapshot_date"]


def test_deal_health_pins_its_context_reads_to_the_opportunitys_organization(monkeypatch, ai_on):
    """The activity descriptions gathered here go straight into a prompt whose output is written
    to a snapshot and emailed in the daily brief. Service role, no RLS behind it."""
    sb = FakeSupabase(
        {
            "GET /opportunities": [
                {
                    "id": "opp-1",
                    "organization_id": "org-a",
                    "owner_id": "user-1",
                    "lead_id": "lead-1",
                    "stage": "negotiation",
                    "updated_at": "2026-08-01T00:00:00+00:00",
                }
            ],
            "GET /activities": [],
            "GET /tasks": [],
        }
    )
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    class Health:
        risk_level = "low"
        reasons = []
        suggested_action = ""
        assessed_by_model = False

    monkeypatch.setattr(ai_jobs, "_run", _returning((Health(), FakeUsage())))

    ai_jobs.run_deal_health()

    assert sb.params_for("GET", "/activities")["organization_id"] == "eq.org-a"
    assert sb.params_for("GET", "/tasks")["organization_id"] == "eq.org-a"


# --- Plan gating ------------------------------------------------------------------
#
# One OpenAI key serves every tenant, so a job that ignores plans spends money on organizations
# that are not paying for AI. The filter must be in the query, not applied afterwards -- see
# _entitled_org_filters for why.

from datetime import datetime, timezone  # noqa: E402

_FUTURE = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
_PAST = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

SUBSCRIPTIONS = [
    {"organization_id": "org-growth", "plan": "growth", "status": "active", "seats": 3},
    {"organization_id": "org-scale", "plan": "scale", "status": "past_due", "seats": 3},
    {"organization_id": "org-starter", "plan": "starter", "status": "active", "seats": 3},
    {"organization_id": "org-trial", "plan": "trial", "status": "trialing", "trial_ends_at": _FUTURE},
    {"organization_id": "org-lapsed", "plan": "trial", "status": "trialing", "trial_ends_at": _PAST},
]


def test_call_notes_only_scans_organizations_whose_plan_includes_ai(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /organization_subscriptions": SUBSCRIPTIONS, "GET /calls": []})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_call_notes()

    scoped = sb.params_for("GET", "/calls")["organization_id"]
    assert scoped == "in.(org-growth,org-scale,org-trial)"


def test_knowledge_base_reindexing_needs_the_voice_agents_feature(monkeypatch, ai_on):
    sb = FakeSupabase({"GET /organization_subscriptions": SUBSCRIPTIONS, "GET /voice_agent_documents": []})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_reindex_knowledge_base()

    scoped = sb.params_for("GET", "/voice_agent_documents")["organization_id"]
    assert scoped == "in.(org-scale,org-trial)"


def test_no_scan_runs_when_no_organization_is_entitled(monkeypatch, ai_on):
    lapsed_only = [s for s in SUBSCRIPTIONS if s["organization_id"] in ("org-starter", "org-lapsed")]
    sb = FakeSupabase({"GET /organization_subscriptions": lapsed_only})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    assert ai_jobs.run_deal_health() == "deal_health:assessed=0,flagged=0"
    assert sb.params_for("GET", "/opportunities") is None


def test_entitled_organizations_are_split_into_bounded_chunks(monkeypatch, ai_on):
    many = [
        {"organization_id": f"org-{i:03d}", "plan": "growth", "status": "active", "seats": 1}
        for i in range(ai_jobs.ORG_FILTER_CHUNK + 1)
    ]
    sb = FakeSupabase({"GET /organization_subscriptions": many, "GET /calls": []})
    monkeypatch.setattr(ai_jobs, "SupabaseAdmin", lambda *_a, **_k: sb)

    ai_jobs.run_call_notes()

    scans = [c[2]["params"] for c in sb.calls if c[1] == "/calls"]
    assert len(scans) == 2
    assert scans[1]["organization_id"] == f"in.(org-{ai_jobs.ORG_FILTER_CHUNK:03d})"
