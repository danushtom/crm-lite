"""Voice agent, phone number, document and call schemas.

See supabase/migrations/20260906000000_voice_agents.sql. Row visibility for `calls` is RLS's
job (own the lead, or hold a full-access role); these schemas only shape the payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from dracara_ai.voice_script import GOALS, LEAD_FIELDS, TONES, TOOL_BRIEFS
from pydantic import Field, field_validator

from app.domain.enums import CallDirection, CallStatus, VoiceAgentDirection
from app.schemas.common import APIModel, PatchModel, StrictAPIModel

#: The script vocabulary is the compiler's (packages/ai), not a second copy of it: a goal or
#: tone the compiler does not know would compile to a silent fallback, and a tool or field name
#: it does not know would be stored and then ignored.
ScriptGoal = Literal[tuple(GOALS)]  # type: ignore[valid-type]
ScriptTone = Literal[tuple(TONES)]  # type: ignore[valid-type]
ToolName = Literal[tuple(TOOL_BRIEFS)]  # type: ignore[valid-type]
LeadFieldName = Literal[tuple(LEAD_FIELDS)]  # type: ignore[valid-type]


class ScriptQuestion(StrictAPIModel):
    ask: str = Field(min_length=1, max_length=400, description="The question, in plain words.")
    why: str = Field(default="", max_length=400, description="Why it is being asked; shapes how the agent follows up.")
    required: bool = Field(default=False, description="The agent must not end the call without an answer.")


class ScriptObjection(StrictAPIModel):
    objection: str = Field(min_length=1, max_length=400, description="What the caller says.")
    response: str = Field(min_length=1, max_length=800, description="How the agent should answer it.")


class VoiceScript(StrictAPIModel):
    """What the agent is for and how it should run the call.

    This is the source of truth for an agent's behaviour; ``system_prompt`` is compiled from it
    (see ``dracara_ai.voice_script``). Every list is capped, because all of it ends up in one
    prompt on the critical path of a live phone call.
    """

    goal: ScriptGoal = "qualify"
    tone: ScriptTone = "warm"
    opening: str = Field(default="", max_length=1000, description="What to say after the recording disclosure.")
    talking_points: list[str] = Field(default_factory=list, max_length=20)
    questions: list[ScriptQuestion] = Field(default_factory=list, max_length=20)
    objections: list[ScriptObjection] = Field(default_factory=list, max_length=20)
    must: list[str] = Field(default_factory=list, max_length=20, description="Always do these.")
    never: list[str] = Field(default_factory=list, max_length=20, description="Never do these.")
    closing: str = Field(default="", max_length=1000)
    handoff: str = Field(default="", max_length=1000, description="When to hand the call to a person.")
    extra: str = Field(default="", max_length=8000, description="Anything else, in free text.")
    max_minutes: int | None = Field(default=None, ge=1, le=120)

    @field_validator("talking_points", "must", "never", mode="after")
    @classmethod
    def _bounded_lines(cls, lines: list[str]) -> list[str]:
        cleaned = [" ".join(line.split()) for line in lines]
        kept = [line for line in cleaned if line]
        for line in kept:
            if len(line) > 500:
                raise ValueError("each line may be at most 500 characters")
        return kept


class VoiceAgentDataAccess(StrictAPIModel):
    """What this agent may use mid-call.

    Enforced server-side in ``app/services/voice_tools.py``, not only here and not only in the
    declarations sent to the platform -- a tool call can arrive for a tool that was never
    declared, so the dispatcher is the gate that counts.
    """

    tools: dict[ToolName, bool] = Field(
        default_factory=dict, description="Mid-call capabilities. Anything omitted is off."
    )
    lead_fields: list[LeadFieldName] = Field(
        default_factory=list,
        max_length=len(LEAD_FIELDS),
        description="The only lead fields get_lead_context will return.",
    )


class ScriptPreviewStep(APIModel):
    label: str
    detail: str
    kind: Literal["says", "asks", "does", "guardrail"]


class VoiceAgentTemplate(APIModel):
    key: str
    name: str
    summary: str
    persona_name: str
    role_title: str
    avatar_key: str
    script: VoiceScript
    data_access: VoiceAgentDataAccess


class VoiceAgent(APIModel):
    id: str
    name: str = Field(description="Internal label in the CRM, e.g. 'Inbound receptionist'.")
    persona_name: str = Field(default="", description="The name the agent gives on the call.")
    role_title: str = Field(default="", description="The job title it introduces itself with.")
    avatar_key: str = Field(default="", description="Which illustrated avatar to show.")
    script: VoiceScript = Field(default_factory=VoiceScript)
    data_access: VoiceAgentDataAccess = Field(default_factory=VoiceAgentDataAccess)
    system_prompt: str = Field(
        description="Compiled from `script`. Read-only: sending it is ignored.",
    )
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
    persona_name: str = Field(default="", max_length=80)
    role_title: str = Field(default="", max_length=120)
    avatar_key: str = Field(default="", max_length=40)
    template: str | None = Field(
        default=None,
        description="Start from a shipped template (see GET /voice-agents/templates). Anything "
        "else sent here overrides that template's value.",
    )
    script: VoiceScript | None = None
    data_access: VoiceAgentDataAccess | None = None
    direction: VoiceAgentDirection = VoiceAgentDirection.OUTBOUND
    voice_id: str | None = Field(default=None, max_length=200)
    phone_number_id: str | None = None
    system_prompt: str | None = Field(
        default=None,
        max_length=8_000,
        deprecated=True,
        description="Deprecated: raw prompt text. Kept so existing integrations keep working; "
        "it is stored as the script's free-text notes and compiled like everything else.",
    )


class VoiceAgentUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    persona_name: str | None = Field(default=None, max_length=80)
    role_title: str | None = Field(default=None, max_length=120)
    avatar_key: str | None = Field(default=None, max_length=40)
    script: VoiceScript | None = None
    data_access: VoiceAgentDataAccess | None = None
    direction: VoiceAgentDirection | None = None
    voice_id: str | None = Field(default=None, max_length=200)
    phone_number_id: str | None = None
    is_active: bool | None = None
    system_prompt: str | None = Field(
        default=None, max_length=8_000, deprecated=True, description="Deprecated; see VoiceAgentCreate."
    )


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
    script_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="The agent's script and data-access policy as they were when this call was "
        "placed -- the agent may have been edited since.",
    )


class OutboundCallRequest(StrictAPIModel):
    contact_id: str = Field(description="Must have ai_call_consent = true, checked at dial time.")
    lead_id: str | None = Field(default=None, description="Attached to the call for lead-timeline linkage.")
    context_note: str | None = Field(default=None, max_length=2000)


class ScriptPreviewRequest(StrictAPIModel):
    """A draft, as the builder currently has it -- nothing here needs to be saved first."""

    name: str = Field(default="", max_length=200)
    persona_name: str = Field(default="", max_length=80)
    role_title: str = Field(default="", max_length=120)
    script: VoiceScript = Field(default_factory=VoiceScript)
    data_access: VoiceAgentDataAccess = Field(default_factory=VoiceAgentDataAccess)


class ScriptPreview(APIModel):
    """What this script makes the agent do, and the prompt it compiles to."""

    preview: list[ScriptPreviewStep] = Field(
        description="A plain-English walkthrough of the call this script produces."
    )
    disclosure_script: str = Field(description="The fixed opening line, spoken before anything else.")
    system_prompt: str = Field(description="Exactly what the AI is told, for an admin to read.")


class ComplianceStatus(APIModel):
    acknowledged: bool
    acknowledged_at: datetime | None = None
