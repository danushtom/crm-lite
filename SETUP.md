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
| `RESEND_API_KEY`, `ADMIN_EMAIL` | Only for the daily brief job | Without these, `daily_brief` runs but sends nothing |
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

## 8. Running the test suites

```bash
cd apps/api && .venv/Scripts/python -m pytest -q
cd apps/worker && .venv/Scripts/python -m pytest -q
cd apps/web && pnpm test
```

The frontend's `pnpm test` runs Vitest with `--passWithNoTests`; no frontend test files exist yet, so this currently passes trivially. `.github/workflows/ci.yml` runs all three (plus a production build and lint of the frontend) on pull requests and on pushes to `master`/`main`.

## 9. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| API returns 401 on every request | `SUPABASE_JWT_SECRET` set incorrectly for an asymmetric-signing project, or the frontend and backend point at different Supabase projects |
| A write succeeds via the service role but not as a logged-in user | A missing or misconfigured RLS policy for that table/operation — check `supabase/migrations/` for the relevant `CREATE POLICY` |
| `pnpm dev` fails to start the API or worker | The corresponding `.venv` has not been created yet (Section 2) — the `dev` script points at `.venv/Scripts/uvicorn` (or `celery`), which does not exist until the virtual environment is created |
| Scheduled jobs never run on Windows | The Celery beat scheduler needs its own process on Windows (Section 6.1) — the worker alone will not trigger scheduled tasks |
| A voice call cannot be placed | Check, in order: the org's compliance acknowledgment (`POST /api/v1/voice-agents/compliance-ack`), the agent has a phone number assigned, `platform_assistant_id` is set (requires `VOICE_PLATFORM_API_KEY`), and the contact has `ai_call_consent = true` |
