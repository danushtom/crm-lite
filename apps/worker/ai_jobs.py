"""Scheduled AI work: call notes, deal health, and knowledge-base reindexing.

Kept out of ``worker_app.py`` because these three jobs share a shape the other jobs do not: they
each drive an async LangGraph workflow from a synchronous Celery task, they each have to attribute
token spend to an organization, and they each need a batch ceiling so a backlog cannot turn into
a thousand model calls in one beat tick.

**Plan-gated.** Each scan only reads rows from organizations whose plan includes the feature
(``_scan``), using the same ``entitlements()`` the API enforces with -- see packages/billing.

**Tenant scoping is manual here, as it is for every worker job.** There is no user token; the
service role sees every organization at once. Each job therefore scans across organizations in one
query and routes its result using the row's own ``organization_id``/``owner_id``, exactly as
``overdue_escalation`` does. Nothing below ever assumes "the" organization.

The graphs themselves come from ``packages/ai`` -- the same code the API runs -- so a prompt change
takes effect in both places or in neither.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from dracara_billing import FEATURE_AI, FEATURE_VOICE_AGENTS, entitlements

from env import ENV
from supabase_admin import SupabaseAdmin, insert_notification

log = logging.getLogger(__name__)

#: Only look this far back. A transcript from three weeks ago is not worth spending tokens on,
#: and a permanently-failing row should not be retried forever.
CALL_NOTES_MAX_AGE_DAYS = 7

#: Deals older than this without activity are already covered by no_touch_alert; deal health is
#: about deals that look alive but are drifting.
DEAL_HEALTH_LOOKBACK_DAYS = 120


def _run(coro: Any) -> Any:
    """Drive one async workflow from a synchronous Celery task.

    ``asyncio.run`` per task rather than a shared loop: Celery's default pool forks processes and
    a loop created in the parent does not survive that. These jobs run every few minutes, so the
    per-call loop setup is irrelevant next to the model latency.
    """
    return asyncio.run(coro)


#: Organization ids per `in.(...)` filter. Keeps a scan's URL well under proxy limits however
#: many organizations are entitled.
ORG_FILTER_CHUNK = 100


def _entitled_org_filters(sb: SupabaseAdmin, feature: str) -> list[dict[str, str]]:
    """PostgREST filters restricting a scan to organizations whose plan includes ``feature``.

    Pushed into the query rather than applied to its results on purpose: expired trials only
    ever accumulate, and scans here take the oldest rows first under a batch limit, so filtering
    afterwards would let lapsed organizations' backlog fill every batch and starve the paying
    ones.

    Returns ``[{}]`` (scan unfiltered) when there are no subscription rows at all -- billing not
    set up, the same fail-open rule as the API's plan gate -- and ``[]`` when rows exist but
    none are entitled. The entitled set is naturally bounded by live customers (paying, or in
    an unexpired trial), so the chunked list stays small.
    """
    rows: list[dict[str, Any]] = []
    page = 1000
    while True:
        batch = sb.request(
            "GET",
            "/organization_subscriptions",
            params={
                "select": "organization_id,plan,status,seats,trial_ends_at,current_period_end",
                "order": "organization_id.asc",
                "limit": str(page),
                "offset": str(len(rows)),
            },
        ) or []
        rows.extend(batch)
        if len(batch) < page:
            break
    if not rows:
        return [{}]
    allowed = [r["organization_id"] for r in rows if entitlements(r).has(feature)]
    return [
        {"organization_id": f"in.({','.join(allowed[i:i + ORG_FILTER_CHUNK])})"}
        for i in range(0, len(allowed), ORG_FILTER_CHUNK)
    ]


def _scan(
    sb: SupabaseAdmin, path: str, params: dict[str, str], *, feature: str, limit: int
) -> list[dict[str, Any]]:
    """Up to ``limit`` rows from ``path`` belonging to organizations entitled to ``feature``."""
    rows: list[dict[str, Any]] = []
    for org_filter in _entitled_org_filters(sb, feature):
        remaining = limit - len(rows)
        if remaining <= 0:
            break
        rows.extend(
            sb.request("GET", path, params={**params, **org_filter, "limit": str(remaining)})
            or []
        )
    return rows


def _record_usage(sb: SupabaseAdmin, organization_id: str, usage: Any) -> None:
    """Attribute tokens to the organization that caused them. Never raises -- accounting must not
    cost us the work that was already done and paid for."""
    if usage is None or (usage.total_tokens <= 0 and getattr(usage, "extra_cost_usd", 0) <= 0):
        return
    try:
        sb.request(
            "POST", "/ai_usage", json_body=usage.to_row(organization_id), prefer="return=minimal"
        )
    except Exception as exc:
        log.warning("ai_usage record failed org=%s: %s", organization_id, exc)


# ---------------------------------------------------------------------------
# Call notes
# ---------------------------------------------------------------------------


def run_call_notes() -> str:
    """Turn finished call transcripts into a summary, action items and a follow-up date.

    Polling rather than webhook-driven: the voice platform is waiting on the webhook's response,
    and a model call would blow its timeout. The same reasoning, and the same shape, as
    ``stale_call_reconciliation``.
    """
    if not ENV.ai_enabled:
        return "skip:ai_disabled"

    from dracara_ai.graphs import call_notes

    sb = SupabaseAdmin(ENV.supabase_url, ENV.supabase_service_role_key)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CALL_NOTES_MAX_AGE_DAYS)).isoformat()
    rows = _scan(
        sb,
        "/calls",
        {
            "select": "id,organization_id,lead_id,transcript,duration_seconds,ended_at",
            "status": "eq.completed",
            "transcript": "not.is.null",
            "ai_notes_generated_at": "is.null",
            "ended_at": f"gte.{cutoff}",
            "order": "ended_at.asc,id.asc",
        },
        feature=FEATURE_AI,
        limit=ENV.ai_batch_limit,
    )

    processed = 0
    for call in rows:
        try:
            notes, usage = _run(
                call_notes.run(
                    transcript=call["transcript"],
                    today=date.today().isoformat(),
                    duration_seconds=call.get("duration_seconds"),
                )
            )
        except Exception as exc:
            log.warning("call_notes failed call=%s: %s", call["id"], exc)
            # Stamp the error but leave ai_notes_generated_at NULL so a transient failure is
            # retried on the next tick; the age cutoff above stops it retrying forever.
            sb.request(
                "PATCH",
                "/calls",
                params={
                    "id": f"eq.{call['id']}",
                    "organization_id": f"eq.{call['organization_id']}",
                },
                json_body={"ai_notes_error": str(exc)[:500]},
                prefer="return=minimal",
            )
            continue

        org_id = call["organization_id"]
        sb.request(
            "PATCH",
            "/calls",
            params={"id": f"eq.{call['id']}", "organization_id": f"eq.{org_id}"},
            json_body={
                "ai_summary": notes.summary,
                "ai_action_items": [a.model_dump() for a in notes.action_items],
                "ai_sentiment": notes.sentiment,
                "ai_suggested_followup_date": notes.suggested_followup_date,
                "suggested_next_action": notes.suggested_next_action,
                "ai_notes_generated_at": datetime.now(timezone.utc).isoformat(),
                "ai_notes_error": None,
            },
            prefer="return=minimal",
        )
        _record_usage(sb, org_id, usage)
        _fan_out_call_notes(sb, call, notes)
        processed += 1

    return f"call_notes:{processed}"


def _fan_out_call_notes(sb: SupabaseAdmin, call: dict[str, Any], notes: Any) -> None:
    """Write the timeline entry, the follow-up tasks and the owner's notification.

    Each step is best-effort and logged: a failure to create one task should not cost the user
    the summary that was already written and paid for.
    """
    lead_id = call.get("lead_id")
    if not lead_id:
        return

    owner_id = None
    try:
        leads = sb.request(
            "GET",
            "/leads",
            params={
                "select": "owner_id",
                "id": f"eq.{lead_id}",
                # Service role bypasses RLS, so the organization clause is what guarantees this
                # call's lead really belongs to this call's tenant before its owner is handed
                # a task and a notification.
                "organization_id": f"eq.{call['organization_id']}",
            },
        )
        owner_id = (leads or [{}])[0].get("owner_id")
    except Exception as exc:
        log.warning("call_notes owner lookup failed lead=%s: %s", lead_id, exc)

    try:
        sb.request(
            "POST",
            "/activities",
            json_body={
                "lead_id": lead_id,
                "type": "note",
                "description": notes.summary,
                "actor_type": "system",
                "performed_by": None,
                "metadata": {
                    "call_id": call["id"],
                    "source": "ai_call_notes",
                    "sentiment": notes.sentiment,
                    "outcome": notes.outcome,
                    "action_items": [a.model_dump() for a in notes.action_items],
                },
            },
            prefer="return=minimal",
        )
    except Exception as exc:
        log.warning("call_notes activity insert failed call=%s: %s", call["id"], exc)

    # Ordering note: the caller stamps `ai_notes_generated_at` BEFORE calling this, so a call is
    # fanned out exactly once and these inserts cannot duplicate on a retry. `tasks` has no
    # dedupe_key column (unlike `notifications`), so that ordering is what provides idempotency --
    # the cost is that a step failing here is logged and not retried, which is the right trade
    # when the alternative is re-running a paid summarisation to recover one task row.
    if owner_id:
        due = notes.suggested_followup_date or date.today().isoformat()
        for item in notes.action_items:
            try:
                sb.request(
                    "POST",
                    "/tasks",
                    json_body={
                        "owner_id": owner_id,
                        "lead_id": lead_id,
                        "title": item.title[:500],
                        "notes": item.detail,
                        "due_at": f"{due}T09:00:00+00:00",
                        "status": "pending",
                    },
                    prefer="return=minimal",
                )
            except Exception as exc:
                log.info("call_notes task skipped (likely duplicate) call=%s: %s", call["id"], exc)

        try:
            insert_notification(
                sb,
                user_id=owner_id,
                notif_type="call_notes_ready",
                title="AI call notes are ready",
                body=notes.suggested_next_action or notes.summary[:300],
                dedupe_key=f"call_notes:{call['id']}",
                metadata={
                    "call_id": call["id"],
                    "lead_id": lead_id,
                    "sentiment": notes.sentiment,
                    "suggested_followup_date": notes.suggested_followup_date,
                },
            )
        except Exception as exc:
            log.warning("call_notes notification failed call=%s: %s", call["id"], exc)


# ---------------------------------------------------------------------------
# Deal health
# ---------------------------------------------------------------------------


def run_deal_health() -> str:
    """Nightly at-risk assessment across every organization's open pipeline.

    Most deals cost nothing: the graph's deterministic gate clears a deal that was touched
    recently, is on schedule and has a next step booked, without reaching a model at all.
    """
    if not ENV.ai_enabled:
        return "skip:ai_disabled"

    from dracara_ai.graphs import deal_health

    sb = SupabaseAdmin(ENV.supabase_url, ENV.supabase_service_role_key)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=DEAL_HEALTH_LOOKBACK_DAYS)).isoformat()

    rows = _scan(
        sb,
        "/opportunities",
        {
            "select": "id,organization_id,owner_id,lead_id,title,stage,quoted_value,currency,"
            "priority_score,score_override,updated_at,created_at,"
            "leads(companies(name))",
            "status": "eq.active",
            "deleted_at": "is.null",
            "created_at": f"gte.{cutoff}",
            "order": "updated_at.asc,id.asc",
        },
        feature=FEATURE_AI,
        limit=500,
    )

    assessed = 0
    flagged = 0
    for row in rows:
        try:
            deal = _build_deal_input(sb, row, now, deal_health.DealInput)
            health, usage = _run(deal_health.run(deal))
        except Exception as exc:
            log.warning("deal_health failed opportunity=%s: %s", row["id"], exc)
            continue

        org_id = row["organization_id"]
        _record_usage(sb, org_id, usage)
        assessed += 1

        try:
            # Upsert onto the day's row rather than stacking duplicates. `on_conflict` has to
            # name the unique index's columns explicitly: without it PostgREST infers the
            # conflict target from the primary key, which is a fresh uuid on every insert and
            # therefore never conflicts -- the daily unique index would then raise instead, and
            # a re-run would fail for every deal.
            sb.request(
                "POST",
                "/deal_health_snapshots",
                params={"on_conflict": "opportunity_id,snapshot_date"},
                json_body={
                    "organization_id": org_id,
                    "opportunity_id": row["id"],
                    "risk_level": health.risk_level,
                    "reasons": health.reasons,
                    "suggested_action": health.suggested_action,
                    "assessed_by_model": health.assessed_by_model,
                    "snapshot_date": now.date().isoformat(),
                    "generated_at": now.isoformat(),
                },
                prefer="return=minimal,resolution=merge-duplicates",
            )
        except Exception as exc:
            log.warning("deal_health snapshot insert failed opportunity=%s: %s", row["id"], exc)
            continue

        if health.risk_level == "high" and row.get("owner_id"):
            flagged += 1
            try:
                insert_notification(
                    sb,
                    user_id=row["owner_id"],
                    notif_type="deal_at_risk",
                    title=f"At risk: {row.get('title') or 'a deal'}",
                    body=health.suggested_action or "; ".join(health.reasons[:2]),
                    # Keyed to the day, so a deal that stays stalled is raised once a day and
                    # not once per run.
                    dedupe_key=f"deal_at_risk:{row['id']}:{now.date().isoformat()}",
                    metadata={
                        "opportunity_id": row["id"],
                        "lead_id": row.get("lead_id"),
                        "risk_level": health.risk_level,
                        "reasons": health.reasons,
                    },
                )
            except Exception as exc:
                log.warning("deal_health notification failed opportunity=%s: %s", row["id"], exc)

    return f"deal_health:assessed={assessed},flagged={flagged}"


def _build_deal_input(sb: SupabaseAdmin, row: dict[str, Any], now: datetime, cls: Any) -> Any:
    """Gather the signals one opportunity's assessment needs.

    Both reads below are pinned to the opportunity's own organization. Filtering on `lead_id`
    alone would be *almost* right -- an opportunity's lead is intra-organization by construction
    -- but this runs as the service role with no RLS behind it, and the text it gathers is fed
    straight into a prompt whose output is written to a snapshot and emailed in a daily brief.
    "Almost right" is not a good enough basis for that.
    """
    lead_id = row.get("lead_id")
    org_id = row["organization_id"]

    days_since_activity: int | None = None
    recent: list[str] = []
    if lead_id:
        activities = sb.request(
            "GET",
            "/activities",
            params={
                "select": "type,description,created_at",
                "lead_id": f"eq.{lead_id}",
                "organization_id": f"eq.{org_id}",
                "order": "created_at.desc,id.desc",
                "limit": "5",
            },
        ) or []
        recent = [
            f"{a.get('created_at', '')[:10]} {a.get('type')}: {(a.get('description') or '')[:160]}"
            for a in activities
        ]
        if activities:
            last = _parse(activities[0].get("created_at"))
            if last:
                days_since_activity = (now - last).days

    # opportunities.lead_id is NOT NULL, so this branch is defensive rather than reachable --
    # but the previous `is.null` fallback would have counted every organization's orphan tasks
    # into one deal's overdue figure, which is not a safe thing to leave lying around.
    open_tasks = (
        sb.request(
            "GET",
            "/tasks",
            params={
                "select": "id,due_at",
                "lead_id": f"eq.{lead_id}",
                "organization_id": f"eq.{org_id}",
                "status": "eq.pending",
                "limit": "50",
            },
        )
        or []
    ) if lead_id else []
    overdue = sum(1 for t in open_tasks if (_parse(t.get("due_at")) or now) < now)

    updated = _parse(row.get("updated_at"))
    company = ((row.get("leads") or {}).get("companies") or {}) if row.get("leads") else {}

    return cls(
        opportunity_id=row["id"],
        stage=row.get("stage") or "unknown",
        estimated_value=float(row["quoted_value"]) if row.get("quoted_value") is not None else None,
        currency=row.get("currency") or "INR",
        # `updated_at` moves on any edit, not only a stage change, so this is an upper bound on
        # time-in-stage rather than an exact figure. Good enough to rank deals by drift, and the
        # prompt is given the number rather than a conclusion drawn from it.
        days_in_stage=(now - updated).days if updated else 0,
        days_since_last_activity=days_since_activity,
        overdue_task_count=overdue,
        open_task_count=len(open_tasks),
        score=float(row.get("score_override") or row.get("priority_score") or 0),
        recent_activity=recent,
        company_name=company.get("name") if isinstance(company, dict) else None,
    )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Knowledge-base reindex
# ---------------------------------------------------------------------------


def run_reindex_knowledge_base() -> str:
    """Index voice-agent documents the API could not index at upload time.

    Uploads deliberately succeed even when indexing fails (an embedding outage should not lose a
    user's file), which leaves rows with `indexed_at IS NULL`. This is the retry.

    The document bytes come back out of Supabase Storage, which is what makes "Postgres is the
    record, Qdrant is a derived index" true rather than aspirational: the vector store can be
    rebuilt from scratch at any time.
    """
    if not ENV.ai_enabled:
        return "skip:ai_disabled"

    import httpx
    from dracara_ai import chunking, embeddings, vector_store
    from dracara_ai.extract import extract_text, is_supported

    sb = SupabaseAdmin(ENV.supabase_url, ENV.supabase_service_role_key)
    rows = _scan(
        sb,
        "/voice_agent_documents",
        {
            "select": "id,organization_id,voice_agent_id,filename,file_url",
            "indexed_at": "is.null",
            "order": "created_at.asc,id.asc",
        },
        feature=FEATURE_VOICE_AGENTS,
        limit=ENV.ai_batch_limit,
    )

    indexed = 0
    for doc in rows:
        if not is_supported(doc.get("filename") or ""):
            # Permanently unindexable: stamp it so the scan stops picking it up every tick.
            sb.request(
                "PATCH",
                "/voice_agent_documents",
                params={
                    "id": f"eq.{doc['id']}",
                    "organization_id": f"eq.{doc['organization_id']}",
                },
                json_body={
                    "index_error": "This file type cannot be indexed.",
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                    "chunk_count": 0,
                },
                prefer="return=minimal",
            )
            continue

        try:
            response = httpx.get(
                f"{ENV.supabase_url.rstrip('/')}/storage/v1/object/"
                f"{ENV.voice_kb_bucket}/{doc['file_url']}",
                headers={"Authorization": f"Bearer {ENV.supabase_service_role_key}"},
                timeout=60.0,
            )
            response.raise_for_status()
            text = extract_text(response.content, doc["filename"])
            chunks = chunking.chunk_text(text)
            vectors = _run(embeddings.embed_texts(chunks))
            written = _run(
                vector_store.upsert_document_chunks(
                    organization_id=doc["organization_id"],
                    voice_agent_id=doc["voice_agent_id"],
                    document_id=doc["id"],
                    filename=doc["filename"],
                    chunks=chunks,
                    vectors=vectors,
                )
            )
        except Exception as exc:
            log.warning("reindex failed document=%s: %s", doc["id"], exc)
            sb.request(
                "PATCH",
                "/voice_agent_documents",
                params={
                    "id": f"eq.{doc['id']}",
                    "organization_id": f"eq.{doc['organization_id']}",
                },
                json_body={"index_error": str(exc)[:500]},
                prefer="return=minimal",
            )
            continue

        sb.request(
            "PATCH",
            "/voice_agent_documents",
            params={"id": f"eq.{doc['id']}"},
            json_body={
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "chunk_count": written,
                "extracted_chars": len(text),
                "index_error": None,
            },
            prefer="return=minimal",
        )
        indexed += 1

    return f"reindexed:{indexed}"
