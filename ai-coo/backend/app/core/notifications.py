"""
core/notifications.py — Notification + push helpers.

Two delivery channels:
  1. In-app: row inserted into `notifications` table, polled by frontend
  2. Telegram push: triggered automatically for high/urgent priority

Agents call send_notification() — never insert into the table directly.
"""

from __future__ import annotations
from typing import List
import logging

from app.db.supabase_client import get_client
from app.schemas.notifications import Notification
from app.config import settings

logger = logging.getLogger(__name__)

# Priority levels that trigger a Telegram push
PUSH_PRIORITIES = {"high", "urgent"}


def send_notification(
    agent: str,
    title: str,
    body: str,
    priority: str = "medium",
) -> Notification:
    """
    Create an in-app notification and optionally send a Telegram push.

    Args:
        agent:    Name of the agent creating the notification
        title:    Short headline shown in the notification list header
        body:     Full message body
        priority: low | medium | high | urgent
                  "high" and "urgent" also trigger Telegram message.

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
        send_telegram(f"{title}\n{body}")

    return notification


def _get_chat_id() -> str | None:
    """Return the user's stored Telegram chat ID from DB."""
    try:
        r = get_client().table("user_settings").select("value").eq("key", "telegram_chat_id").maybe_single().execute()
        if r.data:
            return r.data["value"]
    except Exception:
        pass
    return None


def send_telegram(text: str) -> None:
    """
    Send a Telegram message via the configured bot.
    Silently no-ops if bot token or chat ID are not configured.
    Never raises — notification failures must not crash agent execution.
    """
    if not settings.telegram_bot_token:
        return

    chat_id = _get_chat_id()
    if not chat_id:
        return

    try:
        import urllib.request
        import urllib.parse
        import json

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        logger.info("Telegram message sent to chat %s", chat_id)
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


# ── Backward-compat shims ─────────────────────────────────────────────────────

def send_sms(title: str, body: str) -> None:
    """Backward-compat alias — routes to Telegram now."""
    send_telegram(f"{title}\n{body}")


def _send_sms(title: str, body: str) -> None:
    send_telegram(f"{title}\n{body}")


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


# ── Backward-compat shim for older agent code ─────────────────────────────────

async def notify(agent: str, title: str, body: str, priority: str = "medium") -> None:
    """Async shim wrapping send_notification for legacy agent code."""
    send_notification(agent=agent, title=title, body=body, priority=priority)
