#!/usr/bin/env python3
"""
Seed Dracara Growth OS demo data via Supabase REST + Auth Admin API.

Requires (apps/api/.env or env):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

Optional:
  SUPABASE_ANON_KEY — used only for anon connectivity probe (falls back to service role)
  SEED_PASSWORD — password for demo users (default: DracaraSeed!2026)

Usage:
  cd /path/to/crm-lite && python scripts/seed_database.py
  python scripts/seed_database.py --dry-run   # connectivity + auth create only, skip inserts

Creates two organizations to demonstrate tenant isolation:

  Dracara (dracara.dev)        — the main demo dataset, one user per role
    danush@dracara.dev   admin
    arjun@dracara.dev    agent
    meera@dracara.dev    sdr
    kabir@dracara.dev    partner

  Acme Corp (acme.corp)        — a second, otherwise-empty tenant
    priya@acme.corp      admin

All non-founding users (arjun, meera, kabir) join via a redeemed org_invites
token rather than a post-creation role PATCH: a service-role PATCH that
changes someone's role_id is rejected by guard_user_role_change() (it only
trusts a role change made by an authenticated admin, not a bare service-role
connection with no auth.uid()), and organization/role are no longer
something a client can set directly on signup anyway -- see
supabase/migrations/20260905160000_dynamic_roles.sql's handle_new_user().
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Windows consoles default to cp1252, which cannot encode the arrows and ellipses used in the
# progress output below -- the script died with a UnicodeEncodeError partway through seeding,
# after having already created auth users. Force UTF-8 on the streams we print to instead of
# stripping the characters, so the same output works on every platform.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

ROOT = Path(__file__).resolve().parents[1]

DRACARA_ORG_NAME = "Dracara"
ACME_ORG_NAME = "Acme Corp"

ADMIN_EMAIL = "danush@dracara.dev"
AGENT_EMAIL = "arjun@dracara.dev"
SDR_EMAIL = "meera@dracara.dev"
PARTNER_EMAIL = "kabir@dracara.dev"
ACME_ADMIN_EMAIL = "danush@acme.corp"


#: Mirrors app/domain/attribution.derive_lead_source. Duplicated rather than imported because
#: this script runs standalone against a project URL, with apps/api not on the path -- the same
#: reason apps/worker/env.py duplicates settings instead of sharing a config module.
_LINKEDIN_SOURCES = {"linkedin", "li"}
_REFERRAL_MEDIUMS = {"referral", "partner", "affiliate"}


def derive_lead_source(utm_source: str | None, utm_medium: str | None) -> str:
    source = (utm_source or "").strip().lower()
    medium = (utm_medium or "").strip().lower()
    if source in _LINKEDIN_SOURCES:
        return "linkedin"
    if medium in _REFERRAL_MEDIUMS:
        return "referral"
    if source or medium:
        return "website"
    return "other"


#: Acquisition mix for the seeded contacts, keyed by name so the insert path and
#: --backfill-attribution stay in step. Values are the UTM set exactly as a real click carries
#: it -- note the deliberate facebook / fb / instagram spread, which is what Meta actually
#: sends depending on placement, and which lib/attribution.ts collapses back into one channel.
#: A None means the contact was entered by hand and has only the coarse `source` enum.
_META_LP = "https://dracara.dev/mvp-sprint"
_LI_LP = "https://dracara.dev/enterprise-build"
_GADS_LP = "https://dracara.dev/erp-migration"

CONTACT_ATTRIBUTION: dict[str, dict[str, Any] | None] = {
    "Aditi Rao": {"utm_source": "linkedin", "utm_medium": "cpc", "utm_campaign": "q3-enterprise-build", "utm_content": "case-study-carousel", "landing_page_url": _LI_LP},
    "Rohit Menon": None,
    "Sandra Baxter": {"utm_source": "facebook", "utm_medium": "cpc", "utm_campaign": "q3-mvp-sprint", "utm_content": "founder-video-a", "landing_page_url": _META_LP},
    "Vikram Shah": {"utm_source": "linkedin", "utm_medium": "cpc", "utm_campaign": "q3-enterprise-build", "utm_content": "testimonial-single", "landing_page_url": _LI_LP},
    "Meera Iyer": {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "erp-migration-search", "utm_term": "erp migration consultant", "landing_page_url": _GADS_LP},
    "Ananya Das": {"utm_source": "instagram", "utm_medium": "paid_social", "utm_campaign": "q3-mvp-sprint", "utm_content": "reel-b", "landing_page_url": _META_LP},
    "Karthik Nambiar": {"utm_source": "fb", "utm_medium": "cpc", "utm_campaign": "retargeting-visitors", "utm_content": "static-pricing", "landing_page_url": _META_LP},
    "Neha Kapoor": {"utm_source": "clutch", "utm_medium": "referral", "utm_campaign": "directory-listing", "landing_page_url": "https://dracara.dev/"},
    "Arjun Pillai": None,
    "Divya Krishnan": {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "erp-migration-search", "utm_term": "sap alternative", "landing_page_url": _GADS_LP},
    "Imran Qureshi": {"utm_source": "linkedin", "utm_medium": "organic", "landing_page_url": "https://dracara.dev/blog/scaling-delivery"},
    "Leena Thomas": {"utm_source": "facebook", "utm_medium": "cpc", "utm_campaign": "q3-mvp-sprint", "utm_content": "founder-video-a", "landing_page_url": _META_LP},
}

#: Coarse source for the hand-entered ones, which have no UTM to derive from.
CONTACT_MANUAL_SOURCE: dict[str, str] = {
    "Rohit Menon": "cold_call",
    "Arjun Pillai": "referral",
}


def load_dotenv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def merged_env() -> dict[str, str]:
    env = {**load_dotenv_file(ROOT / "apps" / "api" / ".env")}
    env.update(load_dotenv_file(ROOT / "apps" / "web" / ".env.local"))
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def check_reachable(url: str, anon_key: str | None, service_key: str) -> None:
    """Verify Supabase REST responds before spending time on seed inserts."""
    base = url.rstrip("/")
    with httpx.Client(timeout=15.0) as client:
        key = anon_key or service_key
        r = client.get(
            f"{base}/rest/v1/companies",
            params={"select": "id", "limit": "1"},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
        )
        if r.status_code >= 500:
            raise RuntimeError(f"Supabase REST unreachable (HTTP {r.status_code}): {r.text[:500]}")
        print(f"OK: REST reachable ({base}) — probe status {r.status_code}")


def wait_public_user(client: httpx.Client, base: str, headers: dict[str, str], uid: str, retries: int = 15) -> dict[str, Any]:
    """Trigger may lag — poll public.users until profile row exists."""
    for _ in range(retries):
        r = client.get(
            f"{base}/rest/v1/users",
            params={"select": "id,email,full_name,role_id,organization_id", "id": f"eq.{uid}"},
            headers=headers,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]
        time.sleep(0.35)
    raise RuntimeError(f"public.users row never appeared for auth user {uid}")


def auth_admin_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def rest_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def find_existing_user(client: httpx.Client, base: str, headers: dict[str, str], email: str) -> dict[str, Any] | None:
    r = client.get(
        f"{base}/rest/v1/users",
        params={"select": "id,email,role_id,organization_id", "email": f"eq.{email}"},
        headers=headers,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def get_role_id(client: httpx.Client, base: str, service_key: str, organization_id: str, role_name: str) -> str:
    r = client.get(
        f"{base}/rest/v1/roles",
        params={"select": "id", "organization_id": f"eq.{organization_id}", "name": f"ilike.{role_name}"},
        headers=rest_headers(service_key),
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise RuntimeError(f"Role {role_name} not found in org {organization_id}")
    return rows[0]["id"]


def _create_auth_user(
    client: httpx.Client, base: str, service_key: str, email: str, password: str, user_metadata: dict[str, Any]
) -> str:
    headers = auth_admin_headers(service_key)
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": user_metadata,
    }
    r = client.post(f"{base}/auth/v1/admin/users", json=payload, headers=headers)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Auth admin create failed for {email} ({r.status_code}): {r.text[:800]}")
    uid = r.json()["id"]
    print(f"  Created auth user {email} → {uid}")
    profile = wait_public_user(client, base, headers, uid)
    return profile


def create_or_get_founder(
    client: httpx.Client, base: str, service_key: str, email: str, password: str, full_name: str, organization_name: str
) -> dict[str, Any]:
    """Create the first (admin) user of a brand-new organization, or return the existing one.

    No invite_token in metadata: handle_new_user() mints a new organization and makes this
    user its admin.
    """
    headers = auth_admin_headers(service_key)
    existing = find_existing_user(client, base, headers, email)
    if existing:
        print(f"  Using existing user {email} → {existing['id']}")
        return existing
    return _create_auth_user(
        client, base, service_key, email, password,
        {"full_name": full_name, "organization_name": organization_name},
    )


def create_or_get_invited(
    client: httpx.Client, base: str, service_key: str, email: str, password: str, full_name: str,
    organization_id: str, role: str, invited_by: str,
) -> dict[str, Any]:
    """Create a user who joins an existing organization with a specific role, or return the
    existing one. A raw PATCH to change someone's role after the fact is rejected by
    guard_role_escalation() for service-role callers, so this goes through the same
    org_invites redemption path POST /agents/invite uses -- see handle_new_user()."""
    headers = auth_admin_headers(service_key)
    existing = find_existing_user(client, base, headers, email)
    if existing:
        print(f"  Using existing user {email} → {existing['id']}")
        return existing

    role_id = get_role_id(client, base, service_key, organization_id, role)
    invite = insert_row(
        client, base, service_key, "org_invites",
        {"organization_id": organization_id, "email": email, "role_id": role_id, "created_by": invited_by},
    )
    return _create_auth_user(
        client, base, service_key, email, password,
        {"full_name": full_name, "invite_token": invite["id"]},
    )


def insert_row(client: httpx.Client, base: str, service_key: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
    r = client.post(f"{base}/rest/v1/{table}", headers=rest_headers(service_key), json=row)
    if r.status_code >= 400:
        raise RuntimeError(f"INSERT {table} failed {r.status_code}: {r.text[:1200]}")
    data = r.json()
    return data[0] if isinstance(data, list) else data


def patch_row(client: httpx.Client, base: str, service_key: str, table: str, pk_col: str, pk: str, body: dict[str, Any]) -> None:
    r = client.patch(
        f"{base}/rest/v1/{table}",
        headers=rest_headers(service_key),
        params={pk_col: f"eq.{pk}"},
        json=body,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"PATCH {table} failed {r.status_code}: {r.text[:800]}")


def backfill_attribution(
    client: httpx.Client, base: str, service_key: str, organization_id: str
) -> None:
    """Add attribution to contacts seeded before the UTM columns existed.

    Matched by name within the organization, and scoped to that organization explicitly: this
    runs on the service-role key, so row-level security is not filtering anything and a missing
    organization_id filter would happily update a same-named contact in another tenant.

    Only fills columns that are currently empty. Re-running is therefore safe, and a contact
    whose attribution was captured for real is never overwritten by demo values.
    """
    updated = 0
    skipped = 0

    for full_name, attr in CONTACT_ATTRIBUTION.items():
        found = client.get(
            f"{base}/rest/v1/contacts",
            params={
                "select": "id,full_name,utm_source,source",
                "organization_id": f"eq.{organization_id}",
                "full_name": f"eq.{full_name}",
            },
            headers=rest_headers(service_key),
        )
        found.raise_for_status()
        rows = found.json()
        if not rows:
            print(f"  - {full_name}: not found, skipping")
            continue

        for row in rows:
            if row.get("utm_source"):
                skipped += 1
                continue

            manual_source = CONTACT_MANUAL_SOURCE.get(full_name)
            body: dict[str, Any] = {
                "source": manual_source
                or (
                    derive_lead_source(attr.get("utm_source"), attr.get("utm_medium"))
                    if attr
                    else "other"
                )
            }
            if attr:
                body.update({k: v for k, v in attr.items() if v is not None})
                body["captured_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=3 * updated + 1)
                ).isoformat()

            patch_row(client, base, service_key, "contacts", "id", row["id"], body)
            updated += 1
            channel = attr.get("utm_source") if attr else body["source"]
            print(f"  + {full_name}: {channel}")

    # Anything in this organization that is not a seed contact is left alone. Fuzzy-matching
    # would be guessing: "Leena Thom" may well be a renamed "Leena Thomas", but it may equally
    # be a different person, and this writes to a real tenant's records.
    others = client.get(
        f"{base}/rest/v1/contacts",
        params={"select": "full_name", "organization_id": f"eq.{organization_id}"},
        headers=rest_headers(service_key),
    )
    others.raise_for_status()
    unknown = [c["full_name"] for c in others.json() if c["full_name"] not in CONTACT_ATTRIBUTION]

    print("")
    print(f"Backfilled {updated} contact(s); {skipped} already had attribution.")
    if unknown:
        print(f"Left alone (not seed contacts): {', '.join(sorted(unknown))}")


def get_opportunity_for_lead(client: httpx.Client, base: str, service_key: str, lead_id: str) -> dict[str, Any]:
    r = client.get(
        f"{base}/rest/v1/opportunities",
        params={"select": "id", "lead_id": f"eq.{lead_id}"},
        headers=rest_headers(service_key),
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise RuntimeError(f"Missing opportunity shell for lead {lead_id}")
    return rows[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Dracara demo data")
    parser.add_argument("--dry-run", action="store_true", help="Only connectivity + ensure seed users exist")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Insert demo rows even if a previous seed is detected (tags contain 'seed')",
    )
    parser.add_argument(
        "--backfill-attribution",
        action="store_true",
        help=(
            "Update existing seeded contacts with UTM attribution instead of inserting. "
            "For a database seeded before attribution existed: --force would add a second "
            "copy of every company, contact and lead rather than enriching the ones there."
        ),
    )
    parser.add_argument(
        "--organization-id",
        help=(
            "Which tenant --backfill-attribution targets. Defaults to the Dracara seed org. "
            "Required to reach an organization the seed did not create, such as the one a "
            "real signup makes -- the backfill is deliberately single-tenant, since it runs "
            "on the service-role key with no row-level security filtering it."
        ),
    )
    args = parser.parse_args()

    env = merged_env()
    url = env.get("SUPABASE_URL", "").rstrip("/")
    service_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    anon_key = env.get("SUPABASE_ANON_KEY", "").strip() or env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip() or None

    if not url or not service_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY (set in apps/api/.env)", file=sys.stderr)
        sys.exit(1)

    password = env.get("SEED_PASSWORD", "DracaraSeed!2026")

    print("Checking Supabase connectivity…")
    check_reachable(url, anon_key, service_key)

    base = url.rstrip("/")
    h_rest = rest_headers(service_key)

    with httpx.Client(timeout=60.0) as client:
        admin = create_or_get_founder(client, base, service_key, ADMIN_EMAIL, password, "Danush", DRACARA_ORG_NAME)
        admin_id, dracara_org_id = admin["id"], admin["organization_id"]

        agent = create_or_get_invited(client, base, service_key, AGENT_EMAIL, password, "Arjun", dracara_org_id, "agent", admin_id)
        sdr = create_or_get_invited(client, base, service_key, SDR_EMAIL, password, "Meera", dracara_org_id, "sdr", admin_id)
        partner = create_or_get_invited(client, base, service_key, PARTNER_EMAIL, password, "Kabir", dracara_org_id, "partner", admin_id)
        agent_id, sdr_id, partner_id = agent["id"], sdr["id"], partner["id"]

        acme_admin = create_or_get_founder(client, base, service_key, ACME_ADMIN_EMAIL, password, "Danush", ACME_ORG_NAME)
        acme_admin_id, acme_org_id = acme_admin["id"], acme_admin["organization_id"]

        print(f"Dracara org: {dracara_org_id} (admin={admin_id}, agent={agent_id}, sdr={sdr_id}, partner={partner_id})")
        print(f"Acme Corp org: {acme_org_id} (admin={acme_admin_id})")

        if args.dry_run:
            print("Dry run — skipping inserts.")
            return

        if args.backfill_attribution:
            backfill_attribution(
                client, base, service_key, args.organization_id or dracara_org_id
            )
            return

        # Avoid duplicate seed rows on re-run (FK explosions)
        if not args.force:
            chk = client.get(
                f"{base}/rest/v1/leads",
                params={"select": "id", "limit": "1", "tags": "cs.{seed}"},
                headers=h_rest,
            )
            chk.raise_for_status()
            if chk.json():
                print(
                    "Seed data already exists (leads tagged 'seed'). Re-run with --force to insert anyway.",
                    file=sys.stderr,
                )
                sys.exit(2)

        today = date.today()
        iso = lambda d: d.isoformat()

        companies_spec: list[dict[str, Any]] = [
            {"name": "Nova Labs", "industry": "SaaS", "size": "51-200", "website": "https://nova.example.com", "location": "Singapore", "segment": "startup"},
            {"name": "Riverbank Analytics", "industry": "Analytics", "size": "201-500", "website": "https://riverbank.example.com", "location": "Bangalore", "segment": "enterprise"},
            {"name": "Meridian Health", "industry": "HealthTech", "size": "11-50", "website": "https://meridian.example.com", "location": "Mumbai", "segment": "sme"},
            {"name": "Copper Foundry", "industry": "Manufacturing", "size": "501+", "website": "https://copper.example.com", "location": "Chennai", "segment": "enterprise"},
            {"name": "Brightcart Retail", "industry": "Retail", "size": "51-200", "website": "https://brightcart.example.com", "location": "Delhi NCR", "segment": "sme"},
            {"name": "Skyline Media", "industry": "Media", "size": "11-50", "website": "https://skyline.example.com", "location": "Hyderabad", "segment": "startup"},
            {"name": "Atlas ERP Group", "industry": "ERP", "size": "501+", "website": "https://atlas.example.com", "location": "Pune", "segment": "enterprise"},
            {"name": "Pinewood Edu", "industry": "EdTech", "size": "51-200", "website": "https://pinewood.example.com", "location": "Remote", "segment": "sme"},
            {"name": "Drift Payments", "industry": "Fintech", "size": "11-50", "website": "https://drift.example.com", "location": "Mumbai", "segment": "startup"},
            {"name": "Keystone Realty", "industry": "PropTech", "size": "201-500", "website": "https://keystone.example.com", "location": "Gurugram", "segment": "sme"},
        ]

        company_ids: list[str] = []
        for c in companies_spec:
            row = {
                **c,
                "created_by": admin_id,
                "logo_url": f"https://api.dicebear.com/7.x/shapes/svg?seed={c['name']}",
                "linkedin_url": f"https://www.linkedin.com/company/{c['name'].lower().replace(' ', '-')}",
            }
            inserted = insert_row(client, base, service_key, "companies", row)
            company_ids.append(inserted["id"])
        print(f"Inserted {len(company_ids)} companies.")

        contacts_spec: list[dict[str, Any]] = [
            {"ci": 0, "full_name": "Aditi Rao", "role": "VP Engineering", "email": "aditi@nova.example.com", "phone": "+91 90000 10001"},
            {"ci": 0, "full_name": "Rohit Menon", "role": "Procurement", "email": "rohit@nova.example.com", "phone": "+91 90000 10002"},
            {"ci": 1, "full_name": "Sandra Baxter", "role": "Analytics Lead", "email": "sandra@riverbank.example.com", "phone": "+91 90000 10003"},
            {"ci": 2, "full_name": "Vikram Shah", "role": "CTO", "email": "vikram@meridian.example.com", "phone": "+91 90000 10004"},
            {"ci": 3, "full_name": "Meera Iyer", "role": "Plant Head", "email": "meera@copper.example.com", "phone": "+91 90000 10005"},
            {"ci": 4, "full_name": "Ananya Das", "role": "COO", "email": "ananya@brightcart.example.com", "phone": "+91 90000 10006"},
            {"ci": 5, "full_name": "Karthik Nambiar", "role": "Creative Director", "email": "karthik@skyline.example.com", "phone": "+91 90000 10007"},
            {"ci": 6, "full_name": "Neha Kapoor", "role": "Program Director", "email": "neha@atlas.example.com", "phone": "+91 90000 10008"},
            {"ci": 7, "full_name": "Arjun Pillai", "role": "Principal", "email": "arjun@pinewood.example.com", "phone": "+91 90000 10009"},
            {"ci": 8, "full_name": "Divya Krishnan", "role": "CFO", "email": "divya@drift.example.com", "phone": "+91 90000 10010"},
            {"ci": 9, "full_name": "Imran Qureshi", "role": "Head of Ops", "email": "imran@keystone.example.com", "phone": "+91 90000 10011"},
            {"ci": 3, "full_name": "Leena Thomas", "role": "PMO", "email": "leena@copper.example.com", "phone": "+91 90000 10012"},
        ]

        contact_ids: list[str] = []
        for i, cs in enumerate(contacts_spec):
            prev_ci = contacts_spec[i - 1]["ci"] if i else None
            is_primary = prev_ci is None or cs["ci"] != prev_ci
            attr = CONTACT_ATTRIBUTION.get(cs["full_name"])
            row = {
                "company_id": company_ids[cs["ci"]],
                "full_name": cs["full_name"],
                "role": cs["role"],
                "email": cs["email"],
                "phone": cs["phone"],
                "linkedin_url": f"https://www.linkedin.com/in/seed-{i}",
                "avatar_url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={cs['full_name']}",
                "is_primary": is_primary,
                # Same derivation the public capture endpoint applies, so seeded and captured
                # contacts are indistinguishable downstream.
                "source": CONTACT_MANUAL_SOURCE.get(cs["full_name"])
                or (derive_lead_source(attr.get("utm_source"), attr.get("utm_medium")) if attr else "other"),
            }
            if attr:
                row.update({k: v for k, v in attr.items() if v is not None})
                row["captured_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=3 * i + 1)
                ).isoformat()
            ins = insert_row(client, base, service_key, "contacts", row)
            contact_ids.append(ins["id"])

        print(f"Inserted {len(contact_ids)} contacts.")

        owners_cycle = [admin_id, agent_id, sdr_id]

        # stage / estimated value / deal probability / priority score all live on the
        # opportunity the ensure_opportunity_for_lead() trigger auto-creates per lead, not on
        # leads itself -- see supabase/migrations/20260905140000_initial_schema.sql's leads
        # table. They're applied in a PATCH right after each insert, below.
        leads_spec: list[dict[str, Any]] = [
            {"ci": 0, "pci": 0, "stage": "prospect", "pt": "saas", "src": "linkedin", "ev": 4200000, "prob": 40},
            {"ci": 1, "pci": 2, "stage": "contacting", "pt": "ai", "src": "website", "ev": 8900000, "prob": 55},
            {"ci": 2, "pci": 3, "stage": "discovery_scheduled", "pt": "webapp", "src": "referral", "ev": 2100000, "prob": 45},
            {"ci": 3, "pci": 4, "stage": "requirements_gathering", "pt": "erp", "src": "cold_call", "ev": 15200000, "prob": 50},
            {"ci": 4, "pci": 5, "stage": "solution_design", "pt": "saas", "src": "linkedin", "ev": 6700000, "prob": 60},
            {"ci": 5, "pci": 6, "stage": "proposal_sent", "pt": "mvp", "src": "website", "ev": 3100000, "prob": 65},
            {"ci": 6, "pci": 7, "stage": "negotiation", "pt": "erp", "src": "referral", "ev": 24500000, "prob": 70},
            {"ci": 7, "pci": 8, "stage": "won", "pt": "webapp", "src": "linkedin", "ev": 9800000, "prob": 100},
            {"ci": 8, "pci": 9, "stage": "lost", "pt": "saas", "src": "other", "ev": 1800000, "prob": 0},
            {"ci": 9, "pci": 10, "stage": "followup_later", "pt": "ai", "src": "website", "ev": 5400000, "prob": 35},
            {"ci": 0, "pci": 1, "stage": "contacting", "pt": "saas", "src": "linkedin", "ev": 1200000, "prob": 30},
            {"ci": 2, "pci": 3, "stage": "on_hold", "pt": "mvp", "src": "cold_call", "ev": 900000, "prob": 25},
            {"ci": 4, "pci": 5, "stage": "discovery_scheduled", "pt": "webapp", "src": "referral", "ev": 4400000, "prob": 48},
            {"ci": 6, "pci": 7, "stage": "delivery_transition", "pt": "saas", "src": "website", "ev": 32000000, "prob": 95},
        ]

        lead_rows: list[dict[str, Any]] = []
        opp_ids: list[str] = []
        for li, ls in enumerate(leads_spec):
            owner = owners_cycle[li % len(owners_cycle)]
            lcd = today - timedelta(days=7 + li)
            nfd = today + timedelta(days=3 + (li % 5))
            row = {
                "company_id": company_ids[ls["ci"]],
                "primary_contact_id": contact_ids[ls["pci"]],
                "owner_id": owner,
                "project_type": ls["pt"],
                "lead_source": ls["src"],
                "last_contact_date": iso(lcd),
                "next_followup_date": iso(nfd),
                "tags": ["seed", ls["stage"], ls["pt"]],
            }
            ins = insert_row(client, base, service_key, "leads", row)
            lead_rows.append(ins)

            opp = get_opportunity_for_lead(client, base, service_key, ins["id"])
            patch_row(
                client, base, service_key, "opportunities", "id", opp["id"],
                {
                    "stage": ls["stage"],
                    "quoted_value": float(ls["ev"]),
                    "currency": "INR",
                    "deal_probability": ls["prob"],
                    "priority_score": min(95, 25 + ls["prob"] // 2),
                },
            )
            opp_ids.append(opp["id"])

        print(f"Inserted {len(lead_rows)} leads (+ their auto-created opportunities).")

        # Enrich a subset of lead_intelligence rows
        intel_updates = [
            (0, {"pain_points": "Legacy billing reconciliation", "tech_stack": "Postgres, Rails", "budget_hints": "8–12 Cr INR FY"}),
            (1, {"decision_makers": "CTO + CFO", "competitors_involved": "Vendor A"}),
            (3, {"strategic_notes": "Pilot region APAC first", "objections_raised": "Security review timeline"}),
            (7, {"pain_points": "Compliance automation", "tech_stack": "Azure, Snowflake"}),
        ]
        for idx, patch in intel_updates:
            lid = lead_rows[idx]["id"]
            patch_row(client, base, service_key, "lead_intelligence", "lead_id", lid, {**patch, "updated_by": admin_id})

        # Activities
        act_types = ["call", "email", "meeting", "note", "stage_change"]
        for i, lr in enumerate(lead_rows[:12]):
            owner = owners_cycle[i % 3]
            for j in range(2):
                insert_row(
                    client,
                    base,
                    service_key,
                    "activities",
                    {
                        "lead_id": lr["id"],
                        "type": act_types[(i + j) % len(act_types)],
                        "description": f"Seed activity {j + 1} for pipeline touchpoint",
                        "performed_by": owner,
                        "metadata": {"seed": True, "idx": i * 2 + j},
                    },
                )
        print("Inserted activities.")

        # Tasks
        for i in range(14):
            lr = lead_rows[i % len(lead_rows)]
            due = today + timedelta(days=(i % 10) - 2)
            insert_row(
                client,
                base,
                service_key,
                "tasks",
                {
                    "lead_id": lr["id"],
                    "owner_id": owners_cycle[i % 3],
                    "title": f"Follow-up: {lr['id'][:8]} task",
                    "due_at": f"{iso(due)}T09:00:00+05:30",
                    "status": "pending" if i % 4 != 0 else "completed",
                },
            )
        print("Inserted tasks.")

        # Meetings (mix CRM-linked + calendar-only)
        for i in range(6):
            lr_id = lead_rows[i % len(lead_rows)]["id"]
            sched = today + timedelta(days=i + 1)
            insert_row(
                client,
                base,
                service_key,
                "meetings",
                {
                    "lead_id": lr_id if i != 5 else None,
                    "owner_id": owners_cycle[i % 3],
                    "title": f"Seed discovery slot {i + 1}",
                    "scheduled_at": f"{iso(sched)}T10:00:00+05:30",
                    "duration_minutes": 45,
                    "status": "scheduled",
                },
            )
        print("Inserted meetings.")

        # Further enrich a subset of opportunities (title, scope) + a draft proposal each
        opp_indices = [5, 6, 7, 13]
        for oi, idx in enumerate(opp_indices):
            ls_row = leads_spec[idx]
            opp_id = opp_ids[idx]
            patch_row(
                client,
                base,
                service_key,
                "opportunities",
                "id",
                opp_id,
                {
                    "title": f"Opportunity — {companies_spec[ls_row['ci']]['name']}",
                    "timeline_weeks": 12 + oi * 4,
                    "tech_stack": "Node, Postgres",
                    "requirements_doc": "High-level scope outlined in seed.",
                },
            )
            insert_row(
                client,
                base,
                service_key,
                "proposals",
                {
                    "opportunity_id": opp_id,
                    "title": f"Proposal v1 ({oi + 1})",
                    "quoted_price": float(ls_row["ev"]) * 0.95,
                    "status": "draft",
                    "created_by": admin_id,
                },
            )

        print("Enriched opportunities + proposals.")

        # Marketing metrics (CAC snapshot — current month). No natural parent row to derive
        # organization_id from, so it's supplied directly (trusted for a service-role caller —
        # see set_marketing_metric_organization()).
        month_start = date(today.year, today.month, 1)
        channels = [
            ("Events", 640000, 0.15),
            ("Micro KOL", 480000, 0.20),
            ("Meta Ads", 456000, 0.23),
            ("Referral", 235000, 0.42),
        ]
        for ch, spend, share in channels:
            insert_row(
                client,
                base,
                service_key,
                "marketing_channel_metrics",
                {
                    "organization_id": dracara_org_id,
                    "period_month": iso(month_start),
                    "channel": ch,
                    "spend": spend,
                    "new_customer_share": share,
                    "metadata": {"seed": True, "note": "Demo CAC mix"},
                },
            )
        print("Inserted marketing_channel_metrics.")

        # A second, otherwise-empty tenant: one company/contact/lead owned by Acme's admin, to
        # prove Dracara's users can't see it (and Acme's admin can't see Dracara's data).
        acme_company = insert_row(
            client, base, service_key, "companies",
            {"name": "Acme Corp Client", "industry": "Retail", "size": "51-200",
             "created_by": acme_admin_id},
        )
        acme_contact = insert_row(
            client, base, service_key, "contacts",
            {"company_id": acme_company["id"], "full_name": "Wile Coyote", "role": "Ops Lead",
             "email": "wile@acmecorpclient.example.com", "is_primary": True},
        )
        acme_lead = insert_row(
            client, base, service_key, "leads",
            {"company_id": acme_company["id"], "primary_contact_id": acme_contact["id"],
             "owner_id": acme_admin_id, "project_type": "webapp", "lead_source": "referral",
             "tags": ["seed"]},
        )
        acme_opp = get_opportunity_for_lead(client, base, service_key, acme_lead["id"])
        patch_row(
            client, base, service_key, "opportunities", "id", acme_opp["id"],
            {"stage": "contacting", "quoted_value": 1500000.0, "currency": "INR", "deal_probability": 40},
        )
        print("Inserted a lone Acme Corp company/contact/lead (isolation check).")

        print("\nDone. Sign in to the web app with:")
        print(f"  {ADMIN_EMAIL}    / {password}   (admin, org: {DRACARA_ORG_NAME})")
        print(f"  {AGENT_EMAIL}     / {password}   (agent, org: {DRACARA_ORG_NAME})")
        print(f"  {SDR_EMAIL}     / {password}   (sdr, org: {DRACARA_ORG_NAME})")
        print(f"  {PARTNER_EMAIL}    / {password}   (partner, org: {DRACARA_ORG_NAME})")
        print(f"  {ACME_ADMIN_EMAIL}      / {password}   (admin, org: {ACME_ORG_NAME})")


if __name__ == "__main__":
    main()
