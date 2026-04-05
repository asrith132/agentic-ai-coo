"""
api/agents/legal.py — /api/legal/* routes

All stateful operations (generate, draft) call the LegalAgent synchronously
in the route handler. This means the HTTP response waits for the LLM call
(typically 5–15 seconds). For production, swap to Celery task dispatch and
return a task_id for polling.

Routes:
  POST /api/legal/generate        — Generate compliance checklist
  GET  /api/legal/checklist       — Current checklist with item statuses
  POST /api/legal/draft/{id}      — Draft a document for a checklist item
  GET  /api/legal/deadlines       — Items with upcoming deadlines (30 days)
  POST /api/legal/run             — Manually trigger the Legal agent
  GET  /api/legal/status          — Last run status + open item counts
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.db.supabase_client import get_client
from app.schemas.triggers import AgentTrigger, TriggerType

router = APIRouter(prefix="/api/legal", tags=["Legal"])


# ── Request models ────────────────────────────────────────────────────────────

class GenerateChecklistRequest(BaseModel):
    entity_type:  str          # e.g. "Delaware C-Corp", "LLC", "Ltd"
    jurisdiction: str          # e.g. "Delaware, USA", "England and Wales"
    stage:        str = "pre_launch"    # pre_launch | launched | fundraising | series_a
    product_type: str = "SaaS"          # SaaS | marketplace | hardware | fintech | healthtech


class DraftDocumentRequest(BaseModel):
    context: str | None = None  # optional additional detail for the draft


# ── Helper: run agent synchronously ──────────────────────────────────────────

def _run_legal_agent(trigger: AgentTrigger) -> dict:
    """
    Instantiate LegalAgent and call run() synchronously.
    The global + domain context is loaded inside agent.run().
    """
    from app.agents.legal.agent import LegalAgent
    agent = LegalAgent()
    return agent.run(trigger)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/generate",
    summary="Generate a tailored compliance checklist",
    status_code=201,
)
def generate_checklist(body: GenerateChecklistRequest):
    """
    Use the LLM to generate a compliance checklist tailored to the company's
    entity type, jurisdiction, stage, and product type.

    The agent:
    1. Calls Claude to produce 12–18 prioritised checklist items
    2. Resolves deadline rules into actual due dates
    3. Inserts all items into the `legal_checklist` table
    4. Emits `legal.deadline_approaching` events for any already-overdue items
    5. Returns the full checklist

    **Note:** This call takes 5–15 seconds (LLM generation).
    """
    trigger = AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input="generate_checklist",
        parameters={
            "entity_type":  body.entity_type,
            "jurisdiction": body.jurisdiction,
            "stage":        body.stage,
            "product_type": body.product_type,
        },
    )
    try:
        return _run_legal_agent(trigger)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/checklist",
    summary="Get current compliance checklist",
)
def get_checklist(
    category: str | None = Query(default=None, description="Filter by category"),
    status: str | None = Query(
        default=None,
        description="Filter by status: pending | in_progress | done | overdue",
    ),
):
    """
    Return all checklist items sorted by priority (urgent → high → medium → low),
    then by due_date ascending within each priority bucket.

    Optionally filter by `category` or `status`.
    """
    client = get_client()

    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

    query = client.table("legal_checklist").select("*")
    if category:
        query = query.eq("category", category)
    if status:
        query = query.eq("status", status)

    resp = query.execute()
    items = resp.data or []

    # Sort: priority first, then due_date (None sorts last)
    items.sort(key=lambda x: (
        priority_order.get(x.get("priority", "low"), 99),
        x.get("due_date") or "9999-99-99",
    ))

    return {"items": items, "total": len(items)}


@router.post(
    "/draft/{checklist_item_id}",
    summary="Draft a legal document for a checklist item",
    status_code=201,
)
def draft_document(checklist_item_id: str, body: DraftDocumentRequest):
    """
    Ask the Legal agent to draft a legal document for the specified checklist item.

    The agent:
    1. Loads the checklist item to determine document type
    2. Uses company profile + product details from global context
    3. Calls Claude to produce a complete first draft
    4. Stores it in `legal_documents` with status "draft"
    5. Creates an approval request (required before marking final)
    6. Updates the checklist item status to "in_progress"

    **Autonomy:** Drafting is autonomous. Marking final requires user approval.
    **Note:** This call takes 10–30 seconds (document-length LLM generation).
    """
    trigger = AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input="draft_document",
        parameters={
            "checklist_item_id": checklist_item_id,
            "context":           body.context or "",
        },
    )
    try:
        return _run_legal_agent(trigger)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/deadlines",
    summary="Upcoming compliance deadlines",
)
def list_deadlines(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Return items due within this many days (also includes overdue)",
    ),
):
    """
    Return checklist items with deadlines due within `days` days (default 30),
    plus any items that are already overdue. Sorted by due_date ascending.

    This is the data source for the dashboard deadline ticker.
    """
    from datetime import date, timedelta

    client = get_client()
    cutoff = (date.today() + timedelta(days=days)).isoformat()

    resp = (
        client.table("legal_checklist")
        .select("*")
        .neq("status", "done")
        .not_.is_("due_date", "null")
        .lte("due_date", cutoff)
        .order("due_date", desc=False)
        .execute()
    )
    items = resp.data or []

    # Annotate each item with days_remaining
    today = date.today()
    for item in items:
        due = date.fromisoformat(item["due_date"])
        item["days_remaining"] = (due - today).days

    return {"items": items, "total": len(items), "window_days": days}


@router.get(
    "/documents",
    summary="List drafted legal documents",
)
def list_documents(
    status: str | None = Query(default=None, description="draft | review | final"),
    document_type: str | None = Query(default=None),
):
    """
    Return all entries in legal_documents, optionally filtered by status or type.
    Document content (full text) is included — consider paginating for large sets.
    """
    client = get_client()
    query = (
        client.table("legal_documents")
        .select("id, document_type, title, status, checklist_item_id, approval_id, created_at, updated_at")
        .order("created_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    if document_type:
        query = query.eq("document_type", document_type)

    resp = query.execute()
    return {"documents": resp.data or [], "total": len(resp.data or [])}


@router.get(
    "/documents/{document_id}",
    summary="Get a specific legal document including full content",
)
def get_document(document_id: str):
    """Return the full document record including content text."""
    client = get_client()
    resp = (
        client.table("legal_documents")
        .select("*")
        .eq("id", document_id)
        .maybe_single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    return resp.data


@router.post(
    "/run",
    summary="Manually trigger the Legal agent (deadline check)",
)
def run_legal():
    """
    Enqueue a manual run of the Legal agent via Celery.
    Equivalent to the daily 8 AM deadline check task.
    """
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run(
        "legal",
        {"type": "scheduled", "task_name": "deadline_check"},
    )


@router.get(
    "/status",
    summary="Legal agent status and open item counts",
)
def legal_status():
    """
    Return a summary of the current legal compliance state:
    open item counts by status, next upcoming deadline, and document counts.
    """
    from datetime import date

    client = get_client()

    # Checklist counts
    cl_resp = client.table("legal_checklist").select("status, due_date").execute()
    rows = cl_resp.data or []

    counts: dict[str, int] = {}
    next_deadline = None
    today = date.today()

    for row in rows:
        s = row["status"]
        counts[s] = counts.get(s, 0) + 1
        if row.get("due_date") and s not in ("done",):
            d = date.fromisoformat(row["due_date"])
            if d >= today and (next_deadline is None or d < next_deadline):
                next_deadline = d

    # Document counts
    doc_resp = client.table("legal_documents").select("status").execute()
    doc_counts: dict[str, int] = {}
    for row in (doc_resp.data or []):
        s = row["status"]
        doc_counts[s] = doc_counts.get(s, 0) + 1

    return {
        "agent":           "legal",
        "status":          "active",
        "checklist":       counts,
        "total_items":     len(rows),
        "next_deadline":   next_deadline.isoformat() if next_deadline else None,
        "documents":       doc_counts,
        "total_documents": sum(doc_counts.values()),
    }


# ── File upload ───────────────────────────────────────────────────────────────

@router.post("/upload", summary="Upload a legal document for the chatbot to reference")
async def upload_legal_file(file: UploadFile = File(...)):
    """Store a legal document (contract, policy, brief) for chat context."""
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = content_bytes.decode("latin-1")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    file_type = ext if ext in {"pdf", "txt", "md", "docx", "csv"} else "text"

    try:
        get_client().table("legal_uploads").insert({
            "filename": file.filename,
            "file_type": file_type,
            "content": content,
        }).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"filename": file.filename, "file_type": file_type, "size": len(content)}


# ── Chat ──────────────────────────────────────────────────────────────────────

class LegalChatMessage(BaseModel):
    role: str
    content: str

class LegalChatRequest(BaseModel):
    message: str
    history: list[LegalChatMessage] = []


def _build_legal_system_prompt(
    global_ctx: Any | None,
    checklist_items: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    uploaded_files: list[dict[str, Any]],
) -> str:
    parts: list[str] = []

    # 1. Business context
    if global_ctx:
        cp = global_ctx.company_profile
        bs = global_ctx.business_state
        parts += [
            "=== BUSINESS CONTEXT ===",
            f"Company:      {cp.name or '(not set)'}",
            f"Entity type:  {cp.entity_type or '(not set)'}",
            f"Jurisdiction: {cp.jurisdiction or '(not set)'}",
            f"Product:      {cp.product_name} — {cp.product_description}",
            f"Phase:        {bs.phase}",
            "========================",
            "",
        ]

    company_name = global_ctx.company_profile.name if global_ctx else "this company"
    parts += [
        f"You are the Legal Agent for {company_name}. "
        "You have access to the company's compliance checklist, drafted documents, and any uploaded legal files shown below. "
        "Answer questions accurately. Flag risks clearly. "
        "Do not give final legal advice — recommend consulting a qualified attorney for anything binding.",
        "",
    ]

    # 2. Compliance checklist
    if checklist_items:
        overdue = [i for i in checklist_items if i.get("status") == "overdue"]
        pending = [i for i in checklist_items if i.get("status") == "pending"]
        done = [i for i in checklist_items if i.get("status") == "done"]
        parts += [
            f"## Compliance Checklist ({len(checklist_items)} items)",
            f"- Overdue: {len(overdue)}, Pending: {len(pending)}, Done: {len(done)}",
        ]
        for item in checklist_items[:30]:
            due = f" | due {item['due_date']}" if item.get("due_date") else ""
            parts.append(
                f"  [{item.get('status','?').upper()}] [{item.get('priority','?')}] "
                f"{item.get('item','')} ({item.get('category','')}){due}"
            )
        parts.append("")

    # 3. Drafted documents
    if documents:
        parts.append(f"## Legal Documents ({len(documents)} drafted)")
        for doc in documents:
            parts.append(
                f"  [{doc.get('status','?').upper()}] {doc.get('title','')} "
                f"({doc.get('document_type','')})"
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


@router.post("/chat", summary="Conversational Q&A about legal compliance")
def legal_chat(body: LegalChatRequest):
    """Answer questions about compliance status, documents, and uploaded legal files."""
    from app.core.llm import llm
    from app.core.context import get_global_context

    client = get_client()

    try:
        global_ctx = get_global_context()
    except Exception:
        global_ctx = None

    checklist_resp = client.table("legal_checklist").select("*").execute()
    checklist_items = checklist_resp.data or []

    docs_resp = (
        client.table("legal_documents")
        .select("id, document_type, title, status, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    documents = docs_resp.data or []

    uploads_resp = (
        client.table("legal_uploads")
        .select("filename, file_type, content, uploaded_at")
        .order("uploaded_at", desc=True)
        .limit(3)
        .execute()
    )
    uploaded_files = uploads_resp.data or []

    system_prompt = _build_legal_system_prompt(global_ctx, checklist_items, documents, uploaded_files)

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    try:
        reply = llm.conversation(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.4,
            max_tokens=1024,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"reply": reply}
