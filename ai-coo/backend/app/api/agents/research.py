"""
api/agents/research.py — /api/research/* routes

Routes:
  POST /api/research/query        — Submit a research request
  GET  /api/research/reports      — List past research reports
  GET  /api/research/reports/{id} — Get a specific research report
  POST /api/research/run          — Manually trigger the Research agent
  GET  /api/research/status       — Last run status
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/research", tags=["Research"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


class ResearchQueryRequest(BaseModel):
    query: str
    focus: str | None = None     # "competitor" | "trend" | "lead" | "market"
    depth: str = "standard"      # "quick" | "standard" | "deep"


@router.post(
    "/query",
    summary="Submit a research request",
)
def submit_research_query(body: ResearchQueryRequest):
    """
    Submit an ad-hoc research question to the Research agent.
    The agent uses web search, scraping, and LLM synthesis to produce a report.

    `focus` narrows the type of research (competitor analysis, trend spotting, etc).
    `depth` controls how many sources are consulted and response detail level.

    Returns a report ID for polling. The report is also stored and listed
    under GET /api/research/reports.
    """
    # TODO (Prompt 4): enqueue ResearchAgent Celery task with query trigger
    return {"status": "queued", "agent": "research", "report_id": None}


@router.get(
    "/reports",
    summary="List past research reports",
)
def list_reports(
    finding_type: str | None = Query(default=None, description="competitor|trend|lead|market"),
    actioned: bool | None = Query(default=None, description="Filter by whether the finding was acted on"),
    limit: int = Query(default=20, le=100),
):
    """
    Return a list of research findings/reports sorted by created_at descending.
    Each report includes: title, type, relevance score, source URL, actioned flag.
    """
    # TODO (Prompt 4): query research_findings table
    return _NOT_IMPLEMENTED


@router.get(
    "/reports/{report_id}",
    summary="Get a specific research report",
)
def get_report(report_id: str):
    """
    Return the full content of a specific research report, including the
    raw sources consulted, synthesized findings, and recommended actions.
    """
    # TODO (Prompt 4): query research_findings where id = report_id
    return _NOT_IMPLEMENTED


@router.post("/run", summary="Manually trigger the Research agent")
def run_research():
    """Enqueue a manual run of the Research agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("research", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Research agent last run status")
def research_status():
    """Return last run timestamp and count of findings by type."""
    return {"agent": "research", "status": "idle", "last_run": None}
