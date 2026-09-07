# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Dracara Growth OS: a multi-tenant deal-flow CRM for software services agencies (lead pipeline, opportunities, proposals, follow-ups, AI voice calling). Turborepo monorepo: `apps/web` (Next.js 15), `apps/api` (FastAPI), `apps/worker` (Celery), `packages/types`, `packages/ui`, `packages/scoring`, backed by Supabase (Postgres + RLS + Auth + Storage). See `README.md` for the feature/tech overview, `SETUP.md` for full environment setup, and `tdd.md` for the complete design record (§23 is a changelog of everything shipped since the original v1.0 scope — read it before trusting anything else in that document, since several earlier sections are now stale and §23.5 lists which ones).

## Commands

```bash
# Everything, from repo root (requires apps/api/.venv and apps/worker/.venv to already exist)
pnpm install
pnpm dev              # turbo dev: web + api + worker together
pnpm build            # turbo build
pnpm lint             # turbo lint
pnpm test             # turbo test

# Frontend only
pnpm --filter web dev
pnpm --filter web build     # also type-checks and lints; treat a failure here as a real error
pnpm --filter web lint

# Backend (from apps/api, venv already created per SETUP.md)
.venv/Scripts/python -m pytest -q                                  # all tests
.venv/Scripts/python -m pytest tests/test_voice_agents.py -q       # one file
.venv/Scripts/python -m pytest tests/test_voice_agents.py::test_an_admin_can_create_a_voice_agent -q   # one test
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# Worker (from apps/worker)
.venv/Scripts/python -m pytest -q
.venv\Scripts\celery -A worker_app worker --loglevel=info -P solo   # Windows: worker only
.venv\Scripts\celery -A worker_app beat --loglevel=info             # Windows: scheduler needs its own process
.venv/bin/celery -A worker_app worker -B --loglevel=info            # macOS/Linux: both together

# Database migrations
supabase db push --dry-run    # review before applying
supabase db push              # migrations are forward-only: fix a mistake with a new one, never by editing an applied file
```

The API test suite (`apps/api/tests/test_api_contract.py`) enforces its own conventions in CI — every route versioned under `/api/v1`, every operation with a summary/response schema/security requirement — so a new endpoint that skips one of those fails the suite, not just a lint pass.

## Architecture

### Authorization is layered, and RLS is the real authority

Postgres row-level security decides what a query can see; the API's dependencies (`AdminDep`, `require_permission(...)` in `apps/api/app/api/deps.py`) are an *additional* application-layer gate on top, not a replacement. When adding a mutating endpoint on an existing table, check that a corresponding RLS policy exists for that operation — a missing one fails silently (PostgREST returns zero rows affected, no error), not loudly. This has happened twice in this codebase already (`organizations` and `phone_numbers` were both missing their `UPDATE` policy after being added).

`is_admin(uid)` is the single chokepoint nearly every RLS policy calls rather than inlining a role check — this is what made converting the fixed role enum to the dynamic `roles` table (below) a mostly mechanical change. The one function that had an inlined check instead (`can_access_lead()`) broke silently when that migration landed and caused a real outage; if a permission/role change ever seems to have no effect somewhere, check for an inlined check that bypassed the chokepoint.

### Multi-tenancy

Every tenant-owned table carries `organization_id`, populated by a `BEFORE INSERT` trigger (`set_parent_organization()` in `supabase/migrations/20260905140000_initial_schema.sql`, or a bespoke per-table version where the generic shape doesn't fit — see `set_meeting_organization()`, `set_role_organization()`, `set_call_organization()`). Never accept `organization_id` from a request body; it is always derived server-side. The one legitimate exception is a service-role write where the org id has already been resolved from a trusted, signature-verified lookup (see the voice-webhook pattern below) — even there, the trigger only trusts the value when `auth.uid()` is absent (a real user session always overrides it with the derived value).

### Dynamic RBAC

Roles are organization-owned data (`roles`, `role_permissions`, `permissions` tables — `supabase/migrations/20260905160000_dynamic_roles.sql`), not a fixed enum. `roles.grants_full_access` is the "sees everything in the org" flag; permissions are feature gates on top (which actions/screens a role can use), not a row-visibility mechanism — row visibility is still "own your records, or hold a full-access role." An admin can create/edit/delete roles and their permission grants from the "User management" (`/agents`) screen. `require_permission("<resource>.<action>")` in `deps.py` is how an endpoint checks a specific granted permission; `AdminDep` checks `grants_full_access` specifically. New organizations get the four seeded default roles (Admin/Agent/SDR/Partner) via `seed_default_roles()`, called from `handle_new_user()`.

### Voice agents: the trust boundary that matters most

`apps/api/app/api/v1/endpoints/voice_webhooks.py` receives callbacks from an external voice-calling platform (Vapi), not a logged-in user — there is no JWT, so it is verified by HMAC signature instead (`app/core/webhook_security.py`) and deliberately declares none of the usual auth dependencies. The payload's own claims (including anything that looks like an organization or user id) are never trusted directly; `organization_id` is always resolved server-side from the platform's `call_id` via a lookup into the `calls` table that this API itself created at dial time. Every mid-call tool in `app/services/voice_tools.py` receives that resolved org id as a parameter and must scope its own queries by it — an LLM's tool-call arguments are attacker/hallucination-controllable in the same way a browser's request body is, and should be treated with the same suspicion.

Outbound calling has two independent gates before a call is placed: a per-contact `ai_call_consent` flag (`contacts` table) and a one-time per-organization compliance acknowledgment (`organizations.ai_calling_compliance_ack_at`). A blocked attempt is still logged (`calls.status = 'no_consent_blocked'`), not silently dropped.

### FastAPI route registration order matters

A single-segment wildcard route (`/{resource_id}`) registered before a literal-path route (`/resource/special-path`) will swallow it — FastAPI matches in declaration order. Literal sibling paths (`/phone-numbers`, `/calls`) must be declared before the `/{id}` CRUD routes in the same router file; this has already caused one real bug in `voice_agents.py`.

### Worker: service-role, tenant-scoping is manual

`apps/worker` has no per-request user token — it always acts with the service role and is responsible for its own tenant scoping. Most scheduled jobs (`apps/worker/worker_app.py`) scan across every organization in one query and rely on the row's own `organization_id`/`owner_id` to route the resulting notification correctly, rather than filtering the query itself (`overdue_escalation` groups admins by `organization_id` in Python after fetching them, for example). `packages/scoring` exists specifically so the API and the worker never run two independent copies of the opportunity-scoring formula that can silently drift — both install it from the workspace rather than vendoring their own copy.

### Frontend: the drawer pattern

Every create/edit form is a slide-in panel built on `EntityDrawer` (`apps/web/components/shared/entity-drawer.tsx`), not a separate page or a modal. All backend calls go through `apps/web/lib/api.ts` (`apiFetch`/`apiList`/`apiPage`/`apiListAll`) rather than a raw `fetch` — this is where the Supabase access token gets attached and where `ApiError` (carrying the backend's RFC 9457 Problem Details fields) gets thrown. See `apps/web/README.md` for the full convention.

### Testing patterns worth reusing

`apps/api/tests/conftest.py`'s `FakeDb` fakes the PostgREST client by keying responses on `"{METHOD} {table}"} (ignoring query params), and `authed_client` overrides both `get_db` and `get_admin_db` with the same fake instance. For mocking an outbound HTTP call (an external API, not Supabase), monkeypatch the relevant module's `get_http_client` to a small fake object recording calls — see `tests/test_auth_endpoints.py` or `tests/test_voice_platform.py` for the pattern.
