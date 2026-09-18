"""Celery worker — §15 jobs with Supabase service role."""

from __future__ import annotations

import html
import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from celery import Celery
from celery.schedules import crontab

from dracara_billing import entitlements

from env import ENV
from scoring import compute_priority_score
from supabase_admin import SupabaseAdmin, insert_notification

log = logging.getLogger(__name__)

if ENV.sentry_dsn:
    # Scheduled jobs fail silently otherwise: nobody is watching a beat tick. CeleryIntegration
    # reports every task exception with the task name; request data is never attached.
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=ENV.sentry_dsn,
        environment=ENV.environment,
        release=ENV.release or None,
        send_default_pii=False,
        integrations=[CeleryIntegration(monitor_beat_tasks=True)],
    )

REDIS_URL = ENV.redis_url or "redis://localhost:6379/0"
app = Celery("growth_os", broker=REDIS_URL, backend=REDIS_URL)

app.conf.beat_schedule = {
    "followup-reminder": {"task": "worker_app.followup_reminder", "schedule": crontab(minute="*/30")},
    "no-touch-alert": {"task": "worker_app.no_touch_alert", "schedule": crontab(minute=0, hour="*/6")},
    "score-recalculate": {"task": "worker_app.score_recalculate", "schedule": crontab(minute=0)},
    "calendar-sync": {"task": "worker_app.calendar_sync", "schedule": crontab(minute="*/15")},
    "post-meeting-prompt": {"task": "worker_app.post_meeting_prompt", "schedule": crontab(minute="*/5")},
    "overdue-escalation": {"task": "worker_app.overdue_escalation", "schedule": crontab(minute=0, hour=9)},
    "daily-brief": {"task": "worker_app.daily_brief", "schedule": crontab(minute=0, hour=8)},
    "stale-call-reconciliation": {
        "task": "worker_app.stale_call_reconciliation",
        "schedule": crontab(minute="*/10"),
    },
    # AI jobs. Call notes are near-real-time (a rep opening the call log right after a call
    # should find them); deal health runs nightly and reaches owners through per-tenant
    # notifications (never the global daily brief); reindexing is a slow retry path for uploads that failed to index.
    "call-notes": {"task": "worker_app.call_notes", "schedule": crontab(minute="*/2")},
    "deal-health": {"task": "worker_app.deal_health", "schedule": crontab(minute=0, hour=7)},
    "calendar-push": {"task": "worker_app.calendar_push", "schedule": crontab(minute="*/2")},
    "reindex-knowledge-base": {
        "task": "worker_app.reindex_knowledge_base",
        "schedule": crontab(minute=30, hour="*/2"),
    },
}


def _sb() -> SupabaseAdmin:
    if not ENV.supabase_url or not ENV.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for worker")
    return SupabaseAdmin(ENV.supabase_url, ENV.supabase_service_role_key)


def _today_iso() -> str:
    return date.today().isoformat()


def _full_access_users(sb: SupabaseAdmin) -> list[dict]:
    """Every active user, in every organization, whose role grants full access.

    "Admin" is organization-configurable data (roles.grants_full_access), not a column on users:
    the old ``users.role`` enum was dropped by the dynamic-roles migration, and a query that
    still filtered on it failed every run. Callers group by ``organization_id`` themselves.
    """
    return sb.request(
        "GET",
        "/users",
        params={
            "select": "id,email,full_name,organization_id,roles!inner(grants_full_access)",
            "roles.grants_full_access": "eq.true",
            "is_active": "eq.true",
        },
    ) or []


def _writable_org_ids(sb: SupabaseAdmin) -> set[str] | None:
    """Organizations on a live plan (paid or in trial), or None when billing has no rows at all
    (not set up -- fail open, as the API's plan gate does)."""
    rows = sb.request(
        "GET",
        "/organization_subscriptions",
        params={"select": "organization_id,plan,status,seats,trial_ends_at,current_period_end"},
    ) or []
    if not rows:
        return None
    return {str(r["organization_id"]) for r in rows if entitlements(r).writable}


@app.task(name="worker_app.followup_reminder")
def followup_reminder() -> str:
    """Remind owners of tasks falling due in the next hour.

    tasks.due_at is an absolute instant, so this no longer depends on the worker host's
    calendar day agreeing with the owner's -- which it did not for anyone outside UTC.
    """
    sb = _sb()
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=1)
    rows = sb.request(
        "GET",
        "/tasks",
        params={
            "select": "id,owner_id,title,lead_id,due_at",
            "due_at": f"gte.{now.isoformat()}",
            "and": f"(due_at.lt.{window_end.isoformat()})",
            "status": "eq.pending",
            "limit": "1000",
        },
    )
    tasks = rows or []
    for t in tasks:
        oid = str(t["owner_id"])
        tid = str(t["id"])
        insert_notification(
            sb,
            user_id=oid,
            notif_type="followup_reminder",
            title="Follow-up due soon",
            body=str(t.get("title") or "Task"),
            # One reminder per task per due instant: rescheduling a task should be able to
            # produce a fresh reminder, whereas a re-run within the window should not.
            dedupe_key=f"followup_reminder:{tid}:{t.get('due_at')}",
            metadata={"task_id": tid, "lead_id": str(t.get("lead_id"))},
            source_task_id=tid,
        )
    return f"ok:{len(tasks)}"


@app.task(name="worker_app.no_touch_alert")
def no_touch_alert() -> str:
    sb = _sb()
    cutoff = date.today() - timedelta(days=14)
    # Filter upstream instead of pulling every lead and discarding most of them in Python:
    # already-flagged rows and recently-contacted rows can never produce an alert.
    rows = sb.request(
        "GET",
        "/leads",
        params={
            "select": "id,owner_id,last_contact_date,no_touch_alert",
            "no_touch_alert": "is.false",
            "or": f"(last_contact_date.is.null,last_contact_date.lt.{cutoff.isoformat()})",
            "limit": "5000",
        },
    )
    leads = rows or []
    n = 0
    for row in leads:
        lcd = row.get("last_contact_date")
        lid = str(row["id"])
        sb.request(
            "PATCH",
            "/leads",
            params={"id": f"eq.{lid}"},
            json_body={"no_touch_alert": True},
            prefer="return=minimal",
        )
        insert_notification(
            sb,
            user_id=str(row["owner_id"]),
            notif_type="no_touch",
            title="Lead inactive 14+ days",
            body=f"Last contact: {lcd}",
            dedupe_key=f"no_touch:{lid}:{_today_iso()}",
            metadata={"lead_id": lid},
        )
        n += 1
    return f"flagged:{n}"


@app.task(name="worker_app.score_recalculate")
def score_recalculate() -> str:
    """Recompute priority scores for recently-touched pursuits.

    Scores are a property of the opportunity: they derive from quoted value, probability and
    stage, all of which live there since leads and opportunities were separated. This job
    used to read those columns off leads, where they were mirrored copies.
    """
    sb = _sb()
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    rows = sb.request(
        "GET",
        "/opportunities",
        params={"select": "*", "updated_at": f"gte.{since}", "limit": "1000"},
    )
    opportunities = rows or []
    updated = 0
    for opp in opportunities:
        oid = str(opp["id"])
        lead_id = str(opp["lead_id"])
        intel_rows = sb.request(
            "GET", "/lead_intelligence", params={"select": "*", "lead_id": f"eq.{lead_id}"}
        )
        intel = intel_rows[0] if intel_rows else None
        ov = opp.get("score_override")
        score = compute_priority_score(
            estimated_value=float(opp["quoted_value"]) if opp.get("quoted_value") is not None else None,
            currency=str(opp.get("currency") or "INR"),
            deal_probability=int(opp.get("deal_probability") or 50),
            stage=str(opp.get("stage")),
            next_followup_date=None,
            intelligence=intel,
            score_override=int(ov) if ov is not None else None,
        )

        # Writing unconditionally was self-perpetuating: the PATCH bumps updated_at, putting
        # the row back inside the next run's "changed in the last hour" window. Every row it
        # touched stayed in scope forever and the job degenerated into an hourly full rewrite.
        if int(opp.get("priority_score") or 0) == score:
            continue

        sb.request(
            "PATCH",
            "/opportunities",
            params={"id": f"eq.{oid}"},
            json_body={"priority_score": score},
            prefer="return=minimal",
        )
        updated += 1
    return f"scores:{updated}"


@app.task(name="worker_app.calendar_sync")
def calendar_sync() -> str:
    if not ENV.google_client_id or not ENV.google_client_secret:
        return "skip:no_google_config"
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return "skip:google_libs_missing"

    sb = _sb()
    users = sb.request(
        "GET",
        "/users",
        params={"select": "id,google_refresh_token,google_access_token", "google_refresh_token": "not.is.null"},
    )
    if not users:
        return "sync:0"
    inserted = 0
    for u in users:
        # Shared with calendar_push so the two directions cannot drift on scopes or token
        # persistence -- see _google_credentials.
        creds = _google_credentials(sb, u)
        if creds is None:
            continue

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        now = datetime.now(timezone.utc).isoformat()
        later = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        ev = (
            service.events()
            .list(calendarId="primary", timeMin=now, timeMax=later, singleEvents=True, orderBy="startTime")
            .execute()
        )
        uid = str(u["id"])
        for item in ev.get("items", [])[:200]:
            eid = item.get("id")
            start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            if not start or not eid:
                continue
            scheduled_at = start if "T" in start else f"{start}T09:00:00+00:00"
            existing = sb.request("GET", "/meetings", params={"select": "id", "google_event_id": f"eq.{eid}"})
            if existing:
                continue
            title = (item.get("summary") or "Calendar event")[:500]
            payload = {
                "owner_id": uid,
                "lead_id": None,
                "title": title,
                "scheduled_at": scheduled_at,
                "google_event_id": eid,
                "google_meet_link": item.get("hangoutLink"),
                "status": "scheduled",
            }
            try:
                sb.request("POST", "/meetings", json_body=payload, prefer="return=minimal")
                inserted += 1
            except RuntimeError as ex:
                if "23502" in str(ex) or "null value" in str(ex).lower():
                    log.warning(
                        "Skipping calendar insert (migration 20260429120003 may be pending): %s",
                        ex,
                    )
                    continue
                raise
    return f"inserted:{inserted}"


@app.task(name="worker_app.post_meeting_prompt")
def post_meeting_prompt() -> str:
    sb = _sb()
    now = datetime.now(timezone.utc)
    # The prompt window is the 15 minutes after a meeting ends, so only recent meetings can
    # ever qualify. Without a lower bound this scanned every scheduled meeting ever recorded,
    # growing unboundedly while the job runs every five minutes.
    window_start = (now - timedelta(hours=6)).isoformat()
    rows = sb.request(
        "GET",
        "/meetings",
        params={
            "select": "*",
            "status": "eq.scheduled",
            "outcome": "is.null",
            "scheduled_at": f"gte.{window_start}",
            "order": "scheduled_at.asc",
            "limit": "500",
        },
    )
    meetings = rows or []
    n = 0
    for m in meetings:
        try:
            start = datetime.fromisoformat(str(m["scheduled_at"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        dur = int(m.get("duration_minutes") or 30)
        end = start + timedelta(minutes=dur)
        if end <= now <= end + timedelta(minutes=15):
            oid = str(m["owner_id"])
            mid = str(m["id"])
            insert_notification(
                sb,
                user_id=oid,
                notif_type="post_meeting",
                title="Capture meeting outcome",
                body=str(m.get("title")),
                dedupe_key=f"post_meeting:{mid}",
                meeting_id=mid,
                metadata={"meeting_id": mid},
            )
            n += 1
    return f"prompts:{n}"


@app.task(name="worker_app.overdue_escalation")
def overdue_escalation() -> str:
    sb = _sb()
    now_iso = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    rows = sb.request(
        "GET",
        "/tasks",
        params={
            "select": "id,owner_id,title,due_at,organization_id",
            "due_at": f"lt.{now_iso}",
            "status": "eq.pending",
            "order": "due_at.asc",
            "limit": "1000",
        },
    )
    tasks = rows or []
    admins = _full_access_users(sb)
    # Admins are scoped to their own tenant -- an admin in one organization must never be
    # notified about (or learn the existence of) an overdue task in another's.
    admin_ids_by_org: dict[str, list[str]] = {}
    for a in admins or []:
        admin_ids_by_org.setdefault(str(a["organization_id"]), []).append(str(a["id"]))
    for t in tasks:
        oid = str(t["owner_id"])
        tid = str(t["id"])
        org_id = str(t["organization_id"])
        insert_notification(
            sb,
            user_id=oid,
            notif_type="task_overdue",
            title="Overdue task",
            body=str(t.get("title")),
            dedupe_key=f"overdue:{tid}:{today}",
            metadata={"task_id": tid},
            source_task_id=tid,
        )
        for aid in admin_ids_by_org.get(org_id, []):
            insert_notification(
                sb,
                user_id=aid,
                notif_type="task_overdue_admin",
                title="Team overdue task",
                body=str(t.get("title")),
                dedupe_key=f"overdue_admin:{tid}:{aid}:{today}",
                metadata={"task_id": tid, "owner_id": oid},
            )
    return f"escalated:{len(tasks)}"


def _count_by_org(rows: list[dict] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows or []:
        key = str(row["organization_id"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def _brief_html(*, name: str, org_name: str, due_today: int, overdue: int, new_leads: int) -> str:
    link = f"{ENV.web_app_url.rstrip('/')}/dashboard"
    rows = "".join(
        f"<tr><td style='padding:4px 16px 4px 0'>{label}</td>"
        f"<td style='padding:4px 0;font-weight:600'>{value}</td></tr>"
        for label, value in (
            ("Follow-ups due today", due_today),
            ("Overdue follow-ups", overdue),
            ("New leads in the last 24 hours", new_leads),
        )
    )
    return (
        f"<p>Good morning {html.escape(name)},</p>"
        f"<p>Here is today's picture for <strong>{html.escape(org_name)}</strong>:</p>"
        f"<table>{rows}</table>"
        f"<p><a href='{html.escape(link)}'>Open your dashboard</a></p>"
        "<p style='color:#6b7280;font-size:12px'>You receive this because you are an admin of "
        "this workspace in Dracara Growth OS.</p>"
    )


@app.task(name="worker_app.daily_brief")
def daily_brief() -> str:
    """Morning email to each organization's admins, about their own organization only.

    Every count is grouped by the row's own ``organization_id`` and sent only to that
    organization's full-access users, the same routing rule as ``overdue_escalation``. Lapsed
    organizations (expired trial, cancelled plan) are skipped rather than emailed forever.
    """
    if not ENV.resend_api_key:
        return "skip:no_resend"
    sb = _sb()
    now = datetime.now(timezone.utc)
    today = date.today()
    tomorrow = today + timedelta(days=1)

    live_orgs = _writable_org_ids(sb)
    due_today = _count_by_org(
        sb.request(
            "GET",
            "/tasks",
            params={
                "select": "organization_id",
                "status": "eq.pending",
                "and": f"(due_at.gte.{today.isoformat()}T00:00:00+00:00,"
                f"due_at.lt.{tomorrow.isoformat()}T00:00:00+00:00)",
                "limit": "10000",
            },
        )
    )
    overdue = _count_by_org(
        sb.request(
            "GET",
            "/tasks",
            params={
                "select": "organization_id",
                "status": "eq.pending",
                "due_at": f"lt.{today.isoformat()}T00:00:00+00:00",
                "limit": "10000",
            },
        )
    )
    new_leads = _count_by_org(
        sb.request(
            "GET",
            "/leads",
            params={
                "select": "organization_id",
                "created_at": f"gte.{(now - timedelta(days=1)).isoformat()}",
                "deleted_at": "is.null",
                "limit": "10000",
            },
        )
    )
    org_names = {
        str(o["id"]): o.get("name") or "your workspace"
        for o in sb.request("GET", "/organizations", params={"select": "id,name"}) or []
    }

    sent = 0
    for admin in _full_access_users(sb):
        org_id = str(admin["organization_id"])
        if not admin.get("email") or (live_orgs is not None and org_id not in live_orgs):
            continue
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {ENV.resend_api_key}",
                    "Content-Type": "application/json",
                    # A retried task must not email the same person twice in one day.
                    "Idempotency-Key": f"daily-brief/{admin['id']}/{today.isoformat()}",
                },
                json={
                    "from": ENV.email_from,
                    "to": [admin["email"]],
                    "subject": f"Your Dracara brief for {today.strftime('%d %b')}",
                    "html": _brief_html(
                        name=admin.get("full_name") or "there",
                        org_name=org_names.get(org_id, "your workspace"),
                        due_today=due_today.get(org_id, 0),
                        overdue=overdue.get(org_id, 0),
                        new_leads=new_leads.get(org_id, 0),
                    ),
                },
                timeout=30.0,
            )
            response.raise_for_status()
            sent += 1
        except Exception as e:
            log.warning("daily brief failed user=%s: %s", admin["id"], e)
    return f"sent:{sent}"


@app.task(name="worker_app.stale_call_reconciliation")
def stale_call_reconciliation() -> str:
    """Safety net for a lost webhook: an AI call that never received a terminal status update
    from the voice platform would otherwise stay 'in_progress' forever. A real call lasts
    minutes, not an hour, so a one-hour timeout is generous rather than a live platform status
    check -- simpler, and avoids duplicating the API's voice_platform adapter into the worker.
    """
    sb = _sb()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    stale = sb.request(
        "GET",
        "/calls",
        params={
            "select": "id",
            "status": "in.(queued,ringing,in_progress)",
            "created_at": f"lt.{cutoff}",
            "limit": "500",
        },
    )
    rows = stale or []
    for row in rows:
        sb.request(
            "PATCH",
            "/calls",
            params={"id": f"eq.{row['id']}"},
            json_body={"status": "failed", "outcome": "reconciled: no terminal status received"},
            prefer="return=minimal",
        )
    return f"reconciled:{len(rows)}"


# ---------------------------------------------------------------------------
# AI jobs. The implementations live in ai_jobs.py; these are the Celery bindings.
# ---------------------------------------------------------------------------


@app.task(name="worker_app.call_notes")
def call_notes() -> str:
    """Summarise finished calls, extract action items, create the follow-up tasks."""
    from ai_jobs import run_call_notes

    return run_call_notes()


@app.task(name="worker_app.deal_health")
def deal_health() -> str:
    """Nightly at-risk assessment over every organization's open pipeline."""
    from ai_jobs import run_deal_health

    return run_deal_health()


@app.task(name="worker_app.reindex_knowledge_base")
def reindex_knowledge_base() -> str:
    """Retry indexing for voice-agent documents that failed at upload time."""
    from ai_jobs import run_reindex_knowledge_base

    return run_reindex_knowledge_base()


# ---------------------------------------------------------------------------
# Google Calendar push.
# ---------------------------------------------------------------------------


def _google_credentials(sb: SupabaseAdmin, user: dict) -> object | None:
    """Refresh and return one user's Google credentials, persisting the new access token.

    Extracted so calendar_sync (pull) and calendar_push (push) cannot drift on token handling --
    the scope list in particular, which silently degrades to "read only" if the two disagree.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    refresh_token = user.get("google_refresh_token")
    if not refresh_token:
        return None

    creds = Credentials(
        token=user.get("google_access_token"),
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=ENV.google_client_id,
        client_secret=ENV.google_client_secret,
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    try:
        creds.refresh(Request())
    except Exception as e:
        log.warning("calendar token refresh failed for %s: %s", user.get("id"), e)
        return None

    sb.request(
        "PATCH",
        "/users",
        params={"id": f"eq.{user['id']}"},
        json_body={"google_access_token": creds.token},
        prefer="return=minimal",
    )
    return creds


@app.task(name="worker_app.calendar_push")
def calendar_push() -> str:
    """Push CRM-created meetings out to the owner's Google Calendar.

    calendar_sync only ever pulled *from* Google, which is why voice_tools.book_appointment used
    to end with an apology -- the AI agent could book a meeting on a live call and the rep would
    never see it on their calendar. This is the missing direction.

    `google_event_id IS NULL` is what identifies a meeting that originated in the CRM: rows pulled
    from Google always carry one. Writing the id back is also what makes this idempotent, and the
    column's UNIQUE constraint is the backstop if two workers race.
    """
    if not ENV.google_client_id or not ENV.google_client_secret:
        return "skip:no_google_config"
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return "skip:google_libs_missing"

    sb = _sb()
    # Only forward-looking meetings: back-filling a month of history into someone's calendar the
    # first time this job runs would be worse than not running it.
    now = datetime.now(timezone.utc)
    rows = sb.request(
        "GET",
        "/meetings",
        params={
            "select": "id,owner_id,title,scheduled_at,duration_minutes,lead_id",
            "google_event_id": "is.null",
            "status": "eq.scheduled",
            "scheduled_at": f"gte.{now.isoformat()}",
            "order": "scheduled_at.asc,id.asc",
            "limit": "100",
        },
    ) or []
    if not rows:
        return "pushed:0"

    # One credential refresh per owner rather than per meeting.
    credentials_by_owner: dict[str, object | None] = {}
    pushed = 0

    for meeting in rows:
        owner_id = str(meeting["owner_id"])
        if owner_id not in credentials_by_owner:
            users = sb.request(
                "GET",
                "/users",
                params={
                    "select": "id,google_refresh_token,google_access_token",
                    "id": f"eq.{owner_id}",
                },
            )
            user = (users or [None])[0]
            credentials_by_owner[owner_id] = _google_credentials(sb, user) if user else None

        creds = credentials_by_owner[owner_id]
        if creds is None:
            # The rep has not connected Google. The meeting still exists in the CRM; there is
            # simply nowhere to push it.
            continue

        start = _parse_instant(meeting.get("scheduled_at"))
        if start is None:
            log.warning("calendar_push bad scheduled_at meeting=%s", meeting["id"])
            continue
        end = start + timedelta(minutes=int(meeting.get("duration_minutes") or 30))

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            event = (
                service.events()
                .insert(
                    calendarId="primary",
                    body={
                        "summary": meeting.get("title") or "Meeting",
                        "description": "Created in Dracara Growth OS.",
                        "start": {"dateTime": start.isoformat()},
                        "end": {"dateTime": end.isoformat()},
                    },
                )
                .execute()
            )
        except Exception as e:
            log.warning("calendar_push insert failed meeting=%s: %s", meeting["id"], e)
            continue

        sb.request(
            "PATCH",
            "/meetings",
            params={"id": f"eq.{meeting['id']}"},
            json_body={
                "google_event_id": event.get("id"),
                "google_meet_link": event.get("hangoutLink"),
            },
            prefer="return=minimal",
        )
        pushed += 1

    return f"pushed:{pushed}"


def _parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
