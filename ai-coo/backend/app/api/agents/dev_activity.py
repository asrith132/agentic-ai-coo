"""
api/agents/dev_activity.py — /api/dev/* routes

Routes:
  POST /api/dev/webhook    — GitHub webhook receiver (HMAC-SHA256 verified)
  GET  /api/dev/commits    — Recent parsed commits from dev_commits table
  GET  /api/dev/features   — Feature map from dev_features table
  POST /api/dev/run        — Manually trigger the agent
  GET  /api/dev/status     — Commit counts, feature counts, last commit SHA
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.config import settings
from app.agents.dev_activity.tools import (
    parse_pr_merged_event,
    parse_push_event,
    verify_github_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["Dev Activity"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_dev_agent(commit_data: dict) -> dict:
    """Instantiate DevActivityAgent and process a commit synchronously."""
    from app.agents.dev_activity.agent import DevActivityAgent
    from app.agents.pm.agent import PMAgent
    from app.schemas.triggers import AgentTrigger, TriggerType

    agent   = DevActivityAgent()
    trigger = AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input="process_commit",
        parameters={"commit_data": commit_data},
    )
    result = agent.run(trigger)

    # After dev agent emits events, immediately wake the PM agent to consume them
    if result.get("status") == "ok":
        try:
            pm_agent = PMAgent()
            pm_trigger = AgentTrigger(type=TriggerType.EVENT)
            pm_agent.run(pm_trigger)
        except Exception:
            logger.exception("PM agent event processing failed after webhook commit")

    return result


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/webhook",
    summary="GitHub webhook receiver",
    status_code=200,
)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    """
    Receive and verify GitHub webhook payloads (push, pull_request).

    Validates the HMAC-SHA256 signature using GITHUB_WEBHOOK_SECRET.
    Runs the DevActivityAgent synchronously for each recognised event.

    GitHub setup: Settings → Webhooks → Add webhook
      Payload URL:   https://your-domain/api/dev/webhook
      Content type:  application/json
      Events:        Just the push event  (or also pull_request)
    """
    body = await request.body()

    # ── Signature verification ─────────────────────────────────────────────
    if settings.github_webhook_secret:
        sig = x_hub_signature_256 or ""
        if not verify_github_signature(body, sig, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # ── Parse payload ──────────────────────────────────────────────────────
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Payload is not valid JSON")

    event_type = (x_github_event or "push").lower()
    logger.info("GitHub webhook received: event=%s", event_type)

    # ── ping — sent by GitHub on webhook creation ──────────────────────────
    if event_type == "ping":
        return {"status": "ok", "message": "pong"}

    # ── push ───────────────────────────────────────────────────────────────
    if event_type == "push":
        commit_data = parse_push_event(payload)
        if not commit_data:
            # Tag push or empty push — no commits to process
            return {"status": "ok", "message": "no commits to process"}

        result = _run_dev_agent(commit_data)
        return {"status": "ok", "processed": result}

    # ── pull_request (merged only) ─────────────────────────────────────────
    if event_type == "pull_request":
        action = payload.get("action", "")
        if action != "closed":
            # Only care about closed (potentially merged) PRs
            return {"status": "ok", "message": f"pr action '{action}' ignored"}

        commit_data = parse_pr_merged_event(payload)
        if not commit_data:
            return {"status": "ok", "message": "pr closed but not merged"}

        result = _run_dev_agent(commit_data)
        return {"status": "ok", "processed": result}

    # ── Other events — acknowledge without processing ──────────────────────
    logger.debug("GitHub webhook: ignoring event type '%s'", event_type)
    return {"status": "ok", "message": f"event '{event_type}' not processed"}


@router.get(
    "/commits",
    summary="List recent parsed commits",
)
def list_commits(
    limit: int = Query(default=20, ge=1, le=100),
    branch: str | None = Query(default=None, description="Filter by branch name"),
):
    """
    Return recent commits that have been parsed by the Dev Activity agent.

    Each commit includes the LLM-generated plain-English summary alongside
    the raw commit metadata (SHA, author, timestamp, files changed).
    """
    from app.db.supabase_client import get_client

    client = get_client()
    query  = (
        client.table("dev_commits")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if branch:
        query = query.eq("branch", branch)

    resp = query.execute()
    return {"commits": resp.data or [], "total": len(resp.data or [])}


@router.get(
    "/features",
    summary="Get feature map derived from commits",
)
def get_feature_map(
    status: str | None = Query(
        default=None,
        description="Filter by status: shipped | in_progress | deprecated",
    ),
):
    """
    Return the current feature map — all features the Dev Activity agent has
    detected from commit analysis, with their descriptions and related commit SHAs.

    This is the authoritative source of shipped features for the PM and
    Marketing agents.
    """
    from app.db.supabase_client import get_client

    client = get_client()
    query  = (
        client.table("dev_features")
        .select("*")
        .order("shipped_at", desc=True)
    )
    if status:
        query = query.eq("status", status)

    resp = query.execute()
    return {"features": resp.data or [], "total": len(resp.data or [])}


@router.post(
    "/run",
    summary="Manually trigger the Dev Activity agent",
)
def run_dev_activity():
    """
    Enqueue a manual run of the Dev Activity agent via Celery.
    Returns a status summary (commit count, feature count, last commit).
    """
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run(
        "dev_activity",
        {"type": "user_request", "user_input": "manual run"},
    )


@router.get(
    "/status",
    summary="Dev Activity agent status",
)
def dev_activity_status():
    """
    Return a live summary of the dev activity state:
    total commits parsed, total features detected, and most recent commit.
    """
    from app.db.supabase_client import get_client
    from datetime import date, timedelta

    client = get_client()

    # Total commits stored
    commits_resp = (
        client.table("dev_commits")
        .select("sha, timestamp, branch, parsed_summary")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    all_commits_resp = (
        client.table("dev_commits")
        .select("id", count="exact")
        .execute()
    )

    # Feature counts by status
    features_resp = (
        client.table("dev_features")
        .select("status")
        .execute()
    )
    feature_counts: dict[str, int] = {}
    for row in (features_resp.data or []):
        s = row["status"]
        feature_counts[s] = feature_counts.get(s, 0) + 1

    last_commit = commits_resp.data[0] if commits_resp.data else None

    return {
        "agent":          "dev_activity",
        "status":         "active",
        "total_commits":  getattr(all_commits_resp, "count", 0) or len(all_commits_resp.data or []),
        "features":       feature_counts,
        "total_features": sum(feature_counts.values()),
        "last_commit":    {
            "sha":     (last_commit["sha"][:12] if last_commit else None),
            "branch":  (last_commit.get("branch") if last_commit else None),
            "summary": (last_commit.get("parsed_summary") if last_commit else None),
        } if last_commit else None,
    }


# ── Chat ──────────────────────────────────────────────────────────────────────

class DevChatMessage(BaseModel):
    role: str
    content: str

class DevChatRequest(BaseModel):
    message: str
    history: list[DevChatMessage] = []


def _build_dev_system_prompt(
    global_ctx: Any | None,
    commits: list[dict[str, Any]],
    features: list[dict[str, Any]],
    dev_events: list[dict[str, Any]],
) -> str:
    parts: list[str] = []

    if global_ctx:
        cp = global_ctx.company_profile
        parts += [
            "=== BUSINESS CONTEXT ===",
            f"Company:  {cp.name or '(not set)'}",
            f"Product:  {cp.product_name} — {cp.product_description}",
            f"Stack:    {', '.join(cp.tech_stack) if cp.tech_stack else '(not set)'}",
            "========================",
            "",
        ]

    company_name = global_ctx.company_profile.name if global_ctx else "this company"
    parts += [
        f"You are the Dev Activity Agent for {company_name}. "
        "You have access to GitHub commit history, the shipped feature map, and dev events. "
        "Answer questions about what has shipped, what changed, technical debt, release history, and engineering velocity. "
        "Be concise and accurate.",
        "",
    ]

    if commits:
        parts.append(f"## Recent Commits ({len(commits)})")
        for c in commits:
            ctype = f"[{c.get('commit_type','?')}] " if c.get('commit_type') else ""
            parts.append(
                f"- {(c.get('timestamp') or '')[:10]} | {ctype}"
                f"{c.get('parsed_summary') or c.get('message','')[:80]} "
                f"| {c.get('author','')} | {c.get('branch','')}"
            )
        parts.append("")

    if features:
        parts.append(f"## Shipped Features ({len(features)})")
        for f in features:
            parts.append(f"  - {f.get('feature_name','')} — {f.get('description','')[:80]}")
        parts.append("")

    if dev_events:
        parts.append(f"## Recent Dev Events ({len(dev_events)})")
        for ev in dev_events:
            parts.append(f"  [{ev.get('event_type','')}] {ev.get('summary','')}")
        parts.append("")

    return "\n".join(parts)


@router.post("/chat", summary="Conversational Q&A about dev activity")
def dev_chat(body: DevChatRequest):
    """Answer questions about commits, features, and dev events."""
    from app.core.llm import llm
    from app.core.context import get_global_context
    from app.db.supabase_client import get_client

    client = get_client()

    try:
        global_ctx = get_global_context()
    except Exception:
        global_ctx = None

    commits_resp = (
        client.table("dev_commits")
        .select("sha, message, author, branch, timestamp, parsed_summary, commit_type")
        .order("created_at", desc=True)
        .limit(40)
        .execute()
    )
    commits = commits_resp.data or []

    features_resp = (
        client.table("dev_features")
        .select("feature_name, description, status, shipped_at")
        .order("shipped_at", desc=True)
        .limit(30)
        .execute()
    )
    features = features_resp.data or []

    events_resp = (
        client.table("events")
        .select("event_type, summary, payload, priority, timestamp")
        .eq("source_agent", "dev_activity")
        .order("timestamp", desc=True)
        .limit(20)
        .execute()
    )
    dev_events = events_resp.data or []

    from app.core.context import CONTEXT_EXTRACTION_PROMPT, extract_and_save_context

    system_prompt = _build_dev_system_prompt(global_ctx, commits, features, dev_events)
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

    reply = extract_and_save_context(raw_reply, "dev_activity")
    return {"reply": reply}
