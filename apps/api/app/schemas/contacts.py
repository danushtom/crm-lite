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
    source: LeadSource | None = None
    is_primary: bool = False
    created_at: datetime | None = None


class ContactWithCompany(Contact):
    """List representation: includes the parent company name to avoid an N+1 on the client."""

    companies: CompanyRef | None = None
