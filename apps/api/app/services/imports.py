"""CSV import: turn mapped rows into companies, contacts and leads.

**Runs as the caller** (the RLS-scoped client), exactly like creating the same records one at a
time through the UI: an import can only create what its user could, owns what its user would,
and matches only records its user can see. ``organization_id`` is set by the tables' own
triggers; nothing here names an organization.

**Re-running a file is safe.** Companies are matched by website domain, then by exact
(case-insensitive) name; contacts by email, or by name within the same company when there is
no email; leads by company plus primary contact. A match is reported as ``existing`` (or
``skipped`` for a lead) and nothing is written for it -- an import never overwrites a record
someone has since edited.

**One bad row never sinks a batch.** Rows are validated first, then written with one bulk
insert per table; if PostgREST rejects the bulk insert, it is retried row by row so the failure
is pinned to the row that caused it and every other row still lands.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from app.core.errors import APIError
from app.db.supabase import SupabaseClient
from app.domain import imports as norm
from app.domain.imports import ImportKind, RowError, Warnings
from app.services.leads import score_for

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Concurrent lookups per request. Enough to make a 200-row batch quick, few enough not to
#: look like a burst to PostgREST.
_LOOKUP_CONCURRENCY = 8


@dataclass(slots=True)
class RowResult:
    row_number: int
    status: str = "error"  # created | existing | skipped | error
    record_id: str | None = None
    message: str | None = None
    warnings: list[str] = field(default_factory=list)


async def _bounded(calls: list[Callable[[], Awaitable[T]]]) -> list[T]:
    gate = asyncio.Semaphore(_LOOKUP_CONCURRENCY)

    async def run(call: Callable[[], Awaitable[T]]) -> T:
        async with gate:
            return await call()

    return list(await asyncio.gather(*(run(c) for c in calls)))


def _exact_ilike(value: str) -> str:
    """An ``ilike`` value that matches ``value`` exactly, ignoring case. LIKE's wildcards are
    escaped; PostgREST's own ``*`` wildcard cannot be escaped, so it is dropped (the lookup then
    simply misses, and the import creates rather than matches)."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "ilike." + escaped.replace("*", "")


def _message(exc: Exception) -> str:
    if isinstance(exc, APIError):
        return exc.detail
    return "Could not be saved"


async def _insert_many(
    db: SupabaseClient, table: str, payloads: list[dict[str, Any]]
) -> list[dict[str, Any] | Exception]:
    """Bulk insert, falling back to one insert per row to isolate a failure."""
    if not payloads:
        return []
    try:
        rows = (await db.insert(table, payloads)).rows
        if len(rows) == len(payloads):
            return list(rows)
        logger.warning("import_bulk_insert_short table=%s sent=%s got=%s", table, len(payloads), len(rows))
    except APIError as exc:
        logger.info("import_bulk_insert_fallback table=%s reason=%s", table, exc.detail)

    results: list[dict[str, Any] | Exception] = []
    for payload in payloads:
        try:
            results.append((await db.insert(table, payload)).one(table))
        except APIError as exc:
            results.append(exc)
    return results


# --- Companies ---------------------------------------------------------------------------------


async def _find_company(db: SupabaseClient, name: str, domain: str | None) -> str | None:
    if domain:
        candidates = await db.select(
            "companies",
            params={"select": "id,website", "website": f"ilike.*{domain.replace('*', '')}*", "limit": "20"},
        )
        for row in candidates.rows:
            if norm.domain_of(row.get("website")) == domain:
                return str(row["id"])
    found = await db.select("companies", params={"select": "id", "name": _exact_ilike(name), "limit": "1"})
    row = found.first()
    return str(row["id"]) if row else None


@dataclass(slots=True)
class _CompanyWanted:
    name: str
    domain: str | None
    payload: dict[str, Any]
    rows: list[int] = field(default_factory=list)  # indexes into the batch


async def _resolve_companies(
    db: SupabaseClient, wanted: dict[str, _CompanyWanted], user_id: str
) -> dict[str, tuple[str | None, bool, str | None]]:
    """key -> (company id, created?, error). One lookup per distinct company, then one bulk
    insert for the ones that do not exist yet."""
    keys = list(wanted)
    found = await _bounded([lambda w=wanted[k]: _find_company(db, w.name, w.domain) for k in keys])
    out: dict[str, tuple[str | None, bool, str | None]] = {}
    missing: list[str] = []
    for key, company_id in zip(keys, found):
        if company_id:
            out[key] = (company_id, False, None)
        else:
            missing.append(key)

    payloads = [{**wanted[k].payload, "created_by": user_id} for k in missing]
    for key, result in zip(missing, await _insert_many(db, "companies", payloads)):
        if isinstance(result, Exception):
            out[key] = (None, False, _message(result))
        else:
            out[key] = (str(result["id"]), True, None)
    return out


def _company_key(name: str) -> str:
    return " ".join(name.lower().split())


# --- Contacts ----------------------------------------------------------------------------------


async def _find_contact(
    db: SupabaseClient, company_id: str, name: str, email: str | None
) -> tuple[str, str] | None:
    """(contact id, its company id) for an existing match, or None."""
    if email:
        params = {"select": "id,company_id", "email": _exact_ilike(email), "limit": "1"}
    else:
        params = {
            "select": "id,company_id",
            "company_id": f"eq.{company_id}",
            "full_name": _exact_ilike(name),
            "limit": "1",
        }
    row = (await db.select("contacts", params=params)).first()
    return (str(row["id"]), str(row["company_id"])) if row else None


def _contact_key(company_id: str, name: str, email: str | None) -> str:
    return f"email:{email}" if email else f"name:{company_id}:{' '.join(name.lower().split())}"


# --- Entry point -------------------------------------------------------------------------------


@dataclass(slots=True)
class _Parsed:
    index: int
    values: dict[str, Any]
    warnings: Warnings


async def run_import(
    db: SupabaseClient,
    kind: ImportKind,
    rows: list[tuple[int, dict[str, str | None]]],
    *,
    user_id: str,
    full_access: bool,
) -> list[RowResult]:
    results = [RowResult(row_number=n) for n, _ in rows]
    parsed: list[_Parsed] = []
    for index, (_, values) in enumerate(rows):
        warnings = Warnings()
        try:
            parsed.append(_Parsed(index, _parse(kind, values, warnings), warnings))
        except RowError as exc:
            results[index].message = str(exc)
        # The same list object: warnings added in later phases (owner, deal) land here too.
        results[index].warnings = warnings.items

    if kind == "companies":
        await _import_companies(db, parsed, results, user_id)
    elif kind == "contacts":
        await _import_contacts(db, parsed, results, user_id)
    else:
        await _import_leads(db, parsed, results, user_id, full_access)
    return results


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _enum_value(value: Any) -> str | None:
    return value.value if value is not None else None


def _parse(kind: ImportKind, values: dict[str, str | None], warnings: Warnings) -> dict[str, Any]:
    if kind == "companies":
        name = norm.text(values, "name", max_length=200)
        if not name:
            raise RowError("Company name is required")
        website = norm.text(values, "website")
        return {
            "name": name,
            "domain": norm.domain_of(website),
            "payload": _compact(
                {
                    "name": name,
                    "website": website,
                    "industry": norm.text(values, "industry", max_length=120),
                    "size": norm.text(values, "size", max_length=60),
                    "location": norm.text(values, "location", max_length=200),
                    "linkedin_url": norm.text(values, "linkedin_url"),
                    "segment": _enum_value(norm.segment(values, warnings)),
                }
            ),
        }

    company = norm.text(values, "company", max_length=200)
    person = norm.full_name(values)
    email = norm.email(values)
    website = norm.text(values, "company_website")
    contact = None
    if person or email:
        contact = _compact(
            {
                "full_name": person or email.split("@")[0],
                "email": email,
                "phone": norm.text(values, "phone", max_length=40),
                "role": norm.text(values, "title", max_length=120),
                "linkedin_url": norm.text(values, "linkedin_url"),
            }
        )

    if kind == "contacts":
        if not company:
            raise RowError("Company is required: every contact belongs to a company")
        if contact is None:
            raise RowError("A name or an email is required")
        return {"company": company, "domain": norm.domain_of(website), "website": website, "contact": contact}

    if not company:
        raise RowError("Company is required: every lead belongs to a company")
    owner_email = norm.text(values, "owner_email", max_length=254)
    return {
        "company": company,
        "domain": norm.domain_of(website),
        "website": website,
        "contact": contact,
        "owner_email": owner_email.lower() if owner_email else None,
        "lead": {
            "project_type": norm.project_type(values, warnings).value,
            "lead_source": norm.lead_source(values, warnings).value,
            "next_followup_date": _iso(norm.parse_date(values, "next_followup_date")),
            "last_contact_date": _iso(norm.parse_date(values, "last_contact_date")),
            "tags": norm.tags(values),
        },
        "deal": _compact(
            {
                "title": norm.text(values, "deal_title", max_length=200),
                "stage": _enum_value(norm.stage(values)),
                "quoted_value": norm.money(values),
                "currency": norm.currency(values),
            }
        ),
    }


async def _import_companies(
    db: SupabaseClient, parsed: list[_Parsed], results: list[RowResult], user_id: str
) -> None:
    wanted: dict[str, _CompanyWanted] = {}
    first_row: dict[str, int] = {}
    for p in parsed:
        key = _company_key(p.values["name"])
        entry = wanted.setdefault(key, _CompanyWanted(p.values["name"], p.values["domain"], p.values["payload"]))
        entry.rows.append(p.index)
        first_row.setdefault(key, p.index)

    resolved = await _resolve_companies(db, wanted, user_id)
    for key, entry in wanted.items():
        company_id, created, error = resolved[key]
        for index in entry.rows:
            result = results[index]
            if error:
                result.message = error
                continue
            result.record_id = company_id
            if created and index == first_row[key]:
                result.status = "created"
            else:
                result.status = "existing"
                if index != first_row[key]:
                    result.message = f"Same company as row {results[first_row[key]].row_number}"


async def _companies_for(
    db: SupabaseClient, parsed: list[_Parsed], results: list[RowResult], user_id: str
) -> dict[int, str]:
    """Resolve (match or create) the company every row names. Returns batch index -> id and marks
    rows whose company could not be created as errors."""
    wanted: dict[str, _CompanyWanted] = {}
    for p in parsed:
        key = _company_key(p.values["company"])
        payload = {"name": p.values["company"]}
        if p.values.get("website"):
            payload["website"] = p.values["website"]
        entry = wanted.setdefault(key, _CompanyWanted(p.values["company"], p.values["domain"], payload))
        entry.rows.append(p.index)

    resolved = await _resolve_companies(db, wanted, user_id)
    by_index: dict[int, str] = {}
    for key, entry in wanted.items():
        company_id, _created, error = resolved[key]
        for index in entry.rows:
            if company_id:
                by_index[index] = company_id
            else:
                results[index].message = f"Company could not be created: {error}"
    return by_index


async def _contacts_for(
    db: SupabaseClient, parsed: list[_Parsed], company_ids: dict[int, str], results: list[RowResult]
) -> dict[int, tuple[str, bool]]:
    """Resolve each row's contact. Returns batch index -> (contact id, created?)."""
    wanted: dict[str, dict[str, Any]] = {}
    rows_for: dict[str, list[int]] = {}
    for p in parsed:
        contact = p.values.get("contact")
        if contact is None or p.index not in company_ids:
            continue
        key = _contact_key(company_ids[p.index], contact["full_name"], contact.get("email"))
        wanted.setdefault(key, {**contact, "company_id": company_ids[p.index]})
        rows_for.setdefault(key, []).append(p.index)

    keys = list(wanted)
    found = await _bounded(
        [
            lambda c=wanted[k]: _find_contact(db, c["company_id"], c["full_name"], c.get("email"))
            for k in keys
        ]
    )
    out: dict[int, tuple[str, bool]] = {}
    parsed_by_index = {p.index: p for p in parsed}
    missing = []
    for key, match in zip(keys, found):
        if match is None:
            missing.append(key)
            continue
        contact_id, their_company = match
        for index in rows_for[key]:
            out[index] = (contact_id, False)
            if their_company != company_ids[index]:
                # Same email, different company: most likely someone who changed jobs. Linked
                # anyway (an email identifies a person), but flagged for a human to look at.
                parsed_by_index[index].warnings.add(
                    "This email already belongs to a contact at a different company; linked to that contact"
                )

    inserted = await _insert_many(db, "contacts", [wanted[k] for k in missing])
    for key, result in zip(missing, inserted):
        for position, index in enumerate(rows_for[key]):
            if isinstance(result, Exception):
                results[index].message = f"Contact could not be created: {_message(result)}"
            else:
                # Only the first row naming a new contact "created" it.
                out[index] = (str(result["id"]), position == 0)
    return out


async def _import_contacts(
    db: SupabaseClient, parsed: list[_Parsed], results: list[RowResult], user_id: str
) -> None:
    company_ids = await _companies_for(db, parsed, results, user_id)
    contacts = await _contacts_for(db, parsed, company_ids, results)
    for index, (contact_id, created) in contacts.items():
        result = results[index]
        result.record_id = contact_id
        result.status = "created" if created else "existing"
        if not created:
            result.message = "A contact with this email (or name, at this company) already exists"


async def _owner_ids(
    db: SupabaseClient, parsed: list[_Parsed], user_id: str, full_access: bool
) -> dict[int, str]:
    emails = {p.values["owner_email"] for p in parsed if p.values.get("owner_email")}
    owners: dict[str, str] = {}
    if emails and full_access:
        users = await db.select("users", params={"select": "id,email", "is_active": "eq.true"})
        owners = {str(u["email"]).lower(): str(u["id"]) for u in users.rows if u.get("email")}

    by_index: dict[int, str] = {}
    for p in parsed:
        wanted = p.values.get("owner_email")
        if not wanted:
            by_index[p.index] = user_id
        elif not full_access:
            p.warnings.add("Only an admin can assign leads to others; this lead is yours")
            by_index[p.index] = user_id
        elif wanted in owners:
            by_index[p.index] = owners[wanted]
        else:
            p.warnings.add(f"No active teammate has the email {wanted}; this lead is yours")
            by_index[p.index] = user_id
    return by_index


async def _import_leads(
    db: SupabaseClient,
    parsed: list[_Parsed],
    results: list[RowResult],
    user_id: str,
    full_access: bool,
) -> None:
    company_ids = await _companies_for(db, parsed, results, user_id)
    contacts = await _contacts_for(db, parsed, company_ids, results)
    owners = await _owner_ids(db, parsed, user_id, full_access)

    # A row whose contact failed is not turned into a contact-less lead: it errors, so the user
    # fixes it rather than ending up with a lead missing the person the file named.
    ready = [
        p for p in parsed
        if p.index in company_ids and (p.values.get("contact") is None or p.index in contacts)
    ]

    existing: set[tuple[str, str | None]] = set()
    company_list = sorted({company_ids[p.index] for p in ready})
    for start in range(0, len(company_list), 100):
        chunk = company_list[start:start + 100]
        found = await db.select(
            "leads",
            params={"select": "company_id,primary_contact_id", "company_id": f"in.({','.join(chunk)})"},
        )
        existing |= {(str(r["company_id"]), r.get("primary_contact_id")) for r in found.rows}

    to_insert: list[_Parsed] = []
    payloads: list[dict[str, Any]] = []
    first_in_file: dict[tuple[str, str | None], int] = {}
    for p in ready:
        contact_id = contacts[p.index][0] if p.index in contacts else None
        key = (company_ids[p.index], contact_id)
        result = results[p.index]
        if key in existing:
            result.status = "skipped"
            result.message = "A lead for this company and contact already exists"
            continue
        if key in first_in_file:
            result.status = "skipped"
            result.message = f"Same lead as row {results[first_in_file[key]].row_number}"
            continue
        first_in_file[key] = p.index
        lead = {k: v for k, v in p.values["lead"].items() if v not in (None, [])}
        lead.update(company_id=key[0], owner_id=owners[p.index])
        if contact_id:
            lead["primary_contact_id"] = contact_id
        to_insert.append(p)
        payloads.append(lead)

    inserted = await _insert_many(db, "leads", payloads)
    created: dict[str, _Parsed] = {}
    for p, row in zip(to_insert, inserted):
        result = results[p.index]
        if isinstance(row, Exception):
            result.message = _message(row)
            continue
        result.status = "created"
        result.record_id = str(row["id"])
        created[result.record_id] = p

    await _apply_deals(db, created)


async def _apply_deals(db: SupabaseClient, created: dict[str, _Parsed]) -> None:
    """Fill in the pursuit each new lead's insert trigger opened, for rows that carried deal
    fields. A failure here leaves a valid lead with a default pursuit and says so."""
    with_deal = {lead_id: p for lead_id, p in created.items() if p.values["deal"]}
    if not with_deal:
        return
    lead_ids = list(with_deal)
    pursuits: dict[str, dict[str, Any]] = {}
    for start in range(0, len(lead_ids), 100):
        chunk = lead_ids[start:start + 100]
        found = await db.select(
            "opportunities",
            params={"select": "*", "lead_id": f"in.({','.join(chunk)})", "order": "created_at.asc,id.asc"},
        )
        for row in found.rows:
            pursuits.setdefault(str(row["lead_id"]), row)

    async def apply(lead_id: str) -> None:
        p = with_deal[lead_id]
        pursuit = pursuits.get(lead_id)
        if pursuit is None:
            p.warnings.add("The lead was created, but its deal details could not be applied")
            return
        updates: dict[str, Any] = {k: (str(v) if k == "quoted_value" else v) for k, v in p.values["deal"].items()}
        updates["priority_score"] = score_for(
            {**pursuit, **updates, "next_followup_date": p.values["lead"].get("next_followup_date")}, None
        )
        try:
            await db.update("opportunities", {"id": f"eq.{pursuit['id']}"}, updates)
        except APIError as exc:
            p.warnings.add(f"The lead was created, but its deal details were not saved: {exc.detail}")

    await _bounded([lambda lead_id=lead_id: apply(lead_id) for lead_id in lead_ids])
