"""
agents/marketing/tools.py — Reddit, X, LinkedIn API helpers.

Tools used by MarketingAgent:
  - search_reddit()       — search subreddits for relevant posts
  - search_x()            — search X/Twitter for relevant tweets
  - search_linkedin()     — search LinkedIn for relevant posts
  - post_to_reddit()      — submit post/comment to Reddit via PRAW
  - post_to_x()           — tweet via X API v2
  - post_to_linkedin()    — share post via LinkedIn API
  - get_post_engagement() — fetch likes/comments/shares for a post
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from app.config import settings
from app.db.supabase_client import get_client

logger = logging.getLogger(__name__)

# LinkedIn REST API version header — required by all /rest/* endpoints
LINKEDIN_API_VERSION = "202504"


def _linkedin_headers() -> dict[str, str]:
    """Build the standard headers for LinkedIn REST API calls."""
    return {
        "Authorization": f"Bearer {settings.linkedin_access_token}",
        "Content-Type": "application/json",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


# Character limits per platform
PLATFORM_CHAR_LIMITS = {
    "x": 280,
    "reddit": 10000,
    "linkedin": 3000,
}

SUPPORTED_PLATFORMS = list(PLATFORM_CHAR_LIMITS.keys())


# ── Search helpers ───────────────────────────────────────────────────────────
# These wrap platform APIs to find recent posts matching keywords.
# In production, swap the placeholder implementations for real SDK calls.


async def search_reddit(keywords: list[str], hours: int = 24) -> list[dict[str, Any]]:
    """
    Search Reddit for recent posts matching keywords.

    Uses asyncpraw to search across configured subreddits for posts from the
    last `hours` hours that match any of the provided keywords. Each keyword
    is searched independently; results are deduplicated by post ID.

    Returns list of dicts with: platform, url, author, content, posted_at
    """
    try:
        import asyncpraw  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("asyncpraw not installed — returning empty Reddit results")
        return []

    if not all([settings.reddit_client_id, settings.reddit_client_secret]):
        logger.warning("Reddit credentials not configured — skipping Reddit search")
        return []

    if not keywords:
        return []

    reddit = asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        username=settings.reddit_username or None,
        password=settings.reddit_password or None,
        user_agent=settings.reddit_user_agent,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ts = cutoff.timestamp()

    # Determine which subreddits to scan
    sub_names = [s.strip() for s in settings.reddit_subreddits.split(",") if s.strip()]
    if not sub_names:
        sub_names = ["all"]

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    try:
        for sub_name in sub_names:
            try:
                subreddit = await reddit.subreddit(sub_name)
            except Exception:
                logger.exception("Error accessing r/%s — skipping", sub_name)
                continue

            for keyword in keywords:
                try:
                    async for submission in subreddit.search(
                        keyword, sort="new", time_filter="day", limit=25
                    ):
                        if submission.id in seen_ids:
                            continue
                        if submission.created_utc < cutoff_ts:
                            continue

                        seen_ids.add(submission.id)
                        # Combine title + selftext for full content
                        body = submission.selftext or ""
                        content = f"{submission.title}\n\n{body}".strip() if body else submission.title

                        results.append({
                            "platform": "reddit",
                            "url": f"https://www.reddit.com{submission.permalink}",
                            "author": str(submission.author) if submission.author else "[deleted]",
                            "content": content,
                            "posted_at": datetime.fromtimestamp(
                                submission.created_utc, tz=timezone.utc
                            ).isoformat(),
                            "subreddit": sub_name,
                            "post_id": submission.id,
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                        })
                except Exception:
                    logger.exception(
                        "Error searching r/%s for keyword '%s'", sub_name, keyword
                    )
    finally:
        await reddit.close()

    logger.info("search_reddit found %d posts for keywords=%s", len(results), keywords)
    return results


async def search_x(keywords: list[str], hours: int = 24) -> list[dict[str, Any]]:
    """
    Search X (Twitter) for recent tweets matching keywords.

    Returns list of dicts with: platform, url, author, content, posted_at
    """
    try:
        import tweepy  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("tweepy not installed — returning empty X results")
        return []

    logger.info("search_x called with keywords=%s hours=%d", keywords, hours)
    return []


async def search_linkedin(keywords: list[str], hours: int = 24) -> list[dict[str, Any]]:
    """
    Search LinkedIn for recent posts matching keywords.

    LinkedIn does not offer a public post-search API. Instead, this fetches
    the authenticated user's feed via the Community Management API and
    filters posts client-side by keyword match within the `hours` window.

    Requires: linkedin_access_token and linkedin_person_id in settings.

    Returns list of dicts with: platform, url, author, content, posted_at
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

    # Use the Posts API to fetch recent posts from the authenticated member's feed.
    # The `q=author` parameter lets us pull our own posts + reshares; for broader
    # feed scanning we fall back to the organization feed if configured.
    authors_to_scan = [settings.linkedin_person_id]
    if settings.linkedin_organization_id:
        authors_to_scan.append(settings.linkedin_organization_id)

    async with httpx.AsyncClient() as client:
        for author_urn in authors_to_scan:
            try:
                # LinkedIn REST API v2 — Posts by author
                resp = await client.get(
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
                        "LinkedIn API returned %d for author %s: %s",
                        resp.status_code, author_urn, resp.text[:200],
                    )
                    continue

                data = resp.json()
                for post in data.get("elements", []):
                    post_id = post.get("id", "")
                    if post_id in seen_ids:
                        continue

                    created_at_ms = post.get("createdAt", 0)
                    if created_at_ms < cutoff_ms:
                        continue

                    # Extract text content from the commentary field
                    content = post.get("commentary", "")
                    if not content:
                        # Some post types store text in a different field
                        content = post.get("specificContent", {}).get(
                            "com.linkedin.ugc.ShareContent", {}
                        ).get("shareCommentary", {}).get("text", "")

                    if not content:
                        continue

                    # Check if any keyword matches (case-insensitive)
                    content_lower = content.lower()
                    if not any(kw.lower() in content_lower for kw in keywords):
                        continue

                    seen_ids.add(post_id)
                    author_name = post.get("author", author_urn)

                    results.append({
                        "platform": "linkedin",
                        "url": f"https://www.linkedin.com/feed/update/{post_id}",
                        "author": author_name,
                        "content": content,
                        "posted_at": datetime.fromtimestamp(
                            created_at_ms / 1000, tz=timezone.utc
                        ).isoformat(),
                        "post_id": post_id,
                    })
            except Exception:
                logger.exception("Error fetching LinkedIn posts for %s", author_urn)

    logger.info("search_linkedin found %d posts for keywords=%s", len(results), keywords)
    return results


PLATFORM_SEARCHERS = {
    "reddit": search_reddit,
    "x": search_x,
    "linkedin": search_linkedin,
}


async def search_all_platforms(keywords: list[str], hours: int = 24) -> list[dict[str, Any]]:
    """Run search across all platforms and return combined results."""
    results: list[dict[str, Any]] = []
    for platform, searcher in PLATFORM_SEARCHERS.items():
        try:
            platform_results = await searcher(keywords, hours)
            for r in platform_results:
                r.setdefault("platform", platform)
            results.extend(platform_results)
        except Exception:
            logger.exception("Error searching %s", platform)
    return results


# ── Posting helpers ──────────────────────────────────────────────────────────


async def post_to_reddit(
    subreddit: str,
    title: str,
    body: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """
    Post to Reddit. If parent_id is provided, posts a comment reply instead.

    Requires reddit_username + reddit_password in settings (script-type OAuth
    apps need authenticated user context to submit content).

    Returns dict with: platform_post_id, url
    """
    try:
        import asyncpraw  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError("asyncpraw dependency not installed")

    if not all([
        settings.reddit_client_id,
        settings.reddit_client_secret,
        settings.reddit_username,
        settings.reddit_password,
    ]):
        raise RuntimeError(
            "Reddit posting requires reddit_client_id, reddit_client_secret, "
            "reddit_username, and reddit_password to be configured"
        )

    reddit = asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        username=settings.reddit_username,
        password=settings.reddit_password,
        user_agent=settings.reddit_user_agent,
    )

    try:
        if parent_id:
            # Reply to an existing post or comment
            comment = await reddit.comment(parent_id)
            reply = await comment.reply(body)
            logger.info("Replied to comment %s on Reddit", parent_id)
            return {
                "platform_post_id": reply.id,
                "url": f"https://www.reddit.com{reply.permalink}",
            }
        else:
            # Submit a new post to a subreddit
            if not subreddit:
                raise ValueError("subreddit is required for new Reddit posts")
            sub = await reddit.subreddit(subreddit)
            submission = await sub.submit(title=title, selftext=body)
            logger.info(
                "Submitted post '%s' to r/%s (id=%s)", title, subreddit, submission.id
            )
            return {
                "platform_post_id": submission.id,
                "url": f"https://www.reddit.com{submission.permalink}",
            }
    finally:
        await reddit.close()


async def post_to_x(text: str, reply_to: str | None = None) -> dict[str, Any]:
    """
    Post a tweet. If reply_to is provided, posts as a reply.

    Returns dict with: platform_post_id, url
    """
    try:
        import tweepy  # type: ignore[import-untyped]
    except ImportError:
        logger.error("tweepy not installed — cannot post to X")
        raise RuntimeError("tweepy dependency not installed")

    logger.info("post_to_x text=%s...", text[:50])
    # TODO: implement real posting
    raise NotImplementedError("X posting not yet configured")


async def post_to_linkedin(text: str) -> dict[str, Any]:
    """
    Share a text post on LinkedIn as the authenticated user (or organization).

    Uses the LinkedIn REST API v2 Posts endpoint. Posts as the person by
    default; if linkedin_organization_id is set, posts as the organization.

    Requires: linkedin_access_token, linkedin_person_id in settings.

    Returns dict with: platform_post_id, url
    """
    if not all([settings.linkedin_access_token, settings.linkedin_person_id]):
        raise RuntimeError(
            "LinkedIn posting requires linkedin_access_token and "
            "linkedin_person_id to be configured"
        )

    # Post as organization if configured, otherwise as the person
    author = settings.linkedin_organization_id or settings.linkedin_person_id

    headers = _linkedin_headers()

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

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.linkedin.com/rest/posts",
            headers=headers,
            json=payload,
        )

        if resp.status_code == 201:
            # The post ID is returned in the x-restli-id header
            post_id = resp.headers.get("x-restli-id", "")
            logger.info("Published LinkedIn post id=%s", post_id)
            return {
                "platform_post_id": post_id,
                "url": f"https://www.linkedin.com/feed/update/{post_id}",
            }

        # Non-201 is an error
        logger.error(
            "LinkedIn post failed with status %d: %s",
            resp.status_code, resp.text[:500],
        )
        raise RuntimeError(
            f"LinkedIn API returned {resp.status_code}: {resp.text[:200]}"
        )


PLATFORM_POSTERS = {
    "reddit": post_to_reddit,
    "x": post_to_x,
    "linkedin": post_to_linkedin,
}


async def publish_to_platform(
    platform: str,
    content: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Publish content to the specified platform.

    Returns dict with platform_post_id and url on success.
    Raises on failure.
    """
    if platform not in PLATFORM_POSTERS:
        raise ValueError(f"Unsupported platform: {platform}")

    if platform == "reddit":
        return await post_to_reddit(
            subreddit=kwargs.get("subreddit", ""),
            title=kwargs.get("title", ""),
            body=content,
            parent_id=kwargs.get("parent_id"),
        )
    elif platform == "x":
        return await post_to_x(text=content, reply_to=kwargs.get("reply_to"))
    else:
        return await post_to_linkedin(text=content)


# ── Engagement tracking ─────────────────────────────────────────────────────


async def get_post_engagement(platform: str, platform_post_id: str) -> dict[str, int]:
    """
    Fetch current engagement metrics for a published post.

    Returns dict with: likes, comments, shares
    """
    logger.info("get_post_engagement platform=%s id=%s", platform, platform_post_id)

    if platform == "reddit":
        return await _get_reddit_engagement(platform_post_id)
    if platform == "linkedin":
        return await _get_linkedin_engagement(platform_post_id)

    # X — not yet implemented
    return {"likes": 0, "comments": 0, "shares": 0}


async def _get_reddit_engagement(post_id: str) -> dict[str, int]:
    """Fetch score and comment count for a Reddit submission."""
    try:
        import asyncpraw  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("asyncpraw not installed — cannot fetch Reddit engagement")
        return {"likes": 0, "comments": 0, "shares": 0}

    if not all([settings.reddit_client_id, settings.reddit_client_secret]):
        return {"likes": 0, "comments": 0, "shares": 0}

    reddit = asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        username=settings.reddit_username or None,
        password=settings.reddit_password or None,
        user_agent=settings.reddit_user_agent,
    )

    try:
        submission = await reddit.submission(post_id)
        # Reddit doesn't expose share count publicly; upvote_ratio * score
        # gives a rough sense but we just report score + comments.
        return {
            "likes": submission.score,
            "comments": submission.num_comments,
            "shares": 0,  # not exposed by Reddit API
        }
    except Exception:
        logger.exception("Failed to fetch Reddit engagement for %s", post_id)
        return {"likes": 0, "comments": 0, "shares": 0}
    finally:
        await reddit.close()


async def _get_linkedin_engagement(post_id: str) -> dict[str, int]:
    """
    Fetch likes, comments, and shares for a LinkedIn post.

    Uses the LinkedIn socialMetadata endpoint to get aggregate counts.
    """
    if not settings.linkedin_access_token:
        return {"likes": 0, "comments": 0, "shares": 0}

    headers = _linkedin_headers()

    try:
        async with httpx.AsyncClient() as client:
            # The Social Metadata endpoint returns aggregate social action counts
            resp = await client.get(
                f"https://api.linkedin.com/rest/socialMetadata/{post_id}",
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning(
                    "LinkedIn engagement API returned %d for %s",
                    resp.status_code, post_id,
                )
                return {"likes": 0, "comments": 0, "shares": 0}

            data = resp.json()
            return {
                "likes": data.get("totalShareStatistics", {}).get("likeCount", 0),
                "comments": data.get("totalShareStatistics", {}).get("commentCount", 0),
                "shares": data.get("totalShareStatistics", {}).get("shareCount", 0),
            }
    except Exception:
        logger.exception("Failed to fetch LinkedIn engagement for %s", post_id)
        return {"likes": 0, "comments": 0, "shares": 0}


# ── DB helpers ───────────────────────────────────────────────────────────────


async def store_trend(trend: dict[str, Any]) -> dict[str, Any]:
    """Insert a trend into marketing_trends and return the stored row."""
    client = get_client()
    response = (
        client.table("marketing_trends")
        .insert({
            "platform": trend["platform"],
            "url": trend.get("url"),
            "author": trend.get("author"),
            "post_content": trend["content"],
            "topic": trend.get("topic", ""),
            "relevance_score": trend["relevance_score"],
            "relevance_reason": trend.get("relevance_reason", ""),
            "suggested_action": trend.get("suggested_action"),
        })
        .execute()
    )
    return response.data[0]


async def get_trend(trend_id: str) -> dict[str, Any] | None:
    """Fetch a single trend by ID."""
    client = get_client()
    response = (
        client.table("marketing_trends")
        .select("*")
        .eq("id", trend_id)
        .maybe_single()
        .execute()
    )
    return response.data


async def store_content(content: dict[str, Any]) -> dict[str, Any]:
    """Insert a draft into marketing_posts and return the stored row."""
    client = get_client()
    response = (
        client.table("marketing_posts")
        .insert({
            "platform": content["platform"],
            "content": content["content"],
            "content_type": content.get("content_type"),
            "topic": content.get("topic", ""),
            "trend_id": content.get("trend_id"),
            "status": "draft",
        })
        .execute()
    )
    return response.data[0]


async def update_content_status(
    content_id: str,
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    """Update the status and optional fields of a marketing_posts row."""
    client = get_client()
    payload: dict[str, Any] = {"status": status, **extra}
    response = (
        client.table("marketing_posts")
        .update(payload)
        .eq("id", content_id)
        .execute()
    )
    return response.data[0]


async def get_content(content_id: str) -> dict[str, Any] | None:
    """Fetch a single content row by ID."""
    client = get_client()
    response = (
        client.table("marketing_posts")
        .select("*")
        .eq("id", content_id)
        .maybe_single()
        .execute()
    )
    return response.data


async def get_recent_trends(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch recent trends ordered by creation time."""
    client = get_client()
    response = (
        client.table("marketing_trends")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


async def get_content_by_status(status: str, limit: int = 20) -> list[dict[str, Any]]:
    """Fetch marketing_posts filtered by status."""
    client = get_client()
    response = (
        client.table("marketing_posts")
        .select("*")
        .eq("status", status)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data
