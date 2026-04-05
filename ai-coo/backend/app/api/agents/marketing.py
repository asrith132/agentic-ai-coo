"""
api/agents/marketing.py — /api/marketing/* routes

Routes:
  POST /api/marketing/draft     — Draft a LinkedIn post (LLM + approval)
  POST /api/marketing/publish   — Publish an approved post to LinkedIn
  GET  /api/marketing/trends    — Recent LinkedIn trends
  GET  /api/marketing/content   — Content list by status
  POST /api/marketing/run       — Manually trigger the agent
  GET  /api/marketing/status    — Agent status
  POST /api/marketing/chat      — Conversational Q&A / content requests
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.marketing import tools
from app.agents.marketing.agent import MarketingAgent
from app.schemas.triggers import AgentTrigger, TriggerType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


# ── Request models ────────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    content_type: str = "thought_leadership"   # announcement | reply | thought_leadership | engagement
    platform: str = "linkedin"
    trend_id: str | None = None
    topic: str | None = None


class PublishRequest(BaseModel):
    content_id: str


class MarketingChatMessage(BaseModel):
    role: str
    content: str

class MarketingChatRequest(BaseModel):
    message: str
    history: list[MarketingChatMessage] = []


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/draft", status_code=201, summary="Draft a LinkedIn post")
def draft_content(body: DraftRequest):
    """
    Draft a post for LinkedIn. The agent uses global context (brand voice,
    product description) and optionally a trend or topic. Creates an
    approval request — user must approve before it can be published.
    """
    if body.platform not in tools.SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {body.platform}")
    if not body.trend_id and not body.topic:
        raise HTTPException(status_code=400, detail="Either trend_id or topic must be provided")

    agent = MarketingAgent()
    agent._global_context = agent.load_global_context()
    agent._domain_context = agent.load_domain_context()

    try:
        row = agent.draft_content(
            content_type=body.content_type,
            platform=body.platform,
            trend_id=body.trend_id,
            topic=body.topic,
        )
        return {"status": "draft_created", "content": row}
    except Exception as exc:
        logger.exception("Draft content failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/publish", summary="Publish an approved LinkedIn post")
def publish_content(body: PublishRequest):
    """
    Publish a post that has been approved. Verifies approval status before
    calling the LinkedIn API.
    """
    from app.core.approvals import get_pending_approvals

    content_row = tools.get_content(body.content_id)
    if not content_row:
        raise HTTPException(status_code=404, detail="Content not found")

    approval_id = content_row.get("approval_id")
    if approval_id:
        # Check that approval exists and is approved
        pending = get_pending_approvals()
        approval_ids = {str(a["id"]) for a in pending}
        if str(approval_id) in approval_ids:
            raise HTTPException(
                status_code=409,
                detail="Content is still pending approval — approve it first",
            )

    agent = MarketingAgent()
    agent._global_context = agent.load_global_context()
    agent._domain_context = {}

    result = agent._execute_approved_publish(body.content_id, content_row)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return {"status": "published", **result}


@router.get("/trends", summary="Recent LinkedIn trends")
def list_trends(limit: int = 20):
    return {"trends": tools.get_recent_trends(limit=limit), "count": 0}


@router.get("/content", summary="Marketing content by status")
def list_content(status: str = "pending_approval", limit: int = 20):
    valid = ("draft", "pending_approval", "published", "rejected")
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {valid}")
    items = tools.get_content_by_status(status, limit=limit)
    return {"content": items, "count": len(items)}


@router.post("/run", summary="Manually trigger the Marketing agent")
def run_marketing():
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("marketing", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="Marketing agent status")
def marketing_status():
    drafts    = tools.get_content_by_status("pending_approval", limit=100)
    published = tools.get_content_by_status("published", limit=100)
    trends    = tools.get_recent_trends(limit=100)
    return {
        "agent":           "marketing",
        "status":          "active",
        "pending_posts":   len(drafts),
        "published_posts": len(published),
        "trends_tracked":  len(trends),
    }


# ── Chat ──────────────────────────────────────────────────────────────────────

def _build_marketing_system_prompt(
    global_ctx: Any | None,
    posts: list[dict[str, Any]],
    trends: list[dict[str, Any]],
) -> str:
    parts: list[str] = []

    if global_ctx:
        cp = global_ctx.company_profile
        bv = global_ctx.brand_voice
        tc = global_ctx.target_customer
        parts += [
            "=== BUSINESS CONTEXT ===",
            f"Company:     {cp.name or '(not set)'}",
            f"Product:     {cp.product_name} — {cp.product_description}",
            f"Brand tone:  {bv.tone or '(not set)'}",
            f"ICP:         {tc.persona or '(not set)'} in {tc.industry or '(not set)'}",
            "========================",
            "",
        ]

    company_name = global_ctx.company_profile.name if global_ctx else "this company"
    parts += [
        f"You are the Marketing Agent for {company_name}. "
        "You manage the company's LinkedIn presence. "
        "You can draft posts, analyze trends, and advise on content strategy. "
        "When the user asks you to draft a post, respond with the draft AND use this exact format:",
        "",
        "  <draft_post>",
        '  {"content_type": "thought_leadership", "platform": "linkedin", "topic": "..."}',
        "  </draft_post>",
        "",
        "content_type options: announcement | thought_leadership | engagement | reply",
        "",
    ]

    if posts:
        parts.append(f"## Content Pipeline ({len(posts)} posts)")
        for p in posts[:10]:
            preview = (p.get("body") or "")[:80].replace("\n", " ")
            parts.append(
                f"  [{p.get('status','?').upper()}] [{p.get('platform','?')}] "
                f"{p.get('content_type','?')} — {preview}…"
            )
        parts.append("")

    if trends:
        parts.append(f"## Recent LinkedIn Trends ({len(trends)})")
        for t in trends[:8]:
            parts.append(
                f"  [score {t.get('relevance_score',0)}] {t.get('topic','')} "
                f"— {t.get('suggested_action','')}"
            )
        parts.append("")

    return "\n".join(parts)


@router.post("/chat", summary="Conversational chat with the Marketing agent")
def marketing_chat(body: MarketingChatRequest):
    """
    Chat with the Marketing agent. Can answer questions about content strategy,
    draft LinkedIn posts on request, and review the content pipeline.
    """
    from app.core.llm import llm
    from app.core.context import get_global_context, CONTEXT_EXTRACTION_PROMPT, extract_and_save_context

    try:
        global_ctx = get_global_context()
    except Exception:
        global_ctx = None

    posts  = tools.get_content_by_status("pending_approval", limit=20) + tools.get_content_by_status("draft", limit=10)
    trends = tools.get_recent_trends(limit=15)

    system_prompt  = _build_marketing_system_prompt(global_ctx, posts, trends)
    system_prompt += CONTEXT_EXTRACTION_PROMPT

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    try:
        raw_reply = llm.chat_conversation(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.6,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.exception("Marketing chat LLM call failed")
        raise HTTPException(status_code=500, detail=str(exc))

    # Parse <draft_post> blocks and create real drafts
    import re as _re, json as _json
    drafted_posts: list[dict] = []

    def _handle_draft_block(match: "_re.Match") -> str:
        try:
            data = _json.loads(match.group(1).strip())
            topic        = data.get("topic", "").strip()
            content_type = data.get("content_type", "thought_leadership").strip()
            platform     = data.get("platform", "linkedin").strip()
            if not topic:
                return ""
            agent = MarketingAgent()
            agent._global_context = agent.load_global_context()
            agent._domain_context = {}
            post = agent.draft_content(
                content_type=content_type,
                platform=platform,
                topic=topic,
            )
            drafted_posts.append(post)
        except Exception:
            logger.warning("Marketing chat: failed to parse draft_post block")
        return ""

    clean_reply = _re.sub(
        r"<draft_post>\s*([\s\S]*?)\s*</draft_post>",
        _handle_draft_block,
        raw_reply,
    ).strip()

    clean_reply = extract_and_save_context(clean_reply, "marketing")

    return {"reply": clean_reply, "posts_drafted": drafted_posts}
