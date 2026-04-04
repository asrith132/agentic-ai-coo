"""
api/agents/dev_activity.py — /api/dev/* routes

Exposes the Dev Activity agent to the frontend and external systems (GitHub).

Routes:
  POST /api/dev/webhook    — GitHub webhook receiver (signed HMAC-SHA256)
  GET  /api/dev/commits    — Recent parsed commits
  GET  /api/dev/features   — Feature map derived from merged PRs
  POST /api/dev/run        — Manually trigger the agent
  GET  /api/dev/status     — Last run status and summary
"""

from __future__ import annotations
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["Dev Activity"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


@router.post(
    "/webhook",
    summary="GitHub webhook receiver",
)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
):
    """
    Receive and verify GitHub webhook payloads (push, pull_request, workflow_run).

    Validates the HMAC-SHA256 signature using GITHUB_WEBHOOK_SECRET.
    On valid payload, enqueues a Celery task to process the event.
    Returns 204 immediately — processing is async.

    GitHub sends this on: push, PR open/merge, CI status change.
    """
    body = await request.body()

    # Validate signature
    if settings.github_webhook_secret:
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256 or ""):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # TODO (Prompt 4): parse payload and dispatch Celery task
    logger.info("GitHub webhook received (%d bytes)", len(body))
    return {"status": "received"}


@router.get(
    "/commits",
    summary="List recent parsed commits",
)
def list_commits(limit: int = Query(default=20, le=100)):
    """
    Return recent commits parsed from GitHub webhook events or polling.
    Each commit includes: sha, message, author, timestamp, files_changed.
    """
    # TODO (Prompt 4): query dev_agent_state or a commits sub-table
    return _NOT_IMPLEMENTED


@router.get(
    "/features",
    summary="Get feature map from merged PRs",
)
def get_feature_map():
    """
    Return a structured map of recently shipped features derived from
    merged PRs. Used by the PM agent and the dashboard feature timeline.
    """
    # TODO (Prompt 4): query dev_agent_state.recent_commits and derive feature map
    return _NOT_IMPLEMENTED


@router.post(
    "/run",
    summary="Manually trigger the Dev Activity agent",
)
def run_dev_activity():
    """
    Enqueue a manual run of the Dev Activity agent via Celery.
    Returns the Celery task ID for status polling.
    """
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run(
        "dev_activity",
        {"type": "user_request", "user_input": "manual run"},
    )


@router.get(
    "/status",
    summary="Get Dev Activity agent last run status",
)
def dev_activity_status():
    """Return the last run timestamp, CI status, and open PR count."""
    # TODO (Prompt 4): read from dev_agent_state table
    return {"agent": "dev_activity", "status": "idle", "last_run": None}
