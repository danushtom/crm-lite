"""Contact endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbDep
from app.core.errors import ConflictError, ForbiddenError
from app.core.pagination import Page, PageParamsDep
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
        "order": "created_at.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if company_id:
        params["company_id"] = f"eq.{company_id}"
    if search and search.strip():
        cleaned = search.strip().replace("*", "").replace("%", "").replace(",", "")[:200]
        if cleaned:
            params["or"] = f"(full_name.ilike.*{cleaned}*,email.ilike.*{cleaned}*)"

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
async def get_contact(contact_id: str, db: DbDep) -> Contact:
    result = await db.select("contacts", params={"select": "*", "id": f"eq.{contact_id}"})
    return Contact.model_validate(result.one("Contact"))


@router.patch(
    "/{contact_id}",
    response_model=Contact,
    summary="Update a contact",
    responses=ERROR_RESPONSES,
)
async def update_contact(contact_id: str, body: ContactUpdate, db: DbDep) -> Contact:
    changes = body.changes()
    if not changes:
        return await get_contact(contact_id, db)
    result = await db.update(
        "contacts", {"id": f"eq.{contact_id}"}, ContactUpdate.model_validate(changes).model_dump(
            exclude_unset=True, mode="json"
        )
    )
    return Contact.model_validate(result.one("Contact"))


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a contact",
    description=(
        "Fails with 409 when a lead still names this contact as its primary contact; "
        "reassign the lead first."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_contact(contact_id: str, db: DbDep) -> Response:
    existing = await db.select("contacts", params={"select": "id", "id": f"eq.{contact_id}"})
    existing.one("Contact")

    referencing = await db.select(
        "leads",
        params={"select": "id", "primary_contact_id": f"eq.{contact_id}", "limit": "1"},
    )
    if referencing.first() is not None:
        raise ConflictError("Contact is the primary contact on a lead; reassign the lead first")

    deleted = await db.delete("contacts", {"id": f"eq.{contact_id}"})
    if deleted.first() is None:
        # Visible to SELECT but filtered out of DELETE => the caller lacks the delete grant.
        raise ForbiddenError("You do not have permission to delete this contact")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
