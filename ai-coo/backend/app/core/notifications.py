"""
core/notifications.py — Notification + push helpers.

Two delivery channels:
  1. In-app: row inserted into `notifications` table, polled by frontend
  2. SMS push via Twilio: triggered automatically for high/urgent priority

Agents call send_notification() — never insert into the table directly.
"""

from __future__ import annotations
from typing import List
import logging

from app.db.supabase_client import get_client
from app.schemas.notifications import Notification
from app.config import settings

logger = logging.getLogger(__name__)

# Priority levels that trigger an SMS push
PUSH_PRIORITIES = {"high", "urgent"}


def send_notification(
    agent: str,
    title: str,
    body: str,
    priority: str = "medium",
) -> Notification:
    """
    Create an in-app notification and optionally send an SMS push.

    Args:
        agent:    Name of the agent creating the notification
        title:    Short headline shown in the notification list header
        body:     Full message body
        priority: low | medium | high | urgent
                  "high" and "urgent" also trigger Twilio SMS.

    Returns:
        The persisted Notification object.
    """
    client = get_client()
    response = (
        client.table("notifications")
        .insert({"agent": agent, "title": title, "body": body, "priority": priority})
        .execute()
    )
    notification = Notification(**response.data[0])

    if priority in PUSH_PRIORITIES:
        _send_sms(title, body)

    return notification


def _send_sms(title: str, body: str) -> None:
    """
    Send an SMS via Twilio for high/urgent notifications.
    Silently no-ops if Twilio credentials are not configured.
    Never raises — notification failures must not crash agent execution.
    """
    if not all([
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        settings.twilio_phone_from,
        settings.twilio_phone_to,
    ]):
        return

    try:
        from twilio.rest import Client as TwilioClient
        twilio = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        twilio.messages.create(
            body=f"[AI COO] {title}\n{body}",
            from_=settings.twilio_phone_from,
            to=settings.twilio_phone_to,
        )
    except Exception as exc:
        logger.warning("Twilio SMS failed: %s", exc)


def get_notifications(unread_only: bool = False, limit: int = 50) -> List[Notification]:
    """
    Return notifications for the dashboard, newest-first.

    Args:
        unread_only: If True, filter to unread=False rows only.
        limit:       Max rows returned.
    """
    client = get_client()
    query = (
        client.table("notifications")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if unread_only:
        query = query.eq("read", False)
    response = query.execute()
    return [Notification(**row) for row in response.data]


def mark_notification_read(notification_id: str) -> None:
    """Mark a single notification as read."""
    client = get_client()
    client.table("notifications").update({"read": True}).eq("id", notification_id).execute()


def mark_all_read() -> None:
    """Mark all unread notifications as read."""
    client = get_client()
    client.table("notifications").update({"read": True}).eq("read", False).execute()
