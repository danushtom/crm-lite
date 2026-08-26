"""Celery worker — §15 jobs with Supabase service role."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from celery import Celery
from celery.schedules import crontab

from env import ENV
from scoring import compute_priority_score
from supabase_admin import SupabaseAdmin, insert_notification

log = logging.getLogger(__name__)

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
}


def _sb() -> SupabaseAdmin:
    if not ENV.supabase_url or not ENV.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required for worker")
    return SupabaseAdmin(ENV.supabase_url, ENV.supabase_service_role_key)


def _today_iso() -> str:
    return date.today().isoformat()


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
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
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
        rt = u.get("google_refresh_token")
        if not rt:
            continue
        creds = Credentials(
            token=u.get("google_access_token"),
            refresh_token=rt,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=ENV.google_client_id,
            client_secret=ENV.google_client_secret,
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        try:
            creds.refresh(Request())
        except Exception as e:
            log.warning("calendar token refresh failed for %s: %s", u["id"], e)
            continue

        sb.request(
            "PATCH",
            "/users",
            params={"id": f"eq.{u['id']}"},
            json_body={"google_access_token": creds.token},
            prefer="return=minimal",
        )

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
            "select": "id,owner_id,title,due_at",
            "due_at": f"lt.{now_iso}",
            "status": "eq.pending",
            "order": "due_at.asc",
            "limit": "1000",
        },
    )
    tasks = rows or []
    admins = sb.request("GET", "/users", params={"select": "id", "role": "eq.admin"})
    admin_ids = [str(a["id"]) for a in (admins or [])]
    for t in tasks:
        oid = str(t["owner_id"])
        tid = str(t["id"])
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
        for aid in admin_ids:
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


@app.task(name="worker_app.daily_brief")
def daily_brief() -> str:
    if not ENV.resend_api_key or not ENV.admin_email:
        return "skip:no_resend"
    sb = _sb()
    today = _today_iso()
    tasks_today = sb.request(
        "GET",
        "/tasks",
        params={
            "select": "id",
            "due_at": f"gte.{date.today().isoformat()}T00:00:00+00:00",
            "and": f"(due_at.lt.{(date.today() + timedelta(days=1)).isoformat()}T00:00:00+00:00)",
            "status": "eq.pending",
        },
    )
    n_tasks = len(tasks_today or [])
    html = f"<p>Daily brief — follow-ups due today: {n_tasks}</p>"
    try:
        httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {ENV.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": "Growth OS <onboarding@resend.dev>",
                "to": [ENV.admin_email],
                "subject": f"Dracara daily brief {today}",
                "html": html,
            },
            timeout=30.0,
        )
    except Exception as e:
        log.warning("Resend failed: %s", e)
        return f"fail:{e}"
    return "sent"
