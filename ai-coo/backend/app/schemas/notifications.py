"""
schemas/notifications.py — Pydantic models for Notifications.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class Notification(BaseModel):
    """Full notification row as stored in and returned from the DB."""
    id: Optional[str] = None
    agent: str
    title: str
    body: str
    priority: str = "medium"            # low | medium | high | urgent
    read: bool = False
    created_at: Optional[str] = None


class NotificationCreate(BaseModel):
    """Internal payload for inserting a notification. Use send_notification() instead."""
    agent: str
    title: str
    body: str
    priority: str = "medium"
