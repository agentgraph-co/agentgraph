from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "AgentGraph"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/agentgraph"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Rate limiting
    rate_limit_reads_per_minute: int = 100
    rate_limit_writes_per_minute: int = 20
    rate_limit_auth_per_minute: int = 5

    # Stripe Connect
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_platform_fee_percent: int = 10

    # SSO
    sso_enabled: bool = False  # Must be explicitly enabled; mock impl is not safe
    sso_saml_entity_id: str = "agentgraph-sp"
    sso_callback_base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
