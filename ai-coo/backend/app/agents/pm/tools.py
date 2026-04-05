"""
agents/pm/tools.py — Supabase DB helpers for PMAgent.

Pure data access — no LLM calls here.

Functions:
    get_tasks()              — fetch backlog sorted by priority_score DESC
    get_active_tasks()       — all tasks where status != 'done'
    get_task()               — fetch single task by id
    create_task()            — insert a new task row
    update_task()            — update fields; auto-sets completed_at on done
    get_milestones()         — milestones with computed task counts
    save_priority_history()  — record a reprioritization run
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.supabase_client import get_client

logger = logging.getLogger(__name__)


def get_tasks(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return tasks sorted by priority_score DESC. Optionally filter by status."""
    client = get_client()
    query = (
        client.table("pm_tasks")
        .select("*")
        .order("priority_score", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    return query.execute().data or []


def get_active_tasks() -> list[dict[str, Any]]:
    """All tasks that are not done, sorted by priority_score DESC."""
    client = get_client()
    return (
        client.table("pm_tasks")
        .select("*")
        .neq("status", "done")
        .order("priority_score", desc=True)
        .execute()
        .data or []
    )


def get_task(task_id: str) -> dict[str, Any] | None:
    """Fetch a single task by id. Returns None if not found."""
    resp = (
        get_client()
        .table("pm_tasks")
        .select("*")
        .eq("id", task_id)
        .maybe_single()
        .execute()
    )
    return resp.data


def create_task(
    title: str,
    description: str | None = None,
    priority_score: float = 50.0,
    status: str = "todo",
    milestone_id: str | None = None,
    due_date: str | None = None,
    source_agent: str | None = None,
    source_event_id: str | None = None,
    assigned_agent: str | None = None,
) -> dict[str, Any]:
    """Insert a new task and return the stored row."""
    row: dict[str, Any] = {
        "title": title,
        "status": status,
        "priority_score": priority_score,
    }
    if description:
        row["description"] = description
    if milestone_id:
        row["milestone_id"] = milestone_id
    if due_date:
        row["due_date"] = due_date
    if source_agent:
        row["source_agent"] = source_agent
    if source_event_id:
        row["source_event_id"] = source_event_id
    if assigned_agent:
        row["assigned_agent"] = assigned_agent

    resp = get_client().table("pm_tasks").insert(row).execute()
    return resp.data[0]


def delete_task(task_id: str) -> bool:
    """Delete a task by id. Returns True if a row was deleted."""
    resp = (
        get_client()
        .table("pm_tasks")
        .delete()
        .eq("id", task_id)
        .execute()
    )
    return bool(resp.data)


def update_task(task_id: str, **fields: Any) -> dict[str, Any]:
    """
    Update a task row. Auto-sets completed_at when status is changed to 'done'.
    Returns the updated row.
    """
    if fields.get("status") == "done" and "completed_at" not in fields:
        fields["completed_at"] = datetime.now(timezone.utc).isoformat()
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    resp = (
        get_client()
        .table("pm_tasks")
        .update(fields)
        .eq("id", task_id)
        .execute()
    )
    return resp.data[0]


def get_milestones() -> list[dict[str, Any]]:
    """
    Return all milestones with computed task_count, completed_count,
    and progress_pct fields appended.
    """
    client = get_client()
    milestones = client.table("pm_milestones").select("*").execute().data or []
    if not milestones:
        return milestones

    tasks = (
        client.table("pm_tasks")
        .select("id,milestone_id,status")
        .execute()
        .data or []
    )

    for m in milestones:
        mid = m["id"]
        m_tasks = [t for t in tasks if t.get("milestone_id") == mid]
        total = len(m_tasks)
        done = sum(1 for t in m_tasks if t.get("status") == "done")
        m["task_count"] = total
        m["completed_count"] = done
        m["progress_pct"] = round(done / total * 100) if total else 0

    return milestones


def save_priority_history(
    previous_top_3: list[dict[str, Any]],
    new_top_3: list[dict[str, Any]],
    reasoning: str,
    trigger_event: str,
) -> dict[str, Any]:
    """Record a reprioritization run in pm_priority_history."""
    resp = (
        get_client()
        .table("pm_priority_history")
        .insert({
            "previous_top_3": previous_top_3,
            "new_top_3": new_top_3,
            "reasoning": reasoning,
            "trigger_event": trigger_event,
        })
        .execute()
    )
    return resp.data[0]
