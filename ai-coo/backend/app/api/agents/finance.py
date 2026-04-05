"""
api/agents/finance.py — /api/finance/* routes

Routes:
  POST /api/finance/upload        — Upload a bank/Stripe CSV and run the Finance agent
  GET  /api/finance/transactions  — Categorized transaction list
  GET  /api/finance/summary       — Plain English financial health summary
  GET  /api/finance/runway        — Current runway + burn from latest snapshot
  GET  /api/finance/snapshots     — All monthly snapshots (for charting)
  POST /api/finance/run           — Manually trigger the Finance agent
  GET  /api/finance/status        — Live counts + latest snapshot
  POST /api/finance/chat          — Conversational Q&A about financial data
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.db.supabase_client import get_client

router = APIRouter(prefix="/api/finance", tags=["Finance"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _run_finance_agent(params: dict) -> dict:
    from app.agents.finance.agent import FinanceAgent
    from app.schemas.triggers import AgentTrigger, TriggerType

    agent = FinanceAgent()
    trigger = AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input="run",
        parameters=params,
    )
    return agent.run(trigger)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/upload", summary="Upload a bank statement or Stripe CSV")
async def upload_statement(
    file: UploadFile = File(...),
    current_balance: float | None = Form(default=None),
    replace_existing: bool = Form(default=False),
    notes: str | None = Form(default=None),
):
    """
    Upload a CSV export from a bank or Stripe. The Finance agent parses,
    categorizes, and persists all transactions, then computes a snapshot
    (burn, revenue, runway) and emits events.

    Supports any CSV with date, amount, description columns.
    Optionally pass `current_balance` (your cash balance today) to calculate runway.
    """
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode CSV file — ensure UTF-8 or Latin-1 encoding.")

    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Persist raw file content so the chatbot can reference it directly
    try:
        get_client().table("finance_uploads").insert({
            "filename": file.filename,
            "file_type": "csv",
            "content": csv_text,
        }).execute()
    except Exception:
        pass  # non-fatal — don't block the upload if this fails

    try:
        result = _run_finance_agent({
            "csv_content": csv_text,
            "current_balance": current_balance,
            "replace_existing": replace_existing,
            "notes": notes,
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@router.get("/transactions", summary="List categorized transactions")
def list_transactions(
    limit: int = Query(default=50, le=500),
    category: str | None = Query(default=None, description="Filter by category"),
    month: str | None = Query(default=None, description="Filter by month (YYYY-MM)"),
):
    """
    Return parsed and categorized transactions, newest first.
    Each row: date, description, amount, category, subcategory, is_recurring, source.
    """
    client = get_client()
    query = (
        client.table("finance_transactions")
        .select("*")
        .order("date", desc=True)
        .limit(limit)
    )
    if category:
        query = query.eq("category", category)
    if month:
        # month = "YYYY-MM", filter date >= YYYY-MM-01 and < next month
        from datetime import date, timedelta
        try:
            year, mo = int(month[:4]), int(month[5:7])
            start = date(year, mo, 1).isoformat()
            end_mo = mo + 1 if mo < 12 else 1
            end_yr = year if mo < 12 else year + 1
            end = date(end_yr, end_mo, 1).isoformat()
            query = query.gte("date", start).lt("date", end)
        except Exception:
            pass

    resp = query.execute()
    return {"transactions": resp.data or [], "total": len(resp.data or [])}


@router.get("/runway", summary="Current runway calculation")
def runway():
    """
    Return the latest financial snapshot: cash balance, monthly burn,
    runway in months, revenue, and net. Also includes the month the
    snapshot covers and when it was last updated.
    """
    client = get_client()
    resp = (
        client.table("finance_snapshots")
        .select("*")
        .order("month", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return {
            "snapshot": None,
            "message": "No financial data yet. Upload a CSV to get started.",
        }

    snapshot = resp.data[0]
    return {
        "snapshot": snapshot,
        "runway_months": snapshot.get("runway_months"),
        "monthly_burn": snapshot.get("total_expenses"),
        "monthly_revenue": snapshot.get("total_income"),
        "net": snapshot.get("net"),
        "current_balance": snapshot.get("current_balance"),
        "month": snapshot.get("month"),
    }


@router.get("/summary", summary="Plain English financial health summary")
def financial_summary():
    """
    Return an LLM-generated natural language summary of the current financial
    position: revenue, burn, runway, and any spending anomalies.
    """
    from app.agents.finance.tools import (
        detect_spending_anomalies,
        generate_plain_english_summary,
        FinanceDataError,
    )

    client = get_client()
    resp = (
        client.table("finance_snapshots")
        .select("*")
        .order("month", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return {
            "summary": "No financial data yet. Upload a CSV to get started.",
            "snapshot": None,
            "anomalies": [],
        }

    snapshot = resp.data[0]
    try:
        anomalies = detect_spending_anomalies(month=snapshot["month"])
    except FinanceDataError:
        anomalies = []

    summary = generate_plain_english_summary(snapshot, anomalies)
    return {"summary": summary, "snapshot": snapshot, "anomalies": anomalies}


@router.get("/snapshots", summary="All monthly snapshots")
def list_snapshots(limit: int = Query(default=12, le=60)):
    """Return monthly snapshots newest-first, useful for charting trends."""
    client = get_client()
    resp = (
        client.table("finance_snapshots")
        .select("*")
        .order("month", desc=True)
        .limit(limit)
        .execute()
    )
    return {"snapshots": resp.data or [], "total": len(resp.data or [])}


@router.post("/run", summary="Manually trigger the Finance agent")
def run_finance():
    """Trigger a Finance agent run without uploading new data."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("finance", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Finance agent status and live counts")
def finance_status():
    """Return transaction count, snapshot count, and latest snapshot summary."""
    client = get_client()

    tx_resp = (
        client.table("finance_transactions")
        .select("id", count="exact")
        .execute()
    )
    snap_resp = (
        client.table("finance_snapshots")
        .select("*")
        .order("month", desc=True)
        .limit(1)
        .execute()
    )

    latest = snap_resp.data[0] if snap_resp.data else None
    tx_count = getattr(tx_resp, "count", None) or len(tx_resp.data or [])

    return {
        "agent": "finance",
        "status": "active" if latest else "idle",
        "transaction_count": tx_count,
        "latest_snapshot": {
            "month": latest.get("month"),
            "runway_months": latest.get("runway_months"),
            "monthly_burn": latest.get("total_expenses"),
            "monthly_revenue": latest.get("total_income"),
            "net": latest.get("net"),
        } if latest else None,
    }


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


def _build_finance_system_prompt(
    global_ctx: Any | None,
    snapshot: dict[str, Any] | None,
    all_snapshots: list[dict[str, Any]],
    recent_txs: list[dict[str, Any]],
    uploaded_files: list[dict[str, Any]] | None = None,
) -> str:
    parts: list[str] = []

    # ── 1. Business context from global_context (mirrors BaseAgent._build_context_header) ──
    if global_ctx:
        cp = global_ctx.company_profile
        bs = global_ctx.business_state
        bv = global_ctx.brand_voice
        priorities_str = (
            "\n".join(f"  - {p}" for p in bs.active_priorities)
            if bs.active_priorities else "  (none set)"
        )
        parts += [
            "=== BUSINESS CONTEXT ===",
            f"Company:   {cp.name or '(not set)'}",
            f"Product:   {cp.product_name} — {cp.product_description}",
            f"Phase:     {bs.phase}",
            f"Team size: {bs.team_size}",
            "Active priorities:",
            priorities_str,
        ]
        # Include recent events that finance emitted (weekly_summary, runway_warning, etc.)
        finance_events = [
            e for e in (global_ctx.recent_events or [])
            if e.get("source_agent") == "finance"
        ][-10:]
        if finance_events:
            parts.append("\nRecent finance events:")
            for e in finance_events:
                parts.append(f"  [{e.get('event_type')}] {e.get('summary')}")
        parts += ["========================", ""]

    # ── 2. Role instruction ──
    company_name = global_ctx.company_profile.name if global_ctx else "this company"
    parts += [
        f"You are the Finance Agent for {company_name}. "
        "You have access to the company's real financial data shown below. "
        "Answer questions concisely and accurately. "
        "Format currency as $12,345. "
        "If data is missing, say so rather than guessing.",
        "",
    ]

    # ── 3. Latest snapshot ──
    if snapshot:
        by_cat = snapshot.get("by_category") or {}
        top_cats = sorted(by_cat.items(), key=lambda x: float(x[1]), reverse=True)[:5]
        top_cat_str = ", ".join(f"{k}: ${float(v):,.0f}" for k, v in top_cats) or "none"
        runway = snapshot.get("runway_months")
        parts += [
            f"## Latest Snapshot ({snapshot.get('month', 'unknown')})",
            f"- Revenue:       ${float(snapshot.get('total_income') or 0):,.2f}",
            f"- Expenses:      ${float(snapshot.get('total_expenses') or 0):,.2f}",
            f"- Net:           ${float(snapshot.get('net') or 0):,.2f}",
            f"- Cash balance:  ${float(snapshot.get('current_balance') or 0):,.2f}" if snapshot.get('current_balance') else "- Cash balance:  not set",
            f"- Runway:        {f'{float(runway):.1f} months' if runway is not None else 'unknown'}",
            f"- Top categories: {top_cat_str}",
            "",
        ]
    else:
        parts += ["## Financial Data", "No snapshots found yet. Upload a CSV to get started.", ""]

    # ── 4. Historical snapshots (for trend questions) ──
    prior = [s for s in all_snapshots if s.get("month") != (snapshot or {}).get("month")]
    if prior:
        parts.append("## Historical Snapshots")
        for s in prior[:6]:
            parts.append(
                f"- {s.get('month')}: revenue ${float(s.get('total_income') or 0):,.0f}, "
                f"expenses ${float(s.get('total_expenses') or 0):,.0f}, "
                f"net ${float(s.get('net') or 0):,.0f}"
            )
        parts.append("")

    # ── 5. Recent transactions ──
    if recent_txs:
        parts.append(f"## Transactions (most recent {len(recent_txs)})")
        for tx in recent_txs:
            amt = float(tx.get("amount", 0))
            sign = "+" if amt > 0 else ""
            parts.append(
                f"- {tx.get('date')} | {str(tx.get('description', ''))[:45]} | "
                f"{sign}${amt:,.2f} | {tx.get('category')}"
            )
        parts.append("")

    # ── 6. Raw uploaded files ──
    if uploaded_files:
        for upload in uploaded_files:
            fname = upload.get("filename") or "uploaded file"
            uploaded_at = upload.get("uploaded_at", "")[:10]
            content = upload.get("content", "")
            # Truncate very large files to avoid exceeding context limits (~200KB)
            if len(content) > 40_000:
                content = content[:40_000] + "\n... (truncated)"
            parts += [
                f"## Raw File: {fname} (uploaded {uploaded_at})",
                content,
                "",
            ]

    return "\n".join(parts)


@router.post("/chat", summary="Conversational Q&A about financial data")
def finance_chat(body: ChatRequest):
    """
    Answer natural-language questions about the company's financial data.
    Loads global_context (shared business state the finance agent writes to) plus
    finance_snapshots and finance_transactions (the agent's domain storage).
    """
    from app.core.llm import llm
    from app.core.context import get_global_context

    client = get_client()

    # 1. Load global context (contains business state + recent events finance agent wrote)
    try:
        global_ctx = get_global_context()
    except Exception:
        global_ctx = None

    # 2. Load all snapshots (latest first, up to 12 for trend questions)
    snap_resp = (
        client.table("finance_snapshots")
        .select("*")
        .order("month", desc=True)
        .limit(12)
        .execute()
    )
    all_snapshots = snap_resp.data or []
    snapshot = all_snapshots[0] if all_snapshots else None

    # 3. Load recent transactions (all categories, newest first)
    tx_resp = (
        client.table("finance_transactions")
        .select("date, description, amount, category")
        .order("date", desc=True)
        .limit(50)
        .execute()
    )
    recent_txs = tx_resp.data or []

    # 4. Load raw uploaded files so the chatbot can answer file-specific questions
    uploads_resp = (
        client.table("finance_uploads")
        .select("filename, file_type, content, uploaded_at")
        .order("uploaded_at", desc=True)
        .limit(3)
        .execute()
    )
    uploaded_files = uploads_resp.data or []

    system_prompt = _build_finance_system_prompt(global_ctx, snapshot, all_snapshots, recent_txs, uploaded_files)

    # 4. Build multi-turn message list
    messages = [{"role": msg.role, "content": msg.content} for msg in body.history]
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
