"""Voice agent, phone number, document and call schemas.

See supabase/migrations/20260906000000_voice_agents.sql. Row visibility for `calls` is RLS's
job (own the lead, or hold a full-access role); these schemas only shape the payloads.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import CallDirection, CallStatus, VoiceAgentDirection
from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class VoiceAgent(APIModel):
    id: str
    name: str
    system_prompt: str
    direction: VoiceAgentDirection
    voice_id: str | None = None
    platform: str
    platform_assistant_id: str | None = None
    phone_number_id: str | None = None
    disclosure_script: str
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class VoiceAgentCreate(StrictAPIModel):
    name: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    direction: VoiceAgentDirection = VoiceAgentDirection.OUTBOUND
    voice_id: str | None = Field(default=None, max_length=200)
    phone_number_id: str | None = None


class VoiceAgentUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=20_000)
    direction: VoiceAgentDirection | None = None
    voice_id: str | None = Field(default=None, max_length=200)
    phone_number_id: str | None = None
    is_active: bool | None = None


class PhoneNumber(APIModel):
    id: str
    e164_number: str
    provider: str
    provider_number_sid: str | None = None
    assigned_voice_agent_id: str | None = None
    created_at: datetime | None = None


class PhoneNumberCreate(StrictAPIModel):
    e164_number: str = Field(min_length=1, max_length=32, description="Already-owned Twilio number, e.g. +14155550100.")
    provider_number_sid: str | None = Field(default=None, max_length=64)


class VoiceAgentDocument(APIModel):
    id: str
    filename: str
    file_url: str
    content_type: str | None = None
    created_at: datetime | None = None

    # Knowledge-base indexing state. A document is stored whether or not it indexes, so the UI
    # needs to distinguish "uploaded and searchable by the agent" from "uploaded only".
    indexed_at: datetime | None = Field(
        default=None, description="When this document was last indexed for agent retrieval"
    )
    chunk_count: int | None = Field(
        default=None, description="Passages indexed. Null or 0 means the agent cannot cite it yet"
    )
    index_error: str | None = Field(
        default=None,
        description="Why indexing failed, if it did. The worker retries these automatically.",
    )


class CallSummary(APIModel):
    """List-view projection -- no transcript, to keep the call log page light."""

    id: str
    voice_agent_id: str
    contact_id: str | None = None
    lead_id: str | None = None
    direction: CallDirection
    status: CallStatus
    to_number: str
    from_number: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    outcome: str | None = None
    created_at: datetime | None = None


class Call(CallSummary):
    recording_url: str | None = None
    transcript: str | None = None
    summary: str | None = None
    suggested_next_action: str | None = None


class OutboundCallRequest(StrictAPIModel):
    contact_id: str = Field(description="Must have ai_call_consent = true, checked at dial time.")
    lead_id: str | None = Field(default=None, description="Attached to the call for lead-timeline linkage.")
    context_note: str | None = Field(default=None, max_length=2000)


class ComplianceStatus(APIModel):
    acknowledged: bool
    acknowledged_at: datetime | None = None
