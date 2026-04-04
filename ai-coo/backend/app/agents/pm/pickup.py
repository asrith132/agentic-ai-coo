"""
agents/pm/pickup.py — Runtime PM queue for non-PM agents.

Call ``load_pm_tasks_for_agent`` at the start of an agent run to fetch the
execution-ready task list without going through HTTP.
"""

from __future__ import annotations

from typing import Any


def load_pm_tasks_for_agent(
    agent_name: str,
    *,
    limit: int = 10,
    include_blocked: bool = False,
) -> dict[str, Any]:
    """
    Fetch PM-assigned open tasks for this agent (same data as
    ``GET /api/pm/tasks/pickup/{agent_name}``, in-process).
    """
    from app.agents.pm.tools import get_open_tasks_for_agent

    return get_open_tasks_for_agent(
        agent_name,
        limit=limit,
        include_blocked=include_blocked,
    )
