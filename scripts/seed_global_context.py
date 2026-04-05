"""
scripts/seed_global_context.py — Seeds the initial Global Context row.

Run once after applying migrations:
  cd backend
  python ../scripts/seed_global_context.py

Edit the INITIAL_CONTEXT dict below to reflect your actual company before running.
"""

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.db.supabase_client import get_client

INITIAL_CONTEXT = {
    "company_profile": {
        "name": "Acme AI",
        "website": "https://acme.ai",
        "industry": "B2B SaaS",
        "stage": "seed",
        "founded_year": 2024,
        "team_size": 4,
        "description": "AI-powered operations platform for early-stage startups",
    },
    "target_customer": {
        "persona": "Technical co-founder at a seed-stage B2B SaaS startup",
        "pain_points": [
            "Wearing too many hats",
            "No bandwidth for proactive outreach",
            "Losing track of engineering velocity",
        ],
        "channels": ["LinkedIn", "X (Twitter)", "Hacker News"],
        "company_size": "1-10 employees",
        "geography": "US, UK, Canada",
    },
    "business_state": {
        "mrr": 0,
        "runway_months": 18,
        "active_users": 0,
        "open_issues": 0,
        "last_deploy": None,
        "current_sprint_goal": "Launch MVP",
    },
    "brand_voice": {
        "tone": "Direct, pragmatic, and founder-empathetic. No fluff.",
        "values": ["Clarity", "Speed", "Leverage"],
        "avoid": ["Corporate speak", "Excessive hedging", "Buzzwords"],
        "example_copy": "Your AI COO runs your ops so you can build the product.",
    },
    "competitive_landscape": {
        "competitors": [],
        "positioning": "The only AI system designed specifically for solo technical founders",
        "differentiators": [
            "Multi-agent coordination",
            "Event-driven architecture",
            "Human-in-the-loop approval gates",
        ],
    },
    "recent_events": [],
    "version": 1,
}


def seed():
    client = get_client()

    # Check if already seeded
    existing = client.table("global_context").select("id").limit(1).execute()
    if existing.data:
        print(f"Global context already seeded (id={existing.data[0]['id']}). Skipping.")
        return

    response = client.table("global_context").insert(INITIAL_CONTEXT).execute()
    print(f"✓ Global context seeded with id={response.data[0]['id']}")


if __name__ == "__main__":
    seed()
