"""
api/agents/legal.py — /api/legal/* routes

Routes:
  POST /api/legal/generate        — Generate compliance checklist (entity type + jurisdiction)
  GET  /api/legal/checklist       — Current checklist with item statuses
  POST /api/legal/draft/{item}    — Draft a specific legal document
  GET  /api/legal/deadlines       — Upcoming compliance deadlines
  POST /api/legal/run             — Manually trigger the Legal agent
  GET  /api/legal/status          — Last run status
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/legal", tags=["Legal"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


class GenerateChecklistRequest(BaseModel):
    entity_type: str         # "LLC" | "C-Corp" | "Ltd" | "Sole Proprietor"
    jurisdiction: str        # e.g. "Delaware, USA" | "England and Wales"
    stage: str = "pre_launch"  # pre_launch | launched | fundraising


class DraftDocumentRequest(BaseModel):
    context: str | None = None    # optional additional context for the draft


@router.post(
    "/generate",
    summary="Generate a compliance checklist",
    status_code=201,
)
def generate_checklist(body: GenerateChecklistRequest):
    """
    Use the LLM + Legal agent to generate a tailored compliance checklist
    for the given entity type, jurisdiction, and business stage.

    Checklist items include: registration, filing deadlines, required policies
    (Privacy Policy, Terms of Service), employment law, tax obligations, etc.

    Returns a checklist ID. Items can be retrieved via GET /api/legal/checklist.
    """
    # TODO (Prompt 4): call LegalAgent to generate checklist, store in legal_documents
    return _NOT_IMPLEMENTED


@router.get(
    "/checklist",
    summary="Get current compliance checklist",
)
def get_checklist():
    """
    Return the current compliance checklist with item statuses:
    pending | in_progress | complete | overdue.

    Grouped by category (formation, tax, employment, IP, privacy).
    """
    # TODO (Prompt 4): query legal_documents where type="checklist"
    return _NOT_IMPLEMENTED


@router.post(
    "/draft/{item_id}",
    summary="Draft a specific legal document",
)
def draft_document(item_id: str, body: DraftDocumentRequest):
    """
    Ask the Legal agent to draft a document for a specific checklist item
    (e.g. Privacy Policy, NDA template, Employee Agreement).

    The draft is stored in legal_documents and a Supabase Storage file is
    created. An approval is requested before the document is finalized.
    Always requires human review — the agent never finalizes legal docs autonomously.
    """
    # TODO (Prompt 4): call LegalAgent to draft document + create approval
    return _NOT_IMPLEMENTED


@router.get(
    "/deadlines",
    summary="Upcoming compliance deadlines",
)
def list_deadlines():
    """
    Return upcoming legal/compliance deadlines sorted by date ascending.
    Includes: deadline name, due date, category, linked checklist item.

    The Legal agent monitors these and sends high-priority notifications
    when a deadline is within 30 days.
    """
    # TODO (Prompt 4): query legal_documents for deadline-type items
    return _NOT_IMPLEMENTED


@router.post("/run", summary="Manually trigger the Legal agent")
def run_legal():
    """Enqueue a manual run of the Legal agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("legal", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Legal agent last run status")
def legal_status():
    """Return last run timestamp and count of open checklist items."""
    return {"agent": "legal", "status": "idle", "last_run": None}
