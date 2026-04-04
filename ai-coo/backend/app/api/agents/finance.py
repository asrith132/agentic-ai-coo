"""
api/agents/finance.py — /api/finance/* routes

Routes:
  POST /api/finance/upload        — Upload a bank statement or Stripe CSV
  GET  /api/finance/transactions  — Categorized transaction list
  GET  /api/finance/summary       — Plain English financial health summary
  GET  /api/finance/runway        — Current runway calculation
  POST /api/finance/run           — Manually trigger the Finance agent
  GET  /api/finance/status        — Last run status
"""

from __future__ import annotations

from fastapi import APIRouter, File, Query, UploadFile

router = APIRouter(prefix="/api/finance", tags=["Finance"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


@router.post(
    "/upload",
    summary="Upload a bank statement or Stripe CSV",
)
async def upload_statement(file: UploadFile = File(...)):
    """
    Accept a CSV export from a bank or Stripe and hand it to the Finance agent
    for parsing, categorization, and MRR/burn/runway extraction.

    Supported formats: any CSV with date, amount, description columns.
    The agent uses the LLM to categorize transactions and update business_state.

    Returns a job ID for polling upload status.
    """
    # TODO (Prompt 4): save to Supabase Storage, enqueue FinanceAgent Celery task
    return {"status": "uploaded", "filename": file.filename, "task_id": None}


@router.get(
    "/transactions",
    summary="List categorized transactions",
)
def list_transactions(
    limit: int = Query(default=50, le=500),
    category: str | None = Query(default=None, description="Filter by category (e.g. 'revenue', 'payroll')"),
):
    """
    Return parsed and categorized transactions from the most recent upload.
    Each transaction includes: date, amount, description, category, source.
    """
    # TODO (Prompt 4): query finance_snapshots or a transactions sub-table
    return _NOT_IMPLEMENTED


@router.get(
    "/summary",
    summary="Plain English financial health summary",
)
def financial_summary():
    """
    Return an LLM-generated natural language summary of the current financial
    position: MRR, ARR, monthly burn, runway, and trend direction.

    This is the text displayed in the dashboard finance card.
    """
    # TODO (Prompt 4): call FinanceAgent to generate summary from latest snapshot
    return _NOT_IMPLEMENTED


@router.get(
    "/runway",
    summary="Current runway calculation",
)
def runway():
    """
    Return the runway calculation: cash balance, monthly burn rate,
    runway in months, and the date at which cash runs out at current burn.

    Also returns the last updated timestamp so the user knows data freshness.
    """
    # TODO (Prompt 4): read from finance_snapshots latest row + business_state
    return _NOT_IMPLEMENTED


@router.post("/run", summary="Manually trigger the Finance agent")
def run_finance():
    """Enqueue a manual run of the Finance agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("finance", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Finance agent last run status")
def finance_status():
    """Return last run timestamp and latest MRR/runway snapshot."""
    return {"agent": "finance", "status": "idle", "last_run": None}
