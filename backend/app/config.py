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

    # ── Gmail ─────────────────────────────────────────────────────────────────
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    # ── Twilio (push notifications via SMS) ───────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_from: str = ""
    twilio_phone_to: str = ""

    # ── Social Platforms (Marketing Agent) ─────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_username: str = ""
    reddit_password: str = ""
    reddit_user_agent: str = "ai-coo-bot/1.0"
    reddit_subreddits: str = ""  # comma-separated list of subreddits to scan
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""
    linkedin_access_token: str = ""
    linkedin_person_id: str = ""       # URN like "urn:li:person:XXXXXXX" — your LinkedIn member ID
    linkedin_organization_id: str = "" # URN like "urn:li:organization:XXXXXXX" — optional, for company pages

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton of the settings object."""
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()
