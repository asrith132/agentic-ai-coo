"""
schemas/events.py — Pydantic models for Event Bus.

Event type naming convention: "<agent>.<past_tense_action>"
Examples:
  dev.pr_merged           dev.build_failed          dev.issue_opened
  outreach.email_sent     outreach.reply_received   outreach.meeting_booked
  marketing.post_published  marketing.engagement_spike
  finance.mrr_changed     finance.runway_updated    finance.expense_spike
  pm.sprint_started       pm.blocker_detected       pm.sprint_completed
  research.competitor_found  research.trend_found   research.lead_found
  legal.contract_flagged  legal.compliance_alert
"""

from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class Event(BaseModel):
    """Full event row as stored in and returned from the DB."""
    id: Optional[str] = None
    timestamp: Optional[str] = None
    source_agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    priority: str = "medium"            # low | medium | high | urgent
    consumed_by: List[str] = Field(default_factory=list)


class EventCreate(BaseModel):
    """Internal payload for inserting a new event. Used by emit_event()."""
    source_agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    priority: str = "medium"


class EventEmitRequest(BaseModel):
    """Request body for POST /api/events/emit (debug endpoint)."""
    source_agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str
    priority: str = "medium"
