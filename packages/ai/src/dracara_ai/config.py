"""Settings for every AI feature, loaded from the environment.

Both ``apps/api`` and ``apps/worker`` already load their own settings independently (see
``app/core/config.py`` and ``apps/worker/env.py``). This module is a third, narrower reader for the
AI-specific keys only, so neither app has to pass a settings object across the package boundary and
the two cannot disagree about which model is in use.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Feature flag -----------------------------------------------------
    #: Master switch. Off by default so a deployment without an API key behaves predictably
    #: (features report "not configured") instead of failing per-request deep in a graph.
    ai_enabled: bool = Field(default=False, validation_alias="AI_ENABLED")

    # --- OpenAI -----------------------------------------------------------
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_api_base: str = Field(default="", validation_alias="OPENAI_API_BASE")
    #: Everyday work: call notes, the assistant, deal health. Cheap and fast.
    openai_chat_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_CHAT_MODEL")
    #: Long-form generation where quality is worth the cost: proposal drafting.
    openai_reasoning_model: str = Field(default="gpt-4o", validation_alias="OPENAI_REASONING_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", validation_alias="OPENAI_EMBEDDING_MODEL"
    )
    #: Dimensionality of the embedding model above. text-embedding-3-small is 1536; change both
    #: together, and re-index, or every existing point in the collection becomes unsearchable.
    openai_embedding_dimensions: int = Field(
        default=1536, validation_alias="OPENAI_EMBEDDING_DIMENSIONS"
    )
    openai_timeout_seconds: float = Field(default=60.0, validation_alias="OPENAI_TIMEOUT_SECONDS")
    openai_max_retries: int = Field(default=2, validation_alias="OPENAI_MAX_RETRIES")

    # --- Qdrant -----------------------------------------------------------
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", validation_alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="voice_agent_kb", validation_alias="QDRANT_COLLECTION")
    qdrant_timeout_seconds: float = Field(default=15.0, validation_alias="QDRANT_TIMEOUT_SECONDS")

    # --- Web research (Exa) ------------------------------------------------
    #: Only a company's name and web domain are ever sent -- see search.py.
    exa_api_key: str = Field(default="", validation_alias="EXA_API_KEY")
    exa_api_base: str = Field(default="https://api.exa.ai", validation_alias="EXA_API_BASE")
    exa_timeout_seconds: float = Field(default=30.0, validation_alias="EXA_TIMEOUT_SECONDS")
    #: Research older than this is re-run on request; anything newer is served from storage, so
    #: repeatedly opening the same company does not re-bill the search.
    research_ttl_days: int = Field(default=14, validation_alias="RESEARCH_TTL_DAYS")

    # --- Cost control -----------------------------------------------------
    #: Per-organization, per-calendar-month ceiling on total tokens. Zero disables the check.
    #: This is a multi-tenant product sharing one API key -- without a ceiling, one tenant's
    #: runaway usage is billed to everyone.
    ai_monthly_token_budget: int = Field(default=0, validation_alias="AI_MONTHLY_TOKEN_BUDGET")

    @property
    def is_configured(self) -> bool:
        return bool(self.ai_enabled and self.openai_api_key)


@lru_cache
def get_ai_settings() -> AiSettings:
    return AiSettings()


ai_settings = get_ai_settings()
