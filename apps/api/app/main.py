"""Application entrypoint.

Built as a factory (:func:`create_app`) so tests can construct an isolated instance, with a
module-level ``app`` for ``uvicorn app.main:app``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_router as v1_router
from app.core.config import API_V1_PREFIX, settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.monitoring import init_monitoring
from app.core.idempotency import IdempotencyMiddleware
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import limiter
from app.db.supabase import close_http_client, open_http_client
from app.schemas.dashboard import ServiceInfo

logger = logging.getLogger(__name__)

API_VERSION = "v1"
SERVICE_VERSION = "1.0.0"

DESCRIPTION = """
Deal-flow command centre for **dracara.dev** -- lead pipeline, founder CRM intelligence,
follow-up engine, proposals and revenue forecasting.

### Authentication
Every endpoint outside `/health*` requires a Supabase access token:

```
Authorization: Bearer <supabase_access_token>
```

The token is verified against the project's JWKS (ES256/RS256) or, for legacy projects, a
shared HS256 secret. Requests are then executed **as the calling user**, so PostgreSQL
row-level security -- not application code -- is the authority on what each caller can see.

### Conventions
* **Versioning** -- all resources live under `/api/v1`. Breaking changes ship as `/api/v2`.
* **Collections** -- return `{"items": [...], "page": {...}}` and accept `limit` / `offset`.
* **Errors** -- RFC 9457 Problem Details (`application/problem+json`) with a stable `code`.
* **Correlation** -- send `X-Request-ID` to have it echoed and threaded through server logs.
* **Idempotency** -- send `Idempotency-Key` on a POST to make retries safe; the original
  response is replayed and marked with `Idempotent-Replay: true`.
"""

TAGS_METADATA = [
    {"name": "Health", "description": "Liveness and readiness probes. Unversioned and unauthenticated."},
    {"name": "Authentication", "description": "Caller identity and Google Calendar OAuth."},
    {"name": "Dashboard", "description": "Pipeline KPIs and the follow-up queues."},
    {"name": "Leads", "description": "The lead lifecycle, CRM intelligence, activities, tasks and meetings."},
    {"name": "Opportunities", "description": "Pipeline positions and versioned proposals."},
    {"name": "Companies", "description": "Organisations leads belong to."},
    {"name": "Contacts", "description": "People at those organisations."},
    {"name": "Tasks", "description": "Follow-up tasks: complete, snooze, reschedule."},
    {"name": "Meetings", "description": "Scheduled meetings and outcome capture."},
    {"name": "Notifications", "description": "In-app notification inbox."},
    {"name": "Roles", "description": "Organization-owned roles and their permission grants."},
    {"name": "Agents", "description": "Team management and performance. Admin only."},
    {"name": "Organizations", "description": "The caller's own tenant. Read by any member, renamed by an admin."},
    {"name": "Lead Capture", "description": "Public form/ad lead intake, authenticated by a capture key rather than a JWT, plus admin management of those keys."},
    {"name": "Voice Agents", "description": "AI voice agents that place and receive phone calls. Not to be confused with 'Agents' (team members)."},
    {"name": "Voice Webhooks", "description": "Callbacks from the voice platform (call lifecycle, tool-calling). Signature-verified, not JWT-authenticated."},
    {"name": "Imports", "description": "CSV import of companies, contacts and leads, de-duplicated against what already exists."},
    {"name": "Billing", "description": "The organization's plan, trial and seats; checkout, plan changes and the customer portal (Dodo Payments)."},
    {"name": "Billing Webhooks", "description": "Subscription events from Dodo Payments. Signature-verified (Standard Webhooks), not JWT-authenticated."},
]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Own process-wide resources: one HTTP connection pool for the whole application."""
    configure_logging(settings.log_level, settings.log_json)
    await open_http_client()
    logger.info(
        "api starting environment=%s version=%s prefix=%s",
        settings.environment,
        SERVICE_VERSION,
        API_V1_PREFIX,
    )
    for problem in settings.production_problems():
        logger.error("production config: %s", problem)
    try:
        yield
    finally:
        await close_http_client()
        logger.info("api stopped")


def create_app() -> FastAPI:
    init_monitoring()
    app = FastAPI(
        title=settings.project_name,
        version=SERVICE_VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        servers=[{"url": "/", "description": "This deployment"}],
        contact={"name": "dracara.dev", "url": "https://dracara.dev"},
        license_info={"name": "Proprietary"},
        # Trailing-slash redirects turn an authenticated POST into a GET; fail loudly instead.
        redirect_slashes=False,
    )

    app.state.limiter = limiter
    register_exception_handlers(app)

    # Middleware runs bottom-up: request context is added last so it wraps everything and every
    # log line -- including those from error handling -- carries the request id.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(IdempotencyMiddleware, enabled=bool(settings.supabase_service_role_key))
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list or ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "If-Match"],
        expose_headers=["X-Request-ID", "X-API-Version", "Location", "Server-Timing"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, api_version=API_VERSION)

    app.include_router(health_router)
    app.include_router(v1_router, prefix=API_V1_PREFIX)

    @app.get(
        "/",
        response_model=ServiceInfo,
        tags=["Health"],
        summary="Service metadata",
    )
    async def root() -> ServiceInfo:
        return ServiceInfo(
            service="dracara-growth-os-api",
            version=SERVICE_VERSION,
            environment=settings.environment,
            docs_url="/docs",
            api_versions=[API_VERSION],
        )

    return app


app = create_app()
