"""
api/agents/dev_activity.py — /api/dev/* routes

Routes:
  POST /api/dev/webhook    — GitHub webhook receiver (HMAC-SHA256 verified)
  GET  /api/dev/commits    — Recent parsed commits from dev_commits table
  GET  /api/dev/features   — Feature map from dev_features table
  POST /api/dev/run        — Manually trigger the agent
  GET  /api/dev/status     — Commit counts, feature counts, last commit SHA
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from app.config import settings
from app.agents.dev_activity.tools import (
    parse_pr_merged_event,
    parse_push_event,
    verify_github_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["Dev Activity"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_dev_agent(commit_data: dict) -> dict:
    """Instantiate DevActivityAgent and process a commit synchronously."""
    from app.agents.dev_activity.agent import DevActivityAgent
    from app.schemas.triggers import AgentTrigger, TriggerType

    agent   = DevActivityAgent()
    trigger = AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input="process_commit",
        parameters={"commit_data": commit_data},
    )
    return agent.run(trigger)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/webhook",
    summary="GitHub webhook receiver",
    status_code=200,
)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    """
    Receive and verify GitHub webhook payloads (push, pull_request).

    Validates the HMAC-SHA256 signature using GITHUB_WEBHOOK_SECRET.
    Runs the DevActivityAgent synchronously for each recognised event.

    GitHub setup: Settings → Webhooks → Add webhook
      Payload URL:   https://your-domain/api/dev/webhook
      Content type:  application/json
      Events:        Just the push event  (or also pull_request)
    """
    body = await request.body()

    # ── Signature verification ─────────────────────────────────────────────
    if settings.github_webhook_secret:
        sig = x_hub_signature_256 or ""
        if not verify_github_signature(body, sig, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # ── Parse payload ──────────────────────────────────────────────────────
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Payload is not valid JSON")

    event_type = (x_github_event or "push").lower()
    logger.info("GitHub webhook received: event=%s", event_type)

    # ── ping — sent by GitHub on webhook creation ──────────────────────────
    if event_type == "ping":
        return {"status": "ok", "message": "pong"}

    # ── push ───────────────────────────────────────────────────────────────
    if event_type == "push":
        commit_data = parse_push_event(payload)
        if not commit_data:
            # Tag push or empty push — no commits to process
            return {"status": "ok", "message": "no commits to process"}

        result = _run_dev_agent(commit_data)
        return {"status": "ok", "processed": result}

    # ── pull_request (merged only) ─────────────────────────────────────────
    if event_type == "pull_request":
        action = payload.get("action", "")
        if action != "closed":
            # Only care about closed (potentially merged) PRs
            return {"status": "ok", "message": f"pr action '{action}' ignored"}

        commit_data = parse_pr_merged_event(payload)
        if not commit_data:
            return {"status": "ok", "message": "pr closed but not merged"}

        result = _run_dev_agent(commit_data)
        return {"status": "ok", "processed": result}

    # ── Other events — acknowledge without processing ──────────────────────
    logger.debug("GitHub webhook: ignoring event type '%s'", event_type)
    return {"status": "ok", "message": f"event '{event_type}' not processed"}


@router.get(
    "/commits",
    summary="List recent parsed commits",
)
def list_commits(
    limit: int = Query(default=20, ge=1, le=100),
    branch: str | None = Query(default=None, description="Filter by branch name"),
):
    """
    Return recent commits that have been parsed by the Dev Activity agent.

    Each commit includes the LLM-generated plain-English summary alongside
    the raw commit metadata (SHA, author, timestamp, files changed).
    """
    from app.db.supabase_client import get_client

    client = get_client()
    query  = (
        client.table("dev_commits")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if branch:
        query = query.eq("branch", branch)

    resp = query.execute()
    return {"commits": resp.data or [], "total": len(resp.data or [])}


@router.get(
    "/features",
    summary="Get feature map derived from commits",
)
def get_feature_map(
    status: str | None = Query(
        default=None,
        description="Filter by status: shipped | in_progress | deprecated",
    ),
):
    """
    Return the current feature map — all features the Dev Activity agent has
    detected from commit analysis, with their descriptions and related commit SHAs.

    This is the authoritative source of shipped features for the PM and
    Marketing agents.
    """
    from app.db.supabase_client import get_client

    client = get_client()
    query  = (
        client.table("dev_features")
        .select("*")
        .order("shipped_at", desc=True)
    )
    if status:
        query = query.eq("status", status)

    resp = query.execute()
    return {"features": resp.data or [], "total": len(resp.data or [])}


@router.post(
    "/run",
    summary="Manually trigger the Dev Activity agent",
)
def run_dev_activity():
    """
    Enqueue a manual run of the Dev Activity agent via Celery.
    Returns a status summary (commit count, feature count, last commit).
    """
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run(
        "dev_activity",
        {"type": "user_request", "user_input": "manual run"},
    )


@router.get(
    "/status",
    summary="Dev Activity agent status",
)
def dev_activity_status():
    """
    Return a live summary of the dev activity state:
    total commits parsed, total features detected, and most recent commit.
    """
    from app.db.supabase_client import get_client
    from datetime import date, timedelta

    client = get_client()

    # Total commits stored
    commits_resp = (
        client.table("dev_commits")
        .select("sha, timestamp, branch, parsed_summary")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    all_commits_resp = (
        client.table("dev_commits")
        .select("id", count="exact")
        .execute()
    )

    # Feature counts by status
    features_resp = (
        client.table("dev_features")
        .select("status")
        .execute()
    )
    feature_counts: dict[str, int] = {}
    for row in (features_resp.data or []):
        s = row["status"]
        feature_counts[s] = feature_counts.get(s, 0) + 1

    last_commit = commits_resp.data[0] if commits_resp.data else None

    return {
        "agent":          "dev_activity",
        "status":         "active",
        "total_commits":  getattr(all_commits_resp, "count", 0) or len(all_commits_resp.data or []),
        "features":       feature_counts,
        "total_features": sum(feature_counts.values()),
        "last_commit":    {
            "sha":     (last_commit["sha"][:12] if last_commit else None),
            "branch":  (last_commit.get("branch") if last_commit else None),
            "summary": (last_commit.get("parsed_summary") if last_commit else None),
        } if last_commit else None,
    }
