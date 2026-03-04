from __future__ import annotations

import secrets

from pydantic_settings import BaseSettings

_DEFAULT_SECRET = "CHANGE-ME-IN-PRODUCTION"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "AgentGraph"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    base_url: str = "http://localhost:5173"

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/agentgraph"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = _DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Google OAuth
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://***REMOVED***:5173",
        "http://***REMOVED***:5174",
        "https://agentgraph.io",
        "http://***REMOVED***",
    ]

    # Rate limiting — human tier (default, also used by existing rate_limit_reads/writes)
    rate_limit_reads_per_minute: int = 100
    rate_limit_writes_per_minute: int = 20
    rate_limit_auth_per_minute: int = 5
    trusted_proxies: list[str] = []

    # Rate limiting — anonymous tier (no auth)
    rate_limit_anon_reads_per_minute: int = 30
    rate_limit_anon_writes_per_minute: int = 10

    # Rate limiting — agent tier (entity.type == "agent")
    rate_limit_agent_reads_per_minute: int = 300
    rate_limit_agent_writes_per_minute: int = 150

    # Rate limiting — trusted agent tier (agent with trust_score > 0.7)
    rate_limit_trusted_agent_reads_per_minute: int = 600
    rate_limit_trusted_agent_writes_per_minute: int = 300

    # Trust score threshold for the trusted_agent tier
    rate_limit_trusted_agent_threshold: float = 0.7

    # Stripe Connect
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_platform_fee_percent: int = 10
    escrow_auto_release_hours: int = 72

    # Webhook encryption (Fernet key for signing key at-rest encryption)
    webhook_encryption_key: str | None = None

    # SSO
    sso_enabled: bool = False  # Must be explicitly enabled; mock impl is not safe
    sso_saml_entity_id: str = "agentgraph-sp"
    sso_callback_base_url: str = "http://localhost:8000"

    # Email (SMTP)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    from_email: str = "noreply@agentgraph.co"

    # Perspective API (Google text toxicity scoring)
    perspective_api_key: str | None = None
    perspective_toxicity_block: float = 0.85
    perspective_toxicity_flag: float = 0.70
    perspective_timeout: int = 5

    # Auto-moderation: auto-hide posts with this many flags
    auto_hide_flag_threshold: int = 5

    # Error tracking
    sentry_dsn: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# If debug mode uses the default secret, replace it with a random one so
# even dev tokens are unpredictable.  Non-debug mode crashes in main.py.
if settings.debug and settings.jwt_secret == _DEFAULT_SECRET:
    settings.jwt_secret = secrets.token_urlsafe(64)
