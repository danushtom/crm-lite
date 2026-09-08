"""Turning a public form submission into a company, a contact and a lead.

Everything here runs on the service-role client, because the caller is an anonymous web form
with no Supabase session. That means row-level security is *not* the safety net it is elsewhere
in this API, so the tenant boundary is enforced explicitly instead: ``organization_id`` is
resolved once from the capture key and every subsequent query is filtered by that resolved
value. Nothing from the request body is ever used to decide which organization is written to.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from app.db.supabase import SupabaseClient
from app.domain.attribution import derive_lead_source
from app.schemas.lead_capture import LeadCaptureSubmission

logger = logging.getLogger(__name__)

#: Prefix makes a leaked key greppable in logs and obvious in a support ticket.
_KEY_PREFIX = "lck_"


def generate_key() -> str:
    """A capture key. 32 bytes of urandom, hex-encoded -- not a uuid4.

    A uuid would carry a version nibble and variant bits, so only 122 of its 128 bits are
    random, and it looks like a database id, which invites people to treat it as one.
    """
    return _KEY_PREFIX + secrets.token_hex(32)


async def resolve_key(admin_db: SupabaseClient, key: str) -> dict[str, Any] | None:
    """Look up a live capture key. Returns None for unknown, revoked, or malformed keys.

    Deliberately does not distinguish those cases: the caller turns all three into the same
    response, so a key holder cannot probe for which organizations exist.
    """
    if not key or not key.startswith(_KEY_PREFIX) or len(key) > 128:
        return None

    result = await admin_db.select(
        "lead_capture_keys",
        params={
            "select": "id,organization_id,owner_id,is_active",
            "key": f"eq.{key}",
            "is_active": "is.true",
        },
    )
    return result.first()


async def _resolve_owner(admin_db: SupabaseClient, organization_id: str, owner_id: str | None) -> str:
    """Who the captured lead belongs to.

    A key may name an owner; if it does not, or if that person has since been deactivated or
    moved organization, fall back to a full-access user in the *resolved* organization. The
    owner id on the key is still checked against that organization rather than trusted, because
    the database will reject a lead whose owner and company disagree about the tenant anyway --
    better to fail here with a clear reason than as a constraint violation.
    """
    if owner_id:
        result = await admin_db.select(
            "users",
            params={
                "select": "id",
                "id": f"eq.{owner_id}",
                "organization_id": f"eq.{organization_id}",
                "is_active": "is.true",
            },
        )
        if result.first():
            return owner_id

    fallback = await admin_db.select(
        "users",
        params={
            "select": "id,roles!inner(grants_full_access)",
            "organization_id": f"eq.{organization_id}",
            "is_active": "is.true",
            "roles.grants_full_access": "is.true",
            "order": "created_at.asc",
            "limit": "1",
        },
    )
    row = fallback.first()
    if row is None:
        raise LookupError(f"Organization {organization_id} has no active full-access user")
    return str(row["id"])


async def _find_or_create_company(
    admin_db: SupabaseClient, *, organization_id: str, name: str, created_by: str
) -> str:
    """Match an existing company by name within this organization, or create one.

    Matched case-insensitively on the exact name -- a form filled in as "acme inc" should not
    open a second company alongside "Acme Inc". Anything fuzzier belongs to a deduplication
    pass a human reviews, not to an unauthenticated write path.
    """
    escaped = name.strip().replace("*", "").replace("%", "").replace(",", "")
    existing = await admin_db.select(
        "companies",
        params={
            "select": "id",
            "organization_id": f"eq.{organization_id}",
            "name": f"ilike.{escaped}",
            "deleted_at": "is.null",
            "limit": "1",
        },
    )
    row = existing.first()
    if row:
        return str(row["id"])

    # organization_id is set by companies_set_org from created_by, which we resolved above --
    # it is not taken from anything the submission supplied.
    created = await admin_db.insert("companies", {"name": name.strip(), "created_by": created_by})
    return str(created.one("Company")["id"])


async def capture(
    admin_db: SupabaseClient,
    *,
    key_row: dict[str, Any],
    submission: LeadCaptureSubmission,
) -> None:
    """Write the company, contact and lead for one submission.

    Not idempotent by design: a person who fills the form twice from two different ads has
    genuinely arrived twice, and collapsing that would lose the attribution for the second
    click. Duplicate contacts are a review problem, not something to silently discard.
    """
    organization_id = str(key_row["organization_id"])
    owner_id = await _resolve_owner(admin_db, organization_id, key_row.get("owner_id"))

    company_id = await _find_or_create_company(
        admin_db,
        organization_id=organization_id,
        name=submission.company_name,
        created_by=owner_id,
    )

    now = datetime.now(timezone.utc).isoformat()
    lead_source = derive_lead_source(submission.utm_source, submission.utm_medium)

    contact = await admin_db.insert(
        "contacts",
        {
            "company_id": company_id,
            "full_name": submission.full_name.strip(),
            "email": submission.email,
            "phone": submission.phone,
            "role": submission.role,
            "source": lead_source.value,
            "is_primary": False,
            "utm_source": submission.utm_source,
            "utm_medium": submission.utm_medium,
            "utm_campaign": submission.utm_campaign,
            "utm_content": submission.utm_content,
            "utm_term": submission.utm_term,
            "landing_page_url": submission.landing_page_url,
            "referrer_url": submission.referrer_url,
            "captured_at": now,
            # Never set from the submission: an inbound form cannot consent someone to being
            # cold-called by an AI. That has to be recorded by a human on the contact record.
            "ai_call_consent": False,
        },
    )
    contact_id = str(contact.one("Contact")["id"])

    lead = await admin_db.insert(
        "leads",
        {
            "company_id": company_id,
            "primary_contact_id": contact_id,
            "owner_id": owner_id,
            "project_type": "other",
            "lead_source": lead_source.value,
            "last_contact_date": now,
        },
    )
    lead_id = str(lead.one("Lead")["id"])

    if submission.message:
        # actor_type 'system' with no performed_by: nobody in the organization did this, the
        # prospect did. Attributing it to the assigned owner would put words in their mouth.
        await admin_db.insert(
            "activities",
            {
                "lead_id": lead_id,
                "type": "note",
                "description": submission.message,
                "actor_type": "system",
                "performed_by": None,
            },
        )

    await admin_db.update(
        "lead_capture_keys", {"id": f"eq.{key_row['id']}"}, {"last_used_at": now}
    )

    await admin_db.insert(
        "notifications",
        {
            "user_id": owner_id,
            "type": "lead_captured",
            "title": f"New lead: {submission.company_name.strip()}",
            "body": f"{submission.full_name.strip()} submitted a form.",
            "dedupe_key": f"lead_captured:{lead_id}",
            "metadata": {"lead_id": lead_id, "contact_id": contact_id},
        },
    )
