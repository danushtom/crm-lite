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
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]

ADMIN_EMAIL = "dracara.seed.admin@example.com"
AGENT_EMAIL = "dracara.seed.agent@example.com"
SDR_EMAIL = "dracara.seed.sdr@example.com"


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
            params={"select": "id,email,full_name,role", "id": f"eq.{uid}"},
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


def create_or_get_user(
    client: httpx.Client,
    base: str,
    service_key: str,
    email: str,
    password: str,
    full_name: str,
) -> str:
    headers = auth_admin_headers(service_key)
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": full_name},
    }
    r = client.post(f"{base}/auth/v1/admin/users", json=payload, headers=headers)
    if r.status_code in (200, 201):
        uid = r.json()["id"]
        print(f"  Created auth user {email} → {uid}")
        wait_public_user(client, base, headers, uid)
        return uid
    err_text = r.text
    if r.status_code == 422 or "already been registered" in err_text or "already exists" in err_text.lower():
        hr = client.get(
            f"{base}/rest/v1/users",
            params={"select": "id,email", "email": f"eq.{email}"},
            headers=headers,
        )
        hr.raise_for_status()
        rows = hr.json()
        if rows:
            uid = rows[0]["id"]
            print(f"  Using existing user {email} → {uid}")
            return uid
    raise RuntimeError(f"Auth admin create failed ({r.status_code}): {err_text[:800]}")


def rest_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Dracara demo data")
    parser.add_argument("--dry-run", action="store_true", help="Only connectivity + ensure seed users exist")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Insert demo rows even if a previous seed is detected (tags contain 'seed')",
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
        admin_id = create_or_get_user(client, base, service_key, ADMIN_EMAIL, password, "Seed Admin")
        agent_id = create_or_get_user(client, base, service_key, AGENT_EMAIL, password, "Seed Agent")
        sdr_id = create_or_get_user(client, base, service_key, SDR_EMAIL, password, "Seed SDR")

        patch_row(client, base, service_key, "users", "id", admin_id, {"role": "admin"})
        patch_row(client, base, service_key, "users", "id", agent_id, {"role": "agent"})
        patch_row(client, base, service_key, "users", "id", sdr_id, {"role": "sdr"})
        print("Roles assigned (admin / agent / sdr).")

        if args.dry_run:
            print("Dry run — skipping inserts.")
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
            row = {
                "company_id": company_ids[cs["ci"]],
                "full_name": cs["full_name"],
                "role": cs["role"],
                "email": cs["email"],
                "phone": cs["phone"],
                "linkedin_url": f"https://www.linkedin.com/in/seed-{i}",
                "avatar_url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={cs['full_name']}",
                "is_primary": is_primary,
            }
            ins = insert_row(client, base, service_key, "contacts", row)
            contact_ids.append(ins["id"])

        print(f"Inserted {len(contact_ids)} contacts.")

        owners_cycle = [admin_id, agent_id, sdr_id]

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
        for li, ls in enumerate(leads_spec):
            owner = owners_cycle[li % len(owners_cycle)]
            lcd = today - timedelta(days=7 + li)
            nfd = today + timedelta(days=3 + (li % 5))
            row = {
                "company_id": company_ids[ls["ci"]],
                "primary_contact_id": contact_ids[ls["pci"]],
                "owner_id": owner,
                "stage": ls["stage"],
                "project_type": ls["pt"],
                "lead_source": ls["src"],
                "estimated_value": ls["ev"],
                "currency": "INR",
                "deal_probability": ls["prob"],
                "priority_score": min(95, 25 + ls["prob"] // 2),
                "last_contact_date": iso(lcd),
                "next_followup_date": iso(nfd),
                "tags": ["seed", ls["stage"], ls["pt"]],
            }
            ins = insert_row(client, base, service_key, "leads", row)
            lead_rows.append(ins)

        print(f"Inserted {len(lead_rows)} leads.")

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
                    "due_date": iso(due),
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

        # Enrich opportunity shells (trigger created one row per lead) + proposals for a subset
        opp_indices = [5, 6, 7, 13]
        for oi, idx in enumerate(opp_indices):
            lr = lead_rows[idx]
            ls_row = leads_spec[idx]
            or_get = client.get(
                f"{base}/rest/v1/opportunities",
                params={"select": "id", "lead_id": f"eq.{lr['id']}"},
                headers=h_rest,
            )
            or_get.raise_for_status()
            opp_rows = or_get.json()
            if not opp_rows:
                raise RuntimeError(f"Missing opportunity shell for lead {lr['id']}")
            opp_id = opp_rows[0]["id"]
            patch_row(
                client,
                base,
                service_key,
                "opportunities",
                "id",
                opp_id,
                {
                    "title": f"Opportunity — {companies_spec[ls_row['ci']]['name']}",
                    "quoted_value": float(ls_row["ev"]),
                    "currency": "INR",
                    "timeline_weeks": 12 + oi * 4,
                    "tech_stack": "Node, Postgres",
                    "requirements_doc": "High-level scope outlined in seed.",
                    "status": "active",
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
            patch_row(client, base, service_key, "leads", "id", lr["id"], {"is_opportunity": True})

        print("Enriched opportunities + proposals.")

        # Marketing metrics (CAC snapshot — current month)
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
                    "period_month": iso(month_start),
                    "channel": ch,
                    "spend": spend,
                    "new_customer_share": share,
                    "metadata": {"seed": True, "note": "Demo CAC mix"},
                },
            )
        print("Inserted marketing_channel_metrics.")

        print("\nDone. Sign in to the web app with:")
        print(f"  {ADMIN_EMAIL}  /  {password}")
        print(f"  {AGENT_EMAIL}  /  {password}")
        print(f"  {SDR_EMAIL}  /  {password}")


if __name__ == "__main__":
    main()
