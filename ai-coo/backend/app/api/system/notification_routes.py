"""
api/system/notification_routes.py

Routes:
  GET  /api/notifications           — List notifications (filterable)
  POST /api/notifications/{id}/read — Mark a notification as read
"""

from fastapi import APIRouter, HTTPException, Query

from app.core.notifications import get_notifications, mark_notification_read
from app.db.supabase_client import get_client
from app.schemas.notifications import Notification

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=list[Notification],
    summary="List notifications",
)
def list_notifications(
    unread_only: bool = Query(default=False, description="Return only unread notifications"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Return notifications for the dashboard notification bell, newest-first.

    Pass `?unread_only=true` to fetch only unread items (for the badge count).
    """
    return get_notifications(unread_only=unread_only, limit=limit)


@router.post(
    "/{notification_id}/read",
    response_model=Notification,
    summary="Mark a notification as read",
)
def read_notification(notification_id: str):
    """
    Mark a single notification as read and return the updated record.
    """
    client = get_client()

    # Verify it exists
    response = (
        client.table("notifications")
        .select("*")
        .eq("id", notification_id)
        .maybe_single()
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    mark_notification_read(notification_id)

    updated = (
        client.table("notifications")
        .select("*")
        .eq("id", notification_id)
        .single()
        .execute()
    )
    return Notification(**updated.data)
