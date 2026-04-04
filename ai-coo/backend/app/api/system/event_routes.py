"""
api/system/event_routes.py

Routes:
  GET  /api/events                    — Recent events (filterable)
  GET  /api/events/pending/{agent}    — Unconsumed events for a specific agent
  POST /api/events/emit               — [DEV ONLY] Manually emit an event

────────────────────────────────────────────────────────────────────────────────
NOTE on POST /api/events/emit
────────────────────────────────────────────────────────────────────────────────
This endpoint exists for DEVELOPMENT AND TESTING ONLY.

During parallel development, team members can use it to simulate upstream agent
outputs without needing the full agent pipeline running. For example, the
Outreach agent developer can emit a "research.lead_found" event to test that
their agent's event consumption logic works before the Research agent is built.

DO NOT expose this endpoint in production without authentication.
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException

from app.core.events import emit_event, get_all_events, get_pending_events
from app.agents.registry import list_agents
from app.schemas.events import Event, EventCreate

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get(
    "",
    response_model=list[Event],
    summary="List recent events",
)
def list_events(
    limit: int = Query(default=50, ge=1, le=500, description="Max events to return"),
    agent: str | None = Query(default=None, description="Filter by source_agent name"),
    type: str | None = Query(default=None, description="Filter by event_type (exact match)"),
):
    """
    Return recent events from the event bus, newest-first.

    Optional filters:
    - `agent`: return only events emitted by this agent (e.g. "dev_activity")
    - `type`:  return only events of this type (e.g. "dev.pr_merged")
    """
    events = get_all_events(limit=limit)

    if agent:
        events = [e for e in events if e.source_agent == agent]
    if type:
        events = [e for e in events if e.event_type == type]

    return events


@router.get(
    "/pending/{agent_name}",
    response_model=list[Event],
    summary="Get unconsumed events for an agent",
)
def pending_events_for_agent(
    agent_name: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Return events that `agent_name` has not yet consumed.

    Useful for debugging agent event queues and verifying that mark_consumed
    calls are working correctly. In production, agents poll this via the Celery
    task layer — this endpoint is primarily for visibility and testing.
    """
    known = list_agents()
    if agent_name not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent_name}'. Known agents: {known}",
        )
    return get_pending_events(agent_name=agent_name, limit=limit)


@router.post(
    "/emit",
    response_model=Event,
    summary="[DEV ONLY] Manually emit an event",
)
def emit_event_debug(body: EventCreate):
    """
    **Development / testing endpoint only.**

    Emit an event as if an agent fired it. Useful for testing a downstream
    agent's reaction without needing the upstream agent to be fully built.

    Example — test that OutreachAgent reacts to a new lead:
    ```json
    {
      "source_agent": "research",
      "event_type": "research.lead_found",
      "payload": {"email": "founder@example.com", "company": "Acme"},
      "summary": "New lead: founder@example.com at Acme",
      "priority": "medium"
    }
    ```
    """
    return emit_event(
        source_agent=body.source_agent,
        event_type=body.event_type,
        payload=body.payload,
        summary=body.summary,
        priority=body.priority,
    )
