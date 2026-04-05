"""
agents/marketing/tools.py — LinkedIn API helpers + DB helpers.

Platform support: LinkedIn only.
Reddit and X removed — not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from app.config import settings
from app.db.supabase_client import get_client

logger = logging.getLogger(__name__)

LINKEDIN_API_VERSION = "202504"

PLATFORM_CHAR_LIMITS = {
    "linkedin": 3000,
}

SUPPORTED_PLATFORMS = list(PLATFORM_CHAR_LIMITS.keys())


def _linkedin_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.linkedin_access_token}",
        "Content-Type": "application/json",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


# ── Search ────────────────────────────────────────────────────────────────────

def search_linkedin(keywords: list[str], hours: int = 24) -> list[dict[str, Any]]:
    """
    Fetch recent posts from the authenticated LinkedIn author and filter by
    keyword match within the given time window.

    Returns list of dicts: platform, url, author, content, posted_at
    """
    if not all([settings.linkedin_access_token, settings.linkedin_person_id]):
        logger.warning("LinkedIn credentials not configured — skipping LinkedIn search")
        return []
    if not keywords:
        return []

    headers = _linkedin_headers()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ms = int(cutoff.timestamp() * 1000)

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _as_urn(raw: str, kind: str) -> str:
        return raw if raw.startswith("urn:li:") else f"urn:li:{kind}:{raw}"

    authors = [_as_urn(settings.linkedin_person_id, "person")]
    if settings.linkedin_organization_id:
        authors.append(_as_urn(settings.linkedin_organization_id, "organization"))

    with httpx.Client() as client:
        for author_urn in authors:
            try:
                resp = client.get(
                    "https://api.linkedin.com/rest/posts",
                    headers=headers,
                    params={
                        "author": author_urn,
                        "q": "author",
                        "count": 50,
                        "sortBy": "LAST_MODIFIED",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "LinkedIn API %d for %s: %s",
                        resp.status_code, author_urn, resp.text[:200],
                    )
                    continue

                for post in resp.json().get("elements", []):
                    post_id = post.get("id", "")
                    if post_id in seen_ids:
                        continue
                    if post.get("createdAt", 0) < cutoff_ms:
                        continue

                    content = post.get("commentary", "") or (
                        post.get("specificContent", {})
                        .get("com.linkedin.ugc.ShareContent", {})
                        .get("shareCommentary", {})
                        .get("text", "")
                    )
                    if not content:
                        continue
                    if not any(kw.lower() in content.lower() for kw in keywords):
                        continue

                    seen_ids.add(post_id)
                    results.append({
                        "platform": "linkedin",
                        "url": f"https://www.linkedin.com/feed/update/{post_id}",
                        "author": post.get("author", author_urn),
                        "content": content,
                        "posted_at": datetime.fromtimestamp(
                            post["createdAt"] / 1000, tz=timezone.utc
                        ).isoformat(),
                        "post_id": post_id,
                    })
            except Exception:
                logger.exception("Error fetching LinkedIn posts for %s", author_urn)

    logger.info("search_linkedin found %d posts for keywords=%s", len(results), keywords)
    return results


# ── Posting ─────────────────────────────────────────────────────────────��─────

def post_to_linkedin(text: str) -> dict[str, Any]:
    """
    Share a text post on LinkedIn as the authenticated user or organization.
    Returns dict with platform_post_id and url.
    """
    if not all([settings.linkedin_access_token, settings.linkedin_person_id]):
        raise RuntimeError(
            "LinkedIn posting requires linkedin_access_token and linkedin_person_id"
        )

    def _as_urn(raw: str, kind: str) -> str:
        """Ensure the ID is a full LinkedIn URN."""
        if raw.startswith("urn:li:"):
            return raw
        return f"urn:li:{kind}:{raw}"

    if settings.linkedin_organization_id:
        author = _as_urn(settings.linkedin_organization_id, "organization")
    else:
        author = _as_urn(settings.linkedin_person_id, "person")

    payload = {
        "author": author,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    with httpx.Client() as client:
        resp = client.post(
            "https://api.linkedin.com/rest/posts",
            headers=_linkedin_headers(),
            json=payload,
        )

    if resp.status_code == 201:
        post_id = resp.headers.get("x-restli-id", "")
        logger.info("Published LinkedIn post id=%s", post_id)
        return {
            "platform_post_id": post_id,
            "url": f"https://www.linkedin.com/feed/update/{post_id}",
        }

    logger.error("LinkedIn post failed %d: %s", resp.status_code, resp.text[:500])
    raise RuntimeError(f"LinkedIn API returned {resp.status_code}: {resp.text[:200]}")


# ── Engagement ──────────────────────────────���──────────────────────────���──────

def get_linkedin_engagement(post_id: str) -> dict[str, int]:
    """Fetch likes, comments, and shares for a LinkedIn post."""
    if not settings.linkedin_access_token:
        return {"likes": 0, "comments": 0, "shares": 0}

    try:
        with httpx.Client() as client:
            resp = client.get(
                f"https://api.linkedin.com/rest/socialMetadata/{post_id}",
                headers=_linkedin_headers(),
            )
        if resp.status_code != 200:
            return {"likes": 0, "comments": 0, "shares": 0}
        stats = resp.json().get("totalShareStatistics", {})
        return {
            "likes":    stats.get("likeCount", 0),
            "comments": stats.get("commentCount", 0),
            "shares":   stats.get("shareCount", 0),
        }
    except Exception:
        logger.exception("Failed to fetch LinkedIn engagement for %s", post_id)
        return {"likes": 0, "comments": 0, "shares": 0}


# ── DB helpers ─────────────────────��────────────────────────────────��─────────

def store_trend(trend: dict[str, Any]) -> dict[str, Any]:
    """Insert a trend. Table: marketing_trends"""
    resp = (
        get_client()
        .table("marketing_trends")
        .insert({
            "platform":         trend.get("platform", "linkedin"),
            "url":              trend.get("url"),
            "topic":            trend.get("topic", ""),
            "relevance_score":  trend.get("relevance_score", 0),
            "original_content": trend.get("content", ""),
            "suggested_action": trend.get("suggested_action"),
        })
        .execute()
    )
    return resp.data[0]


def get_trend(trend_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table("marketing_trends")
        .select("*")
        .eq("id", trend_id)
        .maybe_single()
        .execute()
    )
    return resp.data


def store_content(content: dict[str, Any]) -> dict[str, Any]:
    """Insert a draft post. Table: marketing_content (body = post text)"""
    resp = (
        get_client()
        .table("marketing_content")
        .insert({
            "platform":     content.get("platform", "linkedin"),
            "body":         content.get("content", ""),
            "content_type": content.get("content_type"),
            "status":       "draft",
        })
        .execute()
    )
    return resp.data[0]


def update_content_status(content_id: str, status: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, **extra}
    resp = (
        get_client()
        .table("marketing_content")
        .update(payload)
        .eq("id", content_id)
        .execute()
    )
    return resp.data[0]


def get_content(content_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table("marketing_content")
        .select("*")
        .eq("id", content_id)
        .maybe_single()
        .execute()
    )
    return resp.data


def get_recent_trends(limit: int = 20) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("marketing_trends")
        .select("*")
        .order("found_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def get_content_by_status(status: str, limit: int = 20) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("marketing_content")
        .select("*")
        .eq("status", status)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []
