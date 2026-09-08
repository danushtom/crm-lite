"""Contact endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep
from app.core.concurrency import IfMatchDep, set_etag, soft_delete_guarded, update_guarded
from app.core.pagination import Page, PageParamsDep
from app.core.search import contains_pattern
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.contacts import Contact, ContactCreate, ContactUpdate, ContactWithCompany

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.get(
    "",
    response_model=Page[ContactWithCompany],
    summary="List contacts",
    description="Contacts visible to the caller, with the parent company name embedded.",
    responses=AUTH_RESPONSES,
)
async def list_contacts(
    db: DbDep,
    page: PageParamsDep,
    company_id: Annotated[str | None, Query(description="Restrict to one company.")] = None,
    search: Annotated[
        str | None, Query(max_length=200, description="Case-insensitive match on name or email.")
    ] = None,
) -> Page[ContactWithCompany]:
    params: dict[str, str] = {
        "select": "*,companies(name)",
        "order": "created_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if company_id:
        params["company_id"] = f"eq.{company_id}"
    # An or= group is the one place where the commas and parentheses really are structural,
    # which is why every caller now goes through the same sanitiser.
    pattern = contains_pattern(search)
    if pattern:
        params["or"] = f"(full_name.ilike.{pattern},email.ilike.{pattern})"

    result = await db.select("contacts", params=params, count=True)
    return Page.build(
        [ContactWithCompany.model_validate(r) for r in result.rows], page, result.count
    )


@router.post(
    "",
    response_model=Contact,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contact",
    responses=ERROR_RESPONSES,
)
async def create_contact(body: ContactCreate, db: DbDep, response: Response) -> Contact:
    result = await db.insert("contacts", body.model_dump(exclude_none=True, mode="json"))
    contact = Contact.model_validate(result.one("Contact"))
    response.headers["Location"] = f"{router.prefix}/{contact.id}"
    return contact


@router.get(
    "/{contact_id}",
    response_model=Contact,
    summary="Get a contact",
    responses=ERROR_RESPONSES,
)
async def get_contact(contact_id: str, db: DbDep, response: Response) -> Contact:
    result = await db.select("contacts", params={"select": "*", "id": f"eq.{contact_id}"})
    row = result.one("Contact")
    set_etag(response, row)
    return Contact.model_validate(row)


@router.patch(
    "/{contact_id}",
    response_model=Contact,
    summary="Update a contact",
    responses=ERROR_RESPONSES,
)
async def update_contact(
    contact_id: str,
    body: ContactUpdate,
    db: DbDep,
    user: CurrentUserDep,
    response: Response,
    if_match: IfMatchDep,
) -> Contact:
    changes = body.changes()
    if not changes:
        return await get_contact(contact_id, db, response)
    validated = ContactUpdate.model_validate(changes).model_dump(exclude_unset=True, mode="json")
    # Stamped server-side, never client-supplied -- see ContactUpdate's comment.
    if validated.get("ai_call_consent") is True:
        validated["ai_call_consent_at"] = datetime.now(timezone.utc).isoformat()
        validated["ai_call_consent_recorded_by"] = user.sub
    elif validated.get("ai_call_consent") is False:
        validated["ai_call_consent_at"] = None
        validated["ai_call_consent_recorded_by"] = None
    row = await update_guarded(
        db,
        "contacts",
        record_id=contact_id,
        changes=validated,
        if_match=if_match,
        what="Contact",
    )
    set_etag(response, row)
    return Contact.model_validate(row)


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a contact",
    description=(
        "A soft delete: the row is marked deleted and disappears from every query, but is "
        "retained for recovery and audit. Fails with 409 when a lead still names this "
        "contact as its primary contact; reassign the lead first."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_contact(contact_id: str, db: DbDep, if_match: IfMatchDep) -> Response:
    # Existence, permission and the referenced-lead check all happen inside the function,
    # in one statement, so there is no window between checking and deleting.
    await soft_delete_guarded(
        db,
        "contacts",
        record_id=contact_id,
        if_match=if_match,
        what="Contact",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
