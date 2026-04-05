"""
test_engagement.py — Test engagement tracking for published LinkedIn posts.

This is the last step of the marketing agent's lifecycle:
  Post is published → agent periodically checks engagement → spikes trigger events

Usage:
    python scripts/test_engagement.py
    python scripts/test_engagement.py <post_urn>   # check a specific post
"""

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import httpx

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID", "")
LINKEDIN_ORGANIZATION_ID = os.environ.get("LINKEDIN_ORGANIZATION_ID", "")
LINKEDIN_API_VERSION = "202504"

# The post we created during the LinkedIn posting test
DEFAULT_POST_URN = "urn:li:share:7446309762226552832"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def get_post_details(post_urn: str) -> dict | None:
    """Try to fetch the post itself (needs Community Mgmt API)."""
    encoded = quote(post_urn, safe="")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.linkedin.com/rest/posts/{encoded}",
            headers=_headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        return None


async def get_social_actions(post_urn: str) -> dict | None:
    """Fetch likes/comments/reposts counts via socialActions."""
    encoded = quote(post_urn, safe="")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.linkedin.com/rest/socialActions/{encoded}",
            headers=_headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        return None


async def get_social_metadata(post_urn: str) -> dict | None:
    """Fetch engagement metrics via socialMetadata endpoint."""
    encoded = quote(post_urn, safe="")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.linkedin.com/rest/socialMetadata/{encoded}",
            headers=_headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        return None


async def get_org_share_statistics() -> dict | None:
    """Fetch aggregate share statistics for the organization."""
    if not LINKEDIN_ORGANIZATION_ID:
        return None

    org_urn = f"urn:li:organization:{LINKEDIN_ORGANIZATION_ID}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.linkedin.com/rest/organizationalEntityShareStatistics",
            headers=_headers(),
            params={"q": "organizationalEntity", "organizationalEntity": org_urn},
        )
        if resp.status_code == 200:
            return resp.json()
        return None


async def get_follower_statistics() -> dict | None:
    """Fetch follower statistics for the organization."""
    if not LINKEDIN_ORGANIZATION_ID:
        return None

    org_urn = f"urn:li:organization:{LINKEDIN_ORGANIZATION_ID}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.linkedin.com/rest/organizationalEntityFollowerStatistics",
            headers=_headers(),
            params={"q": "organizationalEntity", "organizationalEntity": org_urn},
        )
        if resp.status_code == 200:
            return resp.json()
        return None


async def main():
    post_urn = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_POST_URN

    print("=" * 70)
    print("  MARKETING AGENT — ENGAGEMENT TRACKING")
    print("=" * 70)

    if not LINKEDIN_ACCESS_TOKEN:
        print("\nERROR: LINKEDIN_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    print(f"\n  Post URN: {post_urn}")
    print(f"  URL:      https://www.linkedin.com/feed/update/{post_urn}")

    # ── 1. Try to fetch post details ──────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  1. Fetching post details")
    print(f"{'─' * 70}")

    post = await get_post_details(post_urn)
    if post:
        print(f"  Author:      {post.get('author', '?')}")
        print(f"  Text:        {post.get('commentary', '?')[:100]}...")
        print(f"  State:       {post.get('lifecycleState', '?')}")
        print(f"  Visibility:  {post.get('visibility', '?')}")
    else:
        print("  Could not fetch post details (needs Community Mgmt API).")
        print("  This is expected — we can still check engagement via other endpoints.")

    # ── 2. Social Actions (likes, comments, shares) ───────────────────────
    print(f"\n{'─' * 70}")
    print("  2. Checking social actions (likes/comments/shares)")
    print(f"{'─' * 70}")

    actions = await get_social_actions(post_urn)
    if actions:
        likes = actions.get("likesSummary", {}).get("totalLikes", 0)
        comments = actions.get("commentsSummary", {}).get("totalFirstLevelComments", 0)
        print(f"  Likes:    {likes}")
        print(f"  Comments: {comments}")
        print(f"  Full data: {actions}")
    else:
        print("  socialActions endpoint not accessible (needs Community Mgmt API).")

    # ── 3. Social Metadata ────────────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  3. Checking social metadata")
    print(f"{'─' * 70}")

    metadata = await get_social_metadata(post_urn)
    if metadata:
        stats = metadata.get("totalShareStatistics", {})
        print(f"  Likes:       {stats.get('likeCount', 0)}")
        print(f"  Comments:    {stats.get('commentCount', 0)}")
        print(f"  Shares:      {stats.get('shareCount', 0)}")
        print(f"  Impressions: {stats.get('impressionCount', 0)}")
        print(f"  Clicks:      {stats.get('clickCount', 0)}")
        print(f"  Engagement:  {stats.get('engagement', 0)}")
    else:
        print("  socialMetadata endpoint not accessible.")

    # ── 4. Organization-level stats ───────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  4. Organization-level statistics")
    print(f"{'─' * 70}")

    org_stats = await get_org_share_statistics()
    if org_stats:
        elements = org_stats.get("elements", [])
        if elements:
            stats = elements[0].get("totalShareStatistics", {})
            print(f"  Org: {elements[0].get('organizationalEntity', '?')}")
            print(f"  Total likes across all posts:    {stats.get('likeCount', 0)}")
            print(f"  Total comments across all posts: {stats.get('commentCount', 0)}")
            print(f"  Total shares across all posts:   {stats.get('shareCount', 0)}")
            print(f"  Total impressions:               {stats.get('impressionCount', 0)}")
            print(f"  Total clicks:                    {stats.get('clickCount', 0)}")
            print(f"  Engagement rate:                 {stats.get('engagement', 0)}")
        else:
            print("  No stats available yet (org may be too new).")
    else:
        print("  Could not fetch org stats.")

    follower_stats = await get_follower_statistics()
    if follower_stats:
        elements = follower_stats.get("elements", [])
        if elements:
            print(f"  Follower data available: {list(elements[0].keys())}")
    else:
        print("  Could not fetch follower stats.")

    # ── 5. How this works in the agent ────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  HOW ENGAGEMENT TRACKING WORKS IN THE AGENT")
    print(f"{'─' * 70}")
    print(f"""
  After the agent publishes a post, it stores the platform_post_id in the
  marketing_posts table. On subsequent runs, it can check engagement:

  Code path (tools.py):
    get_post_engagement("linkedin", "{post_urn}")
      → _get_linkedin_engagement("{post_urn}")
        → GET /rest/socialMetadata/{post_urn}
        → returns {{"likes": N, "comments": N, "shares": N}}

  The agent uses engagement data to:
    1. Track post performance over time
    2. Detect engagement spikes (sudden jump in likes/comments)
    3. Emit 'marketing.engagement_spike' events when thresholds are hit
    4. Alert you via notifications so you can join hot conversations

  This same function works for Reddit posts too:
    get_post_engagement("reddit", "post_id_123")
      → _get_reddit_engagement("post_id_123")
        → Fetches submission.score + submission.num_comments via asyncpraw
""")


if __name__ == "__main__":
    asyncio.run(main())
