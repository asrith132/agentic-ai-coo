"""api/agents/outreach.py — /api/outreach/* routes"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


@router.post("/run")
async def run_outreach_agent():
    """Manually trigger the Outreach agent via Celery."""
    # TODO (Prompt 4): enqueue Celery task
    return {"status": "queued", "agent": "outreach"}


@router.get("/status")
async def outreach_status():
    """Return the last run status for the Outreach agent."""
    # TODO (Prompt 4)
    return {"agent": "outreach", "status": "idle"}
