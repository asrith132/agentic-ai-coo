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
    status: str | None = None          # todo | in_progress | blocked | done
    priority_score: float | None = None
    assigned_to: str | None = None
    description: str | None = None
    milestone_id: str | None = None
    due_date: str | None = None


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
