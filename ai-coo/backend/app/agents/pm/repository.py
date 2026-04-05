"""
agents/pm/repository.py — Supabase persistence for PM milestones and tasks.

Writes decomposed founder plans to `pm_milestones`, `pm_tasks`, and optionally
`pm_task_dependencies`. Read helpers for backlog verification.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from postgrest.exceptions import APIError

from app.db.supabase_client import get_client
from app.schemas.pm import DecomposedGoalPlan, DecomposedTask, ParsedFounderGoal

logger = logging.getLogger(__name__)

_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """
    Lowercase, trim, collapse whitespace, strip punctuation (word chars + spaces only).
    Used for milestone dedupe and feature/task matching.
    """
    s = value.lower().strip()
    s = _WS.sub(" ", s)
    s = _NON_WORD.sub("", s)
    return s.strip()


# PostgREST: "Could not find the 'effort_points' column of 'pm_tasks' in the schema cache"
_PGRST_MISSING_COLUMN = re.compile(
    r"Could not find the '([a-zA-Z0-9_]+)' column",
)
_PG_MISSING_COLUMN = re.compile(
    r"column\s+(?:pm_tasks\.)?([a-zA-Z0-9_]+)\s+does not exist",
    re.IGNORECASE,
)


def _column_from_pm_tasks_insert_error(exc: APIError) -> str | None:
    """Extract unknown column name from PostgREST / Postgres insert errors."""
    code = str(exc.code or "")
    msg = exc.message or ""
    if code == "PGRST204":
        m = _PGRST_MISSING_COLUMN.search(msg)
        return m.group(1) if m else None
    if code == "42703" or (
        "does not exist" in msg.lower() and "column" in msg.lower()
    ):
        m = _PG_MISSING_COLUMN.search(msg)
        return m.group(1) if m else None
    return None


def _target_agent_column_unavailable(exc: APIError) -> bool:
    msg = (exc.message or "").lower()
    if "target_agent" not in msg:
        return False
    return _api_error_suggests_missing_column(exc) or "could not find" in msg


def _api_error_suggests_missing_column(exc: APIError) -> bool:
    """
    PostgREST may report missing columns as PGRST204 (schema cache) or as Postgres
    42703 / message 'column ... does not exist' when the column is absent in SQL.
    """
    code = str(exc.code or "")
    if code in ("PGRST204", "42703"):
        return True
    msg = (exc.message or "").lower()
    return "column" in msg and "does not exist" in msg

_URGENCY_TO_PRIORITY: dict[str, float] = {
    "low": 30.0,
    "medium": 50.0,
    "high": 75.0,
    "critical": 90.0,
}

_PRIORITY_REASON = "Created from founder goal decomposition"


def _priority_score(urgency: str) -> float:
    return _URGENCY_TO_PRIORITY.get(urgency, 50.0)


def _impact_flags(impact_area: str) -> dict[str, bool]:
    return {
        "is_revenue_generating": impact_area == "revenue",
        "is_cost_saving": impact_area == "cost",
        "is_compliance_related": impact_area == "compliance",
        "is_customer_requested": False,
    }


def _omit_none(row: dict[str, Any]) -> dict[str, Any]:
    """PostgREST is happier omitting optional nulls than sending explicit null."""
    return {k: v for k, v in row.items() if v is not None}


def _task_row(
    task: DecomposedTask,
    milestone_id: str,
) -> dict[str, Any]:
    """Build a pm_tasks insert dict from a DecomposedTask."""
    flags = _impact_flags(task.impact_area)
    row: dict[str, Any] = {
        "title": task.title,
        "description": task.description,
        "status": "todo",
        "priority_score": _priority_score(task.urgency),
        "priority_reason": _PRIORITY_REASON,
        "source_agent": "pm",
        "source_event_id": None,
        "source_event_type": "founder_goal",
        "milestone_id": milestone_id,
        "assigned_to": None,
        "impact_area": task.impact_area,
        "urgency": task.urgency,
        "effort_points": max(1, int(task.effort_points)),
        "target_agent": task.target_agent,
        "task_type": task.task_type,
        **flags,
    }
    return _omit_none(row)


def _log_pm_task_created(
    task_id: str,
    milestone_id: str | None,
    target_agent: str | None,
) -> None:
    """Append-only activity log; failures must not affect save."""
    try:
        from app.agents.pm.tools import log_pm_task_activity

        log_pm_task_activity(
            task_id=task_id,
            action_type="created",
            milestone_id=milestone_id,
            agent_name=target_agent,
            new_status="todo",
        )
    except Exception:
        logger.debug("pm_task_activity (created) skipped", exc_info=True)


def _insert_pm_task_row(client: Any, row: dict[str, Any]) -> dict[str, Any]:
    """
    Insert one pm_tasks row. Drop unknown columns on PGRST204 / Postgres 42703 and retry.
    """
    payload: dict[str, Any] = dict(row)
    for _attempt in range(24):
        try:
            one = client.table("pm_tasks").insert(payload).execute()
            if one.data:
                return one.data[0]
            break
        except APIError as exc:
            col = _column_from_pm_tasks_insert_error(exc)
            if col and col in payload:
                logger.info(
                    "pm_tasks insert: omitting column %r (not in database or schema cache)",
                    col,
                )
                payload.pop(col, None)
                continue
            raise

    # Insert may succeed with empty representation; resolve by title + milestone
    lookup = (
        client.table("pm_tasks")
        .select("id, title")
        .eq("milestone_id", payload.get("milestone_id"))
        .eq("title", payload.get("title"))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not lookup.data:
        raise RuntimeError(
            f"pm_tasks insert returned no row for title={payload.get('title')!r}"
        )
    return lookup.data[0]


def _find_active_milestone_id_for_plan(client: Any, plan: DecomposedGoalPlan) -> str | None:
    """Most recently created planned/active milestone whose name normalizes like plan.parent_title."""
    target = normalize_text(plan.parent_title)
    if not target:
        return None
    res = (
        client.table("pm_milestones")
        .select("id, name")
        .in_("status", ["planned", "active"])
        .order("created_at", desc=True)
        .execute()
    )
    for row in res.data or []:
        if normalize_text(row.get("name") or "") == target:
            return str(row["id"])
    return None


def save_decomposed_plan_to_supabase(
    parsed: ParsedFounderGoal,
    plan: DecomposedGoalPlan,
    *,
    force_new: bool = False,
) -> dict[str, Any]:
    """
    Insert one milestone and all decomposed tasks; then dependency rows.

    When force_new is False, skips creating duplicate work if an active/planned milestone
    with the same normalized name already has tasks (returns deduped=True).

    Returns a dict suitable for API `saved` field:
      milestone_id, tasks_created, dependency_rows_created, dependency_inserts_skipped, deduped
    """
    client = get_client()

    milestone_id: str | None = None
    deduped = False

    if not force_new:
        existing_mid = _find_active_milestone_id_for_plan(client, plan)
        if existing_mid:
            task_chk = (
                client.table("pm_tasks")
                .select("id")
                .eq("milestone_id", existing_mid)
                .limit(1)
                .execute()
            )
            if task_chk.data:
                return {
                    "milestone_id": existing_mid,
                    "tasks_created": 0,
                    "dependency_rows_created": 0,
                    "dependency_inserts_skipped": True,
                    "deduped": True,
                }
            milestone_id = existing_mid

    milestone_payload: dict[str, Any] = {
        "name": plan.parent_title,
        "description": plan.parent_description,
        "status": "active",
    }
    if parsed.deadline is not None:
        milestone_payload["target_date"] = parsed.deadline.isoformat()

    if milestone_id is None:
        # supabase-py: do not chain .select() after .insert() — use .execute() only;
        # inserted rows are in response.data when PostgREST returns representation.
        ms_res = client.table("pm_milestones").insert(
            _omit_none(milestone_payload)
        ).execute()
        if ms_res.data:
            milestone_id = str(ms_res.data[0]["id"])
        else:
            lookup = (
                client.table("pm_milestones")
                .select("id")
                .eq("name", plan.parent_title)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not lookup.data:
                raise RuntimeError(
                    "pm_milestones insert returned no row (check RLS and schema)."
                )
            milestone_id = str(lookup.data[0]["id"])
    else:
        # Reuse empty milestone shell: refresh metadata when schema allows.
        try:
            client.table("pm_milestones").update(
                _omit_none(
                    {
                        "description": plan.parent_description,
                        "target_date": parsed.deadline.isoformat()
                        if parsed.deadline is not None
                        else None,
                        "status": "active",
                    }
                )
            ).eq("id", milestone_id).execute()
        except Exception as exc:
            logger.warning(
                "pm_milestones update on reuse skipped: %s",
                exc,
                exc_info=True,
            )

    if not plan.tasks:
        return {
            "milestone_id": milestone_id,
            "tasks_created": 0,
            "dependency_rows_created": 0,
            "dependency_inserts_skipped": False,
            "deduped": deduped,
        }

    title_to_id: dict[str, str] = {}
    for t in plan.tasks:
        row = _task_row(t, milestone_id)
        rec = _insert_pm_task_row(client, row)
        tid_str = str(rec["id"])
        title_to_id[str(rec["title"])] = tid_str
        _log_pm_task_created(
            tid_str,
            str(milestone_id) if milestone_id else None,
            getattr(t, "target_agent", None),
        )

    dependency_rows_created = 0
    dependency_inserts_skipped = False
    dep_payloads: list[dict[str, str]] = []
    for t in plan.tasks:
        tid = title_to_id.get(t.title)
        if not tid:
            continue
        for dep_title in t.depends_on_titles:
            did = title_to_id.get(dep_title)
            if did and did != tid:
                dep_payloads.append(
                    {"task_id": tid, "depends_on_task_id": did}
                )

    seen_pairs: set[tuple[str, str]] = set()
    unique_deps: list[dict[str, str]] = []
    for p in dep_payloads:
        key = (p["task_id"], p["depends_on_task_id"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        unique_deps.append(p)

    if unique_deps:
        try:
            dep_res = (
                client.table("pm_task_dependencies")
                .insert(unique_deps)
                .execute()
            )
            dependency_rows_created = (
                len(dep_res.data) if dep_res.data else len(unique_deps)
            )
        except Exception as exc:
            logger.warning(
                "pm_task_dependencies insert skipped or failed: %s",
                exc,
                exc_info=True,
            )
            dependency_inserts_skipped = True

    return {
        "milestone_id": milestone_id,
        "tasks_created": len(plan.tasks),
        "dependency_rows_created": dependency_rows_created,
        "dependency_inserts_skipped": dependency_inserts_skipped,
        "deduped": deduped,
    }


def fetch_backlog_tasks(
    *,
    include_done: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Tasks ordered by priority_score desc, then created_at asc.
    By default excludes status = done.
    """
    client = get_client()
    # Wider select first; fall back when optional columns are missing (PGRST204 or 42703).
    select_variants: tuple[tuple[str, bool], ...] = (
        ("id, title, status, priority_score, milestone_id, impact_area, urgency, created_at", True),
        ("id, title, status, priority_score, milestone_id, created_at", True),
        ("id, title, status, milestone_id, created_at", False),
        ("id, title, status, created_at", False),
    )
    rows: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for sel, use_priority_order in select_variants:
        try:
            q = client.table("pm_tasks").select(sel).limit(limit)
            if use_priority_order:
                q = q.order("priority_score", desc=True).order("created_at", desc=False)
            else:
                q = q.order("created_at", desc=False)
            if not include_done:
                q = q.neq("status", "done")
            res = q.execute()
            rows = res.data or []
            break
        except APIError as exc:
            if _api_error_suggests_missing_column(exc):
                last_exc = exc
                continue
            raise
    else:
        if last_exc:
            raise last_exc
        rows = []
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "status": r["status"],
            "priority_score": float(r["priority_score"])
            if r.get("priority_score") is not None
            else None,
            "milestone_id": str(r["milestone_id"])
            if r.get("milestone_id") is not None
            else None,
            "impact_area": r.get("impact_area"),
            "urgency": r.get("urgency"),
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]


def fetch_open_tasks_for_reprioritization(
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """
    Load non-done pm_tasks with as many scoring-related columns as exist.
    Unordered; caller sorts by score. Mirrors backlog-style schema fallbacks.
    """
    client = get_client()
    select_variants = (
        "id, title, status, priority_score, created_at, urgency, impact_area, effort_points, is_revenue_generating, is_compliance_related, is_cost_saving, is_customer_requested",
        "id, title, status, priority_score, created_at, urgency, impact_area, effort_points",
        "id, title, status, priority_score, created_at, urgency, impact_area",
        "id, title, status, priority_score, created_at, urgency",
        "id, title, status, priority_score, created_at",
    )
    rows: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for sel in select_variants:
        try:
            res = (
                client.table("pm_tasks")
                .select(sel)
                .neq("status", "done")
                .limit(limit)
                .execute()
            )
            rows = res.data or []
            break
        except APIError as exc:
            if _api_error_suggests_missing_column(exc):
                last_exc = exc
                continue
            raise
    else:
        if last_exc:
            raise last_exc
    return rows


_WARNING_TARGET_AGENT_UNAVAILABLE = (
    "target_agent column is not available in pm_tasks. "
    "Open ai-coo/supabase/migrations/005_pm_tasks_routing.sql, copy all SQL into "
    "Supabase → SQL Editor → Run (do not execute the file path in the terminal). "
    "Then retry."
)


def _assigned_task_api_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "title": r.get("title") or "",
        "description": r.get("description"),
        "status": r.get("status"),
        "priority_score": float(r["priority_score"])
        if r.get("priority_score") is not None
        else None,
        "milestone_id": str(r["milestone_id"])
        if r.get("milestone_id") is not None
        else None,
        "target_agent": r.get("target_agent"),
        "task_type": r.get("task_type"),
        "impact_area": r.get("impact_area"),
        "urgency": r.get("urgency"),
        "created_at": r.get("created_at"),
    }


def fetch_tasks_assigned_to_agent(
    agent_name: str,
    *,
    include_done: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Tasks for a decomposition target_agent, ordered open-first then priority desc,
    created_at asc. Empty list + warning if target_agent column is missing.
    """
    client = get_client()
    agent = agent_name.strip()
    if not agent:
        return {"tasks": [], "warning": None}

    try:
        client.table("pm_tasks").select("id").eq("target_agent", agent).limit(1).execute()
    except APIError as exc:
        if _target_agent_column_unavailable(exc):
            return {"tasks": [], "warning": _WARNING_TARGET_AGENT_UNAVAILABLE}
        raise

    select_variants = (
        "id, title, description, status, priority_score, milestone_id, target_agent, task_type, impact_area, urgency, created_at",
        "id, title, description, status, priority_score, milestone_id, target_agent, task_type, created_at",
        "id, title, description, status, priority_score, milestone_id, target_agent, created_at",
    )
    fetch_cap = min(max(limit, 1) * 4, 500)
    rows: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for sel in select_variants:
        try:
            q = (
                client.table("pm_tasks")
                .select(sel)
                .eq("target_agent", agent)
                .limit(fetch_cap)
            )
            if not include_done:
                q = q.neq("status", "done")
            res = q.execute()
            rows = res.data or []
            break
        except APIError as exc:
            if _api_error_suggests_missing_column(exc):
                last_exc = exc
                continue
            raise
    else:
        if last_exc:
            raise last_exc

    def sort_key(r: dict[str, Any]) -> tuple[int, float, str]:
        done = 1 if r.get("status") == "done" else 0
        ps = (
            float(r["priority_score"])
            if r.get("priority_score") is not None
            else 0.0
        )
        ca = str(r.get("created_at") or "")
        return (done, -ps, ca)

    rows_sorted = sorted(rows, key=sort_key)[:limit]
    return {
        "tasks": [_assigned_task_api_row(r) for r in rows_sorted],
        "warning": None,
    }


def _pickup_task_api_row(r: dict[str, Any]) -> dict[str, Any]:
    """Execution-ready row (no created_at) for agent pickup."""
    return {
        "id": str(r["id"]),
        "title": r.get("title") or "",
        "description": r.get("description"),
        "status": r.get("status"),
        "priority_score": float(r["priority_score"])
        if r.get("priority_score") is not None
        else None,
        "milestone_id": str(r["milestone_id"])
        if r.get("milestone_id") is not None
        else None,
        "target_agent": r.get("target_agent"),
        "task_type": r.get("task_type"),
        "impact_area": r.get("impact_area"),
        "urgency": r.get("urgency"),
    }


def fetch_open_tasks_for_agent_pickup(
    agent_name: str,
    *,
    limit: int = 10,
    include_blocked: bool = False,
) -> dict[str, Any]:
    """
    Non-done PM tasks for target_agent, optional blocked, priority_score desc
    then created_at asc. For runtime agent execution queues.
    """
    client = get_client()
    agent = agent_name.strip()
    if not agent:
        return {"tasks": [], "warning": None}

    try:
        client.table("pm_tasks").select("id").eq("target_agent", agent).limit(1).execute()
    except APIError as exc:
        if _target_agent_column_unavailable(exc):
            return {"tasks": [], "warning": _WARNING_TARGET_AGENT_UNAVAILABLE}
        raise

    select_variants = (
        "id, title, description, status, priority_score, milestone_id, target_agent, task_type, impact_area, urgency, created_at",
        "id, title, description, status, priority_score, milestone_id, target_agent, task_type, created_at",
        "id, title, description, status, priority_score, milestone_id, target_agent, created_at",
    )
    fetch_cap = min(max(limit, 1) * 6, 400)
    rows: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for sel in select_variants:
        try:
            q = (
                client.table("pm_tasks")
                .select(sel)
                .eq("target_agent", agent)
                .neq("status", "done")
                .limit(fetch_cap)
            )
            if not include_blocked:
                q = q.in_("status", ["todo", "in_progress"])
            res = q.execute()
            rows = res.data or []
            break
        except APIError as exc:
            if _api_error_suggests_missing_column(exc):
                last_exc = exc
                continue
            raise
    else:
        if last_exc:
            raise last_exc

    def pickup_sort_key(r: dict[str, Any]) -> tuple[float, str]:
        ps = (
            float(r["priority_score"])
            if r.get("priority_score") is not None
            else 0.0
        )
        ca = str(r.get("created_at") or "")
        return (-ps, ca)

    rows_sorted = sorted(rows, key=pickup_sort_key)[:limit]
    return {
        "tasks": [_pickup_task_api_row(r) for r in rows_sorted],
        "warning": None,
    }


def start_pm_task(task_id: str) -> dict[str, Any]:
    """
    If task status is ``todo``, set ``in_progress``. Returns updated pickup-style row
    or a structured skip when not applicable.
    """
    client = get_client()
    tid = str(task_id).strip()
    if not tid:
        raise LookupError("empty task id")

    select_variants = (
        "id, title, description, status, priority_score, milestone_id, target_agent, task_type, impact_area, urgency",
        "id, title, description, status, priority_score, milestone_id, target_agent, task_type",
        "id, title, description, status, priority_score, milestone_id, target_agent",
        "id, status, title",
    )
    row: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for sel in select_variants:
        try:
            res = (
                client.table("pm_tasks")
                .select(sel)
                .eq("id", tid)
                .limit(1)
                .execute()
            )
            row = res.data[0] if res.data else None
            break
        except APIError as exc:
            if _api_error_suggests_missing_column(exc):
                last_exc = exc
                continue
            raise
    else:
        if last_exc:
            raise last_exc

    if row is None:
        raise LookupError(tid)

    st = row.get("status")
    if st != "todo":
        return {
            "updated": False,
            "reason": "not_todo",
            "status": st,
            "task": _pickup_task_api_row(row)
            if "title" in row
            else {"id": tid, "status": st},
        }

    try:
        client.table("pm_tasks").update({"status": "in_progress"}).eq("id", tid).execute()
    except APIError as exc:
        return {
            "updated": False,
            "reason": "update_failed",
            "message": str(exc.message or exc)[:400],
            "task": _pickup_task_api_row(row)
            if "title" in row
            else {"id": tid, "status": st},
        }

    row["status"] = "in_progress"
    try:
        from app.agents.pm.tools import log_pm_task_activity

        log_pm_task_activity(
            task_id=tid,
            action_type="started",
            milestone_id=str(row["milestone_id"])
            if row.get("milestone_id")
            else None,
            agent_name=row.get("target_agent"),
            old_status="todo",
            new_status="in_progress",
        )
    except Exception:
        logger.debug("pm_task_activity (started) skipped", exc_info=True)
    return {"updated": True, "task": _pickup_task_api_row(row)}
