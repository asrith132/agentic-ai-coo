"""
api/system/event_routes.py — GET /api/events + POST /api/events/emit

GET  /api/events         — List recent events (for dashboard event feed)
POST /api/events/emit    — Manually emit an event (debug / testing only)
"""

from fastapi import APIRouter, Query
from app.core.events import get_recent_events, emit_event
from app.schemas.events import Event, EventEmitRequest

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[Event])
async def list_events(limit: int = Query(default=100, le=500)):
    """Return the most recent events, newest first."""
    return await get_recent_events(limit=limit)


@router.post("/emit", response_model=Event)
async def emit_event_debug(body: EventEmitRequest):
    """
    Debug endpoint — emit an event as if an agent fired it.
    Useful for testing agent reactions without running the full agent.
    Remove or auth-gate this in production.
    """
    return await emit_event(
        source_agent=body.source_agent,
        event_type=body.event_type,
        payload=body.payload,
        summary=body.summary,
        priority=body.priority,
    )
