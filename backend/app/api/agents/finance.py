"""api/agents/finance.py — /api/finance/* routes"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.post("/run")
async def run_finance_agent():
    return {"status": "queued", "agent": "finance"}


@router.get("/status")
async def finance_status():
    return {"agent": "finance", "status": "idle"}
