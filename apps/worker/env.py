from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    resend_api_key: str = Field(default="", validation_alias="RESEND_API_KEY")
    #: Sender for worker email (the daily brief). Must be on a domain verified in Resend;
    #: onboarding@resend.dev only delivers to the Resend account's own address.
    email_from: str = Field(
        default="Dracara Growth OS <onboarding@resend.dev>", validation_alias="EMAIL_FROM"
    )
    #: Public origin of the web app, for links in emails.
    web_app_url: str = Field(default="http://localhost:3000", validation_alias="WEB_APP_URL")
    #: Error monitoring; unset disables it.
    sentry_dsn: str = Field(default="", validation_alias="SENTRY_DSN")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    release: str = Field(default="", validation_alias="RELEASE")
    google_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", validation_alias="GOOGLE_CLIENT_SECRET")

    # --- AI features ------------------------------------------------------
    #: `packages/ai` reads OPENAI_API_KEY, QDRANT_URL and the model ids from the environment
    #: itself. Only the switch is mirrored here, so a scheduled job can skip its work entirely
    #: (and log that it did) rather than starting and failing per row.
    ai_enabled: bool = Field(default=False, validation_alias="AI_ENABLED")
    #: How many rows one scheduled AI pass will process. A ceiling matters more here than in the
    #: API: a backlog of a thousand untranscribed calls would otherwise become a thousand model
    #: calls in a single beat tick.
    ai_batch_limit: int = Field(default=25, validation_alias="AI_BATCH_LIMIT")
    #: Mirrors VOICE_KB_BUCKET in apps/api -- the reindex job fetches document bytes back out of
    #: Storage to rebuild the vector index.
    voice_kb_bucket: str = Field(default="voice-agent-docs", validation_alias="VOICE_KB_BUCKET")


ENV = WorkerSettings()
