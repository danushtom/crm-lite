# Setup Guide

Complete instructions for running Dracara Growth OS locally: prerequisites, environment variables, database setup, seeding demo data, and running the full stack. For an architectural overview, see [`README.md`](README.md); for the full design record, see [`tdd.md`](tdd.md).

## 1. Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Node.js | 20 or later | Frontend and the Turborepo task runner |
| pnpm | 9.15.4 (pinned in `package.json`) | JavaScript/TypeScript package management |
| Python | 3.12 | The API and worker |
| Supabase CLI | Any recent release | Linking to a project and pushing migrations |
| Redis | Any recent release | The Celery worker's broker and result backend |
| A Supabase project | — | Database, auth, storage. Create one at [supabase.com](https://supabase.com) if you do not already have access to the team's project |

Google Calendar sync, Resend email, Twilio, and a voice-AI platform account (Vapi) are all optional — the application runs without them, with those specific features unavailable until configured. Google and Resend credentials are listed as optional rows in the environment-variable tables in Section 4; Twilio and the voice platform get their own walkthrough in Section 7, since that integration needs a public webhook URL to test locally.

## 2. Clone and install

```bash
git clone https://github.com/danushtom/crm-lite.git
cd crm-lite
pnpm install
```

`pnpm install` resolves the whole workspace: `apps/web`, `packages/types`, and `packages/ui`. The two Python apps (`apps/api`, `apps/worker`) are not part of the pnpm dependency graph and need their own virtual environments:

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # macOS/Linux
cd ../..

cd apps/worker
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # macOS/Linux
cd ../..
```

Both `requirements.txt` files install `packages/scoring` from the workspace (`-e ../../packages/scoring`), so the API and the worker always run the identical opportunity-scoring implementation.

## 3. Supabase project

Two ways to get a working database, depending on whether you are joining an existing team project or starting fresh.

### 3.1 Link to an existing project (the team's shared setup)

```bash
supabase login
supabase link --project-ref <project-ref>
```

The project ref is the subdomain of your Supabase project URL (`https://<project-ref>.supabase.co`) — ask whoever administers the team's Supabase project for it, and for your own `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` from the project dashboard (Project Settings -> API).

### 3.2 Start a fresh project

Create a new project from the [Supabase dashboard](https://supabase.com/dashboard), then link to it as in 3.1 using its project ref and keys.

### 3.3 Apply migrations

Whichever path you took, apply every migration in `supabase/migrations/` in order:

```bash
supabase db push --dry-run   # review what would run
supabase db push             # apply it
```

Migrations are additive and forward-only: a mistake already applied is corrected by a new migration, never by editing one that already ran. Do not attempt `supabase db reset` against a shared project — it is destructive and will drop existing data; it is only appropriate against a project only you use.

### 3.3.1 Auth redirect URLs and email settings

Signup confirmation, password reset and team invites all land on the web app's `/auth/confirm` page, which establishes the session and forwards the user on (to the dashboard, or to `/auth/set-password` for invites and resets). Supabase only redirects to URLs on its allow-list, so in the dashboard under **Authentication -> URL Configuration**:

- **Site URL**: the web app's origin (`https://app.yourdomain.com` in production).
- **Redirect URLs**: add `<web origin>/auth/confirm` (plus `http://localhost:3000/auth/confirm` for local development). Without it, links fall back to the Site URL and invitees never get to set a password.

No email template changes are required: `/auth/confirm` accepts the default templates' links (PKCE `?code=` and invite `#access_token=` fragments) as well as custom `token_hash` templates. For production, configure a custom SMTP sender under **Authentication -> Emails** — Supabase's built-in sender is rate-limited to a handful of emails an hour, which signups, resets and invites will exhaust quickly.

### 3.4 Storage buckets

File uploads need two Supabase Storage buckets. They must be **private**: proposals carry
pricing and contract terms, and a voice agent's knowledge base carries pricing sheets and
internal call scripts. The API stores the object path on the row and mints a short-lived signed
link per response, so a public bucket is not merely unnecessary but actively wrong — a public
link never expires, and it travels out to every member of the organization, into browser
history, and into `Referer` on the next click.

Create them from the Supabase dashboard (Storage, then New bucket) with **Public bucket off**,
or with the CLI-equivalent REST call:

```bash
curl -X POST "$SUPABASE_URL/storage/v1/bucket"   -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"   -H "apikey: $SUPABASE_SERVICE_ROLE_KEY"   -H "Content-Type: application/json"   -d '{"name":"proposals","id":"proposals","public":false,"file_size_limit":52428800}'
```

Repeat for `voice-agent-docs`. Two settings are worth applying to both:

| Setting | Value | Why |
| --- | --- | --- |
| Public | off | A signed link expires; a public URL does not |
| File size limit | 52428800 (50 MiB) | Enforced server-side, matching `MAX_UPLOAD_BYTES` |
| Allowed MIME types | documents and images only | The uploading client's `Content-Type` is not trustworthy |

Uploads fail with an upstream storage error until these exist. Bucket names come from
`PROPOSALS_BUCKET` and `VOICE_KB_BUCKET` if you want different ones.

## 4. Environment variables

### 4.1 Backend (`apps/api/.env`)

Copy the template and fill in your project's values:

```bash
cp .env.example apps/api/.env
```

| Variable | Required | Notes |
| --- | --- | --- |
| `SUPABASE_URL` | Yes | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Yes | Public key from the dashboard; also used by the frontend |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Server-side only. Bypasses row-level security — never expose this to the frontend |
| `SUPABASE_JWT_SECRET` | Only for legacy HS256 projects | Newer projects sign tokens asymmetrically (ES256/RS256) and verify against the public JWKS instead; leave blank unless your project dashboard says otherwise (Project Settings -> Auth -> JWT Keys) |
| `CORS_ORIGINS` | Yes | Comma-separated list of allowed frontend origins, e.g. `http://localhost:3000` |
| `WEB_APP_URL` | Yes in production | Public origin of the web app (default `http://localhost:3000`). Invite emails and billing checkout/portal return here |
| `ENVIRONMENT` | No | `development` \| `staging` \| `production`; default `development` |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_DEFAULT` | No | Default `true`, `300/minute`, keyed per authenticated user (falling back to a hashed token or client IP) |
| `PROPOSALS_BUCKET`, `MAX_UPLOAD_BYTES` | No | Supabase Storage bucket name and per-file upload limit; defaults `proposals` and 50 MiB |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | No | Required only to enable Google Calendar sync |
| `NEXT_PUBLIC_API_URL` | Yes | The frontend's view of the API's base URL |

The voice-agent feature (Section 7) needs several more variables, also present in `.env.example` — see that section for what each one does and how to obtain it.

### 4.2 Frontend (`apps/web/.env.local`)

```bash
cp apps/web/.env.example apps/web/.env.local
```

| Variable | Required | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Same project URL as the backend |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Same anon key as the backend |
| `NEXT_PUBLIC_API_URL` | Yes | Where the FastAPI backend is reachable, e.g. `http://localhost:8000` |

### 4.3 Worker (`apps/worker/.env`)

The worker reads its own `.env` in `apps/worker/` (see `apps/worker/env.py`):

| Variable | Required | Notes |
| --- | --- | --- |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Yes | The worker always acts with the service role — it has no per-request user token |
| `REDIS_URL` | Yes | Celery broker and result backend, e.g. `redis://localhost:6379/0` |
| `RESEND_API_KEY`, `EMAIL_FROM`, `WEB_APP_URL` | Only for the daily brief job | Each organization's admins get a morning summary of their own organization; lapsed organizations are skipped. Without a key the job does nothing. `EMAIL_FROM` must be on a domain verified in Resend |
| `SENTRY_DSN`, `ENVIRONMENT`, `RELEASE` | No | Error monitoring for scheduled jobs; blank disables it |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Only for calendar sync | Duplicated from the backend's `.env` deliberately — the worker is a separate process with its own settings module |

## 5. Seed demo data

```bash
cd apps/api
.venv/Scripts/python ../../scripts/seed_database.py       # Windows
# .venv/bin/python ../../scripts/seed_database.py         # macOS/Linux
```

Reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from the environment (or `apps/api/.env`). Creates two organizations to demonstrate tenant isolation, each with a seeded default role set:

| Organization | User | Role |
| --- | --- | --- |
| Dracara (`dracara.dev`) | `danush@dracara.dev` | Admin |
| Dracara (`dracara.dev`) | `arjun@dracara.dev` | Agent |
| Dracara (`dracara.dev`) | `meera@dracara.dev` | SDR |
| Dracara (`dracara.dev`) | `kabir@dracara.dev` | Partner |
| Acme Corp (`acme.corp`) | `priya@acme.corp` | Admin |

All demo users share one password, set via the `SEED_PASSWORD` environment variable (default `DracaraSeed!2026`). Change this default before running the script against any project other than a disposable local/demo one. Pass `--dry-run` to verify connectivity and account creation without writing pipeline data.

## 6. Running the stack

### 6.1 Everything together

```bash
pnpm dev
```

This runs `turbo dev`, which starts the frontend, the API, and the worker in parallel — provided both Python virtual environments from Section 2 already exist. On Windows, the worker's `dev` script starts the Celery worker process only, in solo-pool mode; the scheduler (`beat`) needs its own process:

```bash
cd apps/worker
.venv\Scripts\celery -A worker_app beat --loglevel=info
```

On macOS/Linux, the worker's `dev:unix` script starts the worker and an embedded beat scheduler together (`celery -A worker_app worker -B`), so a separate beat process is not needed there.

### 6.2 Individually

```bash
pnpm --filter web dev      # frontend only, http://localhost:3000
pnpm --filter api dev      # backend only, http://localhost:8000
pnpm --filter worker dev   # worker only (see the beat note above)
```

### 6.3 Verify it is working

- `http://localhost:8000/health` should return `{"status": "ok"}`.
- `http://localhost:8000/docs` serves interactive API documentation.
- `http://localhost:3000/login` should let you sign in as any seeded user from Section 5.

## 7. Voice agents (optional)

The AI voice-calling feature needs its own accounts. The corresponding settings already exist in `.env.example` (copied into `apps/api/.env` in Section 4.1); fill them in once you have accounts with Twilio and a voice-AI platform:

| Variable | Notes |
| --- | --- |
| `VOICE_PLATFORM_API_KEY` | API key from your Vapi (or equivalent) account |
| `VOICE_PLATFORM_API_BASE` | Default `https://api.vapi.ai` |
| `VOICE_PLATFORM_WEBHOOK_SECRET` | A secret you choose; configured identically on the platform side to verify webhook signatures |
| `VOICE_KB_BUCKET` | Supabase Storage bucket for uploaded knowledge-base documents; default `voice-agent-docs` |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | From your Twilio console |
| `API_PUBLIC_BASE_URL` | A publicly reachable HTTPS URL for this API, so the voice platform's webhooks can reach it |

Because a webhook needs a public URL, local development requires a tunnel, for example [ngrok](https://ngrok.com):

```bash
ngrok http 8000
```

Set `API_PUBLIC_BASE_URL` to the tunnel's HTTPS URL. Without these variables, the rest of the application works normally; creating a voice agent still succeeds, it simply cannot be connected to the voice platform until they are set.

This integration was built against the voice platform's publicly documented API shape and has not been exercised against a live account — verify the adapter (`apps/api/app/services/voice_platform.py`) against current provider documentation before relying on it in production.

## 8. AI features (optional)

Call notes, the CRM assistant, proposal drafting, deal health and the voice agent's knowledge
base all run through one OpenAI key plus a local Qdrant instance. Without them the rest of the
product works normally: every AI endpoint answers `501 not_configured`, the AI buttons hide
themselves (the frontend checks `GET /api/v1/ai/status`), and the scheduled AI jobs return
`skip:ai_disabled` instead of failing every few minutes.

### 8.1 Start Qdrant

Qdrant stores the embedded knowledge-base documents. It is the only service in
`docker-compose.yml`:

```bash
docker compose up -d qdrant
```

The dashboard is at `http://localhost:6333/dashboard`. Its data can always be rebuilt from
Supabase Storage — the worker's `reindex_knowledge_base` job does exactly that — so
`docker compose down -v` is safe if you want a clean slate.

### 8.2 Configure

Add these to **both** `apps/api/.env` and `apps/worker/.env`; `packages/ai` reads them directly in
each process.

| Variable | Notes |
| --- | --- |
| `AI_ENABLED` | Master switch. `false` by default, so a deployment without a key behaves predictably rather than failing per request |
| `OPENAI_API_KEY` | From platform.openai.com |
| `OPENAI_CHAT_MODEL` | Default `gpt-4o-mini` — call notes, the assistant, deal health |
| `OPENAI_REASONING_MODEL` | Default `gpt-4o` — proposal drafting, where quality is worth the cost |
| `OPENAI_EMBEDDING_MODEL` | Default `text-embedding-3-small` |
| `OPENAI_EMBEDDING_DIMENSIONS` | Default `1536`. **Change this only together with the model, and re-index** — a mismatch makes every existing point unsearchable, silently |
| `QDRANT_URL` | Default `http://localhost:6333` |
| `QDRANT_API_KEY` | Empty for the local container. Set it (and `QDRANT__SERVICE__API_KEY` in compose) for any shared or deployed environment |
| `AI_MONTHLY_TOKEN_BUDGET` | Per-organization monthly token ceiling; `0` disables the check. One key serves every tenant, so without a ceiling one organization's runaway usage is billed to all of them |
| `EXA_API_KEY` | From exa.ai. Enables company research and pre-call briefs; without it those panels hide themselves. Only a company's name and website are ever sent to Exa |
| `RESEARCH_TTL_DAYS` | Default `14`. Research newer than this is served from storage instead of re-searching |
| `AI_BATCH_LIMIT` | Worker only. How many rows one scheduled AI pass processes; default `25` |

The OpenAI key lives **only** in the backend. The web app never talks to a model provider.

### 8.3 What runs where

| Feature | Trigger |
| --- | --- |
| CRM assistant ("Ask AI") | `POST /api/v1/ai/chat`, on demand. Reads the CRM through the caller's own permissions |
| Knowledge-base indexing | On upload; retried by the worker's `reindex_knowledge_base` every 2 hours |
| Call notes | Worker `call_notes`, every 2 minutes, for completed calls with a transcript |
| Deal health | Worker `deal_health`, 07:00 daily. Owners are notified per-tenant; results appear on the dashboard |
| Proposal drafting | `POST /api/v1/ai/proposals/{id}/draft`, on demand |
| Company research | `POST /api/v1/ai/companies/{id}/research`, on demand from the company page. Returns cited facts and *suggested* edits; applying them is a normal company edit |
| Pre-call brief | `POST /api/v1/ai/leads/{id}/brief`, on demand from the lead page |
| Calendar push | Worker `calendar_push`, every 2 minutes, so a meeting the voice agent books reaches the rep's Google Calendar |

Check spend with `GET /api/v1/ai/usage` (admin only), or read `public.ai_usage` directly.

## 9. Billing (Dodo Payments)

Every new organization gets a 14-day free trial with every feature and up to 5 seats, no card required. When it ends without a subscription the workspace becomes read-only: every read still works, every write returns `402` (`code: subscription_inactive`), and admins see a banner pointing at **Settings -> Billing**. Plans are priced per seat per month:

| Plan | Suggested price | Adds |
| --- | --- | --- |
| Starter | $19 / seat | The full CRM: leads, opportunities, proposals, follow-ups, calendar sync, lead capture, reports, roles |
| Growth | $49 / seat | AI assistant, call notes, proposal drafting, deal health, company research |
| Scale | $99 / seat | AI voice agents and their document knowledge base |

The prices shown in the app come from `PLANS` in `apps/api/app/services/billing.py`; what customers are actually charged is the price on the Dodo product, so keep the two in step.

1. In the [Dodo Payments dashboard](https://app.dodopayments.com) (start in test mode), create three **subscription** products, each billed monthly *per unit* (the unit is a seat). Put their ids in `DODO_PRODUCT_STARTER`, `DODO_PRODUCT_GROWTH` and `DODO_PRODUCT_SCALE`.
2. Create an API key and set `DODO_PAYMENTS_API_KEY`, with `DODO_PAYMENTS_ENVIRONMENT=test` (or `live`).
3. Add a webhook endpoint pointing at `<API_PUBLIC_BASE_URL>/api/v1/billing-webhooks/dodo`, subscribed to the `subscription.*` events, and set its signing secret as `DODO_PAYMENTS_WEBHOOK_SECRET`. Locally, expose the API with a tunnel (e.g. ngrok) as for the voice agents.
4. Set `WEB_APP_URL` so checkout and the customer portal return to the right place.

How it fits together: the subscription state lives in `organization_subscriptions`, which only the service role can write (members can read their own row). Checkout creates a Dodo customer for the organization and stores its id; the webhook finds the organization by that stored customer id — never by the payload's metadata — verifies the Standard Webhooks signature, ignores duplicate deliveries and out-of-order events, and updates plan, status and seats. Plan changes and seat changes are prorated immediately; invoices, payment methods and cancellation are handled in Dodo's hosted customer portal. Inviting or reactivating a user beyond the seat count is refused with `402` (`code: seat_limit_reached`).

## 10. Deploying

Three images, built from the repo root (each needs the workspace packages):

| Image | Dockerfile | Runs |
| --- | --- | --- |
| API | `apps/api/Dockerfile` | uvicorn on `$PORT` (8000), `--proxy-headers`, `WEB_CONCURRENCY` workers |
| Worker | `apps/worker/Dockerfile` | Celery worker by default; run the **same image** once more with `celery -A worker_app beat --loglevel=info` as the scheduler. Exactly one beat, any number of workers |
| Web | `apps/web/Dockerfile` | Next.js standalone server on 3000. `NEXT_PUBLIC_*` are **build arguments** (compiled into the browser bundle) |

Plus Redis (Celery broker and shared rate-limit counters) and, for the AI features, Qdrant. `docker-compose.prod.yml` wires all of it up on a single host behind your own TLS reverse proxy; on a managed platform deploy the three Dockerfiles as separate services and use its Redis. The web app also deploys unchanged to Vercel (root directory `apps/web`).

Before the first production deploy:

1. **Database**: `supabase db push` against the production project. Migrations are forward-only; apply them before rolling out code that depends on them.
2. **Environment**: `ENVIRONMENT=production`, `LOG_JSON=true`, real `WEB_APP_URL` and `CORS_ORIGINS` (your web origin only), `API_PUBLIC_BASE_URL`, `RATE_LIMIT_STORAGE_URI=redis://...`, `SENTRY_DSN`, live Dodo keys, `QDRANT_API_KEY`. The API logs a `production config:` error at startup for each of these it finds still set for development — check the first boot's logs.
3. **Proxy**: set `FORWARDED_ALLOW_IPS` on the API to your load balancer's address range (or `*` if it is the only way in), so rate limits and logs see real client addresses rather than the proxy's.
4. **Supabase Auth** (section 3.3.1): Site URL, the `/auth/confirm` redirect URL, and custom SMTP.
5. **Webhooks**: Dodo → `https://<api>/api/v1/billing-webhooks/dodo`; the voice platform → `https://<api>/api/v1/voice-webhooks/platform/events`.
6. **Monitoring**: `SENTRY_DSN` (API, worker) and `NEXT_PUBLIC_SENTRY_DSN` (web, a build argument). Nothing is sent without them, and request bodies and user PII are never attached when they are set. Point an uptime check at the API's `/health/ready` and the web app's `/login`.

## 11. Running the test suites

```bash
cd apps/api && .venv/Scripts/python -m pytest -q
cd apps/worker && .venv/Scripts/python -m pytest -q
cd apps/web && pnpm test
```

The frontend's `pnpm test` runs Vitest with `--passWithNoTests`; no frontend test files exist yet, so this currently passes trivially. `.github/workflows/ci.yml` runs all three (plus a production build and lint of the frontend) on pull requests and on pushes to `master`/`main`.

## 12. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| API returns 401 on every request | `SUPABASE_JWT_SECRET` set incorrectly for an asymmetric-signing project, or the frontend and backend point at different Supabase projects |
| A write succeeds via the service role but not as a logged-in user | A missing or misconfigured RLS policy for that table/operation — check `supabase/migrations/` for the relevant `CREATE POLICY` |
| `pnpm dev` fails to start the API or worker | The corresponding `.venv` has not been created yet (Section 2) — the `dev` script points at `.venv/Scripts/uvicorn` (or `celery`), which does not exist until the virtual environment is created |
| Scheduled jobs never run on Windows | The Celery beat scheduler needs its own process on Windows (Section 6.1) — the worker alone will not trigger scheduled tasks |
| A voice call cannot be placed | Check, in order: the org's compliance acknowledgment (`POST /api/v1/voice-agents/compliance-ack`), the agent has a phone number assigned, `platform_assistant_id` is set (requires `VOICE_PLATFORM_API_KEY`), and the contact has `ai_call_consent = true` |
| Every write returns 402 `subscription_inactive` | The organization's trial ended without a subscription (or its subscription lapsed). `GET /api/v1/billing` shows the state; it clears when Dodo's `subscription.active` webhook lands |
| The web app builds but every API call fails in the browser | `NEXT_PUBLIC_API_URL` is baked in at build time — rebuild the web image after changing it, and make sure the web origin is in the API's `CORS_ORIGINS` |
| Every AI endpoint returns 501 | `AI_ENABLED` is not `true`, or `OPENAI_API_KEY` is unset. `GET /api/v1/ai/status` says which |
| An AI request returns 429 `ai_budget_exceeded` | The organization passed `AI_MONTHLY_TOKEN_BUDGET` for the calendar month. Raise it, or wait for the 1st |
| A document shows "Not searchable" | Indexing failed; the reason is in `voice_agent_documents.index_error`. Uploads deliberately succeed anyway, and the worker retries. A scanned PDF with no text layer needs OCR first |
| A document is stuck on "Indexing…" | Qdrant is unreachable (`docker compose up -d qdrant`) or the worker is not running |
| Call notes never appear | The call needs `status = 'completed'` **and** a non-null `transcript`, and must have ended within the last 7 days. `calls.ai_notes_error` records the last failure |
| The agent invents prices mid-call | Its documents are not indexed — check the badge on the agent's document list. With nothing indexed, `search_knowledge_base` returns empty and the model is on its own |
