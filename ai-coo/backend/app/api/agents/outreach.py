"""
api/agents/outreach.py — /api/outreach/* routes

Routes:
  POST /api/outreach/research      — Research a contact (name + company → enriched profile)
  POST /api/outreach/draft         — Draft a personalized cold email for a contact
  POST /api/outreach/send/{id}     — Send a previously drafted and approved email
  GET  /api/outreach/contacts      — List all contacts and their pipeline status
  GET  /api/outreach/messages      — Full message history (sent + received)
  POST /api/outreach/run           — Manually trigger the Outreach agent
  GET  /api/outreach/status        — Last run status
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/outreach", tags=["Outreach"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


class ResearchContactRequest(BaseModel):
    name: str
    company: str
    linkedin_url: str | None = None


class DraftEmailRequest(BaseModel):
    contact_id: str | None = None
    name: str | None = None
    company: str | None = None
    context: str | None = None   # optional extra context for personalization


@router.post(
    "/research",
    summary="Research a contact",
)
def research_contact(body: ResearchContactRequest):
    """
    Look up a contact by name + company and return an enriched profile
    (role, LinkedIn, recent activity, mutual signals).

    Used before drafting an email to personalize the outreach.
    Triggers the Outreach agent's scraping + enrichment tools.
    """
    # TODO (Prompt 4): run enrichment tools and return structured profile
    return _NOT_IMPLEMENTED


@router.post(
    "/draft",
    summary="Draft a personalized cold email",
)
def draft_email(body: DraftEmailRequest):
    """
    Use the LLM + brand voice + ICP data to draft a personalized cold email.
    The draft is stored in the outreach_emails table with status="draft" and
    an approval record is created for the user to review before sending.
    """
    # TODO (Prompt 4): call OutreachAgent to draft and create approval
    return _NOT_IMPLEMENTED


@router.post(
    "/send/{email_id}",
    summary="Send an approved email",
)
def send_email(email_id: str):
    """
    Send a previously drafted email that has been approved.
    Updates the email record status to "sent" and records the send timestamp.
    Raises 409 if the email is not in "approved" status.
    """
    # TODO (Prompt 4): verify approval status, call Gmail send tool
    return _NOT_IMPLEMENTED


@router.get(
    "/contacts",
    summary="List all contacts",
)
def list_contacts(
    status: str | None = Query(default=None, description="Filter by status: new|contacted|replied|booked|dead"),
    limit: int = Query(default=50, le=200),
):
    """
    Return all contacts with their current pipeline status, last contact
    date, and company info. Used by the dashboard CRM view.
    """
    # TODO (Prompt 4): query outreach_leads table
    return _NOT_IMPLEMENTED


@router.get(
    "/messages",
    summary="Message history",
)
def list_messages(
    contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """
    Return the full email thread history (sent + received), optionally
    filtered by contact. Used by the dashboard conversation view.
    """
    # TODO (Prompt 4): query outreach_emails table
    return _NOT_IMPLEMENTED


@router.post("/run", summary="Manually trigger the Outreach agent")
def run_outreach():
    """Enqueue a manual run of the Outreach agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("outreach", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Outreach agent last run status")
def outreach_status():
    """Return last run timestamp and pipeline summary."""
    return {"agent": "outreach", "status": "idle", "last_run": None}
