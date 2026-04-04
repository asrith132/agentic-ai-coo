"""
core/approvals.py — Approval queue helpers.

Agents use the approval queue before taking sensitive external actions
(send email, publish post, initiate payment, etc.).

Pattern:
  1. Agent calls create_approval()  → row inserted with status="pending"
  2. Frontend displays pending items to the user
  3. User clicks Approve/Reject (with optional edits)
  4. Frontend calls POST /api/approvals/{id}/respond
  5. Agent polls get_approval() until status != "pending", then acts accordingly
"""

from __future__ import annotations
from typing import Any, List, Optional
from datetime import datetime, timezone

from app.db.supabase_client import get_client
from app.schemas.approvals import Approval


def create_approval(
    agent: str,
    action_type: str,
    content: dict[str, Any],
) -> Approval:
    """
    Create a new pending approval request.

    Args:
        agent:       Name of the requesting agent (e.g. "outreach")
        action_type: Short label for what is being approved (e.g. "send_email")
        content:     The full payload the agent intends to act on — displayed to user

    Returns:
        Approval with status="pending" and a populated id.
    """
    client = get_client()
    response = (
        client.table("approvals")
        .insert({"agent": agent, "action_type": action_type, "content": content})
        .execute()
    )
    return Approval(**response.data[0])


def get_pending_approvals(agent: Optional[str] = None) -> List[Approval]:
    """
    Return all pending approvals, ordered oldest-first.

    Args:
        agent: Optional filter — only return approvals for this agent name.

    Used by the frontend dashboard to show the approval queue.
    """
    client = get_client()
    query = (
        client.table("approvals")
        .select("*")
        .eq("status", "pending")
        .order("created_at", desc=False)
    )
    if agent:
        query = query.eq("agent", agent)
    response = query.execute()
    return [Approval(**row) for row in response.data]


def respond_to_approval(
    approval_id: str,
    status: str,
    edits: Optional[dict[str, Any]] = None,
) -> Approval:
    """
    Record a human decision on an approval request.

    Args:
        approval_id: UUID string of the approval row
        status:      "approved" or "rejected"
        edits:       Optional user-modified version of content (e.g. edited email body)

    Returns:
        Updated Approval object.

    Raises:
        ValueError: If status is not "approved" or "rejected".
    """
    if status not in ("approved", "rejected"):
        raise ValueError(f"Invalid status '{status}' — must be 'approved' or 'rejected'")

    client = get_client()
    payload: dict[str, Any] = {
        "status": status,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    if edits is not None:
        payload["user_edits"] = edits

    response = (
        client.table("approvals")
        .update(payload)
        .eq("id", approval_id)
        .execute()
    )
    return Approval(**response.data[0])


def get_approval(approval_id: str) -> Optional[Approval]:
    """
    Fetch a single approval by ID.

    Agents poll this in a retry loop to detect when the user has responded.
    Returns None if not found.
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
