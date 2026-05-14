"""Application settings loaded from environment variables."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True
    api_v1_prefix: str = "/v1"
    project_name: str = "AEGIS"
    version: str = "0.1.0"

    # --- Database ---
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://aegis:aegis@postgres:5432/aegis",
    )
    database_url_sync: PostgresDsn = Field(
        default="postgresql+psycopg2://aegis:aegis@postgres:5432/aegis",
        description="Sync URL used by Alembic.",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Redis ---
    redis_url: RedisDsn = Field(default="redis://redis:6379/0")
    celery_broker_url: RedisDsn = Field(default="redis://redis:6379/1")
    celery_result_backend: RedisDsn = Field(default="redis://redis:6379/2")

    # --- Auth (Keycloak) ---
    # Keycloak has two URLs that look identical but mean different things:
    #   internal — what the API uses to fetch JWKS over the docker network.
    #   public   — what appears in `iss` of tokens issued to browsers.
    # In dev, set KC_HOSTNAME=localhost on the Keycloak service so the public
    # URL stays stable whether the caller is the browser, curl on the host,
    # or another container.
    keycloak_url:        str = "http://keycloak:8080"   # internal — for JWKS
    keycloak_public_url: str = "http://localhost:8080"  # public — for issuer
    keycloak_realm:     str = "aegis"
    keycloak_client_id: str = "aegis-api"
    keycloak_audience:  str = "aegis-api"
    keycloak_jwks_url:  str | None = None
    jwt_algorithm:      str = "RS256"
    jwt_leeway_seconds: int = 30

    # --- Ingest API key (shared key for log ingestion endpoints) ---
    ingest_api_key: str = "dev-ingest-key-change-me"

    # --- Encryption (Fernet) for integration credentials ---
    fernet_key: str = "x" * 44  # override in production; 44-char base64 urlsafe key

    # --- Claude API ---
    anthropic_api_key: str | None = None
    claude_model_default: str = "claude-sonnet-4-6"
    claude_model_cheap: str = "claude-haiku-4-5"

    # --- Observability ---
    sentry_dsn: str | None = None
    log_level: str = "INFO"
    log_json: bool = True

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @property
    def jwks_url(self) -> str:
        if self.keycloak_jwks_url:
            return self.keycloak_jwks_url
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

    @property
    def jwt_issuer(self) -> str:
        """Public issuer URL — must match what Keycloak embeds in tokens."""
        return f"{self.keycloak_public_url}/realms/{self.keycloak_realm}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
