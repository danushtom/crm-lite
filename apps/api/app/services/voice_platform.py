"""Adapter over the managed voice-AI platform (default: Vapi) that sits on top of Twilio.

Isolated behind this module so the vendor choice (Vapi vs. Retell, etc.) has contained blast
radius -- only this file's request/response shapes are vendor-specific; everything else in the
voice-agents feature talks to `create_assistant`/`update_assistant`/`place_outbound_call` and
never touches the platform's HTTP API directly.

NOTE: the exact request/response shapes below reflect Vapi's public API as documented at the
time this was written. Verify against https://docs.vapi.ai before relying on this in production
-- vendor APIs move, and this was not tested against a live account.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import NotConfiguredError, UpstreamError
from app.db.supabase import get_http_client

logger = logging.getLogger(__name__)


def _require_configured() -> None:
    if not settings.voice_platform_api_key:
        raise NotConfiguredError("VOICE_PLATFORM_API_KEY is not configured")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.voice_platform_api_key}",
        "Content-Type": "application/json",
    }


#: The mid-call tools declared to the platform, mirroring `app/services/voice_tools.py::TOOLS`.
#:
#: These were previously missing entirely: the dispatcher existed and the webhook could route a
#: tool call, but no assistant was ever told the tools existed, so the model had nothing to call
#: unless someone wired it up by hand in the vendor dashboard. Declaring them here keeps the two
#: halves of the bridge in one repository.
#:
#: `call_id` is deliberately absent from every schema. The webhook injects it from the resolved
#: call row (`arguments.setdefault("call_id", call_id)`), and a model-supplied value would be an
#: attacker-controllable pointer into another organization's data.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_consent",
            "description": "Check whether a contact has consented to AI calls before continuing.",
            "parameters": {
                "type": "object",
                "properties": {"contact_id": {"type": "string"}},
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lead_context",
            "description": "Fetch what the CRM knows about this lead: notes, follow-up date, tags.",
            "parameters": {
                "type": "object",
                "properties": {"lead_id": {"type": "string"}},
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Look something up in this agent's uploaded documents -- pricing, packages, "
                "FAQs, delivery timelines. Use it whenever the caller asks about specifics "
                "rather than answering from memory. If it returns nothing, say you will follow "
                "up with the exact figure rather than guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up, in plain words"},
                    "limit": {"type": "integer", "description": "Passages to return, 1-5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_call_outcome",
            "description": "Record how this call went before it ends.",
            "parameters": {
                "type": "object",
                "properties": {
                    "outcome": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["outcome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_deal_stage",
            "description": "Move a deal to a new pipeline stage when the caller's answer warrants it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    "stage": {"type": "string"},
                },
                "required": ["opportunity_id", "stage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Book a meeting with the rep who owns this lead. Confirm the date and time with "
                "the caller before calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "title": {"type": "string"},
                    "scheduled_at": {
                        "type": "string",
                        "description": "ISO 8601 timestamp including the timezone offset",
                    },
                    "duration_minutes": {"type": "integer"},
                },
                "required": ["scheduled_at"],
            },
        },
    },
]


def _webhook_url(path: str) -> str:
    base = settings.api_public_base_url.rstrip("/") if settings.api_public_base_url else ""
    return f"{base}/api/v1/voice-webhooks/{path}"


async def _request(method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    _require_configured()
    client = get_http_client()
    try:
        response = await client.request(
            method,
            f"{settings.voice_platform_api_base.rstrip('/')}{path}",
            headers=_headers(),
            json=json_body,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Could not reach the voice platform") from exc

    if response.status_code >= 400:
        logger.error("voice_platform_error status=%s body=%s", response.status_code, response.text)
        raise UpstreamError("The voice platform rejected the request")
    return response.json() if response.content else {}


async def create_assistant(
    *, name: str, system_prompt: str, disclosure_script: str, voice_id: str | None
) -> str:
    """Create the remote assistant. `disclosure_script` binds to the platform's own greeting
    field -- never the system prompt -- so it plays first on every call regardless of what the
    admin writes. Returns the platform's assistant id."""
    body: dict[str, Any] = {
        "name": name,
        "firstMessage": disclosure_script,
        "firstMessageMode": "assistant-speaks-first",
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": system_prompt}],
            "tools": TOOL_DEFINITIONS,
        },
        "serverUrl": _webhook_url("platform/events"),
        "serverUrlSecret": settings.voice_platform_webhook_secret or None,
    }
    if voice_id:
        body["voice"] = {"provider": "11labs", "voiceId": voice_id}
    result = await _request("POST", "/assistant", body)
    assistant_id = result.get("id")
    if not assistant_id:
        raise UpstreamError("The voice platform did not return an assistant id")
    return str(assistant_id)


async def update_assistant(
    platform_assistant_id: str,
    *,
    name: str,
    system_prompt: str,
    disclosure_script: str,
    voice_id: str | None,
) -> None:
    body: dict[str, Any] = {
        "name": name,
        "firstMessage": disclosure_script,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": system_prompt}],
            "tools": TOOL_DEFINITIONS,
        },
    }
    if voice_id:
        body["voice"] = {"provider": "11labs", "voiceId": voice_id}
    await _request("PATCH", f"/assistant/{platform_assistant_id}", body)


async def place_outbound_call(
    *,
    platform_assistant_id: str,
    to_number: str,
    from_number: str,
    metadata: dict[str, Any],
) -> str:
    """Places the call via Twilio credentials passed inline (no persistent number import
    required for outbound). Returns the platform's call id."""
    _require_configured()
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        raise NotConfiguredError("TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN are not configured")

    body = {
        "assistantId": platform_assistant_id,
        "customer": {"number": to_number},
        "phoneNumber": {
            "twilioAccountSid": settings.twilio_account_sid,
            "twilioAuthToken": settings.twilio_auth_token,
            "twilioPhoneNumber": from_number,
        },
        "metadata": metadata,
    }
    result = await _request("POST", "/call", body)
    call_id = result.get("id")
    if not call_id:
        raise UpstreamError("The voice platform did not return a call id")
    return str(call_id)


async def import_phone_number(*, e164_number: str) -> str | None:
    """Registers an existing Twilio number with the platform so inbound calls to it route to
    an assistant. Returns the platform's phone-number resource id, or None if inbound routing
    isn't configured (outbound-only numbers don't need this)."""
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        raise NotConfiguredError("TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN are not configured")
    body = {
        "provider": "twilio",
        "number": e164_number,
        "twilioAccountSid": settings.twilio_account_sid,
        "twilioAuthToken": settings.twilio_auth_token,
    }
    result = await _request("POST", "/phone-number", body)
    return str(result["id"]) if result.get("id") else None


async def get_call_status(provider_call_id: str) -> dict[str, Any]:
    """Used by the worker's stale-call reconciliation job to check a call the webhook never
    followed up on."""
    return await _request("GET", f"/call/{provider_call_id}")
