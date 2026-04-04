"""
api/system/approval_routes.py — Approval queue API

GET  /api/approvals              — List pending approvals (dashboard queue)
POST /api/approvals/{id}/respond — Approve or reject with optional edits
"""

from fastapi import APIRouter, HTTPException, Query
from app.core.approvals import get_pending_approvals, respond_to_approval, get_approval_status
from app.schemas.approvals import Approval, ApprovalResponse

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[Approval])
async def list_approvals(agent: str | None = Query(default=None)):
    """
    Return all pending approval requests.
    Optionally filter to a specific agent (e.g. ?agent=outreach).
    """
    return await get_pending_approvals(agent=agent)


@router.get("/{approval_id}", response_model=Approval)
async def get_approval(approval_id: str):
    """Return a single approval by ID."""
    approval = await get_approval_status(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/{approval_id}/respond", response_model=Approval)
async def respond(approval_id: str, body: ApprovalResponse):
    """
    Submit a decision on a pending approval.

    - decision: "approved" or "rejected"
    - user_edits: optional dict of changes to the content (e.g. edited email subject)

    After this call, the waiting Celery task will detect the updated status
    on its next poll cycle and proceed accordingly.
    """
    approval = await get_approval_status(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval already {approval.status}")

    return await respond_to_approval(
        approval_id=approval_id,
        decision=body.decision,
        user_edits=body.user_edits,
    )
