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

    # --- Rate limiting ----------------------------------------------------
    rate_limit_default: str = Field(default="300/minute", validation_alias="RATE_LIMIT_DEFAULT")
    rate_limit_enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")

    # --- Google OAuth -----------------------------------------------------
    google_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="", validation_alias="GOOGLE_REDIRECT_URI")

    # --- Storage ----------------------------------------------------------
    proposals_bucket: str = Field(default="proposals", validation_alias="PROPOSALS_BUCKET")
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")

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
