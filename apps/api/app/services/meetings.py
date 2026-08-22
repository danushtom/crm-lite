"""Meeting outcome handling, including the automatic follow-up rule (tdd.md 14.2)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.supabase import SupabaseClient
from app.domain.enums import OUTCOMES_REQUIRING_FOLLOWUP, MeetingOutcome

logger = logging.getLogger(__name__)

FOLLOWUP_DELAY_DAYS = 2


async def record_outcome(
    db: SupabaseClient,
    meeting_id: str,
    changes: dict[str, Any],
    *,
    owner_id: str,
) -> tuple[dict[str, Any], str | None]:
    """Persist a meeting outcome and, when it implies a next step, schedule the follow-up.

    Returns the updated meeting and the id of any follow-up task created.
    """
    meeting = (
        await db.select("meetings", params={"select": "*", "id": f"eq.{meeting_id}"})
    ).one("Meeting")

    updated = await db.update("meetings", {"id": f"eq.{meeting_id}"}, changes)
    result = updated.one("Meeting")

    outcome = changes.get("outcome")
    lead_id = meeting.get("lead_id")

    # Calendar-synced meetings can exist without a lead; there is nothing to follow up on.
    if lead_id is None or outcome not in OUTCOMES_REQUIRING_FOLLOWUP:
        return result, None

    # An absolute instant, so the follow-up lands correctly whatever zone the owner is in.
    due = (datetime.now(timezone.utc) + timedelta(days=FOLLOWUP_DELAY_DAYS)).isoformat()
    label = MeetingOutcome(outcome).value.replace("_", " ")
    task = await db.insert(
        "tasks",
        {
            "lead_id": lead_id,
            "owner_id": owner_id,
            "title": f"Follow up after meeting ({label})",
            "due_at": due,
            "status": "pending",
            "notes": changes.get("outcome_notes"),
        },
    )
    created = task.first()
    task_id = str(created["id"]) if created else None
    logger.info("auto_followup_created meeting=%s task=%s outcome=%s", meeting_id, task_id, outcome)
    return result, task_id
