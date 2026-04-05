"""
schemas/triggers.py — Pydantic models for agent triggers.

Agents can be activated by three trigger types:
  1. UserTrigger    — explicit user action via the frontend (e.g. "Run outreach now")
  2. ScheduledTrigger — Celery Beat cron schedule (e.g. every 6 hours)
  3. EventTrigger   — fired when a specific event type appears on the bus

Trigger payloads are passed to BaseAgent.run(trigger) so agents know why
they were activated and can tailor their behavior accordingly.
"""

from __future__ import annotations
from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class UserTrigger(BaseModel):
    """Fired when a user manually runs an agent from the dashboard."""
    type: Literal["user"] = "user"
    agent: str
    params: dict[str, Any] = Field(default_factory=dict)
    initiated_at: datetime = Field(default_factory=datetime.utcnow)


class ScheduledTrigger(BaseModel):
    """Fired by Celery Beat on a configured cron schedule."""
    type: Literal["scheduled"] = "scheduled"
    agent: str
    schedule: str                    # Cron expression or human label (e.g. "every_6h")
    triggered_at: datetime = Field(default_factory=datetime.utcnow)


class EventTrigger(BaseModel):
    """
    Fired when an agent's Celery task detects a relevant unconsumed event.
    The triggering event is included so the agent can act on its payload.
    """
    type: Literal["event"] = "event"
    agent: str
    source_event_type: str
    source_event_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    triggered_at: datetime = Field(default_factory=datetime.utcnow)


# Union type for agent run() signatures
AgentTrigger = UserTrigger | ScheduledTrigger | EventTrigger
