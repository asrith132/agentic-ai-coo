"""api/agents/legal.py — /api/legal/* routes"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/legal", tags=["legal"])


@router.post("/run")
async def run_legal_agent():
    return {"status": "queued", "agent": "legal"}


@router.get("/status")
async def legal_status():
    return {"agent": "legal", "status": "idle"}
