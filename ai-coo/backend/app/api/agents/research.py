"""api/agents/research.py — /api/research/* routes"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/run")
async def run_research_agent():
    return {"status": "queued", "agent": "research"}


@router.get("/status")
async def research_status():
    return {"agent": "research", "status": "idle"}
