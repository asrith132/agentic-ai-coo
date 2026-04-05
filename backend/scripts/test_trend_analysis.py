"""
test_trend_analysis.py — Test the trend scanning & analysis pipeline.

Demonstrates the full marketing agent pipeline:
  1. Fetches posts from LinkedIn (or uses realistic sample data)
  2. Scores each post for relevance (keyword matching or Claude LLM)
  3. Classifies: DISCARD / STORE / NOTIFY based on score thresholds
  4. Shows what the agent would do with each post in production

Usage:
    python scripts/test_trend_analysis.py                # keyword scoring + sample posts
    python scripts/test_trend_analysis.py --use-llm      # Claude LLM scoring (needs ANTHROPIC_API_KEY)
    python scripts/test_trend_analysis.py --live          # fetch real LinkedIn posts (needs Community Mgmt API)
"""

import asyncio
import json
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID", "")
LINKEDIN_ORGANIZATION_ID = os.environ.get("LINKEDIN_ORGANIZATION_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LINKEDIN_API_VERSION = "202504"

USE_LLM = "--use-llm" in sys.argv
LIVE_LINKEDIN = "--live" in sys.argv

# Thresholds (same as agent.py)
RELEVANCE_STORE_THRESHOLD = 60
RELEVANCE_NOTIFY_THRESHOLD = 80

# ---------------------------------------------------------------------------
# Company context (same structure as global_context table in Supabase)
# Edit these to match your actual company
# ---------------------------------------------------------------------------

COMPANY_CONTEXT = {
    "company_profile": {
        "name": "TestCo",
        "description": "AI-powered code review tool that helps developers ship faster",
        "industry": "developer tools",
        "stage": "seed",
    },
    "target_customer": {
        "persona": "Senior backend engineer at a startup",
        "pain_points": [
            "slow code reviews",
            "context switching",
            "CI flakiness",
            "developer productivity",
        ],
        "channels": ["reddit", "linkedin"],
    },
    "brand_voice": {
        "tone": "friendly, technical, no-BS",
    },
}


# ---------------------------------------------------------------------------
# Sample posts — realistic LinkedIn/Reddit content for demo
# These simulate what search_reddit() and search_linkedin() return
# ---------------------------------------------------------------------------

SAMPLE_POSTS = [
    {
        "platform": "linkedin",
        "url": "https://linkedin.com/feed/update/urn:li:share:example001",
        "author": "Sarah Chen, VP Engineering at ScaleUp",
        "content": (
            "Hot take: code reviews are the biggest bottleneck in modern software teams. "
            "We spend more time reviewing than writing code. AI-powered review tools are "
            "the future — they give reviewers a head start so they can focus on architecture "
            "instead of style nits. What's your team's experience?"
        ),
    },
    {
        "platform": "reddit",
        "url": "https://reddit.com/r/programming/comments/abc123",
        "author": "dev_user_42",
        "subreddit": "r/programming",
        "content": (
            "Our team switched to AI-assisted code review and cut PR turnaround "
            "from 2 days to 4 hours. The biggest win was reducing context switching — "
            "reviewers get an AI summary before diving in. Anyone else using these tools?"
        ),
    },
    {
        "platform": "reddit",
        "url": "https://reddit.com/r/devops/comments/def456",
        "author": "startup_cto",
        "subreddit": "r/devops",
        "content": (
            "CI has been flaky all week. Tests pass locally but fail in GitHub Actions "
            "randomly. We've tried retry logic but it's masking real issues. "
            "Any recommendations for making CI more reliable?"
        ),
    },
    {
        "platform": "linkedin",
        "url": "https://linkedin.com/feed/update/urn:li:share:example002",
        "author": "Alex Rivera, Engineering Manager",
        "content": (
            "Unpopular opinion: most developer productivity tools create more "
            "context switching, not less. We tried 5 different tools last quarter "
            "and ended up going back to basics — fewer meetings, longer focus blocks, "
            "and async code reviews. Productivity up 30%."
        ),
    },
    {
        "platform": "reddit",
        "url": "https://reddit.com/r/startups/comments/ghi789",
        "author": "founder_mode",
        "subreddit": "r/startups",
        "content": (
            "We just raised our seed round and looking for developer productivity tools. "
            "Our eng team of 8 spends too much time on code reviews and deployments. "
            "Any recs for tools that can cut the review cycle down?"
        ),
    },
    {
        "platform": "linkedin",
        "url": "https://linkedin.com/feed/update/urn:li:share:example003",
        "author": "Marcus Lee, Developer Advocate",
        "content": (
            "Just shipped a blog post about our migration from monolith to microservices. "
            "The hardest part wasn't the architecture — it was getting the team to agree "
            "on API boundaries. Would love your feedback!"
        ),
    },
    {
        "platform": "reddit",
        "url": "https://reddit.com/r/cooking/comments/jkl012",
        "author": "home_chef_99",
        "subreddit": "r/cooking",
        "content": (
            "Just made the most amazing sourdough bread! The trick is a 72-hour "
            "cold ferment in the fridge. The crumb structure was absolutely perfect."
        ),
    },
    {
        "platform": "reddit",
        "url": "https://reddit.com/r/gaming/comments/mno345",
        "author": "gamer_dude",
        "subreddit": "r/gaming",
        "content": (
            "The new Zelda DLC is incredible. 40 hours of new content and the "
            "level design is the best Nintendo has ever done."
        ),
    },
]


# ---------------------------------------------------------------------------
# LinkedIn fetching (live mode — needs Community Management API product)
# ---------------------------------------------------------------------------

async def fetch_linkedin_posts_live(count: int = 10) -> list[dict]:
    """
    Fetch real LinkedIn posts via the REST API.

    Requires the 'Community Management API' product on your LinkedIn app
    which unlocks GET /rest/posts. Without it, you'll get 403.
    """
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Try org posts first, then personal
    authors = []
    if LINKEDIN_ORGANIZATION_ID:
        authors.append(f"urn:li:organization:{LINKEDIN_ORGANIZATION_ID}")
    if LINKEDIN_PERSON_ID:
        authors.append(f"urn:li:person:{LINKEDIN_PERSON_ID}")

    all_posts = []
    async with httpx.AsyncClient(timeout=30) as client:
        for author_urn in authors:
            resp = await client.get(
                "https://api.linkedin.com/rest/posts",
                headers=headers,
                params={"q": "author", "author": author_urn, "count": str(count), "sortBy": "LAST_MODIFIED"},
            )
            if resp.status_code == 200:
                for el in resp.json().get("elements", []):
                    content = el.get("commentary", "")
                    if not content:
                        continue
                    all_posts.append({
                        "platform": "linkedin",
                        "url": f"https://www.linkedin.com/feed/update/{el.get('id', '')}",
                        "author": el.get("author", author_urn),
                        "content": content,
                        "post_id": el.get("id", ""),
                    })
            else:
                print(f"    {author_urn}: {resp.status_code} — {resp.text[:150]}")

    return all_posts


async def fetch_linkedin_org_info() -> dict | None:
    """Fetch organization info to verify LinkedIn connectivity."""
    if not LINKEDIN_ORGANIZATION_ID or not LINKEDIN_ACCESS_TOKEN:
        return None

    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.linkedin.com/rest/organizations/{LINKEDIN_ORGANIZATION_ID}",
            headers=headers,
        )
        if resp.status_code == 200:
            return resp.json()

        # Also grab aggregate stats
        stats_resp = await client.get(
            "https://api.linkedin.com/rest/organizationalEntityShareStatistics",
            headers=headers,
            params={
                "q": "organizationalEntity",
                "organizationalEntity": f"urn:li:organization:{LINKEDIN_ORGANIZATION_ID}",
            },
        )
        if stats_resp.status_code == 200:
            return stats_resp.json()

    return None


# ---------------------------------------------------------------------------
# Scoring: keyword-based (default) or LLM-based (with --use-llm)
# ---------------------------------------------------------------------------

def score_post_keywords(
    post: dict,
    pain_points: list[str],
    company_name: str,
) -> dict:
    """
    Score a post using keyword matching.

    This is a simplified version of what the agent does with Claude.
    In production, Claude reads the full post and provides nuanced scoring
    and reasoning. This keyword-based approach gives a fast approximation.
    """
    content_lower = post.get("content", "").lower()

    # Check pain point matches
    pain_matches = [pp for pp in pain_points if pp.lower() in content_lower]

    # Check product-related keywords
    product_keywords = [
        "code review", "pull request", "PR turnaround", "reviewer",
        "AI-assisted", "AI-powered", "developer tool", "productivity tool",
        "developer productivity", "ship faster", "deploy",
    ]
    product_matches = [kw for kw in product_keywords if kw.lower() in content_lower]

    # Check company name
    company_match = company_name.lower() in content_lower

    # Calculate score
    score = 0
    score += len(pain_matches) * 25       # each pain point match = 25 pts
    score += len(product_matches) * 15    # each product keyword = 15 pts
    score += 20 if company_match else 0   # company name mention = 20 pts
    score = min(score, 100)               # cap at 100

    # Determine suggested action
    if score >= 80:
        action = "reply"
    elif score >= 60:
        action = "new_post"
    else:
        action = "none"

    all_matches = pain_matches + product_matches
    topic = all_matches[0] if all_matches else "unrelated"

    reason = (
        f"Matched {len(pain_matches)} pain points "
        f"({', '.join(pain_matches) if pain_matches else 'none'}) "
        f"and {len(product_matches)} product keywords "
        f"({', '.join(product_matches) if product_matches else 'none'})"
    )

    return {
        "relevance_score": score,
        "reason": reason,
        "topic": topic,
        "suggested_action": action,
    }


async def score_post_llm(
    post: dict,
    product_description: str,
    pain_points: list[str],
) -> dict:
    """Score a post using Claude LLM (same prompt as agent.py:_score_relevance)."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    system = (
        "You are a marketing analyst. Evaluate social media posts for relevance "
        "to our product and audience. Respond ONLY with valid JSON."
    )
    prompt = (
        f"Our product is {product_description}. "
        f"Our target customer's pain points are: {', '.join(pain_points)}.\n\n"
        f"Score this post's relevance (0-100) and explain why:\n"
        f"Post: {post.get('content', '')}\n\n"
        f"Should we engage? If yes, what type of engagement "
        f"(reply, quote, new_post referencing this)?\n\n"
        f"Respond as JSON: "
        f'{{"relevance_score": <int>, "reason": "<str>", '
        f'"topic": "<short topic>", "suggested_action": "<reply|quote|new_post|none>"}}'
    )

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return json.loads(response.content[0].text)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(posts: list[dict]) -> list[dict]:
    """Run the full scoring + classification pipeline."""
    company = COMPANY_CONTEXT["company_profile"]
    target = COMPANY_CONTEXT["target_customer"]
    pain_points = target["pain_points"]
    company_name = company["name"]
    product_description = company["description"]

    scorer = "Claude LLM" if USE_LLM else "keyword matching"
    print(f"  Scoring method: {scorer}")
    if not USE_LLM:
        print(f"  (add --use-llm for smarter Claude-powered scoring)")

    analyzed = []
    for i, post in enumerate(posts):
        platform_tag = post["platform"].upper()
        source = post.get("subreddit", post.get("author", ""))[:40]
        print(f"\n  [{i+1}/{len(posts)}] {platform_tag} | {source}")
        content_preview = post["content"].replace("\n", " ")[:100]
        print(f'    "{content_preview}..."')

        try:
            if USE_LLM:
                score_data = await score_post_llm(post, product_description, pain_points)
            else:
                score_data = score_post_keywords(post, pain_points, company_name)
        except Exception as e:
            print(f"    ERROR scoring: {e}")
            continue

        score = score_data.get("relevance_score", 0)
        reason = score_data.get("reason", "")
        topic = score_data.get("topic", "")
        action = score_data.get("suggested_action", "none")

        # Classify using same thresholds as agent.py
        if score >= RELEVANCE_NOTIFY_THRESHOLD:
            label = "*** NOTIFY + STORE"
            priority = "HIGH" if score > 90 else "MEDIUM"
        elif score >= RELEVANCE_STORE_THRESHOLD:
            label = " *  STORE (silent)"
            priority = "LOW"
        else:
            label = "    DISCARD"
            priority = "-"

        result = {
            **post,
            "score": score,
            "reason": reason,
            "topic": topic,
            "suggested_action": action,
            "label": label,
            "priority": priority,
        }
        analyzed.append(result)

        print(f"    {label}  Score: {score}/100")
        print(f"    Topic: {topic}  |  Action: {action}")
        print(f"    Why: {reason[:200]}")

    return analyzed


async def main():
    print("=" * 70)
    print("  MARKETING AGENT — TREND SCANNING & ANALYSIS PIPELINE")
    print("=" * 70)

    if USE_LLM and not ANTHROPIC_API_KEY:
        print("\nERROR: --use-llm requires ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    company = COMPANY_CONTEXT["company_profile"]
    target = COMPANY_CONTEXT["target_customer"]

    print(f"\n  Company:     {company['name']}")
    print(f"  Product:     {company['description']}")
    print(f"  Pain points: {target['pain_points']}")
    print(f"  Platforms:   {target['channels']}")

    # ── Step 0: Verify LinkedIn connectivity ──────────────────────────────
    if LINKEDIN_ACCESS_TOKEN and LINKEDIN_ORGANIZATION_ID:
        print(f"\n{'─' * 70}")
        print("  STEP 0: Verifying LinkedIn connectivity")
        print(f"{'─' * 70}")
        org_info = await fetch_linkedin_org_info()
        if org_info:
            org_name = org_info.get("localizedName", org_info.get("name", "?"))
            print(f"\n  Connected to LinkedIn org: {org_name} (ID: {LINKEDIN_ORGANIZATION_ID})")
            print(f"  Token is valid, API access confirmed.")
        else:
            print(f"\n  WARNING: Could not fetch org info. Token may be expired.")

    # ── Step 1: Collect posts ─────────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  STEP 1: Collecting posts to analyze")
    print(f"{'─' * 70}")

    posts = []

    if LIVE_LINKEDIN:
        print("\n  --live mode: Fetching real posts from LinkedIn API...")
        live_posts = await fetch_linkedin_posts_live(count=10)
        if live_posts:
            posts = live_posts
            print(f"  Fetched {len(posts)} real LinkedIn posts.")
        else:
            print("  No posts returned. Your app may need the 'Community Management API'")
            print("  product approved. Falling back to sample posts.")

    if not posts:
        posts = SAMPLE_POSTS
        print(f"\n  Using {len(posts)} sample posts (simulating Reddit + LinkedIn search results)")
        print(f"  These represent what the agent finds when scanning platforms.\n")
        if not LIVE_LINKEDIN:
            print(f"  TIP: Add --live to fetch real LinkedIn posts (needs Community Mgmt API)")

    print()
    for i, p in enumerate(posts):
        tag = p["platform"].upper().ljust(8)
        source = p.get("subreddit", p.get("author", ""))[:35]
        preview = p["content"].replace("\n", " ")[:55]
        print(f"    {i+1}. [{tag}] {source}: \"{preview}...\"")

    # ── Step 2: Score & classify ──────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  STEP 2: Scoring each post for relevance")
    print(f"{'─' * 70}")

    analyzed = await run_pipeline(posts)

    # ── Step 3: Summary ───────────────────────────────────────────────────
    stored = [p for p in analyzed if p["score"] >= RELEVANCE_STORE_THRESHOLD]
    notified = [p for p in analyzed if p["score"] >= RELEVANCE_NOTIFY_THRESHOLD]
    discarded = [p for p in analyzed if p["score"] < RELEVANCE_STORE_THRESHOLD]

    print(f"\n{'=' * 70}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 70}")

    print(f"\n  Total posts scanned:       {len(analyzed)}")
    print(f"  NOTIFY + STORE (>=80):     {len(notified)}  — triggers event + push notification")
    print(f"  STORE silently (60-79):    {len(stored) - len(notified)}  — saved for later review")
    print(f"  DISCARDED (<60):           {len(discarded)}  — irrelevant, thrown away")

    if notified:
        print(f"\n  HIGH-RELEVANCE posts (would trigger notifications):")
        for p in notified:
            print(f"    [{p['score']}/100] {p['platform']} — \"{p['topic']}\"")
            print(f"             Action: {p['suggested_action']}  |  {p['url'][:60]}")

    if len(stored) > len(notified):
        print(f"\n  MEDIUM-RELEVANCE posts (stored for review):")
        for p in stored:
            if p["score"] < RELEVANCE_NOTIFY_THRESHOLD:
                print(f"    [{p['score']}/100] {p['platform']} — \"{p['topic']}\"")

    if discarded:
        print(f"\n  DISCARDED posts (irrelevant):")
        for p in discarded:
            preview = p["content"].replace("\n", " ")[:55]
            print(f"    [{p['score']}/100] {p['platform']} — \"{preview}...\"")

    # ── Step 4: What happens next ─────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  WHAT HAPPENS NEXT IN PRODUCTION")
    print(f"{'─' * 70}")
    print("""
  The marketing agent runs this pipeline every 30 minutes via Celery:

  1. SCAN:  search_all_platforms() fetches posts from Reddit, LinkedIn, X
            using your pain points as search keywords

  2. SCORE: Each post is sent to Claude with this prompt:
            "Our product is {description}. Score this post's relevance 0-100.
             Should we engage? What type: reply, quote, or new_post?"

  3. CLASSIFY by score thresholds:
     - Score >= 80 → STORE in DB + emit event + send notification
     - Score 60-79 → STORE in DB silently (browse via API)
     - Score < 60  → DISCARD

  4. DRAFT: For high-relevance posts, you trigger content drafting:
     POST /api/marketing/draft
     {"content_type": "reply", "platform": "linkedin", "trend_id": "<id>"}
     → Claude writes a response in your brand voice
     → Creates an approval request (human-in-the-loop)

  5. PUBLISH: After you approve, the agent posts to the platform:
     POST /api/marketing/publish {"content_id": "<id>"}
     → Calls post_to_linkedin() or post_to_reddit()
     → Updates DB with published URL
     → Emits marketing.content_published event""")

    # ── Bonus: test the posting ───────────────────────────────────────────
    if LINKEDIN_ACCESS_TOKEN and notified:
        print(f"\n{'─' * 70}")
        print("  BONUS: Draft a response for the top trend")
        print(f"{'─' * 70}")
        top = notified[0]
        sample_draft = (
            f"Interesting discussion about {top['topic']}. "
            f"This is exactly what we're solving at {company['name']} — "
            f"{company['description']}. "
            f"Would love to hear how other teams are tackling this. "
            f"#devtools #buildinpublic"
        )
        print(f"\n  Top trend: [{top['score']}/100] \"{top['topic']}\"")
        print(f"  Platform:  {top['platform']}")
        print(f"  Action:    {top['suggested_action']}")
        print(f"\n  Sample draft (what Claude would generate):")
        print(f'  "{sample_draft}"')
        print(f"\n  To actually post this to LinkedIn:")
        print(f"    python scripts/test_linkedin_post.py")


if __name__ == "__main__":
    asyncio.run(main())
