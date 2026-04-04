"""
scripts/test_cascade.py — Simulates a full event cascade for integration testing.

Emits a chain of realistic events and verifies they appear in the DB with
correct shape. Run this after seeding global context to confirm the event bus
is working end-to-end before wiring up real agents.

Usage:
  cd backend
  python ../scripts/test_cascade.py

Expected output:
  ✓ Emitted: dev.pr_merged
  ✓ Emitted: outreach.reply_received
  ✓ Emitted: research.competitor_found
  ✓ Cascade complete — 3 events in DB
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.core.events import emit_event, get_recent_events

CASCADE_EVENTS = [
    {
        "source_agent": "dev_activity",
        "event_type": "dev.pr_merged",
        "payload": {"pr_number": 42, "title": "Add user auth", "author": "alice"},
        "summary": "PR #42 'Add user auth' merged by alice",
        "priority": "medium",
    },
    {
        "source_agent": "outreach",
        "event_type": "outreach.reply_received",
        "payload": {"lead_email": "bob@example.com", "snippet": "Sounds interesting, let's chat"},
        "summary": "Bob from Example replied positively to outreach",
        "priority": "high",
    },
    {
        "source_agent": "research",
        "event_type": "research.competitor_found",
        "payload": {"name": "CompetitorCo", "website": "https://competitor.co", "relevance": 0.85},
        "summary": "New competitor CompetitorCo identified with 0.85 relevance score",
        "priority": "medium",
    },
]


async def run_cascade():
    emitted = []
    for evt in CASCADE_EVENTS:
        result = await emit_event(**evt)
        print(f"✓ Emitted: {evt['event_type']} (id={result.id})")
        emitted.append(result)

    # Verify all events exist in DB
    recent = await get_recent_events(limit=10)
    emitted_ids = {str(e.id) for e in emitted}
    found = [e for e in recent if str(e.id) in emitted_ids]

    assert len(found) == len(CASCADE_EVENTS), (
        f"Expected {len(CASCADE_EVENTS)} events, found {len(found)}"
    )
    print(f"✓ Cascade complete — {len(found)} events confirmed in DB")


if __name__ == "__main__":
    asyncio.run(run_cascade())
