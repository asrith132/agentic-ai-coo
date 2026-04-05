"""
schemas/notifications.py — Pydantic models for Notifications.
"""

from __future__ import annotations
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class Notification(BaseModel):
    """Full notification row as returned from the database."""
    id: UUID
    agent: str
    title: str
    body: str
    priority: str = "medium"     # low | medium | high | urgent
    read: bool = False
    created_at: datetime


class NotificationCreate(BaseModel):
    """Used internally — callers use notify() helper instead."""
    agent: str
    title: str
    body: str
    priority: str = "medium"
