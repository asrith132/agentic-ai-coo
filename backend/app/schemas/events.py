"""
schemas/events.py — Pydantic models for Event Bus.

Event type naming convention: "<agent>.<action>"
Examples:
  - dev.pr_merged
  - dev.build_failed
  - outreach.reply_received
  - outreach.email_sent
  - marketing.post_published
  - finance.runway_updated
  - research.competitor_found
  - pm.sprint_started
  - legal.contract_flagged
"""

from __future__ import annotations
from typing import Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

PRIORITY_VALUES = ("low", "medium", "high", "urgent")


class EventCreate(BaseModel):
    """Payload for creating a new event (used internally by emit_event())."""
    source_agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    priority: str = "medium"


class Event(BaseModel):
    """Full event row as returned from the database."""
    id: UUID
    timestamp: datetime
    source_agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    priority: str = "medium"
    consumed_by: list[str] = Field(default_factory=list)


class EventEmitRequest(BaseModel):
    """Request body for POST /api/events/emit (debug endpoint)."""
    source_agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    priority: str = "medium"
