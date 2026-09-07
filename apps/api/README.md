# Dracara Growth OS — API

FastAPI service fronting Supabase (PostgREST, Auth, Storage). It authenticates the caller,
validates and shapes requests, applies business rules, and forwards queries **as that user** so
PostgreSQL row-level security — not application code — decides what is visible.

## Layout

```text
app/
├── main.py                  # app factory, middleware stack, lifespan
├── core/                    # cross-cutting concerns, no domain knowledge
│   ├── config.py            #   Settings (single source of truth)
│   ├── errors.py            #   RFC 9457 Problem Details + exception handlers
│   ├── logging.py           #   structured logs, request-id ContextVar
│   ├── middleware.py        #   correlation, access logs, security headers
│   ├── pagination.py        #   Page[T] envelope + limit/offset params
│   ├── rate_limit.py        #   per-user limiter
│   └── security.py          #   access-token verification (JWKS / HS256)
├── db/
│   └── supabase.py          # pooled PostgREST client + error translation
├── domain/                  # pure business rules — no I/O, no framework
│   ├── enums.py             #   mirrors the PostgreSQL enum types
│   └── scoring.py           #   weighted opportunity score
├── schemas/                 # Pydantic request/response models, one per resource
├── services/                # orchestration: multi-step writes, invariants
└── api/
    ├── deps.py              # auth / db / role dependencies
    ├── health.py            # unversioned probes
    └── v1/
        ├── router.py        # aggregates the endpoint modules
        └── endpoints/       # one module per resource
```

The dependency direction is one-way: `api → services → db/domain → core`. Nothing in `core`
or `domain` imports from `api`, so business rules stay testable without HTTP.

## Conventions

| Area | Rule |
| --- | --- |
| **Versioning** | Resources live under `/api/v1`. Probes (`/health*`) are unversioned so orchestrator config never moves. Breaking changes ship as `/api/v2` alongside v1. |
| **Collections** | Return `{"items": [...], "page": {limit, offset, total, has_more}}`. `limit` defaults to 50 and is capped at 200. |
| **Errors** | RFC 9457 `application/problem+json` with a stable machine-readable `code`. No upstream error body is ever forwarded verbatim. |
| **Status codes** | `201` + `Location` on create, `202` for accepted-but-async, `204` on delete, `409` on state conflicts, `422` on validation. |
| **Requests** | Bodies reject unknown fields. PATCH uses `exclude_unset`, so an explicit `null` clears a column while an omitted field is left alone. |
| **Enums** | Validated at the edge from `domain/enums.py`, so a bad value is a 422 rather than a 500 from Postgres. |
| **Correlation** | Send `X-Request-ID` to have it echoed and threaded through every server log line for that request. |

## Authentication

```
Authorization: Bearer <supabase_access_token>
```

Tokens are verified against the project JWKS for asymmetric signing keys (ES256/RS256, the
current Supabase default) or a shared secret for legacy HS256 projects. **Unverified decoding is
never performed** — a token whose signature cannot be checked is rejected.

Roles are not in the token and are not a fixed enum. Each organization owns its own `roles`
table (a `grants_full_access` flag, plus a checklist of granted permissions from a shared
`permissions` catalog) — an admin can rename, edit, delete, or create roles from the "User
management" screen. `deps.get_current_profile()` loads the caller's profile with their role and
its permissions embedded in one query. `AdminDep` (an alias for `require_full_access`) gates
routes that require `grants_full_access`; `require_permission("<resource>.<action>")` gates
routes on a specific granted permission instead, e.g. `require_permission("lead_intelligence.write")`
on the endpoint that used to be a hardcoded partner check. See `supabase/migrations/
20260905160000_dynamic_roles.sql` for the schema and `app/api/deps.py` for the dependencies.

One route family is authenticated differently: `api/v1/endpoints/voice_webhooks.py` receives
callbacks from an external voice-calling platform, not a logged-in user, so it carries no
`Authorization` header at all and is verified instead by an HMAC signature
(`app/core/webhook_security.py`). It is the one deliberate exception the contract test
(`tests/test_api_contract.py`) allows to a bearer-token security requirement.

## Running it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app.main:app --reload --port 8000   # Windows: .venv\Scripts\uvicorn
```

Interactive docs at `/docs`, the schema at `/openapi.json`. See `../../SETUP.md` for full
environment-variable and Supabase setup instructions.

```bash
.venv/bin/python -m pytest -q      # Windows: .venv\Scripts\python
```

`tests/test_api_contract.py` enforces the conventions above — that every route is versioned,
every operation declares a summary, a response schema and a security requirement, and that
errors come back as Problem Details. Adding an endpoint that skips any of those fails CI.

## Adding a resource

1. Enums (if any) in `domain/enums.py`.
2. Schemas in `schemas/<resource>.py` — `StrictAPIModel` for input, `APIModel` for output.
3. Multi-step logic in `services/<resource>.py`.
4. Endpoints in `api/v1/endpoints/<resource>.py`, each with `response_model`, `summary` and
   `responses=ERROR_RESPONSES`.
5. Register the router in `api/v1/router.py`. `main.py` does not change.
