"""
api/system/notification_routes.py — Notifications API

GET  /api/notifications          — List notifications (with optional unread filter)
POST /api/notifications/{id}/read — Mark a notification as read
POST /api/notifications/read-all  — Mark all notifications as read
"""

from fastapi import APIRouter, Query
from app.core.notifications import get_notifications, mark_read, mark_all_read
from app.schemas.notifications import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[Notification])
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
):
    """Return notifications newest-first. Pass ?unread_only=true to filter."""
    return await get_notifications(unread_only=unread_only, limit=limit)


@router.post("/{notification_id}/read")
async def read_notification(notification_id: str):
    """Mark a single notification as read."""
    await mark_read(notification_id)
    return {"ok": True}


@router.post("/read-all")
async def read_all_notifications():
    """Mark all unread notifications as read."""
    await mark_all_read()
    return {"ok": True}
