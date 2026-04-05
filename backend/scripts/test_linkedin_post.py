"""
test_linkedin_post.py — Standalone script to test LinkedIn posting.

Usage:
    python scripts/test_linkedin_post.py

This calls the LinkedIn REST API directly (same code path as the marketing
agent's post_to_linkedin function) so you can verify credentials work
before running the full agent.

Set these env vars (or put them in backend/.env):
    LINKEDIN_ACCESS_TOKEN=<your bearer token>
    LINKEDIN_PERSON_ID=urn:li:person:<your member id>
"""

import asyncio
import httpx
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env file automatically (so you don't need to export vars manually)
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    print(f"Loading credentials from {_env_path}")
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
else:
    print(f"No .env file found at {_env_path} — using environment variables only")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID", "")
LINKEDIN_API_VERSION = "202504"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def verify_profile() -> dict:
    """Step 1: Verify the token works by fetching your profile."""
    print("\n[1/3] Verifying LinkedIn access token...")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        )
        if resp.status_code != 200:
            print(f"  FAILED — status {resp.status_code}")
            print(f"  Response: {resp.text[:500]}")
            sys.exit(1)

        data = resp.json()
        print(f"  OK — Logged in as: {data.get('name')} ({data.get('email')})")
        print(f"  Member ID (sub): {data.get('sub')}")
        return data


async def post_to_linkedin(text: str) -> dict:
    """Step 2: Create a text post on LinkedIn."""
    print(f"\n[2/3] Posting to LinkedIn as {PERSON_ID}...")
    print(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")

    payload = {
        "author": PERSON_ID,
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
            headers=_headers(),
            json=payload,
        )

        print(f"  Status: {resp.status_code}")

        if resp.status_code == 201:
            post_id = resp.headers.get("x-restli-id", "unknown")
            post_url = f"https://www.linkedin.com/feed/update/{post_id}"
            print(f"  SUCCESS!")
            print(f"  Post ID: {post_id}")
            print(f"  URL: {post_url}")
            return {"post_id": post_id, "url": post_url}
        else:
            print(f"  FAILED")
            print(f"  Response: {resp.text[:500]}")
            return {"error": resp.text, "status": resp.status_code}


async def check_engagement(post_id: str) -> dict:
    """Step 3: Fetch engagement metrics for the post we just created."""
    print(f"\n[3/3] Checking engagement for {post_id}...")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.linkedin.com/rest/socialMetadata/{post_id}",
            headers=_headers(),
        )

        if resp.status_code == 200:
            data = resp.json()
            stats = data.get("totalShareStatistics", {})
            print(f"  Likes:    {stats.get('likeCount', 0)}")
            print(f"  Comments: {stats.get('commentCount', 0)}")
            print(f"  Shares:   {stats.get('shareCount', 0)}")
            return stats
        else:
            print(f"  Engagement check returned {resp.status_code} (this is normal for brand new posts)")
            return {}


async def main():
    # Validate credentials exist
    if not ACCESS_TOKEN:
        print("ERROR: LINKEDIN_ACCESS_TOKEN is not set.")
        print("Set it via:  export LINKEDIN_ACCESS_TOKEN='your-token-here'")
        sys.exit(1)

    if not PERSON_ID:
        print("ERROR: LINKEDIN_PERSON_ID is not set.")
        print("Set it via:  export LINKEDIN_PERSON_ID='urn:li:person:_j7TIzCzIn'")
        sys.exit(1)

    # Step 1: Verify profile
    await verify_profile()

    # Step 2: Post
    test_text = (
        "Testing the AI COO marketing agent's LinkedIn integration. "
        "This is an automated test post — feel free to ignore! "
        "#buildinpublic #AI #startups"
    )

    # Ask for confirmation before posting
    print(f"\nAbout to post this text to LinkedIn:\n")
    print(f'  "{test_text}"')
    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    result = await post_to_linkedin(test_text)

    # Step 3: Check engagement (will be 0 for a new post)
    if "post_id" in result:
        await check_engagement(result["post_id"])

    print("\n--- Done! ---")
    if "url" in result:
        print(f"View your post at: {result['url']}")


if __name__ == "__main__":
    asyncio.run(main())
