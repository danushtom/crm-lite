# Dracara Growth OS

A multi-tenant deal-flow command center for software services and consulting agencies, covering the full cycle from first outreach through delivery handoff and upsell.

Unlike volume-oriented CRMs (Salesforce, HubSpot, Zoho), Dracara Growth OS is purpose-built for high-value, long-cycle software project sales: lead qualification, founder-level client intelligence, a follow-up engine, versioned proposals, pipeline scoring, and AI voice calling — organized around one opinionated pipeline instead of a generic object model.

For the full business and technical design record, including everything shipped since the original v1.0 scope, see [`tdd.md`](tdd.md).

## 1. What is in this repository

| Capability | Status |
| --- | --- |
| Lead pipeline, opportunities, proposals, activities, tasks, meetings | Shipped |
| Google Calendar two-way sync | Shipped |
| Multi-tenant organizations (self-serve signup, invite-token onboarding) | Shipped |
| Dynamic, admin-configurable roles and permissions (RBAC) | Shipped |
| AI voice sales agents (Twilio + a managed voice-AI platform) | Shipped |
| CRM assistant — answers questions about your pipeline, through your own permissions | Shipped |
| AI call notes — summary, action items and a follow-up date from every call transcript | Shipped |
| AI proposal drafting — a first draft from lead intelligence and requirements | Shipped |
| AI deal health monitor — nightly at-risk review, surfaced on the dashboard and in owner notifications | Shipped |
| Retrieval over voice-agent documents (Qdrant), so the agent can quote real pricing mid-call | Shipped |
| Configurable pipeline stages | Not built — stages are a fixed 12-value enum |
| Billing — per-seat plans on Dodo Payments, 14-day no-card trial, read-only after it lapses | Shipped |
| Self-serve signup, password reset, and invite acceptance (set-password) flows | Shipped |
| CSV import of companies, contacts and leads — column auto-mapping, de-duplication, per-row results | Shipped |
| Company research — cited profile, news and tech signals from the public web, with reviewable suggested edits | Shipped |
| Pre-call brief — who they are, why now, talking points and questions, from CRM facts plus research | Shipped |
| ML-based lead scoring | Not built — scoring is a weighted formula (`packages/scoring`) |
| WhatsApp and email sync | Not built |

Section 4 of [`tdd.md`](tdd.md) covers the original MVP scope in full; its changelog (`tdd.md` §23) documents every major addition since, and explicitly flags which parts of that document those additions made stale.

## 2. Architecture

Dracara Growth OS is a decoupled client-server system inside a Turborepo monorepo, backed by Supabase for data, auth, storage, and row-level security.

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui | Routing, server components, TanStack Query data layer |
| Backend API | FastAPI (Python 3.12), layered `api / services / domain / db / core` | Auth verification, request shaping, business rules; forwards every query to Postgres as the calling user |
| Database | Supabase Postgres, with Row-Level Security | The actual authority on what any caller can see — not application code |
| Background jobs | Celery + Redis | Scheduled reminders, staleness alerts, score recalculation, calendar sync and push, AI-call reconciliation, call notes, deal health, knowledge-base reindexing |
| Voice calling | Twilio (telephony) + a managed voice-AI platform (Vapi) | Places and receives calls for the AI voice agents feature |
| AI | OpenAI + LangGraph, in the shared `packages/ai` workspace package | Every model call in the product. Graphs are pure — no database handle, no tenant resolution |
| Vector store | Qdrant (self-hosted, `docker-compose.yml`) | Voice-agent knowledge-base retrieval. Has no RLS, so the organization filter in `vector_store.py` *is* the tenant boundary |
| Auth | Supabase Auth | JWT access tokens, verified against the project JWKS |
| File storage | Supabase Storage | Proposal documents, voice-agent knowledge-base uploads |
| Email | Resend | The worker's per-organization daily brief |
| Monitoring | Sentry (optional) | API, worker and web errors; request bodies and PII never attached |
| Deployment | Docker | One image per app (`apps/*/Dockerfile`), `docker-compose.prod.yml` for a single host |
| Billing | Dodo Payments (merchant of record) | Checkout, per-seat subscriptions, customer portal; state synced by a signature-verified webhook |

The AI features are optional: without `AI_ENABLED` and an `OPENAI_API_KEY` they report themselves as unconfigured, the UI hides their affordances, and the scheduled jobs no-op. The key lives only in the backend — the web app never talks to a model provider.

Every tenant-owned table carries an `organization_id`, populated by a database trigger and never trusted from client input. Authorization is layered: Postgres RLS is the ultimate authority on row visibility; the API additionally exposes a dynamic, per-organization permission system (roles created and configured by an admin, not a fixed enum) as an application-layer feature gate on top of that.

### 2.1 Monorepo layout

```text
crm-lite/
  apps/
    web/          Next.js frontend            -- see apps/web/README.md
    api/          FastAPI backend              -- see apps/api/README.md
    worker/       Celery background jobs       -- see apps/worker/README.md
  packages/
    types/        Shared TypeScript types (mirrors the Pydantic schemas)
    ui/           Shared shadcn/ui component wrappers
    scoring/      The one implementation of the weighted opportunity score,
                  installed by both apps/api and apps/worker from the workspace
    billing/      Plan catalog and entitlements, shared the same way so the API's
                  enforcement and the worker's AI jobs agree on who has what
    ai/           Every model call (see CLAUDE.md)
  supabase/
    migrations/   Every schema change, in the order it was applied
  scripts/
    seed_database.py   Creates demo organizations, users, and pipeline data
```

## 3. Setup

See [`SETUP.md`](SETUP.md) for the complete, step-by-step guide: prerequisites, environment variables, Supabase project setup, running the full stack, seeding demo data, and running the test suites.

The condensed version, for a Supabase project you have already created and linked:

```bash
git clone https://github.com/danushtom/crm-lite.git
cd crm-lite
pnpm install

cd apps/api && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cd ../..
cd apps/worker && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cd ../..

cp .env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local

supabase link --project-ref <your-project-ref>
supabase db push

pnpm dev
```

`pnpm dev` runs the frontend, the API, and the worker together via Turborepo, provided each Python app's virtual environment already exists (the two `python -m venv` steps above). The frontend is then reachable at `http://localhost:3000`, the API at `http://localhost:8000` (interactive docs at `/docs`), and the worker will start processing scheduled jobs once Redis is reachable.

## 4. Repository conventions

| Area | Convention |
| --- | --- |
| API versioning | Every resource lives under `/api/v1`. Health probes (`/health*`) are unversioned. |
| API collections | `{"items": [...], "page": {limit, offset, total, has_more}}`, `limit` capped at 200. |
| API errors | RFC 9457 Problem Details (`application/problem+json`) with a stable `code`. |
| Database migrations | Additive and forward-only. A mistake is corrected by a new migration, not by editing one already applied. |
| Multi-tenancy | `organization_id` on every tenant-owned table, set by trigger, never accepted from a request body. |
| Authorization | RLS decides row visibility; `require_permission("<resource>.<action>")` gates mutating actions at the API layer. |
| Testing | `pytest` for the API and worker; `vitest` for the frontend's pure logic (`apps/web/tests`). |

See [`apps/api/README.md`](apps/api/README.md) for backend-specific conventions (adding a resource, error shapes, auth dependencies) and [`apps/web/README.md`](apps/web/README.md) for frontend conventions (the drawer pattern, `apiFetch`, query keys).

## 5. Testing

```bash
cd apps/api && .venv/Scripts/python -m pytest -q      # backend: 200+ tests
cd apps/worker && .venv/Scripts/python -m pytest -q   # worker: scheduled-job tests
cd apps/web && pnpm test                              # frontend: vitest
```

Continuous integration (`.github/workflows/ci.yml`) runs all three on pull requests and on pushes to `master`/`main`: a Next.js production build and lint for the frontend, and `pytest` for the API and worker.

## 6. License

Proprietary and confidential to dracara.dev. No license file is present in this repository and none should be assumed; this is an internal tool, not an open-source project. Do not redistribute.

## 7. Contributing

This is an internal project for dracara.dev. Issues and pull requests from collaborators with repository access are welcome; see [`SETUP.md`](SETUP.md) to get a local environment running before making a change.
