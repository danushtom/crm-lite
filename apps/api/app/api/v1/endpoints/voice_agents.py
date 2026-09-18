"""AI voice sales agents: CRUD, knowledge-base documents, phone numbers, call log, and
outbound call placement.

Naming: this is deliberately `voice_agents`, not `agents` -- the existing `/agents` route
already means team members (see app/api/v1/endpoints/agents.py). "Voice agents" are AI
assistants that place/receive phone calls.

Permission model: reading (`voice_agents.read`) is available to any role granted it (Admin
always; Agent/SDR by default -- see the migration). Creating/editing/deleting a voice agent and
placing calls (`voice_agents.write`/`.manage`) is checked here via `require_permission`, and as
of 20260918000000_ai_features.sql the underlying RLS policies check the same grant through
`has_permission()` rather than `is_admin()`. The two layers now agree: a custom role holding
`voice_agents.write` without full org access passes both. Note that several handlers below still
additionally declare `AdminDep` -- that is a deliberate product choice given the cost and
compliance stakes of placing calls, not a limitation of the permission model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.api.deps import AdminDbDep, AdminDep, CurrentUserDep, DbDep, ProfileDep, require_permission
from app.domain.enums import CallDirection, CallStatus
from app.core.config import settings
from app.core.concurrency import IfMatchDep, set_etag, soft_delete_guarded, update_guarded
from app.core.errors import ConflictError, ForbiddenError, NotConfiguredError
from app.core.pagination import Page, PageParamsDep
from app.schemas.common import ERROR_RESPONSES
from app.schemas.voice_agents import (
    Call,
    CallSummary,
    ComplianceStatus,
    OutboundCallRequest,
    PhoneNumber,
    PhoneNumberCreate,
    VoiceAgent,
    VoiceAgentCreate,
    VoiceAgentDocument,
    VoiceAgentUpdate,
)
from app.services import voice_agents as voice_agent_service
from app.services import storage
from app.services import voice_platform
from app.services.ai import budget as ai_budget
from app.services.ai import knowledge_base
from app.services.calls import finalize_call

router = APIRouter(prefix="/voice-agents", tags=["Voice Agents"])

_AGENT_SELECT = "*"


async def _assign_phone_number(db: DbDep, voice_agent_id: str, new_phone_number_id: str | None, old_phone_number_id: str | None) -> None:
    """Keep phone_numbers.assigned_voice_agent_id in sync with voice_agents.phone_number_id.

    Inbound routing (voice_webhooks.py's _resolve_or_create_inbound_call) resolves an incoming
    call's org/agent entirely through this back-reference -- without it, a number can be
    assigned to an agent for outbound purposes but every inbound call to it would be silently
    dropped as unrecognized.
    """
    if old_phone_number_id and old_phone_number_id != new_phone_number_id:
        await db.update(
            "phone_numbers",
            {"id": f"eq.{old_phone_number_id}", "assigned_voice_agent_id": f"eq.{voice_agent_id}"},
            {"assigned_voice_agent_id": None},
        )
    if new_phone_number_id and new_phone_number_id != old_phone_number_id:
        await db.update(
            "phone_numbers", {"id": f"eq.{new_phone_number_id}"}, {"assigned_voice_agent_id": voice_agent_id}
        )


async def _require_compliance_ack(db: DbDep, organization_id: str) -> None:
    result = await db.select(
        "organizations",
        params={"select": "ai_calling_compliance_ack_at", "id": f"eq.{organization_id}"},
    )
    row = result.first()
    if not row or not row.get("ai_calling_compliance_ack_at"):
        raise ForbiddenError(
            "Your organization must acknowledge AI calling compliance requirements first",
            code="compliance_ack_required",
        )


@router.get(
    "/compliance-status",
    response_model=ComplianceStatus,
    summary="Whether this org has acknowledged AI calling compliance requirements",
    responses=ERROR_RESPONSES,
)
async def compliance_status(profile: ProfileDep, db: DbDep) -> ComplianceStatus:
    result = await db.select(
        "organizations",
        params={
            "select": "ai_calling_compliance_ack_at",
            "id": f"eq.{profile['organization_id']}",
        },
    )
    row = result.first() or {}
    ack_at = row.get("ai_calling_compliance_ack_at")
    return ComplianceStatus(acknowledged=bool(ack_at), acknowledged_at=ack_at)


@router.post(
    "/compliance-ack",
    response_model=ComplianceStatus,
    summary="Acknowledge AI calling compliance requirements for this organization",
    description="Requires a role with full organization access. One-time, org-wide gate.",
    responses=ERROR_RESPONSES,
)
async def acknowledge_compliance(profile: ProfileDep, admin_db: AdminDbDep, _admin: AdminDep) -> ComplianceStatus:
    # organizations has no UPDATE policy for authenticated users (only SELECT) -- like the
    # users.google_* token columns, this write goes through the service-role client, gated by
    # AdminDep instead of RLS.
    result = await admin_db.update(
        "organizations",
        {"id": f"eq.{profile['organization_id']}"},
        {
            "ai_calling_compliance_ack_at": datetime.now(timezone.utc).isoformat(),
            "ai_calling_compliance_ack_by": profile["id"],
        },
    )
    row = result.one("Organization")
    return ComplianceStatus(acknowledged=True, acknowledged_at=row.get("ai_calling_compliance_ack_at"))


@router.get("", response_model=list[VoiceAgent], summary="List this organization's voice agents", responses=ERROR_RESPONSES)
async def list_voice_agents(db: DbDep, _perm: Annotated[dict, Depends(require_permission("voice_agents.read"))]) -> list[VoiceAgent]:
    result = await db.select("voice_agents", params={"select": _AGENT_SELECT, "order": "created_at.asc,id.asc"})
    return [VoiceAgent.model_validate(r) for r in result.rows]


@router.post(
    "",
    response_model=VoiceAgent,
    status_code=status.HTTP_201_CREATED,
    summary="Create a voice agent",
    description="Requires a role with full organization access, and the org's AI calling compliance acknowledgment.",
    responses=ERROR_RESPONSES,
)
async def create_voice_agent(
    body: VoiceAgentCreate, db: DbDep, profile: ProfileDep, _admin: AdminDep, response: Response
) -> VoiceAgent:
    await _require_compliance_ack(db, profile["organization_id"])

    org_result = await db.select(
        "organizations", params={"select": "name", "id": f"eq.{profile['organization_id']}"}
    )
    org_name = org_result.one("Organization").get("name") or "our team"
    disclosure_script = (
        f"You're speaking with {body.name}, an AI assistant from {org_name}. "
        "This call may be recorded."
    )
    inserted = await db.insert(
        "voice_agents",
        {
            "name": body.name,
            "system_prompt": body.system_prompt,
            "direction": body.direction.value,
            "voice_id": body.voice_id,
            "phone_number_id": body.phone_number_id,
            "disclosure_script": disclosure_script,
            "created_by": profile["id"],
        },
    )
    row = inserted.one("Voice agent")

    if body.phone_number_id:
        await _assign_phone_number(db, row["id"], body.phone_number_id, None)

    try:
        platform_assistant_id = await voice_platform.create_assistant(
            name=body.name,
            system_prompt=body.system_prompt,
            disclosure_script=disclosure_script,
            voice_id=body.voice_id,
        )
        updated = await db.update(
            "voice_agents", {"id": f"eq.{row['id']}"}, {"platform_assistant_id": platform_assistant_id}
        )
        row = updated.one("Voice agent")
    except NotConfiguredError:
        # The agent still exists in the CRM even if the voice platform isn't configured yet
        # (e.g. local dev without a Vapi key) -- it just can't place/receive calls until it is.
        pass

    set_etag(response, row)
    return VoiceAgent.model_validate(row)


# --- Phone numbers and calls: literal paths registered before the single-segment
# /{voice_agent_id} wildcard below, or FastAPI's first-match routing would swallow
# "/voice-agents/phone-numbers" and "/voice-agents/calls" as if they were an id. -------------


@router.get("/phone-numbers", response_model=list[PhoneNumber], responses=ERROR_RESPONSES)
async def list_phone_numbers(db: DbDep, _perm: Annotated[dict, Depends(require_permission("voice_agents.read"))]) -> list[PhoneNumber]:
    result = await db.select("phone_numbers", params={"select": "*", "order": "created_at.desc,id.desc"})
    return [PhoneNumber.model_validate(r) for r in result.rows]


@router.post(
    "/phone-numbers",
    response_model=PhoneNumber,
    status_code=status.HTTP_201_CREATED,
    summary="Register an existing Twilio number",
    description=(
        "v1 supports attaching a number you already own in Twilio -- automated purchase-and-"
        "provision is not built yet. Requires a role with full organization access."
    ),
    responses=ERROR_RESPONSES,
)
async def register_phone_number(body: PhoneNumberCreate, db: DbDep, user: CurrentUserDep, _admin: AdminDep) -> PhoneNumber:
    inserted = await db.insert(
        "phone_numbers",
        {
            "e164_number": body.e164_number,
            "provider_number_sid": body.provider_number_sid,
            "created_by": user.sub,
        },
    )
    return PhoneNumber.model_validate(inserted.one("Phone number"))


@router.delete(
    "/phone-numbers/{phone_number_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Release a registered phone number",
    description=(
        "Requires a role with full organization access. Refused with 409 while an agent is "
        "still assigned this number -- unassign it from the agent first, so releasing a number "
        "can never silently break inbound routing."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_phone_number(phone_number_id: str, db: DbDep, _admin: AdminDep) -> Response:
    existing = await db.select(
        "phone_numbers",
        params={"select": "id,assigned_voice_agent_id", "id": f"eq.{phone_number_id}"},
    )
    row = existing.one("Phone number")
    if row.get("assigned_voice_agent_id"):
        raise ConflictError(
            "This number is assigned to a voice agent; unassign it from the agent first."
        )

    deleted = await db.delete("phone_numbers", {"id": f"eq.{phone_number_id}"})
    if deleted.first() is None:
        raise ForbiddenError("You do not have permission to delete this phone number")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/calls", response_model=Page[CallSummary], summary="List call history", responses=ERROR_RESPONSES)
async def list_calls(
    db: DbDep,
    page: PageParamsDep,
    _perm: Annotated[dict, Depends(require_permission("voice_agents.read"))],
    voice_agent_id: Annotated[str | None, Query(description="Restrict to one voice agent.")] = None,
    lead_id: Annotated[str | None, Query(description="Restrict to calls about one lead.")] = None,
    contact_id: Annotated[str | None, Query(description="Restrict to calls with one contact.")] = None,
    call_status: Annotated[CallStatus | None, Query(alias="status")] = None,
    direction: Annotated[CallDirection | None, Query()] = None,
) -> Page[CallSummary]:
    params: dict[str, str] = {
        "select": "id,voice_agent_id,contact_id,lead_id,direction,status,to_number,from_number,started_at,ended_at,duration_seconds,outcome,created_at",
        "order": "created_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if voice_agent_id:
        params["voice_agent_id"] = f"eq.{voice_agent_id}"
    if lead_id:
        params["lead_id"] = f"eq.{lead_id}"
    if contact_id:
        params["contact_id"] = f"eq.{contact_id}"
    if call_status:
        params["status"] = f"eq.{call_status.value}"
    if direction:
        params["direction"] = f"eq.{direction.value}"

    result = await db.select("calls", params=params, count=True)
    return Page.build([CallSummary.model_validate(r) for r in result.rows], page, result.count)


@router.get("/calls/{call_id}", response_model=Call, summary="Get full call detail, including transcript", responses=ERROR_RESPONSES)
async def get_call(call_id: str, db: DbDep, _perm: Annotated[dict, Depends(require_permission("voice_agents.read"))]) -> Call:
    result = await db.select("calls", params={"select": "*", "id": f"eq.{call_id}"})
    return Call.model_validate(result.one("Call"))


@router.get("/{voice_agent_id}", response_model=VoiceAgent, summary="Get a voice agent", responses=ERROR_RESPONSES)
async def get_voice_agent(
    voice_agent_id: str, db: DbDep, response: Response, _perm: Annotated[dict, Depends(require_permission("voice_agents.read"))]
) -> VoiceAgent:
    result = await db.select("voice_agents", params={"select": _AGENT_SELECT, "id": f"eq.{voice_agent_id}"})
    row = result.one("Voice agent")
    set_etag(response, row)
    return VoiceAgent.model_validate(row)


@router.patch(
    "/{voice_agent_id}",
    response_model=VoiceAgent,
    summary="Update a voice agent",
    description="Requires a role with full organization access.",
    responses=ERROR_RESPONSES,
)
async def update_voice_agent(
    voice_agent_id: str, body: VoiceAgentUpdate, db: DbDep, response: Response, if_match: IfMatchDep, _admin: AdminDep
) -> VoiceAgent:
    changes = VoiceAgentUpdate.model_validate(body.changes()).model_dump(exclude_unset=True, mode="json")
    if not changes:
        return await get_voice_agent(voice_agent_id, db, response, {})

    old_phone_number_id = None
    if "phone_number_id" in changes:
        existing = await db.select("voice_agents", params={"select": "phone_number_id", "id": f"eq.{voice_agent_id}"})
        old_phone_number_id = existing.one("Voice agent").get("phone_number_id")

    row = await update_guarded(db, "voice_agents", record_id=voice_agent_id, changes=changes, if_match=if_match, what="Voice agent")

    if "phone_number_id" in changes:
        await _assign_phone_number(db, voice_agent_id, changes["phone_number_id"], old_phone_number_id)

    if any(k in changes for k in ("name", "system_prompt", "voice_id")) and row.get("platform_assistant_id"):
        await voice_platform.update_assistant(
            row["platform_assistant_id"],
            name=row["name"],
            system_prompt=row["system_prompt"],
            disclosure_script=row["disclosure_script"],
            voice_id=row.get("voice_id"),
        )

    set_etag(response, row)
    return VoiceAgent.model_validate(row)


@router.delete(
    "/{voice_agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a voice agent",
    description="Requires a role with full organization access. Blocked while a call is in progress.",
    responses=ERROR_RESPONSES,
)
async def delete_voice_agent(
    voice_agent_id: str,
    db: DbDep,
    profile: ProfileDep,
    if_match: IfMatchDep,
    _admin: AdminDep,
) -> Response:
    await soft_delete_guarded(db, "voice_agents", record_id=voice_agent_id, if_match=if_match, what="Voice agent")
    # The agent is soft-deleted, so its documents do not cascade away -- but nothing can reach
    # them again either, and leaving their embedded text sitting in the vector store is a
    # retention problem rather than a feature. Best-effort: a Qdrant outage must not block the
    # delete, and the points are unreachable regardless (search is scoped to org + agent id,
    # and a recreated agent gets a new id).
    await knowledge_base.remove_agent(
        organization_id=profile["organization_id"], voice_agent_id=voice_agent_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Documents ------------------------------------------------------------------


@router.get("/{voice_agent_id}/documents", response_model=list[VoiceAgentDocument], responses=ERROR_RESPONSES)
async def list_documents(
    voice_agent_id: str, db: DbDep, _perm: Annotated[dict, Depends(require_permission("voice_agents.read"))]
) -> list[VoiceAgentDocument]:
    result = await db.select(
        "voice_agent_documents",
        params={"select": "*", "voice_agent_id": f"eq.{voice_agent_id}", "order": "created_at.desc,id.desc"},
    )
    documents = [VoiceAgentDocument.model_validate(r) for r in result.rows]
    for document in documents:
        document.file_url = (
            await storage.signed_url(
                bucket=settings.voice_kb_bucket,
                path=document.file_url,
                filename=document.filename,
            )
            or ""
        )
    return documents


@router.post(
    "/{voice_agent_id}/documents",
    response_model=VoiceAgentDocument,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge-base document (pricing sheet, FAQ, script)",
    responses=ERROR_RESPONSES,
)
async def upload_document(
    voice_agent_id: str,
    db: DbDep,
    admin_db: AdminDbDep,
    user: CurrentUserDep,
    profile: ProfileDep,
    _admin: AdminDep,
    file: Annotated[UploadFile, File(description="Pricing sheet, FAQ, or script.")],
) -> VoiceAgentDocument:
    data = await file.read()
    file_url = await voice_agent_service.upload_document(
        voice_agent_id=voice_agent_id,
        filename=file.filename or "document",
        content_type=file.content_type,
        data=data,
    )
    result = await db.insert(
        "voice_agent_documents",
        {
            "voice_agent_id": voice_agent_id,
            "filename": file.filename or "document",
            "file_url": file_url,
            "content_type": file.content_type,
            "uploaded_by": user.sub,
        },
    )
    document = VoiceAgentDocument.model_validate(result.one("Document"))

    # Index it so the agent can actually use it mid-call. Failure here is recorded on the row
    # (`index_error`) and retried by the worker's reindex pass -- it never fails the upload,
    # because the file is already stored and rejecting it would lose the user's work over a
    # transient embedding-API outage. `indexed_at` on the response tells the UI which it was.
    if settings.ai_configured:
        try:
            chunks, usage = await knowledge_base.index_document(
                admin_db,
                organization_id=profile["organization_id"],
                voice_agent_id=voice_agent_id,
                document_id=document.id,
                filename=document.filename,
                data=data,
            )
            document.chunk_count = chunks
            document.indexed_at = datetime.now(timezone.utc)
            await ai_budget.record(
                admin_db,
                organization_id=profile["organization_id"],
                usage=usage,
                user_id=user.sub,
            )
        except Exception as exc:
            document.index_error = str(exc)[:500]

    document.file_url = (
        await storage.signed_url(
            bucket=settings.voice_kb_bucket, path=file_url, filename=document.filename
        )
        or ""
    )
    return document


@router.delete("/{voice_agent_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES)
async def delete_document(
    voice_agent_id: str,
    document_id: str,
    db: DbDep,
    profile: ProfileDep,
    _admin: AdminDep,
) -> Response:
    deleted = await db.delete("voice_agent_documents", {"id": f"eq.{document_id}", "voice_agent_id": f"eq.{voice_agent_id}"})
    if deleted.first() is None:
        raise ForbiddenError("You do not have permission to delete this document")
    # Postgres is the record and Qdrant is a derived index, so the row goes first and the points
    # follow. remove_document swallows its own failures -- an unreachable vector store must not
    # leave the user unable to delete a document.
    await knowledge_base.remove_document(
        organization_id=profile["organization_id"], document_id=document_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Outbound calls (nested under a specific agent, no ordering conflict) ------------------


@router.post(
    "/{voice_agent_id}/calls",
    response_model=CallSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Place an outbound call",
    description=(
        "Requires a role with full organization access and the org's compliance "
        "acknowledgment. Blocked (still logged, as `no_consent_blocked`) if the contact has "
        "not consented to AI calls."
    ),
    responses=ERROR_RESPONSES,
)
async def place_outbound_call(
    voice_agent_id: str,
    body: OutboundCallRequest,
    db: DbDep,
    admin_db: AdminDbDep,
    profile: ProfileDep,
    _perm: Annotated[dict, Depends(require_permission("voice_agents.manage"))],
) -> CallSummary:
    await _require_compliance_ack(db, profile["organization_id"])

    agent_result = await db.select("voice_agents", params={"select": "*", "id": f"eq.{voice_agent_id}"})
    agent = agent_result.one("Voice agent")
    if not agent.get("platform_assistant_id"):
        raise NotConfiguredError("This voice agent has not been set up with the voice platform yet")
    if not agent.get("phone_number_id"):
        raise NotConfiguredError("This voice agent has no phone number assigned")

    contact_result = await db.select(
        "contacts", params={"select": "phone,ai_call_consent", "id": f"eq.{body.contact_id}"}
    )
    contact = contact_result.one("Contact")
    number_result = await db.select("phone_numbers", params={"select": "e164_number", "id": f"eq.{agent['phone_number_id']}"})
    from_number = number_result.one("Phone number")["e164_number"]

    # body.lead_id is client-supplied -- validated against this org via db (RLS-scoped) before
    # it's ever written to the calls row, exactly like contact/agent/number above. Without
    # this, a lead_id from another organization would still get stored (calls' own
    # organization_id comes from voice_agents, not from lead_id), and finalize_call() would
    # then write an activity + notification into that other org's lead timeline.
    if body.lead_id:
        lead_check = await db.select(
            "leads", params={"select": "id", "id": f"eq.{body.lead_id}"}
        )
        if lead_check.first() is None:
            raise ForbiddenError("This lead is not visible to your organization")

    if not contact.get("phone"):
        raise NotConfiguredError("This contact has no phone number on file")

    if not contact.get("ai_call_consent"):
        blocked = await admin_db.insert(
            "calls",
            {
                "organization_id": profile["organization_id"],
                "voice_agent_id": voice_agent_id,
                "contact_id": body.contact_id,
                "lead_id": body.lead_id,
                "direction": "outbound",
                "status": "no_consent_blocked",
                "to_number": contact["phone"],
                "from_number": from_number,
                "initiated_by": profile["id"],
            },
        )
        row = blocked.one("Call")
        await finalize_call(admin_db, row)
        raise ForbiddenError("This contact has not consented to AI calls", code="no_consent")

    created = await admin_db.insert(
        "calls",
        {
            "organization_id": profile["organization_id"],
            "voice_agent_id": voice_agent_id,
            "contact_id": body.contact_id,
            "lead_id": body.lead_id,
            "direction": "outbound",
            "status": "queued",
            "to_number": contact["phone"],
            "from_number": from_number,
            "initiated_by": profile["id"],
        },
    )
    call = created.one("Call")

    try:
        provider_call_id = await voice_platform.place_outbound_call(
            platform_assistant_id=agent["platform_assistant_id"],
            to_number=contact["phone"],
            from_number=from_number,
            metadata={
                "call_id": call["id"],
                "voice_agent_id": voice_agent_id,
                "organization_id": profile["organization_id"],
                "lead_id": body.lead_id,
                "context_note": body.context_note,
            },
        )
    except Exception:
        # Otherwise this row sits at "queued" indefinitely -- visible in the call log as if
        # still pending -- until the worker's hourly stale-call reconciliation catches it.
        await admin_db.update(
            "calls", {"id": f"eq.{call['id']}"}, {"status": "failed", "outcome": "Could not reach the voice platform"}
        )
        raise

    updated = await admin_db.update(
        "calls", {"id": f"eq.{call['id']}"}, {"provider_call_id": provider_call_id, "status": "ringing"}
    )
    return CallSummary.model_validate(updated.one("Call"))
