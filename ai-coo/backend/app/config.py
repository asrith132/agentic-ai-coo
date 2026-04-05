"""
config.py — Loads all environment variables via pydantic BaseSettings.

All modules should import `settings` from here rather than reading os.environ
directly. Pydantic validates types on startup so missing required vars fail fast.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # ── LLM ──────────────────────────────────────────────────────────────────
    anthropic_api_key: str

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── GitHub ────────────────────────────────────────────────────────────────
    github_webhook_secret: str = ""

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    linkedin_access_token: str = ""
    linkedin_person_id: str = ""
    linkedin_organization_id: str = ""

    # ── Gmail ─────────────────────────────────────────────────────────────────
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    # ── Telegram (push notifications) ────────────────────────────────────────
    telegram_bot_token: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    public_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton of the settings object."""
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()
