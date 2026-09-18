"""CSV import: normalisers, de-duplication, batch isolation, ownership, and the endpoint.

``conftest.FakeDb`` answers by table and ignores filters, which cannot test matching. The
``TableDb`` below keeps rows per table and evaluates the handful of PostgREST filters the import
uses (``eq``, ``in``, ``ilike``), so "re-importing the same file creates nothing" is a real
assertion here rather than a canned response.
"""

from __future__ import annotations

import itertools
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from app.core.config import API_V1_PREFIX as V1
from app.core.errors import UnprocessableError
from app.domain import imports as norm
from app.domain.enums import LeadSource, LeadStage
from app.services.imports import run_import
from tests.conftest import FakeDb, FakeResult

ADMIN_ROLE = {"id": "role-admin", "name": "Admin", "grants_full_access": True, "role_permissions": []}
AGENT_ROLE = {"id": "role-agent", "name": "Agent", "grants_full_access": False, "role_permissions": []}
ME = "11111111-2222-3333-4444-555555555555"


def _like(pattern: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out += re.escape(pattern[i + 1])
            i += 2
            continue
        out += ".*" if ch in "*%" else "." if ch == "_" else re.escape(ch)
        i += 1
    return re.compile(out, re.I | re.S)


def _matches(row: dict[str, Any], key: str, expr: str) -> bool:
    op, _, value = expr.partition(".")
    actual = row.get(key)
    if op == "eq":
        return str(actual).lower() == value.lower() if isinstance(actual, bool) else str(actual) == value
    if op == "in":
        return str(actual) in value.strip("()").split(",")
    if op == "ilike":
        return actual is not None and bool(_like(value).fullmatch(str(actual)))
    if op == "is":
        return actual is None if value == "null" else bool(actual) == (value == "true")
    raise AssertionError(f"filter {key}={expr} not simulated")


class TableDb(FakeDb):
    _RESERVED = {"select", "order", "limit", "offset"}

    def __init__(self, *, reject=None, **tables: list[dict[str, Any]]):
        super().__init__()
        self.tables: dict[str, list[dict[str, Any]]] = {k: list(v) for k, v in tables.items()}
        self.reject = reject or (lambda table, row: None)
        self._ids = itertools.count(1)

    async def select(self, table, *, params=None, count=False):
        params = params or {}
        self.calls.append(("GET", table, {"params": params}))
        rows = [
            r for r in self.tables.get(table, [])
            if all(_matches(r, k, v) for k, v in params.items() if k not in self._RESERVED and "." not in k)
        ]
        if "limit" in params:
            rows = rows[: int(params["limit"])]
        return FakeResult(rows, count=len(rows))

    def _add(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        problem = self.reject(table, row)
        if problem:
            raise UnprocessableError(problem)
        stored = {"id": f"{table}-{next(self._ids)}", **row}
        self.tables.setdefault(table, []).append(stored)
        if table == "leads":  # ensure_opportunity_for_lead()
            self.tables.setdefault("opportunities", []).append(
                {"id": f"opp-{stored['id']}", "lead_id": stored["id"], "stage": "prospect",
                 "currency": "INR", "deal_probability": 50, "created_at": "2026-09-19T00:00:00Z"}
            )
        return stored

    async def insert(self, table, payload):
        self.calls.append(("POST", table, {"payload": payload}))
        if isinstance(payload, list):
            # Postgres runs a multi-row insert in one statement: one bad row fails all of them.
            for row in payload:
                problem = self.reject(table, row)
                if problem:
                    raise UnprocessableError(problem)
            return FakeResult([self._add(table, r) for r in payload])
        return FakeResult(self._add(table, payload))

    async def update(self, table, params, payload):
        self.calls.append(("PATCH", table, {"params": params, "payload": payload}))
        rows = [r for r in self.tables.get(table, []) if all(_matches(r, k, v) for k, v in params.items())]
        for r in rows:
            r.update(payload)
        return FakeResult(rows)

    def inserted(self, table: str) -> list[Any]:
        return [c[2]["payload"] for c in self.calls if c[0] == "POST" and c[1] == table]


def _users(role=ADMIN_ROLE, *extra):
    return [
        {"id": ME, "email": "me@example.com", "is_active": True, "organization_id": "org-1", "roles": role},
        *extra,
    ]


async def _run(db, kind, rows, *, full_access=True):
    numbered = [(i + 2, r) for i, r in enumerate(rows)]  # row 1 is the header
    return await run_import(db, kind, numbered, user_id=ME, full_access=full_access)


# --- normalisers ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-05", date(2026, 10, 5)),
        ("2026-10-05T09:30:00Z", date(2026, 10, 5)),
        ("25/12/2026", date(2026, 12, 25)),
        ("12/25/2026", date(2026, 12, 25)),
        ("05.10.2026", None),  # ambiguous
    ],
)
def test_dates_are_read_only_when_there_is_one_possible_reading(raw, expected):
    values = {"next_followup_date": raw}
    if expected is None:
        with pytest.raises(norm.RowError, match="YYYY-MM-DD"):
            norm.parse_date(values, "next_followup_date")
    else:
        assert norm.parse_date(values, "next_followup_date") == expected


def test_money_tolerates_symbols_and_separators():
    assert norm.money({"quoted_value": "₹ 12,50,000.5"}) == Decimal("1250000.50")
    assert norm.money({"quoted_value": "$4,999"}) == Decimal("4999.00")
    with pytest.raises(norm.RowError):
        norm.money({"quoted_value": "about ten grand"})


def test_crm_vocabulary_maps_onto_ours():
    warnings = norm.Warnings()
    assert norm.stage({"stage": "Closed Won"}) == LeadStage.WON
    assert norm.stage({"stage": "Proposal sent"}) == LeadStage.PROPOSAL_SENT
    assert norm.lead_source({"lead_source": "LinkedIn"}, warnings) == LeadSource.LINKEDIN
    assert norm.lead_source({"lead_source": "Trade show"}, warnings) == LeadSource.OTHER
    assert warnings.items == ["Lead source 'Trade show' is not one of ours; recorded as Other"]
    with pytest.raises(norm.RowError, match="not a pipeline stage"):
        norm.stage({"stage": "Vibes"})


def test_domains_are_normalised_for_matching():
    assert norm.domain_of("https://www.Acme.com/about?x=1") == "acme.com"
    assert norm.domain_of("acme.io") == "acme.io"
    assert norm.domain_of("not a website") is None


def test_every_kind_has_exactly_one_required_company_field():
    for kind, fields in norm.FIELDS.items():
        required = [f.key for f in fields if f.required]
        assert required == (["name"] if kind == "companies" else ["company"]), kind


# --- companies --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_companies_match_by_domain_then_name_and_dedupe_within_the_file():
    db = TableDb(companies=[{"id": "co-existing", "name": "Globex Corporation", "website": "https://globex.com"}])

    results = await _run(
        db,
        "companies",
        [
            {"name": "Acme", "website": "acme.com"},
            {"name": "ACME "},  # same company, different case and spacing
            {"name": "Globex", "website": "www.globex.com/contact"},  # matched by domain
            {"name": ""},
        ],
    )

    assert [r.status for r in results] == ["created", "existing", "existing", "error"]
    assert results[1].message == "Same company as row 2"
    assert results[2].record_id == "co-existing"
    assert results[3].message == "Company name is required"
    assert len(db.tables["companies"]) == 2
    assert db.tables["companies"][1]["created_by"] == ME


# --- contacts ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contacts_share_one_new_company_and_match_existing_emails():
    db = TableDb(contacts=[{"id": "ct-existing", "company_id": "co-x", "email": "Priya@Acme.com", "full_name": "Priya"}])

    results = await _run(
        db,
        "contacts",
        [
            {"first_name": "Asha", "last_name": "Rao", "email": "asha@acme.com", "company": "Acme"},
            {"full_name": "Priya S", "email": "priya@acme.com", "company": "Acme"},
            {"full_name": "No Email", "company": "acme"},
            {"full_name": "Broken", "email": "not-an-email", "company": "Acme"},
        ],
    )

    assert [r.status for r in results] == ["created", "existing", "created", "error"]
    assert "not a valid email" in results[3].message
    assert len(db.tables["companies"]) == 1  # "Acme" and "acme" are one company
    assert db.tables["contacts"][1]["full_name"] == "Asha Rao"


@pytest.mark.asyncio
async def test_one_rejected_row_does_not_sink_the_batch():
    db = TableDb(reject=lambda table, row: "phone is invalid" if row.get("phone") == "BAD" else None)

    results = await _run(
        db,
        "contacts",
        [
            {"full_name": "A", "email": "a@acme.com", "company": "Acme"},
            {"full_name": "B", "email": "b@acme.com", "company": "Acme", "phone": "BAD"},
            {"full_name": "C", "email": "c@acme.com", "company": "Acme"},
        ],
    )

    assert [r.status for r in results] == ["created", "error", "created"]
    assert "phone is invalid" in results[1].message


# --- leads ------------------------------------------------------------------------------------


LEAD_ROWS = [
    {
        "company": "Acme",
        "company_website": "acme.com",
        "full_name": "Asha Rao",
        "email": "asha@acme.com",
        "project_type": "SaaS",
        "lead_source": "Referral",
        "stage": "Proposal sent",
        "quoted_value": "4,50,000",
        "currency": "inr",
        "next_followup_date": "2026-10-01",
        "tags": "warm; q4",
    },
    {"company": "Initech", "lead_source": "Carrier pigeon"},
]


@pytest.mark.asyncio
async def test_leads_bring_their_company_contact_and_deal():
    db = TableDb(users=_users())

    results = await _run(db, "leads", LEAD_ROWS)

    assert [r.status for r in results] == ["created", "created"]
    lead = db.tables["leads"][0]
    assert lead["owner_id"] == ME
    assert lead["project_type"] == "saas" and lead["lead_source"] == "referral"
    assert lead["tags"] == ["warm", "q4"]
    assert lead["primary_contact_id"] == db.tables["contacts"][0]["id"]
    pursuit = db.tables["opportunities"][0]
    assert pursuit["stage"] == "proposal_sent"
    assert pursuit["quoted_value"] == "450000.00" and pursuit["currency"] == "INR"
    assert isinstance(pursuit["priority_score"], int)
    assert "primary_contact_id" not in db.tables["leads"][1]  # no person on that row
    assert results[1].warnings == ["Lead source 'Carrier pigeon' is not one of ours; recorded as Other"]


@pytest.mark.asyncio
async def test_reimporting_the_same_file_creates_nothing():
    db = TableDb(users=_users())
    await _run(db, "leads", LEAD_ROWS)
    counts = {t: len(rows) for t, rows in db.tables.items()}

    again = await _run(db, "leads", LEAD_ROWS)

    assert [r.status for r in again] == ["skipped", "skipped"]
    assert {t: len(rows) for t, rows in db.tables.items()} == counts


@pytest.mark.asyncio
async def test_an_admin_can_assign_owners_by_email():
    teammate = {"id": "user-2", "email": "sam@example.com", "is_active": True, "organization_id": "org-1"}
    db = TableDb(users=_users(ADMIN_ROLE, teammate))

    results = await _run(
        db,
        "leads",
        [{"company": "A", "owner_email": "Sam@Example.com"}, {"company": "B", "owner_email": "ghost@example.com"}],
    )

    assert db.tables["leads"][0]["owner_id"] == "user-2"
    assert db.tables["leads"][1]["owner_id"] == ME
    assert "No active teammate" in results[1].warnings[0]


@pytest.mark.asyncio
async def test_a_non_admin_owns_everything_they_import():
    db = TableDb(users=_users(AGENT_ROLE))

    results = await _run(db, "leads", [{"company": "A", "owner_email": "sam@example.com"}], full_access=False)

    assert db.tables["leads"][0]["owner_id"] == ME
    assert "Only an admin" in results[0].warnings[0]
    # A non-admin cannot list teammates under RLS anyway; the import does not try.
    assert not any(c[1] == "users" for c in db.calls)


@pytest.mark.asyncio
async def test_a_bad_date_fails_its_row_before_anything_is_written():
    db = TableDb(users=_users())

    results = await _run(db, "leads", [{"company": "A", "next_followup_date": "03/04/2026"}])

    assert results[0].status == "error"
    assert "YYYY-MM-DD" in results[0].message
    assert db.inserted("companies") == []


# --- endpoint ---------------------------------------------------------------------------------


@pytest.fixture
def fake_db():
    """Overrides conftest's fake for this module: the authed client then runs on a TableDb."""
    return TableDb(users=_users())


def test_the_field_catalog_is_served(authed_client):
    body = authed_client.get(f"{V1}/imports/fields").json()

    assert set(body["kinds"]) == {"companies", "contacts", "leads"}
    email = next(f for f in body["kinds"]["contacts"] if f["key"] == "email")
    assert "email address" in email["aliases"]
    assert body["max_rows_per_request"] == 200


def test_importing_through_the_api_reports_counts_per_status(authed_client, fake_db):
    payload = {"rows": [{"row_number": 2, "values": {"name": "Acme"}}, {"row_number": 3, "values": {"name": ""}}]}

    response = authed_client.post(f"{V1}/imports/companies", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["created"], body["failed"]) == (1, 1)
    assert body["rows"][1] == {
        "row_number": 3, "status": "error", "record_id": None,
        "message": "Company name is required", "warnings": [],
    }


def test_a_batch_is_capped(authed_client):
    rows = [{"row_number": i + 2, "values": {"name": f"Co {i}"}} for i in range(201)]

    assert authed_client.post(f"{V1}/imports/companies", json={"rows": rows}).status_code == 422


def test_an_unknown_record_type_is_rejected(authed_client):
    response = authed_client.post(f"{V1}/imports/invoices", json={"rows": [{"row_number": 2, "values": {}}]})

    assert response.status_code == 422


def test_a_read_only_workspace_cannot_import(authed_client, fake_db):
    fake_db.tables["organization_subscriptions"] = [
        {
            "organization_id": "org-1",
            "plan": "trial",
            "status": "trialing",
            "trial_ends_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
    ]

    response = authed_client.post(f"{V1}/imports/companies", json={"rows": [{"row_number": 2, "values": {"name": "A"}}]})

    assert response.status_code == 402
    assert fake_db.inserted("companies") == []
