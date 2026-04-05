"""
db/supabase_client.py — Singleton Supabase client.

Use `get_client()` to get the authenticated service-role client throughout the app.
The service role key bypasses Row Level Security — only use it server-side.
The anon key is exposed to the frontend; never use it here.
"""

from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_client() -> Client:
    """
    Return a module-level singleton Supabase client authenticated with
    the service role key (full DB access, bypasses RLS).

    Called by core helpers (context.py, events.py, etc.) and agent tools.
    """
    global _client
    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _client


# Convenience alias
supabase = get_client
