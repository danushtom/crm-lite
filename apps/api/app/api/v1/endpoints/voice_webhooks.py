"""Callbacks from the voice platform: call lifecycle events and mid-call tool-calling.

No `CurrentUserDep`/`DbDep`/`AdminDep` anywhere in this module -- their absence is what skips
Supabase-JWT auth entirely (the same mechanism app/api/health.py relies on), since the caller
here is the voice platform, not a logged-in user. Every route is signature-verified instead
(see app/core/webhook_security.py) and `@limiter.exempt`, matching how health probes are
exempted, so the platform's retries never compete with the per-token/IP default quota.

CRITICAL SECURITY PATTERN: a payload's own `organization_id`/metadata claims are never trusted
directly. `organization_id` is always resolved server-side from `calls.id` (the call_id we
minted and handed to the platform at dial time, in `metadata`), via a service-role lookup.
Every subsequent query in this module is scoped by that resolved value, never by anything the
payload itself claims. This mirrors the only existing precedent for "org id derived from a
trusted DB lookup, not client input" in this codebase: `overdue_escalation` in
apps/worker/worker_app.py.

NOTE: the exact payload shape assumed below (Vapi's `message.type` envelope) reflects the
platform's public webhook format at the time this was written and was not verified against a
live account -- confirm against https://docs.vapi.ai/server-url before relying on it in
production.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, Request

from app.api.deps import AdminDbDep
from app.core.errors import UnauthorizedError
from app.core.rate_limit import limiter
from app.core.webhook_security import verify_platform_signature
from app.services.calls import finalize_call
from app.services.voice_tools import dispatch as dispatch_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-webhooks", tags=["Voice Webhooks"])

_STATUS_MAP = {
    "queued": "queued",
    "ringing": "ringing",
    "in-progress": "in_progress",
    "in_progress": "in_progress",
    "forwarding": "in_progress",
    "completed": "completed",
    "ended": "completed",
    "failed": "failed",
    "no-answer": "failed",
    "busy": "failed",
}


async def _resolve_call(admin_db: AdminDbDep, call_id: str) -> dict[str, Any] | None:
    """The one trusted lookup every handler in this module keys off."""
    result = await admin_db.select("calls", params={"select": "*", "id": f"eq.{call_id}"})
    return result.first()


async def _resolve_or_create_inbound_call(
    admin_db: AdminDbDep, message: dict[str, Any]
) -> dict[str, Any] | None:
    """Outbound calls always carry our own call_id in metadata (set at dial time). An inbound
    call has no such row yet -- resolve the org from the number that was dialed instead, and
    create the row on first contact. If a row already exists for this provider_call_id
    (a later event for the same call), reuse it rather than creating a duplicate."""
    call_payload = message.get("call", {})
    provider_call_id = call_payload.get("id")
    if provider_call_id:
        existing = await admin_db.select(
            "calls", params={"select": "*", "provider_call_id": f"eq.{provider_call_id}"}
        )
        row = existing.first()
        if row is not None:
            return row

    to_number = (call_payload.get("phoneNumber") or {}).get("number")
    from_number = (call_payload.get("customer") or {}).get("number")
    if not to_number:
        return None

    number_result = await admin_db.select(
        "phone_numbers",
        params={"select": "organization_id,assigned_voice_agent_id", "e164_number": f"eq.{to_number}"},
    )
    number_row = number_result.first()
    if number_row is None or not number_row.get("assigned_voice_agent_id"):
        logger.warning("voice_webhook_unrecognized_inbound_number to=%s", to_number)
        return None

    inserted = await admin_db.insert(
        "calls",
        {
            "organization_id": number_row["organization_id"],
            "voice_agent_id": number_row["assigned_voice_agent_id"],
            "direction": "inbound",
            "status": "in_progress",
            "to_number": to_number,
            "from_number": from_number or "",
            "provider_call_id": provider_call_id,
        },
    )
    return inserted.one("Call")


@router.post(
    "/platform/events",
    summary="Call lifecycle + tool-calling callback from the voice platform",
    description=(
        "Signature-verified, not JWT-authenticated -- the caller is the voice platform, not a "
        "logged-in user. Handles status updates, end-of-call reports, and mid-call tool calls "
        "in one consolidated route (matching the platform's single serverUrl design)."
    ),
    include_in_schema=True,
)
@limiter.exempt
async def platform_events(
    request: Request,
    admin_db: AdminDbDep,
    x_vapi_signature: str | None = Header(default=None, alias="X-Vapi-Signature"),
) -> dict[str, Any]:
    raw_body = await request.body()
    if not verify_platform_signature(raw_body, x_vapi_signature):
        logger.warning("voice_webhook_signature_invalid")
        raise UnauthorizedError("Invalid webhook signature")

    payload = await request.json()
    message = payload.get("message", payload)
    message_type = message.get("type")
    call_payload = message.get("call", {})
    metadata = call_payload.get("metadata", {}) or message.get("metadata", {}) or {}
    call_id = metadata.get("call_id")

    call = await _resolve_call(admin_db, call_id) if call_id else None
    if call is None:
        # No pre-created row -- either an inbound call's first event, or metadata we don't
        # recognize. Never trust metadata.get("organization_id") here even if present; the
        # only trusted resolution is via the dialed number, looked up server-side.
        call = await _resolve_or_create_inbound_call(admin_db, message)
    if call is None:
        logger.warning("voice_webhook_unresolvable_call type=%s call_id=%s", message_type, call_id)
        return {"ignored": True}

    org_id = call["organization_id"]
    call_id = call["id"]

    if message_type == "tool-calls":
        return await _handle_tool_calls(admin_db, org_id, call_id, message)

    return await _handle_status_event(admin_db, call, message)


_TERMINAL_CALL_STATUSES = {"completed", "failed"}


async def _handle_status_event(
    admin_db: AdminDbDep, call: dict[str, Any], message: dict[str, Any]
) -> dict[str, Any]:
    # `call` is the row as fetched before this event's changes are applied. A call already at
    # a terminal status has already been through finalize_call() once -- a duplicate delivery,
    # or a platform that fires both a status-update and a separate end-of-call-report, must not
    # insert the activity/notification a second time.
    already_finalized = call.get("status") in _TERMINAL_CALL_STATUSES
    call_payload = message.get("call", {})
    artifact = message.get("artifact", {}) or {}
    provider_status = str(call_payload.get("status") or message.get("status") or "").lower()
    resolved_status = _STATUS_MAP.get(provider_status)

    changes: dict[str, Any] = {}
    if resolved_status:
        changes["status"] = resolved_status
    if call_payload.get("startedAt"):
        changes["started_at"] = call_payload["startedAt"]
    if message.get("endedAt") or call_payload.get("endedAt"):
        changes["ended_at"] = message.get("endedAt") or call_payload.get("endedAt")
    if message.get("durationSeconds") is not None:
        changes["duration_seconds"] = message["durationSeconds"]
    if artifact.get("recordingUrl"):
        changes["recording_url"] = artifact["recordingUrl"]
    if artifact.get("transcript"):
        changes["transcript"] = artifact["transcript"]
    if message.get("summary"):
        changes["summary"] = message["summary"]
    if not call.get("provider_call_id") and call_payload.get("id"):
        changes["provider_call_id"] = call_payload["id"]

    if not changes:
        return {"ok": True}

    updated = await admin_db.update(
        "calls", {"id": f"eq.{call['id']}", "organization_id": f"eq.{call['organization_id']}"}, changes
    )
    row = updated.first() or {**call, **changes}

    if resolved_status in _TERMINAL_CALL_STATUSES and not already_finalized:
        await finalize_call(admin_db, row)

    return {"ok": True}


async def _handle_tool_calls(
    admin_db: AdminDbDep, org_id: str, call_id: str, message: dict[str, Any]
) -> dict[str, Any]:
    results = []
    for tool_call in message.get("toolCalls", []):
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments = function.get("arguments") or {}
        arguments.setdefault("call_id", call_id)
        try:
            result = await dispatch_tool(tool_name, org_id, arguments, admin_db)
        except Exception:
            logger.exception("voice_tool_call_failed tool=%s call_id=%s", tool_name, call_id)
            result = {"error": "internal error handling this tool call"}
        results.append({"toolCallId": tool_call.get("id"), "result": result})
    return {"results": results}
