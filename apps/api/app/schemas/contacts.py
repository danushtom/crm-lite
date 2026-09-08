"""Contact request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.domain.enums import LeadSource
from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class ContactCreate(StrictAPIModel):
    company_id: str = Field(description="Parent company UUID.")
    full_name: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120, description="Job title at the company.")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    linkedin_url: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=1000)
    source: LeadSource | None = None
    is_primary: bool = Field(default=False, description="Primary point of contact at the company.")


class ContactUpdate(PatchModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    linkedin_url: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=1000)
    source: LeadSource | None = None
    is_primary: bool | None = None
    # Deliberately no ai_call_consent_at/_recorded_by here -- those are stamped server-side
    # (see update_contact()) when this flips true, never client-supplied.
    ai_call_consent: bool | None = Field(
        default=None, description="Required before a voice agent may place an outbound AI call to this contact."
    )


class CompanyRef(APIModel):
    """Embedded parent company (PostgREST resource embedding)."""

    name: str | None = None


class Contact(APIModel):
    id: str
    company_id: str
    full_name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    avatar_url: str | None = None
    source: LeadSource | None = Field(
        default=None,
        description="Coarse channel. Derived from the UTM fields below for captured contacts.",
    )
    is_primary: bool = False
    ai_call_consent: bool = False
    created_at: datetime | None = None

    # Marketing attribution, exactly as the click carried it. Read-only: these are stamped by
    # the public capture endpoint and are not part of ContactCreate/ContactUpdate, so nobody
    # can rewrite where a lead came from after the fact.
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None
    landing_page_url: str | None = None
    referrer_url: str | None = None
    captured_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )


class ContactWithCompany(Contact):
    """List representation: includes the parent company name to avoid an N+1 on the client."""

    companies: CompanyRef | None = None
