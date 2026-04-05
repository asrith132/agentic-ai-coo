"""
core/approvals.py — Approval queue helpers.

Certain agent actions require human sign-off before execution — e.g. sending
an email, publishing a post, initiating a payment. Agents request approval via
`request_approval()`, then poll `get_approval_status()` or wait for a Celery
callback triggered by Supabase Realtime.

The Next.js frontend polls GET /api/approvals and the user clicks
Approve / Reject (with optional edits). The backend updates the row and the
waiting agent task is unblocked.

Approval statuses: pending | approved | rejected
"""

from __future__ import annotations
from typing import Any
from datetime import datetime, timezone
from app.db.supabase_client import get_client
from app.schemas.approvals import Approval, ApprovalResponse


async def request_approval(
    agent: str,
    action_type: str,
    content: dict[str, Any],
) -> Approval:
    """
    Create a new pending approval request.

    Args:
        agent:       Name of the requesting agent (e.g. "outreach")
        action_type: Short label for the action (e.g. "send_email", "publish_post")
        content:     The full payload the agent intends to act on — shown to the user

    Returns:
        The created Approval object with status="pending"
    """
    client = get_client()
    response = (
        client.table("approvals")
        .insert({"agent": agent, "action_type": action_type, "content": content})
        .execute()
    )
    return Approval(**response.data[0])


async def respond_to_approval(
    approval_id: str,
    decision: str,
    user_edits: dict[str, Any] | None = None,
) -> Approval:
    """
    Record a human decision on an approval request.

    Args:
        approval_id: UUID of the approval row
        decision:    "approved" or "rejected"
        user_edits:  Optional dict of changes the user made to `content`

    Returns:
        Updated Approval object
    """
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")

    client = get_client()
    payload: dict[str, Any] = {
        "status": decision,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    if user_edits is not None:
        payload["user_edits"] = user_edits

    response = (
        client.table("approvals")
        .update(payload)
        .eq("id", approval_id)
        .execute()
    )
    return Approval(**response.data[0])


async def get_pending_approvals(agent: str | None = None) -> list[Approval]:
    """
    Fetch all pending approvals, optionally filtered by agent.

    Used by the frontend dashboard to show the approval queue.
    """
    client = get_client()
    query = client.table("approvals").select("*").eq("status", "pending").order("created_at")
    if agent:
        query = query.eq("agent", agent)
    response = query.execute()
    return [Approval(**row) for row in response.data]


async def get_approval_status(approval_id: str) -> Approval | None:
    """
    Poll the status of a specific approval request.

    Agents waiting on approval call this in a retry loop (or via Celery chord).
    """
    client = get_client()
    response = (
        client.table("approvals")
        .select("*")
        .eq("id", approval_id)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return None
    return Approval(**response.data)
