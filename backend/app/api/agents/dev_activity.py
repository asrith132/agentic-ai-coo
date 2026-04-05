"""
api/agents/dev_activity.py — /api/dev/* routes

Exposes the Dev Activity agent to the frontend:
  - Manual trigger
  - Current agent status
  - Domain-specific data endpoints (added in Prompt 4)

The route file stays thin — it dispatches to Celery tasks, not agent code directly.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/dev", tags=["dev-activity"])


@router.post("/run")
async def run_dev_activity_agent():
    """Manually trigger the Dev Activity agent via Celery."""
    # TODO (Prompt 4): enqueue Celery task
    return {"status": "queued", "agent": "dev_activity"}


@router.get("/status")
async def dev_activity_status():
    """Return the last run status and summary for the Dev Activity agent."""
    # TODO (Prompt 4): read from agent_state table or Redis
    return {"agent": "dev_activity", "status": "idle"}
