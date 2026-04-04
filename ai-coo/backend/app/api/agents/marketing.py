"""
api/agents/marketing.py — /api/marketing/* routes

Routes:
  POST /api/marketing/scan     — Trigger a trend scan across Reddit, X, HN
  GET  /api/marketing/trends   — List trends found by the last scan
  POST /api/marketing/draft    — Draft a post or reply for a specific trend
  GET  /api/marketing/content  — Content calendar and publication history
  POST /api/marketing/run      — Manually trigger the Marketing agent
  GET  /api/marketing/status   — Last run status
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/marketing", tags=["Marketing"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


class DraftPostRequest(BaseModel):
    trend_id: str | None = None
    platform: str = "reddit"           # reddit | x | linkedin
    prompt: str | None = None          # optional free-text direction


@router.post(
    "/scan",
    summary="Trigger a trend scan",
)
def trigger_trend_scan():
    """
    Kick off a scan of Reddit, X (Twitter), and Hacker News for trends
    relevant to the company's product and ICP.

    Stores findings in research_findings table (type="trend") and emits
    a marketing.scan_completed event. Returns immediately; scan is async.
    """
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run(
        "marketing",
        {"type": "scheduled", "task_name": "trend_scan"},
    )


@router.get(
    "/trends",
    summary="List discovered trends",
)
def list_trends(limit: int = Query(default=20, le=100)):
    """
    Return trends found by recent scans, including the source URL,
    relevance score, and whether the agent has drafted content for it yet.
    """
    # TODO (Prompt 4): query research_findings where type="trend"
    return _NOT_IMPLEMENTED


@router.post(
    "/draft",
    summary="Draft a post or reply for a trend",
)
def draft_post(body: DraftPostRequest):
    """
    Use the LLM + brand voice to draft a post or reply for a specific trend.
    Creates an approval record for the user to review before publishing.

    If `trend_id` is provided, pulls the trend context automatically.
    If `prompt` is provided, uses it as additional direction for the draft.
    """
    # TODO (Prompt 4): call MarketingAgent to draft and create approval
    return _NOT_IMPLEMENTED


@router.get(
    "/content",
    summary="Content calendar and publication history",
)
def list_content(
    status: str | None = Query(default=None, description="draft|pending_approval|published|rejected"),
    platform: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """
    Return all marketing posts with their status, platform, engagement
    metrics (for published posts), and scheduled publish times.
    """
    # TODO (Prompt 4): query marketing_posts table
    return _NOT_IMPLEMENTED


@router.post("/run", summary="Manually trigger the Marketing agent")
def run_marketing():
    """Enqueue a manual run of the Marketing agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("marketing", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Marketing agent last run status")
def marketing_status():
    """Return last run timestamp and last published content summary."""
    return {"agent": "marketing", "status": "idle", "last_run": None}
