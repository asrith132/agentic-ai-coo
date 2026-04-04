"""
api/agents/outreach.py — /api/outreach/* routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.outreach.agent import OutreachAgent
from app.agents.outreach import tools

router = APIRouter(prefix="/api/outreach", tags=["Outreach"])


class ResearchContactRequest(BaseModel):
    name: str
    company: str
    context: str | None = None
    source: str = "manual"
    status: str = "cold"
    contact_type: str = "customer"


class DraftEmailRequest(BaseModel):
    contact_id: str
    email_type: str = Field(pattern="^(cold|follow_up|investor|partnership)$")
    custom_notes: str | None = None


class DiscoverContactsRequest(BaseModel):
    focus: str | None = None
    limit: int = Field(default=5, ge=1, le=10)
    contact_type: str = "customer"
    auto_research: bool = True


@router.post("/research", summary="Research a contact")
def research_contact(body: ResearchContactRequest):
    agent = OutreachAgent()
    try:
        return agent.research_contact(
            name=body.name,
            company=body.company,
            context=body.context,
            source=body.source,
            status=body.status,
            contact_type=body.contact_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/draft", summary="Draft a personalized email")
def draft_email(body: DraftEmailRequest):
    agent = OutreachAgent()
    try:
        return agent.draft_email(
            contact_id=body.contact_id,
            email_type=body.email_type,
            custom_notes=body.custom_notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/discover", summary="Discover high-fit contacts autonomously")
def discover_contacts(body: DiscoverContactsRequest):
    agent = OutreachAgent()
    try:
        return agent.discover_contacts(
            focus=body.focus,
            limit=body.limit,
            contact_type=body.contact_type,
            auto_research=body.auto_research,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/send/{message_id}", summary="Send an approved email")
def send_email(message_id: str):
    agent = OutreachAgent()
    try:
        return agent.send_message(message_id=message_id)
    except ValueError as exc:
        if "not approved" in str(exc) or "pending" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/contacts", summary="List all contacts")
def list_contacts(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    return tools.list_contacts(status=status, limit=limit)


@router.get("/messages", summary="Message history")
def list_messages(
    contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    return tools.list_messages(contact_id=contact_id, limit=limit)


@router.post("/run", summary="Manually trigger the Outreach agent")
def run_outreach():
    from app.api.agents._task_dispatch import dispatch_agent_run

    return dispatch_agent_run("outreach", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Outreach agent last run status")
def outreach_status():
    return {
        "agent": "outreach",
        "status": "ready",
        "contacts": len(tools.list_contacts(limit=200)),
        "messages": len(tools.list_messages(limit=200)),
    }
