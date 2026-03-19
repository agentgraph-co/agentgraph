"""Marketing system configuration.

All settings load from environment variables with sensible defaults.
API keys default to None — adapters gracefully skip when unconfigured.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class MarketingSettings(BaseSettings):
    """Marketing bot configuration loaded from environment."""

    # --- Feature flag ---
    marketing_enabled: bool = False

    # --- LLM budget ---
    marketing_llm_daily_budget: float = 1.0  # USD per day
    marketing_llm_monthly_budget: float = 20.0  # USD per month

    # --- Local LLM (Ollama) ---
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_timeout: int = 300  # 5 min for 9B model

    # --- Anthropic API ---
    anthropic_api_key: str | None = None
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"
    anthropic_sonnet_model: str = "claude-sonnet-4-6"
    anthropic_opus_model: str = "claude-opus-4-6"

    # --- Platform API keys (all optional — skip if missing) ---

    # Twitter/X (Free tier: write-only, 1500 tweets/mo)
    twitter_bearer_token: str | None = None
    twitter_api_key: str | None = None
    twitter_api_secret: str | None = None
    twitter_access_token: str | None = None
    twitter_access_secret: str | None = None

    # Reddit (via asyncpraw)
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_username: str | None = None
    reddit_password: str | None = None
    reddit_user_agent: str = "AgentGraphBot/1.0 by u/AgentGraphBot"

    # Discord
    discord_bot_token: str | None = None

    # LinkedIn (Company page API v2)
    linkedin_access_token: str | None = None
    linkedin_org_id: str | None = None

    # Telegram
    telegram_bot_token: str | None = None
    telegram_channel_id: str | None = None

    # Bluesky (AT Protocol)
    bluesky_handle: str | None = None
    bluesky_app_password: str | None = None

    # Dev.to
    devto_api_key: str | None = None

    # Hashnode
    hashnode_api_key: str | None = None
    hashnode_publication_id: str | None = None

    # GitHub (for Discussions — reuses main github_token from config.py)
    # Falls back to src.config.settings.github_token

    # HuggingFace
    huggingface_token: str | None = None

    # --- Scheduling cadences (seconds) ---
    twitter_post_interval: int = 6 * 60 * 60       # 6hr
    reddit_post_interval: int = 12 * 60 * 60        # 12hr
    discord_post_interval: int = 8 * 60 * 60         # 8hr
    linkedin_post_interval: int = 24 * 60 * 60       # 24hr
    bluesky_post_interval: int = 8 * 60 * 60         # 8hr
    telegram_post_interval: int = 8 * 60 * 60        # 8hr
    devto_post_interval: int = 7 * 24 * 60 * 60      # Weekly
    hashnode_post_interval: int = 7 * 24 * 60 * 60   # Weekly

    # Reactive keyword check interval
    monitor_check_interval: int = 15 * 60  # 15 min

    # Metric refresh interval
    metrics_refresh_interval: int = 2 * 60 * 60  # 2hr

    # --- Content settings ---
    topic_cooldown_hours: int = 48  # Don't repeat same topic on same platform
    max_retry_count: int = 3
    content_dedup_window_days: int = 30  # SHA-256 dedup window

    # --- UTM defaults ---
    utm_source: str = "agentgraph_bot"

    model_config = {
        "env_file": (".env", ".env.secrets"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


marketing_settings = MarketingSettings()
