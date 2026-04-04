"""
Supabase Auth: validate browser access tokens for API routes.

Uses ``GET /auth/v1/user`` with the anon key (no JWT secret in env required).
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException

from app.config import settings


def _parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def fetch_supabase_user(access_token: str) -> dict[str, Any]:
    """Return Supabase user JSON or raise ``HTTPException`` (401)."""
    base = (settings.supabase_url or "").rstrip("/")
    key = (settings.supabase_anon_key or "").strip()
    if not base or not key:
        raise HTTPException(
            status_code=503,
            detail="Supabase URL or anon key is not configured on the server.",
        )
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{base}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": key,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Auth service unreachable: {str(exc)[:400]}",
        ) from exc

    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict) and data.get("id"):
            return data
        raise HTTPException(status_code=401, detail="Invalid auth response.")

    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please sign in again.",
        )

    snippet = (resp.text or "")[:200]
    raise HTTPException(
        status_code=502,
        detail=f"Auth verification failed ({resp.status_code}): {snippet}",
    )


def get_current_user_optional(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any] | None:
    """
    Optional Supabase user from ``Authorization: Bearer <access_token>``.

    Returns ``None`` when no header. Raises 401 when a Bearer token is present
    but invalid.
    """
    token = _parse_bearer(authorization)
    if not token:
        return None
    return fetch_supabase_user(token)


def get_voice_user_optional(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any] | None:
    """
    Resolve Supabase user for PM voice only.

    Returns ``None`` when there is no Bearer token **or** the token is invalid or
    expired, so anonymous clients always get the guest voice path without 401.
    Other routes keep strict ``get_current_user_optional`` (invalid Bearer → 401).
    """
    token = _parse_bearer(authorization)
    if not token:
        return None
    try:
        return fetch_supabase_user(token)
    except HTTPException:
        return None


def require_pm_user(
    user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Sign in to use this endpoint.",
        )
    return user
