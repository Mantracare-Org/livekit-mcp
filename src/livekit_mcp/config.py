"""Configuration settings for the LiveKit MCP Server."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Network & Server Settings
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # Authentication Settings (Mantra Auth OAuth 2.1 / Shared JWT)
    auth_enabled: bool = Field(default=True, validation_alias="AUTH_ENABLED")
    jwt_secret: str | None = Field(
        default=None,
        validation_alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    auth_server_url: str = Field(
        default="http://localhost:3000",
        validation_alias="AUTH_SERVER_URL",
    )
    jwt_issuer: str | None = Field(default=None, validation_alias=AliasChoices("JWT_ISSUER", "MCP_ISSUER_URL"))
    jwt_audience: str | None = Field(default=None, validation_alias="JWT_AUDIENCE")

    # MantraAssist Backend HTTP API Endpoint (:5500)
    mantraassist_backend_url: str = Field(
        default="http://localhost:5500",
        validation_alias="MANTRAASSIST_BACKEND_URL",
    )
    mantraassist_client_id: str | None = Field(
        default=None,
        validation_alias="MANTRAASSIST_CLIENT_ID",
    )
    mantraassist_client_secret: str | None = Field(
        default=None,
        validation_alias="MANTRAASSIST_CLIENT_SECRET",
    )
    mantraassist_webhook_secret: str | None = Field(
        default=None,
        validation_alias="MANTRAASSIST_WEBHOOK_SECRET",
    )

    # PostgreSQL Database (mcp_logs_db / assist_db)
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5442/mcp_logs_db",
        validation_alias="DATABASE_URL",
    )
    assist_db_url: str | None = Field(
        default=None,
        validation_alias="ASSIST_DB_URL",
    )
    mcp_events_db_url: str | None = Field(
        default=None,
        validation_alias="MCP_EVENTS_DB_URL",
    )

    # LKT Voice Agent & Telephony Service
    lkt_api_base_url: str = Field(
        default="http://localhost:8081",
        validation_alias="LKT_API_BASE_URL",
    )
    lkt_api_timeout: float = Field(default=15.0, validation_alias="LKT_API_TIMEOUT")

    # LiveKit Cloud Direct Credentials (Optional)
    livekit_url: str | None = Field(default=None, validation_alias="LIVEKIT_URL")
    livekit_api_key: str | None = Field(default=None, validation_alias="LIVEKIT_API_KEY")
    livekit_api_secret: str | None = Field(default=None, validation_alias="LIVEKIT_API_SECRET")

    @property
    def effective_db_url(self) -> str:
        """Return the effective database URL (MCP_EVENTS_DB_URL, ASSIST_DB_URL, or DATABASE_URL)."""
        return self.mcp_events_db_url or self.assist_db_url or self.database_url


    @property
    def is_production(self) -> bool:
        """Check if server is running in production."""
        return self.environment.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
