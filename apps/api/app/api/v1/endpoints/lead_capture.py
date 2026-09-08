"""Public lead capture, and the admin endpoints that manage its keys.

This module holds the only unauthenticated *write* path in the API, so it is worth being
explicit about what protects it.

`submit` declares no `CurrentUserDep`/`DbDep`/`AdminDep` -- their absence is what skips Supabase
JWT auth, the same mechanism app/api/health.py and voice_webhooks.py rely on. In their place:

  * The capture key identifies the organization. It is resolved server-side against
    `lead_capture_keys` and nothing in the request body is consulted to decide which tenant is
    written to -- the same rule the voice webhooks follow, and the reason both use `AdminDbDep`
    for the lookup rather than trusting a payload claim.
  * The key travels in a header, not the path. A URL ends up in browser history, in `Referer`
    on any outbound link from the thank-you page, and in every access log between the form and
    here; a header does not.
  * `StrictAPIModel` rejects unknown fields, so `organization_id`, `owner_id` and `is_primary`
    cannot be smuggled in, and every string is length-capped in the schema.
  * A tight per-IP rate limit sits on top of the global default, because the usual bucket
    (hashed bearer token) does not exist for an anonymous caller.
  * The response says only "received" -- no ids, no indication of whether the person was
    already known. Anything richer would turn a leaked key into a way to enumerate the CRM.

The key management routes below are ordinary admin-only CRUD and carry the usual dependencies.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.api.deps import AdminDbDep, AdminDep, CurrentUserDep, DbDep
from app.core.rate_limit import limiter
from app.schemas.common import ERROR_RESPONSES
from app.schemas.lead_capture import (
    LeadCaptureKey,
    LeadCaptureKeyCreate,
    LeadCaptureKeyUpdate,
    LeadCaptureResult,
    LeadCaptureSubmission,
)
from app.services import lead_capture as capture_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lead-capture", tags=["Lead Capture"])

_KEY_SELECT = "id,name,key,is_active,owner_id,created_at,last_used_at"


@router.post(
    "",
    response_model=LeadCaptureResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a lead from a public form (no authentication)",
    description=(
        "Called by a landing page or ad lead form. Authenticated by an `X-Capture-Key` header "
        "rather than a JWT; the organization is resolved from that key server-side.\n\n"
        "Creates a company (matched by name, or new), a contact carrying the UTM parameters, "
        "and a lead assigned to the key's owner. Always answers `{\"received\": true}` -- an "
        "unknown, revoked or malformed key is not distinguishable from a good one, so the key "
        "cannot be used to probe for which organizations exist."
    ),
    responses=ERROR_RESPONSES,
)
# Tight, and per-IP: the default bucket keys on a hashed bearer token, which an anonymous form
# does not have, so without this every public submission worldwide would share one quota.
@limiter.limit("20/minute")
async def submit(
    request: Request,
    body: LeadCaptureSubmission,
    response: Response,
    admin_db: AdminDbDep,
    capture_key: Annotated[str | None, Header(alias="X-Capture-Key")] = None,
) -> LeadCaptureResult:
    key_row = await capture_service.resolve_key(admin_db, capture_key or "")
    if key_row is None:
        # Same 202 as success. Logged, because a burst of these is how a leaked-and-revoked key
        # or a misconfigured form shows up.
        logger.info("lead_capture.rejected", extra={"reason": "unresolved_key"})
        return LeadCaptureResult()

    try:
        await capture_service.capture(admin_db, key_row=key_row, submission=body)
    except LookupError:
        # The organization has no active full-access user to assign the lead to. Nothing the
        # submitter can do about it, and telling them would leak that the key is valid.
        logger.warning(
            "lead_capture.no_owner",
            extra={"organization_id": key_row.get("organization_id")},
        )

    return LeadCaptureResult()


@router.get(
    "/keys",
    response_model=list[LeadCaptureKey],
    summary="List this organization's capture keys",
    description="Requires a role with full organization access -- these are credentials.",
    responses=ERROR_RESPONSES,
)
async def list_keys(db: DbDep, _admin: AdminDep) -> list[LeadCaptureKey]:
    result = await db.select(
        "lead_capture_keys",
        params={"select": _KEY_SELECT, "order": "created_at.desc,id.desc"},
    )
    return [LeadCaptureKey.model_validate(row) for row in result.rows]


@router.post(
    "/keys",
    response_model=LeadCaptureKey,
    status_code=status.HTTP_201_CREATED,
    summary="Create a capture key",
    description=(
        "Requires a role with full organization access. Create one per landing page or ad "
        "platform, so a leaked key can be revoked without taking the others down."
    ),
    responses=ERROR_RESPONSES,
)
async def create_key(
    body: LeadCaptureKeyCreate, db: DbDep, user: CurrentUserDep, _admin: AdminDep
) -> LeadCaptureKey:
    result = await db.insert(
        "lead_capture_keys",
        {
            "name": body.name.strip(),
            "key": capture_service.generate_key(),
            "owner_id": body.owner_id,
            "created_by": user.sub,
            "select": _KEY_SELECT,
        },
    )
    return LeadCaptureKey.model_validate(result.one("Capture key"))


@router.patch(
    "/keys/{key_id}",
    response_model=LeadCaptureKey,
    summary="Rename, reassign or revoke a capture key",
    description=(
        "Requires a role with full organization access. Setting `is_active` false revokes the "
        "key immediately; submissions made with it are then indistinguishable from ones made "
        "with a key that never existed."
    ),
    responses=ERROR_RESPONSES,
)
async def update_key(
    key_id: str, body: LeadCaptureKeyUpdate, db: DbDep, _admin: AdminDep
) -> LeadCaptureKey:
    changes = LeadCaptureKeyUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        existing = await db.select(
            "lead_capture_keys", params={"select": _KEY_SELECT, "id": f"eq.{key_id}"}
        )
        return LeadCaptureKey.model_validate(existing.one("Capture key"))

    result = await db.update(
        "lead_capture_keys", {"id": f"eq.{key_id}", "select": _KEY_SELECT}, changes
    )
    return LeadCaptureKey.model_validate(result.one("Capture key"))


@router.delete(
    "/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a capture key",
    description=(
        "Requires a role with full organization access. Prefer revoking (`is_active` false) "
        "over deleting, so the record of which key a lead arrived through survives."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_key(key_id: str, db: DbDep, _admin: AdminDep) -> Response:
    existing = await db.select(
        "lead_capture_keys", params={"select": "id", "id": f"eq.{key_id}"}
    )
    existing.one("Capture key")
    await db.delete("lead_capture_keys", {"id": f"eq.{key_id}"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
