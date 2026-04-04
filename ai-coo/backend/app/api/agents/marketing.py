"""api/agents/marketing.py — /api/marketing/* routes"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


@router.post("/run")
async def run_marketing_agent():
    return {"status": "queued", "agent": "marketing"}


@router.get("/status")
async def marketing_status():
    return {"agent": "marketing", "status": "idle"}
