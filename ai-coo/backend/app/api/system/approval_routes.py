"""
api/system/approval_routes.py

Routes:
  GET  /api/approvals           — List approvals (filterable by status)
  GET  /api/approvals/{id}      — Get a single approval
  POST /api/approvals/{id}/respond — Approve or reject; triggers agent callback

The approval callback (on approval):
  After a user approves an action, this route looks up the originating agent,
  instantiates it, and calls agent.run() with a UserTrigger that carries the
  approval result (approved content + any user edits). This lets the agent
  immediately execute the approved action (e.g. actually send the email).

  The callback runs synchronously in the request. For long-running agents,
  swap this for a Celery task dispatch once tasks are wired in Prompt 4.
"""

from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse

from app.core.approvals import (
    get_pending_approvals,
    get_approval,
    respond_to_approval,
)
from app.schemas.approvals import Approval, ApprovalResponse
from app.schemas.triggers import AgentTrigger, TriggerType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


@router.get(
    "",
    response_model=list[Approval],
    summary="List approvals",
)
def list_approvals(
    status: str = Query(default="pending", description="Filter by status: pending | approved | rejected"),
    agent: str | None = Query(default=None, description="Filter by agent name"),
):
    """
    Return approvals filtered by status (default: pending).

    The frontend polls this to display the approval queue.
    Pass `?agent=outreach` to show only that agent's pending actions.
    """
    if status == "pending":
        return get_pending_approvals(agent=agent)

    # For non-pending statuses, query directly
    from app.db.supabase_client import get_client
    client = get_client()
    query = (
        client.table("approvals")
        .select("*")
        .eq("status", status)
        .order("created_at", desc=True)
    )
    if agent:
        query = query.eq("agent", agent)
    response = query.execute()
    return [Approval(**row) for row in response.data]


@router.get(
    "/{approval_id}",
    response_model=Approval,
    summary="Get a single approval",
)
def get_approval_by_id(approval_id: str):
    """
    Return the full approval record including content (the payload the agent
    wants to act on) and any user edits if already resolved.
    """
    approval = get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    return approval


@router.post(
    "/{approval_id}/respond",
    response_model=Approval,
    summary="Approve or reject an action",
)
def respond_to_approval_route(
    approval_id: str,
    body: ApprovalResponse,
    background_tasks: BackgroundTasks,
):
    """
    Submit a human decision on a pending approval.

    - `status`:  "approved" or "rejected"
    - `edits`:   optional dict of user modifications to the content
                 (e.g. edited email subject/body before sending)

    **On approval**, the originating agent is triggered as a background task
    to immediately execute the approved action. The agent receives a
    UserTrigger with the final content (user edits applied over the original).

    Example body:
    ```json
    {
      "status": "approved",
      "edits": {"subject": "Updated subject line", "body": "..."}
    }
    ```
    """
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")

    existing = get_approval(approval_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    if existing.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval already {existing.status}")

    # Persist the decision
    updated = respond_to_approval(
        approval_id=approval_id,
        status=body.status,
        edits=body.edits,
    )

    # On approval: trigger the agent to execute the approved action
    if body.status == "approved":
        background_tasks.add_task(
            _dispatch_approval_callback,
            agent_name=existing.agent,
            action_type=existing.action_type,
            original_content=existing.content,
            user_edits=body.edits,
            approval_id=approval_id,
        )

    return updated


@router.get(
    "/quick",
    response_class=HTMLResponse,
    summary="Tap-to-approve/reject from SMS link",
    include_in_schema=False,
)
def quick_respond(token: str = Query(...), action: str = Query(...)):
    """
    One-tap approve or reject from an SMS link.
    Returns a styled HTML confirmation page.
    """
    from app.db.supabase_client import get_client

    status = "approved" if action == "approve" else "rejected"
    emoji  = "✅" if status == "approved" else "❌"
    color  = "#22c55e" if status == "approved" else "#ef4444"

    try:
        r = get_client().table("user_settings").select("value").eq("key", f"sms_token:{token}").maybe_single().execute()
        if not r.data:
            return HTMLResponse(_quick_page("❓", "Link expired", "This link has already been used or has expired.", "#888"))

        approval_id = r.data["value"]
        existing = get_approval(approval_id)

        if not existing:
            return HTMLResponse(_quick_page("❓", "Not found", "This approval no longer exists.", "#888"))
        if existing.status != "pending":
            return HTMLResponse(_quick_page("ℹ️", f"Already {existing.status}", f"This request was already {existing.status}.", "#888"))

        respond_to_approval(approval_id=approval_id, status=status)
        get_client().table("user_settings").delete().eq("key", f"sms_token:{token}").execute()

        c = existing.content or {}
        title = c.get("title") or c.get("subject") or existing.action_type.replace("_", " ").title()

        if status == "approved":
            background_tasks_local = BackgroundTasks()
            _dispatch_approval_callback(
                agent_name=existing.agent,
                action_type=existing.action_type,
                original_content=existing.content,
                user_edits=None,
                approval_id=approval_id,
            )

        return HTMLResponse(_quick_page(emoji, status.capitalize(), title[:80], color))

    except Exception as exc:
        logger.exception("Quick respond error: %s", exc)
        return HTMLResponse(_quick_page("⚠️", "Error", "Something went wrong. Open the app to respond.", "#f59e0b"))


def _quick_page(emoji: str, heading: str, detail: str, color: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI COO</title>
<style>
  body{{margin:0;font-family:-apple-system,sans-serif;background:#0a0a0a;color:#fff;
    display:flex;align-items:center;justify-content:center;min-height:100vh;}}
  .card{{text-align:center;padding:2rem;max-width:320px;}}
  .emoji{{font-size:3rem;margin-bottom:1rem;}}
  .heading{{font-size:1.5rem;font-weight:700;color:{color};margin-bottom:.5rem;}}
  .detail{{font-size:.95rem;color:#888;line-height:1.5;}}
</style></head><body>
<div class="card">
  <div class="emoji">{emoji}</div>
  <div class="heading">{heading}</div>
  <div class="detail">{detail}</div>
</div></body></html>"""


def _dispatch_approval_callback(
    agent_name: str,
    action_type: str,
    original_content: dict[str, Any],
    user_edits: dict[str, Any] | None,
    approval_id: str,
) -> None:
    """
    Background task: instantiate the originating agent and run it with a
    UserTrigger carrying the approved content.

    The agent's execute() method receives:
      trigger.user_input   = f"execute_approved:{action_type}"
      trigger.parameters   = {
          "approval_id":   str,
          "action_type":   str,
          "content":       dict,  # original_content merged with user_edits
      }

    Agent builders should check `trigger.parameters.get("approval_id")` inside
    execute() to detect this callback pattern and act accordingly.
    """
    from app.agents.registry import get_agent

    # Merge user edits over original content
    final_content: dict[str, Any] = {**original_content, **(user_edits or {})}

    trigger = AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input=f"execute_approved:{action_type}",
        parameters={
            "approval_id": approval_id,
            "action_type": action_type,
            "content":     final_content,
        },
    )

    try:
        agent = get_agent(agent_name)
        agent.run(trigger)
    except NotImplementedError:
        # Agent stub not yet implemented — expected until Prompt 4
        logger.info(
            "Approval callback for '%s' skipped — agent not yet implemented (Prompt 4).",
            agent_name,
        )
    except Exception as exc:
        logger.exception(
            "Approval callback failed for agent '%s' (approval %s): %s",
            agent_name, approval_id, exc,
        )
