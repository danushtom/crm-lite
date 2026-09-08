"""Public lead-capture submissions, and the keys that authenticate them."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class LeadCaptureSubmission(StrictAPIModel):
    """What a public form posts.

    Every field is length-capped: this endpoint is reachable by anyone who has the key, so the
    bound belongs in the schema rather than in the database's own column limits. `StrictAPIModel`
    rejects unknown fields, so a caller cannot smuggle in `organization_id`, `owner_id` or
    anything else the server is supposed to decide -- which is the whole risk with a public
    write path.
    """

    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    company_name: str = Field(
        min_length=1, max_length=200, description="Free text; matched to an existing company by name, or created."
    )
    role: str | None = Field(default=None, max_length=120)
    message: str | None = Field(
        default=None, max_length=2000, description="Whatever the form's free-text field collected."
    )

    utm_source: str | None = Field(default=None, max_length=120)
    utm_medium: str | None = Field(default=None, max_length=120)
    utm_campaign: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)
    utm_term: str | None = Field(default=None, max_length=200)
    landing_page_url: str | None = Field(default=None, max_length=2000)
    referrer_url: str | None = Field(default=None, max_length=2000)


class LeadCaptureResult(APIModel):
    """Deliberately says nothing about what happened.

    No ids, no "we already had this person", no counts. The endpoint is public, so any detail
    here would let a key holder probe the CRM: submitting an address and reading back whether
    it was new is enough to enumerate a customer list.
    """

    received: bool = True


class LeadCaptureKey(APIModel):
    id: str
    name: str
    key: str = Field(description="The secret itself. Returned only to a full-access role.")
    is_active: bool
    owner_id: str | None = Field(
        default=None,
        description="Who captured leads are assigned to. Null means the organization's first full-access user, resolved at capture time.",
    )
    created_at: datetime | None = None
    last_used_at: datetime | None = Field(
        default=None, description="Last successful capture, so a dead landing page is visible."
    )


class LeadCaptureKeyCreate(StrictAPIModel):
    name: str = Field(
        min_length=1, max_length=120, description="Where this key is used, e.g. 'Meta lead form'."
    )
    owner_id: str | None = None


class LeadCaptureKeyUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = Field(
        default=None, description="Set false to revoke. Revoked keys stop resolving immediately."
    )
    owner_id: str | None = None
