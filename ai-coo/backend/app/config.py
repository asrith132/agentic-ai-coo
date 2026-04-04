"""
config.py — Loads all environment variables via pydantic BaseSettings.

All modules should import `settings` from here rather than reading os.environ
directly. Pydantic validates types on startup so missing required vars fail fast.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # ── LLM ──────────────────────────────────────────────────────────────────
    anthropic_api_key: str

    # ── PM voice (ElevenLabs STT/TTS; STT may be client-side for MVP) ─────────
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_tts_model_id: str = ""
    elevenlabs_scribe_model_id: str = "scribe_v2_realtime"

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

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @field_validator(
        "anthropic_api_key",
        "elevenlabs_api_key",
        "elevenlabs_voice_id",
        "elevenlabs_tts_model_id",
        mode="before",
    )
    @classmethod
    def strip_optional_secrets(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            s = v.strip()
            if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
                s = s[1:-1].strip()
            return s
        return v


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton of the settings object."""
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()
