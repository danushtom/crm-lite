"""Company request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domain.enums import CompanySegment
from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class CompanyBase(StrictAPIModel):
    name: str = Field(min_length=1, max_length=200, description="Registered or trading name.")
    industry: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=60, description="Headcount band, e.g. '11-50'.")
    website: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200, description="'City, Country'.")
    logo_url: str | None = Field(default=None, max_length=1000)
    linkedin_url: str | None = Field(default=None, max_length=500)
    segment: CompanySegment | None = None


class CompanyCreate(CompanyBase):
    """Body for creating a company. ``created_by`` is taken from the access token."""


class CompanyUpdate(PatchModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=60)
    website: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    logo_url: str | None = Field(default=None, max_length=1000)
    linkedin_url: str | None = Field(default=None, max_length=500)
    segment: CompanySegment | None = None


class Company(APIModel):
    id: str
    name: str
    industry: str | None = None
    size: str | None = None
    website: str | None = None
    location: str | None = None
    logo_url: str | None = None
    linkedin_url: str | None = None
    segment: CompanySegment | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    version: int = Field(
        default=1,
        description="Monotonic row version. Returned as an ETag; send it back via If-Match.",
    )
