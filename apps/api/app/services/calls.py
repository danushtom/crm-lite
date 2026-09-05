"""Call finalization: writes the activity-timeline entry and the rep's notification once a
call reaches a terminal status. Runs with the service-role client -- there is no caller JWT in
a webhook handler, so this cannot go through the normal RLS-scoped `leads.py::create_activity`
path. Mirrors the shape of `apps/worker/supabase_admin.py::insert_notification()` rather than
importing across the API/worker package boundary (this codebase already duplicates such
helpers rather than sharing a module -- see the Google OAuth settings in both apps/api and
apps/worker for the established precedent).
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.supabase import SupabaseAdminClient
from app.domain.enums import CallStatus

logger = logging.getLogger(__name__)


_NOTIFICATION_BY_STATUS = {
    CallStatus.COMPLETED: ("call_completed", "AI call completed"),
    CallStatus.FAILED: ("call_failed", "AI call failed"),
    CallStatus.NO_CONSENT_BLOCKED: ("call_blocked", "AI call blocked: no consent on file"),
}


async def finalize_call(admin_db: SupabaseAdminClient, call: dict[str, Any]) -> None:
    """`call` is the full, just-updated `calls` row (organization_id already resolved)."""
    call_id = call["id"]
    lead_id = call.get("lead_id")
    status = call.get("status")

    if lead_id:
        await admin_db.insert(
            "activities",
            {
                "lead_id": lead_id,
                "type": "call",
                "description": call.get("summary") or f"AI call {status}",
                "outcome": call.get("outcome"),
                "actor_type": "system",
                "performed_by": None,
                "metadata": {
                    "call_id": call_id,
                    "recording_url": call.get("recording_url"),
                    "duration_seconds": call.get("duration_seconds"),
                },
            },
        )

        lead_result = await admin_db.select(
            "leads", params={"select": "owner_id", "id": f"eq.{lead_id}"}
        )
        lead = lead_result.first()
        notif_type, title = _NOTIFICATION_BY_STATUS.get(status, ("call_completed", "AI call completed"))
        if lead and lead.get("owner_id"):
            await admin_db.insert(
                "notifications",
                {
                    "user_id": lead["owner_id"],
                    "type": notif_type,
                    "title": title,
                    "body": call.get("summary") or call.get("suggested_next_action"),
                    "metadata": {
                        "call_id": call_id,
                        "lead_id": lead_id,
                        "suggested_next_action": call.get("suggested_next_action"),
                    },
                    "dedupe_key": f"{notif_type}:{call_id}",
                },
            )

    if status == CallStatus.NO_CONSENT_BLOCKED:
        logger.warning("voice_call_blocked_no_consent call_id=%s", call_id)
