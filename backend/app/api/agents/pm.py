"""api/agents/pm.py — /api/pm/* routes"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/pm", tags=["pm"])


@router.post("/run")
async def run_pm_agent():
    return {"status": "queued", "agent": "pm"}


@router.get("/status")
async def pm_status():
    return {"agent": "pm", "status": "idle"}
