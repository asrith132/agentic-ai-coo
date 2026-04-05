"""
api/agents/marketing.py — /api/marketing/* routes.

Endpoints:
  POST /api/marketing/run       — trigger full agent run (scan + events)
  POST /api/marketing/scan      — trend scanning only
  POST /api/marketing/draft     — draft content for a platform
  POST /api/marketing/publish   — publish approved content
  GET  /api/marketing/trends    — list recent trends
  GET  /api/marketing/content   — list content by status
  GET  /api/marketing/status    — agent status
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException

from app.agents.marketing.agent import MarketingAgent

router = APIRouter(prefix="/api/marketing", tags=["marketing"])

# Singleton agent instance
_agent = MarketingAgent()


# ── Request / Response models ────────────────────────────────────────────────


class DraftRequest(BaseModel):
    content_type: str                          # announcement | reply | thought_leadership | engagement
    platform: str                              # reddit | x | linkedin
    trend_id: str | None = None
    topic: str | None = None


class PublishRequest(BaseModel):
    content_id: str


class ScanResponse(BaseModel):
    status: str
    trends_found: int
    trends: list[dict[str, Any]]


class DraftResponse(BaseModel):
    status: str
    content: dict[str, Any]


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/run")
async def run_marketing_agent(trigger: dict[str, Any] | None = None):
    """Trigger a full marketing agent run (scan + event consumption)."""
    result = await _agent.run(trigger)
    return result


@router.post("/scan", response_model=ScanResponse)
async def scan_trends():
    """Run trend scanning across all platforms."""
    trends = await _agent.scan_trends()
    return ScanResponse(
        status="completed",
        trends_found=len(trends),
        trends=trends,
    )


@router.post("/draft", response_model=DraftResponse)
async def draft_content(req: DraftRequest):
    """Draft content for a given platform. Creates an approval request."""
    if req.platform not in ("reddit", "x", "linkedin"):
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {req.platform}")

    if not req.trend_id and not req.topic:
        raise HTTPException(
            status_code=400,
            detail="Either trend_id or topic must be provided",
        )

    row = await _agent.draft_content(
        content_type=req.content_type,
        platform=req.platform,
        trend_id=req.trend_id,
        topic=req.topic,
    )
    return DraftResponse(status="draft_created", content=row)


@router.post("/publish")
async def publish_content(req: PublishRequest):
    """Publish previously approved content to its platform."""
    from app.core.approvals import get_approval_status
    from app.agents.marketing.tools import get_content

    content_row = await get_content(req.content_id)
    if not content_row:
        raise HTTPException(status_code=404, detail="Content not found")

    # Verify approval
    approval_id = content_row.get("approval_id")
    if approval_id:
        approval = await get_approval_status(approval_id)
        if not approval or approval.status != "approved":
            raise HTTPException(
                status_code=403,
                detail="Content has not been approved for publishing",
            )

    result = await _agent.publish(req.content_id)
    return {"status": "published", "content": result}


@router.get("/trends")
async def list_trends(limit: int = 20):
    """List recent trends found by the scanner."""
    from app.agents.marketing.tools import get_recent_trends

    trends = await get_recent_trends(limit=limit)
    return {"trends": trends, "count": len(trends)}


@router.get("/content")
async def list_content(status: str = "draft", limit: int = 20):
    """List marketing content filtered by status."""
    from app.agents.marketing.tools import get_content_by_status

    if status not in ("draft", "pending_approval", "published", "rejected"):
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    items = await get_content_by_status(status, limit=limit)
    return {"content": items, "count": len(items)}


@router.get("/status")
async def marketing_status():
    """Return agent metadata and status."""
    return {
        "agent": _agent.name,
        "description": _agent.description,
        "subscribed_events": _agent.subscribed_events,
        "status": "ready",
    }
