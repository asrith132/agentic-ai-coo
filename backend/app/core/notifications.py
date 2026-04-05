"""
core/notifications.py — Notification + push helpers.

Agents surface important updates to the user through two channels:
  1. In-app notifications stored in the `notifications` table (polled by frontend)
  2. SMS push via Twilio for urgent alerts

Agents should call `notify()` for any user-facing update. The frontend
displays unread notifications with a badge and real-time updates via
Supabase Realtime subscriptions.
"""

from __future__ import annotations
from app.db.supabase_client import get_client
from app.schemas.notifications import Notification
from app.config import settings


async def notify(
    agent: str,
    title: str,
    body: str,
    priority: str = "medium",
    push: bool = False,
) -> Notification:
    """
    Create an in-app notification and optionally send an SMS push.

    Args:
        agent:    Name of the agent creating the notification
        title:    Short headline (shown in notification list header)
        body:     Full message body
        priority: "low" | "medium" | "high" | "urgent"
        push:     If True AND priority is "urgent", send an SMS via Twilio

    Returns:
        The persisted Notification object
    """
    client = get_client()
    response = (
        client.table("notifications")
        .insert({"agent": agent, "title": title, "body": body, "priority": priority})
        .execute()
    )
    notification = Notification(**response.data[0])

    if push and priority == "urgent":
        await _send_sms_push(title, body)

    return notification


async def _send_sms_push(title: str, body: str) -> None:
    """
    Send an urgent SMS via Twilio. Only called for priority="urgent" + push=True.
    Silently no-ops if Twilio credentials are not configured.
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
    except Exception:
        # Never let notification failures crash agent execution
        pass


async def get_notifications(unread_only: bool = False, limit: int = 50) -> list[Notification]:
    """Fetch notifications for the dashboard, optionally filtering to unread."""
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


async def mark_read(notification_id: str) -> None:
    """Mark a single notification as read."""
    client = get_client()
    client.table("notifications").update({"read": True}).eq("id", notification_id).execute()


async def mark_all_read() -> None:
    """Mark all unread notifications as read."""
    client = get_client()
    client.table("notifications").update({"read": True}).eq("read", False).execute()
