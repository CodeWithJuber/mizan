"""
MIZAN Settings — Centralized Configuration
============================================

Uses pydantic-settings for validated, type-safe configuration.
All settings are loaded from environment variables or .env file.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """MIZAN application settings. Loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── AI Providers ─────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_referer: str = "https://github.com/CodeWithJuber/mizan"
    llm_provider: str = ""  # auto-detect if empty; anthropic | openrouter | openai | ollama
    default_model: str = "claude-sonnet-4-20250514"

    # ── System ───────────────────────────────────────────────
    secret_key: str = "change-this-to-a-secure-random-string"
    debug: bool = False
    log_level: str = "INFO"

    # ── Server ───────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])

    # ── Database ─────────────────────────────────────────────
    db_path: str = str(PROJECT_ROOT / "data" / "mizan.db")

    # ── Security ─────────────────────────────────────────────
    jwt_expiry_hours: int = 24
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10
    max_input_length: int = 50000
    ws_max_connections: int = 50

    # ── Local AI ─────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"

    # ── Channels (Optional) ──────────────────────────────────
    telegram_bot_token: str = ""
    discord_bot_token: str = ""
    slack_app_token: str = ""
    whatsapp_token: str = ""

    # ── Email (Optional) ─────────────────────────────────────
    email_host: str = ""
    email_user: str = ""
    email_password: str = ""

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key != "sk-ant-your-key-here")

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key != "sk-your-openai-key-here")

    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def has_any_provider(self) -> bool:
        return self.has_anthropic or self.has_openai or self.has_openrouter


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
