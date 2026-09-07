# Dracara Growth OS — Worker

A Celery worker running scheduled background jobs against Supabase with the service-role key. It has no per-request user token — every job acts with full database access and is responsible for its own tenant scoping, unlike the API, which relies on row-level security as the calling user.

## 1. Why a separate process

Some work does not belong in the request/response cycle of an API call: reminders that fire on a clock rather than in response to a user action, staleness checks that scan every organization, and a nightly digest email. This process exists to run that work on a schedule, independent of whether anyone is using the app at that moment.

## 2. Scheduled jobs

Defined in `worker_app.py`'s `beat_schedule`:

| Job | Schedule | What it does |
| --- | --- | --- |
| `followup_reminder` | Every 30 minutes | Finds tasks due today and not yet completed; notifies the owner. |
| `no_touch_alert` | Every 6 hours | Flags leads with no activity in 14+ days. |
| `score_recalculate` | Hourly | Recomputes the weighted opportunity score for opportunities updated in the last hour, using `packages/scoring`. |
| `calendar_sync` | Every 15 minutes | Pulls each connected user's upcoming Google Calendar events into the `meetings` table. Read-only from Google's side — there is no path in the other direction yet; a meeting created in the CRM does not currently get pushed to Google Calendar. |
| `post_meeting_prompt` | Every 5 minutes | Notifies a meeting's owner to capture its outcome once the meeting has ended. |
| `overdue_escalation` | 09:00 daily | Notifies a task's owner, and that organization's admins, about tasks past their due date. |
| `daily_brief` | 08:00 daily | Emails a single configured address a summary of the day's follow-ups, via Resend. |
| `stale_call_reconciliation` | Every 10 minutes | Marks an AI voice call `failed` if it has sat in `queued`/`ringing`/`in_progress` for over an hour — the safety net for a voice-platform webhook that never arrived. |

Every job that writes an in-app notification goes through `insert_notification()` in `supabase_admin.py`, which uses a `dedupe_key` and a unique index on that column to make re-running a job idempotent — a job that fires twice for the same event does not double-notify anyone.

## 3. Multi-tenancy in a service-role process

The worker has no `organization_id` scoping built into its Supabase client — most jobs scan across every organization in one query and rely on the row's own `organization_id`/`owner_id` column to route the resulting notification correctly, rather than filtering the query itself by tenant. `overdue_escalation` is the clearest example: it fetches all overdue tasks and all admins in one call each, then groups admins by `organization_id` in Python before notifying them, so an admin in one organization is never notified about another organization's task.

## 4. Running it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip

# Windows: the solo pool does not support an embedded scheduler, so worker and
# beat are two separate processes.
.venv\Scripts\celery -A worker_app worker --loglevel=info -P solo
.venv\Scripts\celery -A worker_app beat --loglevel=info

# macOS/Linux: -B runs worker and beat together in one process.
.venv/bin/celery -A worker_app worker -B --loglevel=info
```

Requires a reachable Redis instance (`REDIS_URL`) as the Celery broker and result backend. See `../../SETUP.md` section 4.3 for the full environment-variable list.

## 5. Testing

```bash
.venv/bin/python -m pytest -q      # Windows: .venv\Scripts\python
```

`tests/test_jobs.py` covers the scheduled jobs. `packages/scoring` is installed from the workspace (`-e ../../packages/scoring`) so this process runs the exact same scoring implementation as the API — the two used to be independent copies that could silently drift, which a parity test caught and this shared package now makes structurally impossible.
