"""
api/agents/pm.py — /api/pm/* routes

Routes:
  GET   /api/pm/tasks              — Task backlog sorted by priority
  POST  /api/pm/tasks              — Create a task manually
  PATCH /api/pm/tasks/{id}         — Update task status or fields
  GET   /api/pm/milestones         — Milestones and progress
  POST  /api/pm/reprioritize       — Trigger manual AI reprioritization
  POST  /api/pm/run                — Manually trigger the PM agent
  GET   /api/pm/status             — Last run status
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/pm", tags=["Project Management"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


class CreateTaskRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"           # low | medium | high | urgent
    milestone_id: str | None = None
    labels: list[str] = []


class PatchTaskRequest(BaseModel):
    title: str | None = None
    status: str | None = None          # todo | in_progress | blocked | done
    priority: str | None = None
    assignee: str | None = None
    notes: str | None = None


@router.get(
    "/tasks",
    summary="List task backlog sorted by priority",
)
def list_tasks(
    status: str | None = Query(default=None, description="todo|in_progress|blocked|done"),
    milestone_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """
    Return the full task backlog sorted by priority (urgent → high → medium → low).
    Blocked tasks are surfaced at the top regardless of priority.
    """
    # TODO (Prompt 4): query GitHub issues / pm_sprints table
    return _NOT_IMPLEMENTED


@router.post(
    "/tasks",
    summary="Create a task manually",
    status_code=201,
)
def create_task(body: CreateTaskRequest):
    """
    Create a task (GitHub issue or internal record) directly from the dashboard.
    The PM agent will include it in the next reprioritization run.
    """
    # TODO (Prompt 4): create GitHub issue + local record
    return _NOT_IMPLEMENTED


@router.patch(
    "/tasks/{task_id}",
    summary="Update a task",
)
def update_task(task_id: str, body: PatchTaskRequest):
    """
    Update a task's status, priority, assignee, or notes.
    Status changes emit pm.task_status_changed events for other agents to react.
    """
    # TODO (Prompt 4): update GitHub issue + emit event
    return _NOT_IMPLEMENTED


@router.get(
    "/milestones",
    summary="List milestones and progress",
)
def list_milestones():
    """
    Return all active milestones with: name, target date, total tasks,
    completed tasks, and percentage progress.
    """
    # TODO (Prompt 4): query pm_sprints table + GitHub milestones
    return _NOT_IMPLEMENTED


@router.post(
    "/reprioritize",
    summary="Trigger AI reprioritization",
)
def reprioritize():
    """
    Ask the PM agent to re-rank the task backlog using the LLM, considering
    current business phase, active priorities, and team capacity.

    Returns the new priority ordering for review. A diff is shown to the user
    before changes are applied.
    """
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run(
        "pm",
        {"type": "user_request", "user_input": "reprioritize", "parameters": {"task": "reprioritize"}},
    )


@router.post("/run", summary="Manually trigger the PM agent")
def run_pm():
    """Enqueue a manual run of the PM agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("pm", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="PM agent last run status")
def pm_status():
    """Return last run timestamp and current sprint summary."""
    return {"agent": "pm", "status": "idle", "last_run": None}
