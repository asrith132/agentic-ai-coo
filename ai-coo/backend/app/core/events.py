"""
core/events.py — Event Bus helpers.

Agents communicate exclusively through events. No direct agent-to-agent calls.

Flow:
  1. Agent A calls emit_event()   → row inserted into `events` table
  2. Supabase Realtime broadcasts the INSERT
  3. Agent B's Celery task calls  get_pending_events(agent_name, subscribed_types)
  4. Agent B processes the events and calls mark_event_consumed()

Priority: low | medium | high | urgent
"""

from __future__ import annotations
from typing import Any, List, Optional
from datetime import datetime, timezone

from app.db.supabase_client import get_client
from app.schemas.events import Event, EventCreate


def emit_event(
    source_agent: str,
    event_type: str,
    payload: dict[str, Any],
    summary: str,
    priority: str = "medium",
) -> Event:
    """
    Persist a new event to the event bus.

    Args:
        source_agent: Name of the emitting agent (e.g. "dev_activity")
        event_type:   Namespaced type (e.g. "dev.pr_merged")
        payload:      Structured data about the event
        summary:      Human-readable one-liner (shown in recent_events + notifications)
        priority:     low | medium | high | urgent

    Returns:
        The persisted Event object with id and timestamp populated.
    """
    client = get_client()
    data = EventCreate(
        source_agent=source_agent,
        event_type=event_type,
        payload=payload,
        summary=summary,
        priority=priority,
    )
    response = (
        client.table("events")
        .insert(data.model_dump())
        .execute()
    )
    return Event(**response.data[0])


def get_pending_events(
    agent_name: str,
    event_types: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Event]:
    """
    Return events that `agent_name` has not yet consumed.

    Args:
        agent_name:  The calling agent — events already in its consumed_by list are excluded.
        event_types: Optional allowlist of event_type strings to filter on.
                     If None, returns all unconsumed event types.
        limit:       Max events returned per call, ordered oldest-first.

    Returns:
        List of unconsumed Event objects.
    """
    client = get_client()

    query = (
        client.table("events")
        .select("*")
        # Postgres: NOT (consumed_by @> ARRAY[agent_name])
        .not_.contains("consumed_by", [agent_name])
        .order("timestamp", desc=False)
        .limit(limit)
    )

    if event_types:
        query = query.in_("event_type", event_types)

    response = query.execute()
    return [Event(**row) for row in response.data]


def mark_event_consumed(event_id: str, agent_name: str) -> None:
    """
    Append `agent_name` to the consumed_by array for an event.

    Idempotent — safe to call multiple times for the same agent.
    Called by agents after they have finished processing an event.
    """
    client = get_client()

    # Fetch current array to avoid duplicates
    response = (
        client.table("events")
        .select("consumed_by")
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return

    current: list[str] = response.data.get("consumed_by") or []
    if agent_name not in current:
        client.table("events").update(
            {"consumed_by": current + [agent_name]}
        ).eq("id", event_id).execute()


def get_all_events(limit: int = 50) -> List[Event]:
    """
    Return the most recent events, newest-first.
    Used by the dashboard event feed and debug tooling.
    """
    client = get_client()
    response = (
        client.table("events")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return [Event(**row) for row in response.data]
