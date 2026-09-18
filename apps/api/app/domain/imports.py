"""CSV import: the field catalog and the value normalisers. Pure -- no I/O.

The catalog is served to the web app (``GET /imports/fields``), which uses each field's
``aliases`` to pre-map a file's columns. The aliases cover the headers HubSpot, Pipedrive, Zoho
and Salesforce exports use, plus the obvious spellings, because the first import is usually
someone leaving one of those.

Normalisers are lenient where a wrong guess is harmless and strict where it is not: an unknown
lead source becomes ``other`` with a warning (the lead is still worth having), but an
ambiguous date like ``03/04/2026`` is an error rather than a coin toss between March and April,
because a follow-up silently scheduled a month out is worse than a row the user has to fix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urlsplit

from app.domain.enums import CompanySegment, LeadSource, LeadStage, ProjectType

ImportKind = Literal["companies", "contacts", "leads"]

#: Rows per request. The web app batches a file into requests of this size.
MAX_ROWS_PER_REQUEST = 200


@dataclass(frozen=True, slots=True)
class ImportField:
    key: str
    label: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    help: str = ""


_COMPANY = ImportField(
    "company", "Company name", True,
    ("company", "company name", "organization", "organisation", "organization name", "account",
     "account name", "business name"),
)
_COMPANY_WEBSITE = ImportField(
    "company_website", "Company website", False,
    ("website", "company website", "domain", "company domain", "url", "web", "site"),
    "Used to match an existing company by domain before falling back to its name.",
)
_FULL_NAME = ImportField(
    "full_name", "Contact full name", False,
    # "Name" lives here, not on the company: in a people or deals export it is the person.
    ("full name", "name", "contact name", "contact", "person", "person name", "contact full name"),
    "Or map first and last name separately.",
)
_FIRST = ImportField("first_name", "First name", False, ("first name", "firstname", "given name", "first"))
_LAST = ImportField("last_name", "Last name", False, ("last name", "lastname", "surname", "family name", "last"))
_EMAIL = ImportField(
    "email", "Email", False,
    ("email", "email address", "e-mail", "work email", "contact email", "primary email", "person - email"),
    "Contacts are matched on email, so re-importing a file does not duplicate them.",
)
_PHONE = ImportField(
    "phone", "Phone", False,
    ("phone", "phone number", "mobile", "mobile phone", "work phone", "telephone", "contact phone", "person - phone"),
)
_TITLE = ImportField("title", "Job title", False, ("title", "job title", "role", "position", "designation"))
_CONTACT_LINKEDIN = ImportField(
    "linkedin_url", "LinkedIn URL", False, ("linkedin", "linkedin url", "linkedin profile", "profile url")
)

FIELDS: dict[str, tuple[ImportField, ...]] = {
    "companies": (
        ImportField(
            "name", "Company name", True,
            ("name", "company", "company name", "organization", "organisation", "organization name",
             "account", "account name", "business name"),
        ),
        ImportField("website", "Website", False, _COMPANY_WEBSITE.aliases, _COMPANY_WEBSITE.help),
        ImportField("industry", "Industry", False, ("industry", "sector", "vertical")),
        ImportField(
            "size", "Size", False,
            ("size", "company size", "employees", "number of employees", "headcount", "employee count"),
        ),
        ImportField(
            "location", "Location", False,
            ("location", "city", "country", "address", "hq", "headquarters", "region"),
        ),
        ImportField(
            "linkedin_url", "LinkedIn URL", False,
            ("linkedin", "linkedin url", "company linkedin", "linkedin page"),
        ),
        ImportField(
            "segment", "Segment", False, ("segment", "tier", "company type"),
            "One of: SME, startup, enterprise.",
        ),
    ),
    "contacts": (
        _FULL_NAME, _FIRST, _LAST, _EMAIL, _PHONE, _TITLE, _CONTACT_LINKEDIN, _COMPANY, _COMPANY_WEBSITE,
    ),
    "leads": (
        _COMPANY,
        _COMPANY_WEBSITE,
        _FULL_NAME,
        _FIRST,
        _LAST,
        _EMAIL,
        _PHONE,
        _TITLE,
        ImportField(
            "project_type", "Project type", False,
            ("project type", "project", "service", "category", "type", "deal type"),
            "MVP, SaaS, AI, web app, ERP -- anything else becomes Other.",
        ),
        ImportField(
            "lead_source", "Lead source", False,
            ("lead source", "source", "channel", "original source", "origin"),
            "Cold call, referral, website, LinkedIn -- anything else becomes Other.",
        ),
        ImportField(
            "owner_email", "Owner email", False,
            ("owner", "owner email", "lead owner", "deal owner", "assigned to", "sales rep", "account owner"),
            "An admin can assign leads to teammates by email; otherwise leads are yours.",
        ),
        ImportField(
            "deal_title", "Deal title", False,
            ("deal", "deal name", "deal title", "opportunity", "opportunity name"),
        ),
        ImportField(
            "stage", "Stage", False,
            ("stage", "deal stage", "pipeline stage", "lead status", "status"),
            "One of the pipeline stages, e.g. Prospect, Proposal sent, Won.",
        ),
        ImportField(
            "quoted_value", "Deal value", False,
            ("value", "amount", "deal value", "deal amount", "quoted value", "budget", "expected revenue"),
        ),
        ImportField("currency", "Currency", False, ("currency", "deal currency", "currency code")),
        ImportField(
            "next_followup_date", "Next follow-up", False,
            ("next follow up", "next follow-up", "follow up date", "follow-up date", "next step date",
             "next activity date", "next contact date"),
            "YYYY-MM-DD.",
        ),
        ImportField(
            "last_contact_date", "Last contacted", False,
            ("last contacted", "last contact date", "last activity", "last activity date"),
            "YYYY-MM-DD.",
        ),
        ImportField("tags", "Tags", False, ("tags", "labels", "tag", "label"), "Separated by ; or ,."),
    ),
}


class RowError(ValueError):
    """A row that cannot be imported as given. The message is shown to the user as-is."""


@dataclass(slots=True)
class Warnings:
    items: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.items.append(message)


def text(values: dict[str, str | None], key: str, *, max_length: int = 500) -> str | None:
    """A trimmed value, or None when blank. Over-long values are an error, not a truncation:
    a silently shortened email or URL is a broken one."""
    raw = values.get(key)
    if raw is None:
        return None
    value = " ".join(str(raw).split()) if key not in {"tags"} else str(raw).strip()
    if not value:
        return None
    if len(value) > max_length:
        raise RowError(f"{key.replace('_', ' ').capitalize()} is longer than {max_length} characters")
    return value


def full_name(values: dict[str, str | None]) -> str | None:
    name = text(values, "full_name", max_length=200)
    if name:
        return name
    parts = [text(values, "first_name", max_length=100), text(values, "last_name", max_length=100)]
    joined = " ".join(p for p in parts if p)
    return joined or None


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email(values: dict[str, str | None]) -> str | None:
    value = text(values, "email", max_length=254)
    if value is None:
        return None
    value = value.lower()
    if not _EMAIL_RE.match(value):
        raise RowError(f"'{value}' is not a valid email address")
    return value


def domain_of(website: str | None) -> str | None:
    """``https://www.Acme.com/about`` -> ``acme.com``. None when there is no usable host."""
    if not website:
        return None
    candidate = website.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    host = (urlsplit(candidate).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


_SOURCE_ALIASES = {
    "cold_call": LeadSource.COLD_CALL,
    "cold_calling": LeadSource.COLD_CALL,
    "outbound": LeadSource.COLD_CALL,
    "cold_outreach": LeadSource.COLD_CALL,
    "cold_email": LeadSource.COLD_CALL,
    "referral": LeadSource.REFERRAL,
    "referrals": LeadSource.REFERRAL,
    "word_of_mouth": LeadSource.REFERRAL,
    "partner": LeadSource.REFERRAL,
    "website": LeadSource.WEBSITE,
    "web": LeadSource.WEBSITE,
    "inbound": LeadSource.WEBSITE,
    "organic_search": LeadSource.WEBSITE,
    "seo": LeadSource.WEBSITE,
    "web_form": LeadSource.WEBSITE,
    "contact_form": LeadSource.WEBSITE,
    "linkedin": LeadSource.LINKEDIN,
    "linked_in": LeadSource.LINKEDIN,
    "social_media": LeadSource.OTHER,
    "other": LeadSource.OTHER,
}

_PROJECT_ALIASES = {
    "mvp": ProjectType.MVP,
    "prototype": ProjectType.MVP,
    "saas": ProjectType.SAAS,
    "saas_product": ProjectType.SAAS,
    "ai": ProjectType.AI,
    "ml": ProjectType.AI,
    "ai_ml": ProjectType.AI,
    "machine_learning": ProjectType.AI,
    "webapp": ProjectType.WEBAPP,
    "web_app": ProjectType.WEBAPP,
    "web_application": ProjectType.WEBAPP,
    "website": ProjectType.WEBAPP,
    "erp": ProjectType.ERP,
    "other": ProjectType.OTHER,
}

_STAGE_ALIASES = {
    **{s.value: s for s in LeadStage},
    "new": LeadStage.PROSPECT,
    "lead": LeadStage.PROSPECT,
    "open": LeadStage.PROSPECT,
    "contacted": LeadStage.CONTACTING,
    "in_contact": LeadStage.CONTACTING,
    "qualified": LeadStage.DISCOVERY_SCHEDULED,
    "discovery": LeadStage.DISCOVERY_SCHEDULED,
    "meeting_scheduled": LeadStage.DISCOVERY_SCHEDULED,
    "requirements": LeadStage.REQUIREMENTS_GATHERING,
    "solution": LeadStage.SOLUTION_DESIGN,
    "proposal": LeadStage.PROPOSAL_SENT,
    "proposal_made": LeadStage.PROPOSAL_SENT,
    "presentation_scheduled": LeadStage.SOLUTION_DESIGN,
    "negotiations": LeadStage.NEGOTIATION,
    "contract_sent": LeadStage.NEGOTIATION,
    "closed_won": LeadStage.WON,
    "closedwon": LeadStage.WON,
    "closed_lost": LeadStage.LOST,
    "closedlost": LeadStage.LOST,
    "on_hold": LeadStage.ON_HOLD,
    "paused": LeadStage.ON_HOLD,
    "nurture": LeadStage.FOLLOWUP_LATER,
    "follow_up_later": LeadStage.FOLLOWUP_LATER,
}


def lead_source(values: dict[str, str | None], warnings: Warnings) -> LeadSource:
    raw = text(values, "lead_source", max_length=100)
    if raw is None:
        return LeadSource.OTHER
    source = _SOURCE_ALIASES.get(_slug(raw))
    if source is None:
        warnings.add(f"Lead source '{raw}' is not one of ours; recorded as Other")
        return LeadSource.OTHER
    return source


def project_type(values: dict[str, str | None], warnings: Warnings) -> ProjectType:
    raw = text(values, "project_type", max_length=100)
    if raw is None:
        return ProjectType.OTHER
    kind = _PROJECT_ALIASES.get(_slug(raw))
    if kind is None:
        warnings.add(f"Project type '{raw}' is not one of ours; recorded as Other")
        return ProjectType.OTHER
    return kind


def stage(values: dict[str, str | None]) -> LeadStage | None:
    raw = text(values, "stage", max_length=100)
    if raw is None:
        return None
    found = _STAGE_ALIASES.get(_slug(raw))
    if found is None:
        valid = ", ".join(s.value.replace("_", " ") for s in LeadStage)
        raise RowError(f"Stage '{raw}' is not a pipeline stage (use one of: {valid})")
    return found


def segment(values: dict[str, str | None], warnings: Warnings) -> CompanySegment | None:
    raw = text(values, "segment", max_length=60)
    if raw is None:
        return None
    try:
        return CompanySegment(_slug(raw))
    except ValueError:
        warnings.add(f"Segment '{raw}' is not SME, startup or enterprise; left blank")
        return None


def money(values: dict[str, str | None]) -> Decimal | None:
    raw = text(values, "quoted_value", max_length=40)
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", raw.replace(",", ""))
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise RowError(f"Deal value '{raw}' is not a number") from None
    if amount < 0 or amount >= Decimal("10000000000"):
        raise RowError(f"Deal value '{raw}' is out of range")
    return amount.quantize(Decimal("0.01"))


def currency(values: dict[str, str | None]) -> str | None:
    raw = text(values, "currency", max_length=10)
    if raw is None:
        return None
    symbols = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
    code = symbols.get(raw, raw).upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise RowError(f"Currency '{raw}' is not a 3-letter code like INR or USD")
    return code


def parse_date(values: dict[str, str | None], key: str) -> date | None:
    """ISO dates, plus day/month/year or month/day/year when only one reading is possible.

    ``2026-03-04`` is fine; ``25/12/2026`` can only be the 25th of December; ``03/04/2026`` could
    be either and is refused, with the fix in the message.
    """
    raw = text(values, key, max_length=40)
    if raw is None:
        return None
    label = key.replace("_", " ")
    head = raw.split("T")[0].split(" ")[0]
    try:
        return date.fromisoformat(head)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", head)
    if match:
        first, second, year = (int(g) for g in match.groups())
        readings = set()
        for day, month in ((first, second), (second, first)):
            try:
                readings.add(date(year, month, day))
            except ValueError:
                continue
        if len(readings) == 1:
            return readings.pop()
        if len(readings) == 2:
            raise RowError(
                f"The {label} '{raw}' could be read two ways; write it as YYYY-MM-DD"
            )
    raise RowError(f"The {label} '{raw}' is not a date; write it as YYYY-MM-DD")


def tags(values: dict[str, str | None]) -> list[str]:
    raw = text(values, "tags", max_length=1000)
    if raw is None:
        return []
    found: list[str] = []
    for part in re.split(r"[;,]", raw):
        tag = part.strip()[:50]
        if tag and tag.lower() not in {t.lower() for t in found}:
            found.append(tag)
    return found[:25]
