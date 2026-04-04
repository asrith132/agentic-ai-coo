"""
api/agents/_task_dispatch.py — Shared helper for dispatching agent Celery tasks.

All /api/{agent}/run endpoints call dispatch_agent_run() instead of
importing celery_app directly. This keeps the import chain clean and makes
it easy to swap the backend (e.g. to use Celery chord, canvas, etc.).
"""

from __future__ import annotations
from typing import Any


def dispatch_agent_run(agent_name: str, trigger_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Enqueue run_agent_task for `agent_name` and return a status dict.

    Returns {"status": "queued", "agent": str, "task_id": str}
    """
    from celery_app import run_agent_task

    task = run_agent_task.delay(agent_name, trigger_dict)
    return {"status": "queued", "agent": agent_name, "task_id": task.id}
