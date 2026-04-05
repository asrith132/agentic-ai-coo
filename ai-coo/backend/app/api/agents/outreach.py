"""
api/agents/outreach.py — /api/outreach/* routes
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.agents.outreach.agent import OutreachAgent
from app.agents.outreach import tools
from app.db.supabase_client import get_client

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
    channel: str | None = Field(default=None, pattern="^(email|linkedin_dm|reddit_dm|x_dm|unknown)?$")


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
            channel=body.channel,
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


# ── File upload ───────────────────────────────────────────────────────────────

@router.post("/upload", summary="Upload a prospect list or outreach brief")
async def upload_outreach_file(file: UploadFile = File(...)):
    """Store a CSV prospect list, email brief, or research doc for chat context."""
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = content_bytes.decode("latin-1")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    file_type = ext if ext in {"csv", "txt", "md"} else "text"

    try:
        get_client().table("outreach_uploads").insert({
            "filename": file.filename,
            "file_type": file_type,
            "content": content,
        }).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"filename": file.filename, "file_type": file_type, "size": len(content)}


# ── Chat ──────────────────────────────────────────────────────────────────────

class OutreachChatMessage(BaseModel):
    role: str
    content: str

class OutreachChatRequest(BaseModel):
    message: str
    history: list[OutreachChatMessage] = []


def _build_outreach_system_prompt(
    global_ctx: Any | None,
    contacts: list[dict[str, Any]],
    messages_data: list[dict[str, Any]],
    uploaded_files: list[dict[str, Any]],
) -> str:
    parts: list[str] = []

    # 1. Business context
    if global_ctx:
        cp = global_ctx.company_profile
        tc = global_ctx.target_customer
        bv = global_ctx.brand_voice
        parts += [
            "=== BUSINESS CONTEXT ===",
            f"Company:     {cp.name or '(not set)'}",
            f"Product:     {cp.product_name} — {cp.product_description}",
            f"ICP persona: {tc.persona or '(not set)'}",
            f"ICP industry: {tc.industry or '(not set)'}",
            f"ICP pain points: {', '.join(tc.pain_points) if tc.pain_points else '(not set)'}",
            f"Brand tone:  {bv.tone or '(not set)'}",
            "========================",
            "",
        ]

    company_name = global_ctx.company_profile.name if global_ctx else "this company"
    parts += [
        f"You are the Outreach Agent for {company_name}. "
        "You have access to the company's contact pipeline, message history, and any uploaded files. "
        "Help with outreach strategy, draft emails, analyze the pipeline, and suggest next actions. "
        "Be concise and actionable.",
        "",
        "When the user asks you to ADD a contact (founder, investor, customer, partner), respond with this block:",
        "  <add_contact>",
        '  {"name": "...", "company": "...", "role": "...", "contact_type": "partner|investor|customer", "email": null, "notes": "..."}',
        "  </add_contact>",
        "contact_type must be one of: partner, investor, customer",
        "",
    ]

    # 2. Contacts pipeline
    if contacts:
        by_status: dict[str, int] = {}
        for c in contacts:
            s = c.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        status_str = ", ".join(f"{s}: {n}" for s, n in sorted(by_status.items()))
        parts += [
            f"## Contact Pipeline ({len(contacts)} total — {status_str})",
        ]
        for c in contacts[:25]:
            last = c.get("last_contacted_at", "")[:10] if c.get("last_contacted_at") else "never"
            parts.append(
                f"  [{c.get('status','?').upper()}] {c.get('name','')} @ {c.get('company','')} "
                f"({c.get('contact_type','?')}) | last: {last}"
            )
        parts.append("")

    # 3. Recent messages
    if messages_data:
        parts.append(f"## Recent Messages ({len(messages_data)})")
        for m in messages_data[:15]:
            parts.append(
                f"  [{m.get('direction','?').upper()}] [{m.get('status','?')}] "
                f"{(m.get('subject') or m.get('body',''))[:60]}"
            )
        parts.append("")

    # 4. Uploaded files
    if uploaded_files:
        for upload in uploaded_files:
            fname = upload.get("filename") or "uploaded file"
            uploaded_at = upload.get("uploaded_at", "")[:10]
            content = upload.get("content", "")
            if len(content) > 40_000:
                content = content[:40_000] + "\n... (truncated)"
            parts += [
                f"## Uploaded File: {fname} (uploaded {uploaded_at})",
                content,
                "",
            ]

    return "\n".join(parts)


@router.post("/chat", summary="Conversational Q&A about outreach pipeline")
def outreach_chat(body: OutreachChatRequest):
    """Answer questions about contacts, pipeline, messages, and uploaded prospect lists."""
    from app.core.llm import llm
    from app.core.context import get_global_context

    client = get_client()

    try:
        global_ctx = get_global_context()
    except Exception:
        global_ctx = None

    contacts = tools.list_contacts(limit=100)
    messages_data = tools.list_messages(limit=50)

    uploads_resp = (
        client.table("outreach_uploads")
        .select("filename, file_type, content, uploaded_at")
        .order("uploaded_at", desc=True)
        .limit(3)
        .execute()
    )
    uploaded_files = uploads_resp.data or []

    from app.core.context import CONTEXT_EXTRACTION_PROMPT, extract_and_save_context

    system_prompt = _build_outreach_system_prompt(global_ctx, contacts, messages_data, uploaded_files)
    system_prompt += CONTEXT_EXTRACTION_PROMPT

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    try:
        raw_reply = llm.chat_conversation(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.4,
            max_tokens=1024,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Parse <add_contact> blocks and upsert directly into DB (no scraping needed)
    import re as _re, json as _json, logging as _logging
    _log = _logging.getLogger(__name__)
    added_contacts: list[dict] = []

    def _handle_add_contact(match: "_re.Match") -> str:
        try:
            data = _json.loads(match.group(1).strip())
            name    = (data.get("name") or "").strip()
            company = (data.get("company") or "").strip()
            if not name or not company:
                return ""
            contact = tools.upsert_contact(
                name=name,
                company=company,
                role=data.get("role") or None,
                email=data.get("email") or None,
                contact_type=data.get("contact_type", "customer"),
                status="cold",
                source="manual",
                notes=data.get("notes") or None,
            )
            added_contacts.append(contact)
        except Exception:
            _log.warning("Outreach chat: failed to parse add_contact block")
        return ""

    clean_reply = _re.sub(
        r"<add_contact>\s*([\s\S]*?)\s*</add_contact>",
        _handle_add_contact,
        raw_reply,
    ).strip()

    clean_reply = extract_and_save_context(clean_reply, "outreach")
    return {"reply": clean_reply, "contacts_added": added_contacts}
