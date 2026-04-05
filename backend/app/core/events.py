"""
core/events.py — Event Bus helpers.

Agents communicate with each other ONLY through events — there are no direct
agent-to-agent calls. This decouples agents completely and allows the system
to be audited, replayed, and extended without changing existing agents.

Flow:
  1. Agent A emits an event via `emit_event()`
  2. The event is persisted in the `events` table
  3. Supabase Realtime broadcasts the INSERT to all listeners
  4. Agent B's Celery task wakes up and calls `get_unconsumed_events()`
  5. Agent B processes relevant events and calls `mark_consumed()`

Priority levels: low | medium | high | urgent
"""

from __future__ import annotations
from typing import Any
from datetime import datetime, timezone
from app.db.supabase_client import get_client
from app.schemas.events import Event, EventCreate


async def emit_event(
    source_agent: str,
    event_type: str,
    payload: dict[str, Any],
    summary: str,
    priority: str = "medium",
) -> Event:
    """
    Persist a new event to the event bus.

    Args:
        source_agent: Name of the agent emitting the event (e.g. "dev_activity")
        event_type:   Namespaced type string (e.g. "dev.pr_merged", "outreach.reply_received")
        payload:      Arbitrary structured data relevant to the event
        summary:      Human-readable one-sentence description (shown in notifications)
        priority:     "low" | "medium" | "high" | "urgent"

    Returns:
        The persisted Event object (includes generated id and timestamp)
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


async def get_unconsumed_events(
    consumer_agent: str,
    event_types: list[str] | None = None,
    limit: int = 50,
) -> list[Event]:
    """
    Fetch events that `consumer_agent` has not yet consumed.

    Args:
        consumer_agent: The agent calling this — used to filter the consumed_by array
        event_types:    Optional allowlist of event_type strings to filter on
        limit:          Max events to return per poll (oldest-first)

    Returns:
        List of unconsumed Event objects, ordered by timestamp ascending
    """
    client = get_client()

    query = (
        client.table("events")
        .select("*")
        # Filter out rows where consumer_agent is already in consumed_by
        .not_.contains("consumed_by", [consumer_agent])
        .order("timestamp", desc=False)
        .limit(limit)
    )

    if event_types:
        query = query.in_("event_type", event_types)

    response = query.execute()
    return [Event(**row) for row in response.data]


async def mark_consumed(event_id: str, consumer_agent: str) -> None:
    """
    Append `consumer_agent` to the `consumed_by` array of an event.

    Safe to call multiple times — Postgres array append is idempotent when
    the value already exists (we use array_append logic via RPC if needed,
    but simple update works for now since agents don't race on the same row).
    """
    client = get_client()

    # Fetch current consumed_by list
    response = (
        client.table("events")
        .select("consumed_by")
        .eq("id", event_id)
        .single()
        .execute()
    )
    current: list[str] = response.data.get("consumed_by") or []

    if consumer_agent not in current:
        updated = current + [consumer_agent]
        client.table("events").update({"consumed_by": updated}).eq("id", event_id).execute()


async def get_recent_events(limit: int = 100) -> list[Event]:
    """Fetch the most recent events for display in the dashboard."""
    client = get_client()
    response = (
        client.table("events")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return [Event(**row) for row in response.data]
