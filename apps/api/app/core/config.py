"""Application settings — single source of truth, loaded from env/.env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_V1_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Service identity -------------------------------------------------
    project_name: str = Field(default="Dracara Growth OS API", validation_alias="PROJECT_NAME")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_json: bool = Field(default=False, validation_alias="LOG_JSON")
    #: Error monitoring; unset disables it. See app/core/monitoring.py for what is (not) sent.
    sentry_dsn: str = Field(default="", validation_alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(
        default=0.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE"
    )
    #: Build identifier (e.g. the git SHA), tagged on errors so a regression maps to a deploy.
    release: str = Field(default="", validation_alias="RELEASE")

    # --- Supabase ---------------------------------------------------------
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(default="", validation_alias="SUPABASE_JWT_SECRET")
    jwks_cache_seconds: int = Field(default=600, validation_alias="SUPABASE_JWKS_CACHE_SECONDS")

    # --- HTTP client ------------------------------------------------------
    http_timeout_seconds: float = Field(default=30.0, validation_alias="HTTP_TIMEOUT_SECONDS")
    http_max_connections: int = Field(default=100, validation_alias="HTTP_MAX_CONNECTIONS")
    http_max_keepalive: int = Field(default=20, validation_alias="HTTP_MAX_KEEPALIVE")

    # --- Web / CORS -------------------------------------------------------
    cors_origins: str = Field(default="http://localhost:3000", validation_alias="CORS_ORIGINS")
    #: Public origin of the web app. Auth emails (invites) and billing checkout/portal return
    #: here, so it must be the real domain in production -- and, for auth, listed in Supabase
    #: Auth's redirect allow-list (see SETUP.md).
    web_app_url: str = Field(default="http://localhost:3000", validation_alias="WEB_APP_URL")

    # --- Billing (Dodo Payments) ------------------------------------------
    dodo_payments_api_key: str = Field(default="", validation_alias="DODO_PAYMENTS_API_KEY")
    #: "test" or "live" -- selects https://test.dodopayments.com vs https://live.dodopayments.com.
    dodo_payments_environment: str = Field(
        default="test", validation_alias="DODO_PAYMENTS_ENVIRONMENT"
    )
    #: Standard Webhooks signing secret ("whsec_..."), from the Dodo dashboard's webhook page.
    dodo_webhook_secret: str = Field(default="", validation_alias="DODO_PAYMENTS_WEBHOOK_SECRET")
    #: One per-seat recurring product per tier, created in the Dodo dashboard.
    dodo_product_starter: str = Field(default="", validation_alias="DODO_PRODUCT_STARTER")
    dodo_product_growth: str = Field(default="", validation_alias="DODO_PRODUCT_GROWTH")
    dodo_product_scale: str = Field(default="", validation_alias="DODO_PRODUCT_SCALE")

    # --- Rate limiting ----------------------------------------------------
    rate_limit_default: str = Field(default="300/minute", validation_alias="RATE_LIMIT_DEFAULT")
    rate_limit_enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")
    #: Where limit counters live. "memory://" is per process: with several API replicas (or
    #: uvicorn workers) each keeps its own count, multiplying the effective limit. Point it at
    #: Redis in production, e.g. redis://redis:6379/1 -- the worker's Redis is fine.
    rate_limit_storage_uri: str = Field(
        default="memory://", validation_alias="RATE_LIMIT_STORAGE_URI"
    )

    # --- Google OAuth -----------------------------------------------------
    google_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="", validation_alias="GOOGLE_REDIRECT_URI")

    # --- Storage ----------------------------------------------------------
    proposals_bucket: str = Field(default="proposals", validation_alias="PROPOSALS_BUCKET")
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")

    # --- Voice agents (Twilio + a managed voice-AI platform) ---------------
    voice_kb_bucket: str = Field(default="voice-agent-docs", validation_alias="VOICE_KB_BUCKET")
    voice_platform: str = Field(default="vapi", validation_alias="VOICE_PLATFORM")
    voice_platform_api_key: str = Field(default="", validation_alias="VOICE_PLATFORM_API_KEY")
    voice_platform_api_base: str = Field(
        default="https://api.vapi.ai", validation_alias="VOICE_PLATFORM_API_BASE"
    )
    voice_platform_webhook_secret: str = Field(
        default="", validation_alias="VOICE_PLATFORM_WEBHOOK_SECRET"
    )
    twilio_account_sid: str = Field(default="", validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", validation_alias="TWILIO_AUTH_TOKEN")
    #: Publicly reachable base URL for this API (e.g. an ngrok tunnel in dev, the real domain
    #: in production) -- used to build the webhook URL handed to the voice platform. Calls and
    #: assistant creation fail loudly via NotConfiguredError-style checks if this is unset and
    #: a webhook URL is actually needed.
    api_public_base_url: str = Field(default="", validation_alias="API_PUBLIC_BASE_URL")

    # --- AI features ------------------------------------------------------
    #: These mirror `packages/ai`'s own `AiSettings`, which is what the graphs actually read.
    #: They are repeated here so the API can answer "is this feature configured?" without
    #: importing the AI package at startup, and so `/health/ready` and the OpenAPI description
    #: can report it. `packages/ai` remains the single source of truth for model ids at runtime.
    ai_enabled: bool = Field(default=False, validation_alias="AI_ENABLED")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    #: Web research (company enrichment, pre-call briefs). Only a company's name and website are
    #: ever sent -- see packages/ai/src/dracara_ai/search.py.
    exa_api_key: str = Field(default="", validation_alias="EXA_API_KEY")
    #: Per-organization, per-calendar-month token ceiling; 0 disables the check. One API key is
    #: shared across every tenant, so without a ceiling one organization's runaway usage is
    #: billed to all of them. Enforced in `app/services/ai/budget.py`.
    ai_monthly_token_budget: int = Field(default=0, validation_alias="AI_MONTHLY_TOKEN_BUDGET")

    @property
    def ai_configured(self) -> bool:
        """Whether AI endpoints can do real work. False turns them into a clear 503 rather
        than a failure from somewhere inside a graph."""
        return bool(self.ai_enabled and self.openai_api_key)

    @property
    def research_configured(self) -> bool:
        return bool(self.ai_configured and self.exa_api_key)

    def production_problems(self) -> list[str]:
        """Settings that work in development but are wrong in production. Logged at startup
        (see app.main) -- each of these otherwise fails quietly, far from its cause."""
        if not self.is_production:
            return []
        problems = []
        if "localhost" in self.web_app_url or "127.0.0.1" in self.web_app_url:
            problems.append("WEB_APP_URL points at localhost: invite, reset and billing links will be broken")
        if any("localhost" in o or "127.0.0.1" in o for o in self.cors_origins_list):
            problems.append("CORS_ORIGINS still allows localhost")
        if self.rate_limit_storage_uri.startswith("memory://"):
            problems.append("RATE_LIMIT_STORAGE_URI is memory://: limits are per process, not shared")
        if not self.supabase_service_role_key:
            problems.append("SUPABASE_SERVICE_ROLE_KEY is unset: invites, billing and webhooks will fail")
        if not self.sentry_dsn:
            problems.append("SENTRY_DSN is unset: errors will only reach the logs")
        if not self.billing_configured:
            problems.append("Dodo Payments is not configured: nobody can subscribe")
        elif self.dodo_payments_environment.lower() not in {"live", "live_mode", "production"}:
            problems.append("DODO_PAYMENTS_ENVIRONMENT is not live: checkouts use test mode")
        return problems

    @property
    def billing_configured(self) -> bool:
        return bool(self.dodo_payments_api_key and self.dodo_webhook_secret)

    @property
    def dodo_api_base(self) -> str:
        if self.dodo_payments_environment.lower() in {"live", "live_mode", "production"}:
            return "https://live.dodopayments.com"
        return "https://test.dodopayments.com"

    @property
    def web_app_origin(self) -> str:
        return self.web_app_url.rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def rest_base_url(self) -> str:
        return self.supabase_url.rstrip("/") + "/rest/v1"

    @property
    def auth_base_url(self) -> str:
        return self.supabase_url.rstrip("/") + "/auth/v1"

    @property
    def storage_base_url(self) -> str:
        return self.supabase_url.rstrip("/") + "/storage/v1"

    @property
    def jwt_issuer(self) -> str:
        """Expected `iss` claim on Supabase-issued access tokens."""
        return self.auth_base_url

    @property
    def jwks_url(self) -> str:
        """Public JWKS for asymmetric (ES256/RS256) project signing keys."""
        return self.auth_base_url + "/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
