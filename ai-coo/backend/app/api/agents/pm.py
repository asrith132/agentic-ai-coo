"""
api/agents/pm.py — /api/pm/* routes

Routes:
  GET   /api/pm/tasks              — Task backlog sorted by priority_score
  POST  /api/pm/tasks              — Create a task (LLM-scored)
  PATCH /api/pm/tasks/{id}         — Update task fields
  GET   /api/pm/milestones         — Milestones with progress counts
  POST  /api/pm/reprioritize       — Trigger AI reprioritization (synchronous)
  POST  /api/pm/run                — Enqueue a full agent run via Celery
  GET   /api/pm/status             — Agent status + top tasks
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.agents.pm import tools
from app.agents.pm.agent import PMAgent
from app.schemas.triggers import user_trigger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pm", tags=["Project Management"])


# ── Request models ────────────────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    milestone_id: str | None = None
    due_date: str | None = None


class PatchTaskRequest(BaseModel):
    title: str | None = None
    status: str | None = None          # pending_approval | todo | in_progress | blocked | done
    priority_score: float | None = None
    assigned_to: str | None = None
    description: str | None = None
    milestone_id: str | None = None
    due_date: str | None = None


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tasks", summary="Task backlog sorted by priority")
def list_tasks(
    status: str | None = Query(default=None, description="todo|in_progress|blocked|done"),
    limit: int = Query(default=50, le=200),
):
    """Return tasks sorted by priority_score descending."""
    return tools.get_tasks(status=status, limit=limit)


@router.post("/tasks", status_code=201, summary="Create a task (LLM-scored)")
def create_task(body: CreateTaskRequest):
    """
    Create a task and assign an initial priority score via a quick LLM call
    against the current business context.
    """
    score = _score_new_task(body.title, body.description)
    task = tools.create_task(
        title=body.title,
        description=body.description,
        priority_score=score,
        milestone_id=body.milestone_id,
        due_date=body.due_date,
        source_agent="user",
    )
    return task


@router.delete("/tasks/{task_id}", status_code=204, summary="Delete a task")
def delete_task(task_id: str):
    """Permanently remove a task from the backlog."""
    existing = tools.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    tools.delete_task(task_id)


@router.patch("/tasks/{task_id}", summary="Update a task")
def update_task(task_id: str, body: PatchTaskRequest):
    """Update task fields. Sets completed_at automatically when status → done."""
    existing = tools.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided")
    return tools.update_task(task_id, **fields)


@router.get("/milestones", summary="Milestones with task progress")
def list_milestones():
    """Return all milestones with task_count, completed_count, and progress_pct."""
    return tools.get_milestones()


@router.post("/reprioritize", summary="Trigger AI reprioritization (synchronous)")
def reprioritize():
    """
    Runs the reprioritization engine synchronously so the caller sees the
    updated scores and new top-3 immediately. Suitable for demo / manual use.
    """
    agent = PMAgent()
    try:
        result = agent.run(user_trigger("reprioritize"))
        return result
    except Exception as exc:
        logger.exception("Reprioritization failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/run", summary="Enqueue a full PM agent run via Celery")
def run_pm():
    """Enqueue a background agent run (Celery). Returns immediately with task_id."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("pm", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="PM agent status + top tasks")
def pm_status():
    """Quick status check — returns top 3 tasks by priority."""
    try:
        top = tools.get_tasks(limit=3)
        return {"agent": "pm", "status": "ready", "top_tasks": top}
    except Exception:
        return {"agent": "pm", "status": "ready", "top_tasks": []}


@router.post("/chat", summary="Conversational chat with the PM agent")
def pm_chat(body: ChatRequest):
    """
    Natural-language chat with the PM agent.

    The agent can:
    - Answer questions about the current task backlog
    - Create new tasks proactively when asked (queued as pending_approval)
    - Explain priorities and reasoning
    - Suggest what to work on next
    """
    from app.core.llm import llm
    from app.core.context import get_global_context
    from app.core.approvals import create_approval
    from app.agents.pm.registry import registry_summary_for_llm

    # Load current context
    try:
        global_ctx = get_global_context()
        global_ctx_dict = global_ctx.model_dump() if hasattr(global_ctx, "model_dump") else {}
    except Exception:
        global_ctx_dict = {}

    active_tasks = tools.get_tasks(limit=50)
    tasks_text = "\n".join(
        f'- [id:{t["id"]}] [{t["status"]}] (score {t.get("priority_score", 0):.0f}) {t["title"]}'
        + (f' — {t["description"][:80]}' if t.get("description") else "")
        for t in active_tasks
    ) or "No tasks yet."

    from app.core.context import CONTEXT_EXTRACTION_PROMPT

    system_prompt = f"""You are the PM Agent for an AI-powered startup operating system.
Your role: maintain the task backlog, create tasks proactively, prioritize ruthlessly, and assign each task to the right specialist agent.

CURRENT TASK BACKLOG:
{tasks_text}

BUSINESS CONTEXT:
{global_ctx_dict}

{registry_summary_for_llm()}

CAPABILITIES:
- Answer questions about tasks, priorities, and roadmap
- When the user asks you to create a task (or you proactively decide one is needed), respond with a JSON block AND a natural explanation
- Use this exact format when creating a task (assigned_agent must be one of: finance, dev_activity, outreach, legal, marketing, pm):
  <create_task>
  {{"title": "...", "description": "...", "priority_score": <0-100>, "assigned_agent": "<agent_id>"}}
  </create_task>
- When the user asks you to remove or delete a task, use the task's id from the backlog above:
  <delete_task>
  {{"task_id": "<uuid>"}}
  </delete_task>

GUIDELINES:
- Be direct and decisive — you're a senior PM, not a yes-man
- Always assign each task to the most appropriate agent based on what it needs done
- If the user's request implies a task is needed, create it proactively without being asked twice
- Priority scores: 80-100 = critical/urgent, 50-79 = important, 20-49 = nice to have, 0-19 = backlog
- Always explain your reasoning for task priority and agent assignment
- Keep replies concise and actionable"""
    system_prompt += CONTEXT_EXTRACTION_PROMPT

    messages = [{"role": msg.role, "content": msg.content} for msg in body.history]
    messages.append({"role": "user", "content": body.message})

    try:
        raw_reply = llm.chat_conversation(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.5,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.exception("PM chat LLM call failed")
        raise HTTPException(status_code=500, detail=str(exc))

    # Parse any task creation blocks out of the reply
    import re as _re
    created_tasks = []
    def _create_task_from_match(match: "_re.Match") -> str:
        try:
            import json as _json
            data = _json.loads(match.group(1).strip())
            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            priority_score = float(data.get("priority_score", 50))
            if not title:
                return ""
            assigned_agent = data.get("assigned_agent", "").strip() or None
            task = tools.create_task(
                title=title,
                description=description or None,
                priority_score=priority_score,
                status="pending_approval",
                source_agent="pm_chat",
                assigned_agent=assigned_agent,
            )
            try:
                create_approval(
                    agent="pm",
                    action_type="start_task",
                    content={
                        "task_id": str(task["id"]),
                        "title": task["title"],
                        "description": task.get("description") or "",
                        "priority_score": task.get("priority_score", 50),
                        "priority_reason": "",
                        "source_agent": "pm_chat",
                        "assigned_agent": task.get("assigned_agent") or "",
                    },
                )
            except Exception:
                logger.warning("PM chat: failed to create approval for task %s", task.get("id"))
            created_tasks.append(task)
            return ""  # strip the block from the reply
        except Exception:
            logger.warning("PM chat: failed to parse create_task block")
            return ""

    clean_reply = _re.sub(
        r"<create_task>\s*([\s\S]*?)\s*</create_task>",
        _create_task_from_match,
        raw_reply,
    ).strip()

    # Parse any task deletion blocks
    deleted_task_ids: list[str] = []
    def _delete_task_from_match(match: "_re.Match") -> str:
        try:
            import json as _json
            data = _json.loads(match.group(1).strip())
            task_id = data.get("task_id", "").strip()
            if not task_id:
                return ""
            existing = tools.get_task(task_id)
            if existing:
                tools.delete_task(task_id)
                deleted_task_ids.append(task_id)
        except Exception:
            logger.warning("PM chat: failed to parse delete_task block")
        return ""

    clean_reply = _re.sub(
        r"<delete_task>\s*([\s\S]*?)\s*</delete_task>",
        _delete_task_from_match,
        clean_reply,
    ).strip()

    from app.core.context import extract_and_save_context
    clean_reply = extract_and_save_context(clean_reply, "pm")

    return {
        "reply": clean_reply,
        "tasks_created": created_tasks,
        "tasks_deleted": deleted_task_ids,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _score_new_task(title: str, description: str | None) -> float:
    """
    Ask the LLM to assign an initial priority score for a newly created task.
    Falls back to 50 on any error.
    """
    try:
        agent = PMAgent()
        agent._global_context = agent.load_global_context()
        agent._domain_context = agent.load_domain_context()

        raw = agent.llm_chat(
            system_prompt=(
                "You are a project manager. Score the priority of this new task "
                "0–100 based on the current business context. "
                "Reply with ONLY valid JSON: "
                '{"score": <int>, "reason": "<one sentence>"}'
            ),
            user_message=(
                f"Task: {title}\n"
                f"Description: {description or 'n/a'}"
            ),
            temperature=0.2,
        )
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            return float(parsed.get("score", 50))
    except Exception:
        logger.warning("Task auto-scoring failed, defaulting to 50")
    return 50.0
