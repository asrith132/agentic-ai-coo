"""
agents/pm/tools.py — Project management helpers.

Deterministic parsing and future DB/LLM-backed tools for PMAgent.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from postgrest.exceptions import APIError

from app.agents.pm.repository import (
    fetch_open_tasks_for_agent_pickup,
    fetch_open_tasks_for_reprioritization,
    fetch_tasks_assigned_to_agent,
    normalize_text,
)
from app.db.supabase_client import get_client
from app.schemas.pm import (
    DecomposedGoalPlan,
    DecomposedTask,
    FeatureShippedPayload,
    FounderGoalInput,
    ParsedFounderGoal,
)

logger = logging.getLogger(__name__)


class PmTaskCompletionRefused(Exception):
    """Agent mismatch, blocked task, or other deterministic refusal."""

    __slots__ = ("message", "status_code")

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Fixed display order for inferred workstreams (stable, deterministic).
_WORKSTREAM_ORDER: tuple[str, ...] = (
    "billing",
    "legal",
    "marketing",
    "outreach",
    "pricing",
    "product",
)

# (workstream_id, keyword substrings) — first match wins per id when scanning corpus.
_WORKSTREAM_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pricing", ("pricing",)),
    (
        "billing",
        ("stripe", "checkout", "billing", "payment"),
    ),
    (
        "marketing",
        (
            "landing page",
            "pricing page",
            "copy",
            "launch post",
            "announcement",
        ),
    ),
    ("outreach", ("email", "outreach", "waitlist", "prospects")),
    ("legal", ("legal", "terms", "privacy", "refund", "compliance")),
    (
        "product",
        ("build", "implement", "app", "feature", "flow", "ship", "tier", "mvp"),
    ),
)

# Strip trailing time-box phrases from objective text, e.g. "in 2 weeks".
_OBJECTIVE_TIME_SUFFIX = re.compile(
    r"\s+in\s+\d+\s+(?:week|weeks|day|days|month|months)\s*$",
    re.IGNORECASE,
)


def _corpus_from_input(inp: FounderGoalInput) -> str:
    parts: list[str] = [inp.goal]
    if inp.notes:
        parts.append(inp.notes)
    parts.extend(inp.constraints)
    parts.extend(inp.success_criteria)
    return " ".join(parts).lower()


def _infer_workstreams(corpus: str) -> list[str]:
    matched: set[str] = set()
    for ws_id, keywords in _WORKSTREAM_RULES:
        if ws_id in matched:
            continue
        for kw in keywords:
            if kw in corpus:
                matched.add(ws_id)
                break
    ordered = [ws for ws in _WORKSTREAM_ORDER if ws in matched]
    if not ordered:
        return ["product"]
    return ordered


def _derive_objective(goal: str) -> str:
    text = goal.strip()
    text = _OBJECTIVE_TIME_SUFFIX.sub("", text).strip()
    text = text.rstrip(" .,;:-")
    return text if text else goal.strip()


def _priority_phrase(hint: Literal["low", "medium", "high", "critical"]) -> str:
    return {
        "low": "Lower-priority",
        "medium": "Standard-priority",
        "high": "High-priority",
        "critical": "Critical-priority",
    }[hint]


def _format_workstreams_phrase(workstreams: list[str]) -> str:
    if len(workstreams) == 1:
        return f"the {workstreams[0]} workstream"
    if len(workstreams) == 2:
        return f"{workstreams[0]} and {workstreams[1]} workstreams"
    head = ", ".join(workstreams[:-1])
    return f"{head}, and {workstreams[-1]} workstreams"


def _build_planning_summary(
    inp: FounderGoalInput,
    workstreams: list[str],
) -> str:
    pfx = _priority_phrase(inp.priority_hint)
    goal_lower = inp.goal.lower()
    mid = " launch goal" if "launch" in goal_lower else " goal"
    ws_phrase = _format_workstreams_phrase(workstreams)
    return f"{pfx}{mid} involving {ws_phrase}."


def parse_founder_goal(inp: FounderGoalInput) -> ParsedFounderGoal:
    """
    Map validated founder input to a structured planning view using only
    deterministic rules (no LLM, no DB).
    """
    corpus = _corpus_from_input(inp)
    workstreams = _infer_workstreams(corpus)
    objective = _derive_objective(inp.goal)
    summary = _build_planning_summary(inp, workstreams)

    return ParsedFounderGoal(
        objective=objective,
        deadline=inp.deadline,
        priority_hint=inp.priority_hint,
        constraints=list(inp.constraints),
        success_criteria=list(inp.success_criteria),
        workstreams=workstreams,
        planning_summary=summary,
    )


# ── Deterministic decomposition (Task 1.3) ─────────────────────────────────

_PRICING_TITLE = "Finalize pricing structure"
_STRIPE_TITLE = "Implement Stripe checkout"
_BILLING_VALIDATE_TITLE = "Validate billing flow"
_PRODUCT_TITLE = "Build paid tier upgrade flow"
_MARKETING_COPY_TITLE = "Update pricing page copy"
_MARKETING_LAUNCH_TITLE = "Draft launch announcement"
_OUTREACH_TITLE = "Draft launch email to waitlist"
_LEGAL_TITLE = "Review billing terms and refund language"
_FINANCE_TITLE = "Estimate paid tier revenue impact"

_FINANCE_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "budget",
    "cost",
    "runway",
    "burn",
    "burn rate",
    "expense",
    "mrr",
    "revenue target",
    "financial",
    "finance",
    "cash flow",
    "p&l",
)


def _parsed_finance_corpus(parsed: ParsedFounderGoal) -> str:
    parts: list[str] = [
        parsed.objective,
        parsed.planning_summary,
        *parsed.constraints,
        *parsed.success_criteria,
    ]
    return " ".join(parts).lower()


def _should_include_finance_tasks(parsed: ParsedFounderGoal) -> bool:
    blob = _parsed_finance_corpus(parsed)
    return any(kw in blob for kw in _FINANCE_SIGNAL_KEYWORDS)


def _pricing_dep(ws: set[str]) -> list[str]:
    return [_PRICING_TITLE] if "pricing" in ws else []


def decompose_founder_goal(parsed: ParsedFounderGoal) -> DecomposedGoalPlan:
    """
    Expand a parsed goal into a stable ordered task list using fixed rules only.
    """
    ws = set(parsed.workstreams)
    urgency: Literal["low", "medium", "high", "critical"] = parsed.priority_hint
    tasks: list[DecomposedTask] = []
    seen: set[str] = set()

    def push(t: DecomposedTask) -> None:
        if t.title in seen:
            return
        seen.add(t.title)
        tasks.append(t)

    if "pricing" in ws:
        push(
            DecomposedTask(
                title=_PRICING_TITLE,
                description="Define the initial paid tier pricing and packaging.",
                target_agent="research",
                task_type="research",
                impact_area="revenue",
                urgency=urgency,
                effort_points=2,
                depends_on_titles=[],
            )
        )

    if "billing" in ws:
        push(
            DecomposedTask(
                title=_STRIPE_TITLE,
                description="Build the checkout flow for the paid tier.",
                target_agent="dev_activity",
                task_type="implementation",
                impact_area="revenue",
                urgency=urgency,
                effort_points=5,
                depends_on_titles=_pricing_dep(ws),
            )
        )
        push(
            DecomposedTask(
                title=_BILLING_VALIDATE_TITLE,
                description="End-to-end test of checkout, webhooks, and receipt flows.",
                target_agent="dev_activity",
                task_type="implementation",
                impact_area="revenue",
                urgency=urgency,
                effort_points=2,
                depends_on_titles=[_STRIPE_TITLE],
            )
        )

    if "product" in ws:
        prod_deps: list[str] = []
        if "billing" in ws:
            prod_deps = [_STRIPE_TITLE]
        push(
            DecomposedTask(
                title=_PRODUCT_TITLE,
                description="Ship the in-app path for upgrading to the paid tier.",
                target_agent="dev_activity",
                task_type="implementation",
                impact_area="product",
                urgency=urgency,
                effort_points=5,
                depends_on_titles=prod_deps,
            )
        )

    if "marketing" in ws:
        push(
            DecomposedTask(
                title=_MARKETING_COPY_TITLE,
                description="Refresh public pricing and packaging messaging.",
                target_agent="marketing",
                task_type="content",
                impact_area="growth",
                urgency=urgency,
                effort_points=2,
                depends_on_titles=_pricing_dep(ws),
            )
        )
        push(
            DecomposedTask(
                title=_MARKETING_LAUNCH_TITLE,
                description="Prepare the go-to-market announcement for the paid tier.",
                target_agent="marketing",
                task_type="content",
                impact_area="growth",
                urgency=urgency,
                effort_points=2,
                depends_on_titles=[],
            )
        )

    if "outreach" in ws:
        push(
            DecomposedTask(
                title=_OUTREACH_TITLE,
                description="Notify waitlist and key contacts when the paid tier goes live.",
                target_agent="outreach",
                task_type="outreach",
                impact_area="growth",
                urgency=urgency,
                effort_points=2,
                depends_on_titles=_pricing_dep(ws),
            )
        )

    if "legal" in ws:
        push(
            DecomposedTask(
                title=_LEGAL_TITLE,
                description="Align terms, privacy, and refund copy with the new paid offering.",
                target_agent="legal",
                task_type="compliance",
                impact_area="compliance",
                urgency=urgency,
                effort_points=3,
                depends_on_titles=_pricing_dep(ws),
            )
        )

    if _should_include_finance_tasks(parsed):
        push(
            DecomposedTask(
                title=_FINANCE_TITLE,
                description="Model uptake and revenue implications of the paid tier.",
                target_agent="finance",
                task_type="analysis",
                impact_area="revenue",
                urgency=urgency,
                effort_points=2,
                depends_on_titles=[],
            )
        )

    planning_notes: list[str] = []
    if "billing" in ws and "pricing" in ws:
        planning_notes.append("Billing tasks depend on pricing decisions.")
    if "legal" in ws:
        planning_notes.append("Legal review should happen before launch.")
    if "pricing" in ws and ("marketing" in ws or "outreach" in ws):
        planning_notes.append(
            "Marketing and outreach can proceed in parallel after pricing is finalized."
        )

    return DecomposedGoalPlan(
        parent_title=parsed.objective,
        parent_description="Decomposed execution plan for founder goal.",
        tasks=tasks,
        planning_notes=planning_notes,
    )


# ── feature_shipped (deterministic PM reaction) ───────────────────────────

# Minimum normalized feature_name length for any match (avoids tiny tokens).
_MIN_FEATURE_NORM_LEN = 5
# Title must be at least this long to allow "feature contains title" matches.
_MIN_TITLE_NORM_FOR_SUBFEATURE = 6
# Description-only matches require a longer normalized phrase (fewer false positives).
_MIN_FEATURE_NORM_FOR_DESC_MATCH = 12


def task_matches_feature(
    task_title: str,
    task_description: str | None,
    payload: FeatureShippedPayload,
) -> str | None:
    """
    Deterministic title-first matching. Returns a short strategy label or None.

    Order: normalized title equals feature_name; feature_name in title; title in
    feature_name (guarded); then task description contains full normalized
    feature_name (longer phrases only). Event description/changelog are not used
    as loose needles across the backlog.
    """
    raw_fn = (payload.feature_name or "").strip()
    if not raw_fn:
        return None
    nf = normalize_text(raw_fn)
    if len(nf) < _MIN_FEATURE_NORM_LEN:
        return None

    nt = normalize_text(task_title)
    nd = normalize_text(task_description or "")

    if nt == nf:
        return "title_exact"
    if nf in nt:
        return "title_contains_feature"
    if len(nt) >= _MIN_TITLE_NORM_FOR_SUBFEATURE and nt in nf:
        return "feature_contains_title"

    if len(nf) >= _MIN_FEATURE_NORM_FOR_DESC_MATCH and nf in nd:
        return "description_contains_feature"

    return None


def apply_feature_shipped_event(event_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Consume a ``feature_shipped``-style payload: mark matching open PM tasks done,
    then set milestones to ``completed`` when every task under them is ``done``.

    Matching is strict: driven primarily by ``feature_name`` against task titles,
    with description used only for longer feature phrases when titles do not match.
    """
    payload = FeatureShippedPayload.model_validate(event_payload)
    if not (payload.feature_name or "").strip():
        return {
            "matched_tasks": [],
            "matched_titles": [],
            "tasks_marked_done": 0,
            "milestones_completed": [],
        }

    client = get_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    open_res = (
        client.table("pm_tasks")
        .select("id, title, description, milestone_id, status")
        .neq("status", "done")
        .limit(500)
        .execute()
    )
    open_rows = open_res.data or []

    matched_tasks: list[dict[str, Any]] = []
    matched_ids: list[str] = []
    affected_milestone_ids: set[str] = set()

    for row in open_rows:
        tid = str(row["id"])
        title = row.get("title") or ""
        desc = row.get("description")
        if not isinstance(desc, str):
            desc = None
        strategy = task_matches_feature(title, desc, payload)
        if not strategy:
            continue
        matched_tasks.append(
            {"id": tid, "title": title, "match_strategy": strategy}
        )
        matched_ids.append(tid)
        mid = row.get("milestone_id")
        if mid is not None:
            affected_milestone_ids.add(str(mid))

    tasks_marked_done = 0
    for tid in matched_ids:
        client.table("pm_tasks").update(
            {"status": "done", "completed_at": now_iso}
        ).eq("id", tid).execute()
        tasks_marked_done += 1

    milestones_completed: list[dict[str, str]] = []
    for mid in sorted(affected_milestone_ids):
        all_res = (
            client.table("pm_tasks")
            .select("status")
            .eq("milestone_id", mid)
            .execute()
        )
        all_tasks = all_res.data or []
        if not all_tasks:
            continue
        if any(t.get("status") != "done" for t in all_tasks):
            continue

        ms_res = (
            client.table("pm_milestones")
            .select("id, name, status")
            .eq("id", mid)
            .limit(1)
            .execute()
        )
        ms_rows = ms_res.data or []
        if not ms_rows:
            logger.warning("Milestone %s not found after task updates", mid)
            continue
        m = ms_rows[0]
        name = m.get("name") or ""
        if m.get("status") == "completed":
            continue

        client.table("pm_milestones").update(
            {"status": "completed", "completed_at": now_iso}
        ).eq("id", mid).execute()
        milestones_completed.append({"id": str(m["id"]), "name": name})

    return {
        "matched_tasks": matched_tasks,
        "matched_titles": [m["title"] for m in matched_tasks],
        "tasks_marked_done": tasks_marked_done,
        "milestones_completed": milestones_completed,
    }


# ── dependency-aware task status ───────────────────────────────────────────
#
# Rules: never change ``done``. Never change ``in_progress``. ``todo`` becomes
# ``blocked`` when any declared dependency is not ``done``; ``blocked`` returns
# to ``todo`` when all dependencies are ``done``.

_ID_IN_CHUNK = 120


def _dependency_unavailable_reason(exc: BaseException) -> str:
    """Short, actionable message when pm_task_dependencies cannot be queried."""
    if isinstance(exc, APIError):
        code = str(exc.code or "")
        raw_msg = exc.message or ""
        low = raw_msg.lower()
        if code == "PGRST205" or "could not find the table" in low:
            if "pm_task_dependencies" in low:
                return (
                    "Table pm_task_dependencies is missing. "
                    "Run ai-coo/supabase/migrations/004_pm_task_dependencies.sql in the "
                    "Supabase SQL Editor (or apply migrations 002/003), then retry."
                )
    return str(exc).strip()[:400]


def _dependency_sync_empty(*, skipped: bool = False, reason: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "tasks_blocked": 0,
        "tasks_unblocked": 0,
        "blocked_task_titles": [],
        "unblocked_task_titles": [],
        "dependency_sync_skipped": skipped,
    }
    if reason:
        out["skip_reason"] = reason
    return out


def get_task_dependencies(task_id: str) -> list[str]:
    """
    Direct dependency ids (``depends_on_task_id``) for ``task_id``.
    Empty if none, the table is missing, or the query fails.
    """
    client = get_client()
    try:
        res = (
            client.table("pm_task_dependencies")
            .select("depends_on_task_id")
            .eq("task_id", task_id)
            .execute()
        )
    except Exception as exc:
        logger.debug("get_task_dependencies failed: %s", exc)
        return []
    return [str(r["depends_on_task_id"]) for r in (res.data or [])]


def is_task_blocked(task_id: str) -> bool:
    """
    True when the task has dependencies and at least one is not ``done``.
    Missing dependency task rows are treated as not done.
    """
    deps = get_task_dependencies(task_id)
    if not deps:
        return False
    client = get_client()
    status_by_id: dict[str, str] = {}
    for i in range(0, len(deps), _ID_IN_CHUNK):
        chunk = deps[i : i + _ID_IN_CHUNK]
        try:
            res = (
                client.table("pm_tasks")
                .select("id, status")
                .in_("id", chunk)
                .execute()
            )
        except Exception:
            return True
        for r in res.data or []:
            status_by_id[str(r["id"])] = str(r.get("status") or "")
    for d in deps:
        if status_by_id.get(d) != "done":
            return True
    return False


_PM_TASK_ACTIVITY_MISSING_HINT = (
    "Table pm_task_activity is missing. Run ai-coo/supabase/migrations/006_pm_task_activity.sql "
    "in the Supabase SQL Editor."
)


def _pm_task_activity_table_missing(exc: BaseException) -> bool:
    if isinstance(exc, APIError):
        code = str(exc.code or "")
        msg = (exc.message or "").lower()
        if code == "PGRST205" or "could not find the table" in msg:
            if "pm_task_activity" in msg:
                return True
    low = str(exc).lower()
    return "pm_task_activity" in low and (
        "does not exist" in low or "not found" in low
    )


def log_pm_task_activity(
    *,
    task_id: str,
    action_type: str,
    milestone_id: str | None = None,
    agent_name: str | None = None,
    old_status: str | None = None,
    new_status: str | None = None,
    note: str | None = None,
) -> bool:
    """
    Best-effort insert into ``pm_task_activity``. Never raises.

    Returns True if a row was written, False if skipped or failed (including when
    the table does not exist).
    """
    tid = str(task_id or "").strip()
    at = str(action_type or "").strip()
    if not tid or not at:
        return False

    client = get_client()
    mid = str(milestone_id).strip() if milestone_id else None
    if not mid:
        mid = None
        try:
            ms = (
                client.table("pm_tasks")
                .select("milestone_id")
                .eq("id", tid)
                .limit(1)
                .execute()
            )
            if ms.data:
                raw_mid = ms.data[0].get("milestone_id")
                mid = str(raw_mid) if raw_mid is not None else None
        except Exception as exc:
            logger.debug("pm_task_activity milestone lookup skipped: %s", exc)

    payload: dict[str, Any] = {
        "task_id": tid,
        "action_type": at,
    }
    if mid:
        payload["milestone_id"] = mid
    ag = (agent_name or "").strip() or None
    if ag:
        payload["agent_name"] = ag
    if old_status is not None and str(old_status).strip() != "":
        payload["old_status"] = str(old_status).strip()
    if new_status is not None and str(new_status).strip() != "":
        payload["new_status"] = str(new_status).strip()
    if note is not None:
        nt = str(note).strip()
        if nt:
            payload["note"] = nt[:8000]

    try:
        ins = client.table("pm_task_activity").insert(payload).execute()
        return bool(ins.data)
    except Exception as exc:
        if _pm_task_activity_table_missing(exc):
            logger.debug("pm_task_activity unavailable: %s", exc)
        else:
            logger.warning("pm_task_activity insert failed: %s", exc, exc_info=True)
        return False


def get_pm_task_activity(
    task_id: str,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Return activity rows for a task, newest first. If the table is missing, returns
    an empty list and a warning string (does not raise).
    """
    from uuid import UUID

    raw = str(task_id or "").strip()
    try:
        tid = str(UUID(raw))
    except ValueError:
        return {
            "task_id": raw,
            "count": 0,
            "activity": [],
            "warning": "Invalid task_id format",
        }

    lim = max(1, min(int(limit), 500))
    client = get_client()
    try:
        res = (
            client.table("pm_task_activity")
            .select(
                "action_type, agent_name, old_status, new_status, note, created_at"
            )
            .eq("task_id", tid)
            .order("created_at", desc=True)
            .limit(lim)
            .execute()
        )
    except Exception as exc:
        if _pm_task_activity_table_missing(exc):
            return {
                "task_id": tid,
                "count": 0,
                "activity": [],
                "warning": _PM_TASK_ACTIVITY_MISSING_HINT,
            }
        logger.warning("get_pm_task_activity failed: %s", exc, exc_info=True)
        return {
            "task_id": tid,
            "count": 0,
            "activity": [],
            "warning": (str(exc).strip() or repr(exc))[:500],
        }

    rows = res.data or []
    activity: list[dict[str, Any]] = []
    for r in rows:
        ca = r.get("created_at")
        if hasattr(ca, "isoformat"):
            ca_out = ca.isoformat()
        else:
            ca_out = str(ca) if ca is not None else ""
        activity.append(
            {
                "action_type": r.get("action_type"),
                "agent_name": r.get("agent_name"),
                "old_status": r.get("old_status"),
                "new_status": r.get("new_status"),
                "note": r.get("note"),
                "created_at": ca_out,
            }
        )

    return {
        "task_id": tid,
        "count": len(activity),
        "activity": activity,
    }


def sync_task_blocked_statuses() -> dict[str, Any]:
    """
    Align ``todo`` / ``blocked`` with ``pm_task_dependencies`` and dependency
    completion state. No-op when the table is missing or has no rows.
    """
    client = get_client()
    try:
        dep_res = (
            client.table("pm_task_dependencies")
            .select("task_id, depends_on_task_id")
            .limit(10_000)
            .execute()
        )
    except Exception as exc:
        logger.warning("pm_task_dependencies unavailable: %s", exc)
        return _dependency_sync_empty(
            skipped=True,
            reason=_dependency_unavailable_reason(exc),
        )

    dep_rows = dep_res.data or []
    if not dep_rows:
        return _dependency_sync_empty(skipped=False)

    edges: dict[str, list[str]] = {}
    all_ids: set[str] = set()
    for r in dep_rows:
        tid = str(r["task_id"])
        did = str(r["depends_on_task_id"])
        edges.setdefault(tid, []).append(did)
        all_ids.add(tid)
        all_ids.add(did)

    ids_list = list(all_ids)
    status_by_id: dict[str, str] = {}
    title_by_id: dict[str, str] = {}
    for i in range(0, len(ids_list), _ID_IN_CHUNK):
        chunk = ids_list[i : i + _ID_IN_CHUNK]
        try:
            res = (
                client.table("pm_tasks")
                .select("id, status, title")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            logger.warning("pm_tasks batch read in dependency sync failed: %s", exc)
            return _dependency_sync_empty(
                skipped=True,
                reason=_dependency_unavailable_reason(exc),
            )
        for row in res.data or []:
            uid = str(row["id"])
            status_by_id[uid] = str(row.get("status") or "")
            title_by_id[uid] = str(row.get("title") or "")

    tasks_blocked = 0
    tasks_unblocked = 0
    blocked_task_titles: list[str] = []
    unblocked_task_titles: list[str] = []
    status_changes: list[tuple[str, str, str]] = []

    for task_uid in sorted(edges.keys()):
        st = status_by_id.get(task_uid)
        if st is None or st == "done" or st == "in_progress":
            continue
        deps = edges[task_uid]
        unmet = any(status_by_id.get(d) != "done" for d in deps)
        new_st: str | None = None
        if st == "todo" and unmet:
            new_st = "blocked"
        elif st == "blocked" and not unmet:
            new_st = "todo"
        if new_st is None:
            continue
        try:
            client.table("pm_tasks").update({"status": new_st}).eq(
                "id", task_uid
            ).execute()
        except Exception as exc:
            logger.warning(
                "dependency sync status update failed for %s: %s",
                task_uid,
                exc,
            )
            continue
        title = title_by_id.get(task_uid) or ""
        if new_st == "blocked":
            tasks_blocked += 1
            blocked_task_titles.append(title)
        else:
            tasks_unblocked += 1
            unblocked_task_titles.append(title)
        status_by_id[task_uid] = new_st
        status_changes.append((task_uid, st, new_st))

    if status_changes:
        milestone_by_task: dict[str, str | None] = {}
        seen_task_ids = list({c[0] for c in status_changes})
        for i in range(0, len(seen_task_ids), _ID_IN_CHUNK):
            chunk = seen_task_ids[i : i + _ID_IN_CHUNK]
            try:
                mres = (
                    client.table("pm_tasks")
                    .select("id, milestone_id")
                    .in_("id", chunk)
                    .execute()
                )
                for mr in mres.data or []:
                    midv = mr.get("milestone_id")
                    milestone_by_task[str(mr["id"])] = (
                        str(midv) if midv is not None else None
                    )
            except Exception as exc:
                logger.debug(
                    "pm_task_activity milestone batch in dependency sync skipped: %s",
                    exc,
                )
        for task_uid, old_s, new_s in status_changes:
            log_pm_task_activity(
                task_id=task_uid,
                action_type="blocked" if new_s == "blocked" else "unblocked",
                milestone_id=milestone_by_task.get(task_uid),
                old_status=old_s,
                new_status=new_s,
            )

    return {
        "tasks_blocked": tasks_blocked,
        "tasks_unblocked": tasks_unblocked,
        "blocked_task_titles": blocked_task_titles,
        "unblocked_task_titles": unblocked_task_titles,
        "dependency_sync_skipped": False,
    }


def get_tasks_assigned_to_agent(
    agent_name: str,
    include_done: bool = False,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Agent pickup list: PM tasks whose persisted ``target_agent`` matches,
    ordered open-first, then priority (desc), then ``created_at`` (asc).
    """
    agent = agent_name.strip()
    if not agent:
        return {
            "agent": "",
            "tasks": [],
            "count": 0,
            "open_count": 0,
            "warning": "agent_name is empty",
        }

    raw = fetch_tasks_assigned_to_agent(
        agent, include_done=include_done, limit=limit
    )
    tasks = raw["tasks"]
    open_count = sum(1 for t in tasks if t.get("status") != "done")
    out: dict[str, Any] = {
        "agent": agent,
        "tasks": tasks,
        "count": len(tasks),
        "open_count": open_count,
    }
    if raw.get("warning"):
        out["warning"] = raw["warning"]
    return out


def get_open_tasks_for_agent(
    agent_name: str,
    limit: int = 10,
    include_blocked: bool = False,
) -> dict[str, Any]:
    """
    Execution queue: non-done tasks for ``target_agent``, excluding ``blocked``
    unless ``include_blocked``. Ordered by ``priority_score`` desc, ``created_at`` asc.
    """
    agent = agent_name.strip()
    if not agent:
        return {
            "agent": "",
            "count": 0,
            "tasks": [],
            "warning": "agent_name is empty",
        }

    raw = fetch_open_tasks_for_agent_pickup(
        agent,
        limit=limit,
        include_blocked=include_blocked,
    )
    out: dict[str, Any] = {
        "agent": agent,
        "count": len(raw["tasks"]),
        "tasks": raw["tasks"],
    }
    if raw.get("warning"):
        out["warning"] = raw["warning"]
    return out


# ── deterministic backlog reprioritization ─────────────────────────────────

_REP_URGENCY_BASE: dict[str, float] = {
    "low": 20.0,
    "medium": 40.0,
    "high": 65.0,
    "critical": 85.0,
}

_REP_IMPACT_BONUS: dict[str, float] = {
    "revenue": 20.0,
    "growth": 15.0,
    "compliance": 18.0,
    "product": 12.0,
    "cost": 16.0,
    "retention": 14.0,
}


def _reprioritize_effort_points(row: dict[str, Any]) -> int:
    raw = row.get("effort_points")
    if raw is None:
        return 3
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3


def _compute_reprioritize_score(row: dict[str, Any]) -> float:
    """Deterministic 0–100 score from urgency, impact, effort, flags, blocked."""
    u = str(row.get("urgency") or "medium").lower()
    base = _REP_URGENCY_BASE.get(u, 40.0)
    ia = str(row.get("impact_area") or "").lower()
    bonus = _REP_IMPACT_BONUS.get(ia, 10.0)
    eff = _reprioritize_effort_points(row)
    score = base + bonus - (eff * 2.0)

    if row.get("is_revenue_generating") is True:
        score += 10.0
    if row.get("is_compliance_related") is True:
        score += 12.0
    if row.get("is_cost_saving") is True:
        score += 8.0
    if row.get("is_customer_requested") is True:
        score += 6.0
    if row.get("status") == "blocked":
        score -= 20.0

    return max(0.0, min(100.0, score))


def _reprioritize_reasoning(trigger_event: str | None) -> str:
    tail = "based on urgency, impact area, effort, and task flags."
    if trigger_event:
        return f"Backlog reprioritized after {trigger_event} {tail}"
    return f"Backlog reprioritized {tail}"


def _sort_tasks_by_score_created_id(
    rows: list[dict[str, Any]],
    score_getter: Callable[[dict[str, Any]], float],
) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple[float, str, str]:
        sc = float(score_getter(r))
        created = str(r.get("created_at") or "")
        rid = str(r.get("id") or "")
        return (-sc, created, rid)

    return sorted(rows, key=key)


def _top3_snapshot(
    rows: list[dict[str, Any]],
    score_getter: Callable[[dict[str, Any]], float],
) -> list[dict[str, Any]]:
    ordered = _sort_tasks_by_score_created_id(rows, score_getter)
    out: list[dict[str, Any]] = []
    for r in ordered[:3]:
        sc = round(float(score_getter(r)), 2)
        out.append(
            {
                "task_id": str(r["id"]),
                "title": r.get("title") or "",
                "score": sc,
            }
        )
    return out


def _top3_changed(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> bool:
    def norm(x: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "task_id": e["task_id"],
                "title": e["title"],
                "score": round(float(e["score"]), 2),
            }
            for e in x
        ]

    return norm(before) != norm(after)


def _try_insert_pm_priority_history(
    client: Any,
    *,
    trigger_event: str,
    previous_top_3: list[dict[str, Any]],
    new_top_3: list[dict[str, Any]],
    reasoning: str,
) -> tuple[bool, str | None]:
    payloads: list[dict[str, Any]] = [
        {
            "trigger_event": trigger_event,
            "trigger_event_type": trigger_event,
            "previous_top_3": previous_top_3,
            "new_top_3": new_top_3,
            "reasoning": reasoning,
        },
        {
            "trigger_event": trigger_event,
            "previous_top_3": previous_top_3,
            "new_top_3": new_top_3,
            "reasoning": reasoning,
        },
    ]
    last_err: str | None = None
    for payload in payloads:
        try:
            client.table("pm_priority_history").insert(payload).execute()
            return True, None
        except Exception as exc:
            last_err = str(exc).strip() or repr(exc)
            logger.warning("pm_priority_history insert failed: %s", last_err)
    return False, last_err


def reprioritize_backlog(trigger_event: str | None = None) -> dict[str, Any]:
    """
    Recompute deterministic priority_score for all open tasks, persist changes,
    and record pm_priority_history when the top 3 ordering/scores change.
    """
    te = (trigger_event or "").strip() or None
    trigger_label = te or "manual_reprioritize"
    reasoning = _reprioritize_reasoning(te)

    rows = fetch_open_tasks_for_reprioritization()
    if not rows:
        return {
            "tasks_updated": 0,
            "previous_top_3": [],
            "new_top_3": [],
            "top_3_changed": False,
            "history_written": False,
            "reasoning": reasoning,
            "history_warning": None,
        }

    def old_score(r: dict[str, Any]) -> float:
        ps = r.get("priority_score")
        if ps is None:
            return 0.0
        try:
            return float(ps)
        except (TypeError, ValueError):
            return 0.0

    previous_top_3 = _top3_snapshot(rows, old_score)

    scored: list[dict[str, Any]] = []
    for r in rows:
        nr = dict(r)
        nr["_new_score"] = _compute_reprioritize_score(r)
        scored.append(nr)

    def new_score(r: dict[str, Any]) -> float:
        return float(r["_new_score"])

    new_top_3 = _top3_snapshot(scored, new_score)
    changed_top = _top3_changed(previous_top_3, new_top_3)

    client = get_client()
    tasks_updated = 0
    for r in scored:
        tid = str(r["id"])
        new_s = round(float(r["_new_score"]), 2)
        old_s = round(old_score(r), 2)
        if new_s == old_s:
            continue
        client.table("pm_tasks").update({"priority_score": new_s}).eq("id", tid).execute()
        tasks_updated += 1

    history_written = False
    history_warning: str | None = None
    if changed_top:
        ok, warn = _try_insert_pm_priority_history(
            client,
            trigger_event=trigger_label,
            previous_top_3=previous_top_3,
            new_top_3=new_top_3,
            reasoning=reasoning,
        )
        history_written = ok
        history_warning = warn

    return {
        "tasks_updated": tasks_updated,
        "previous_top_3": previous_top_3,
        "new_top_3": new_top_3,
        "top_3_changed": changed_top,
        "history_written": history_written,
        "reasoning": reasoning,
        "history_warning": history_warning,
    }


def _try_complete_milestone_if_all_tasks_done(
    client: Any,
    milestone_id: str,
    now_iso: str,
) -> dict[str, str] | None:
    """
    If every pm_tasks row for this milestone has status ``done``, ensure the
    milestone is marked ``completed`` with ``completed_at`` set.
    Returns ``{id, name}`` when all tasks are done; otherwise ``None``.
    """
    all_res = (
        client.table("pm_tasks")
        .select("status")
        .eq("milestone_id", milestone_id)
        .execute()
    )
    all_tasks = all_res.data or []
    if not all_tasks:
        return None
    if any((t.get("status") or "") != "done" for t in all_tasks):
        return None
    ms_res = (
        client.table("pm_milestones")
        .select("id, name, status")
        .eq("id", milestone_id)
        .limit(1)
        .execute()
    )
    if not ms_res.data:
        return None
    m = ms_res.data[0]
    mid = str(m["id"])
    name = m.get("name") or ""
    if (m.get("status") or "") != "completed":
        client.table("pm_milestones").update(
            {"status": "completed", "completed_at": now_iso}
        ).eq("id", milestone_id).execute()
    return {"id": mid, "name": name}


def _fetch_pm_task_row_with_target_agent(
    client: Any,
    tid: str,
) -> tuple[dict[str, Any] | None, bool]:
    """
    Load one pm_tasks row. Returns ``(row, target_agent_column_ok)``.
    If ``target_agent`` is missing from the schema, retries without it and
    returns ``target_agent_column_ok=False``.
    """
    try:
        res = (
            client.table("pm_tasks")
            .select("id, title, status, milestone_id, target_agent")
            .eq("id", tid)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        msg_l = (exc.message or "").lower()
        code = str(exc.code or "")
        if "target_agent" in msg_l and (
            code in ("PGRST204", "42703")
            or "does not exist" in msg_l
            or "could not find" in msg_l
        ):
            res = (
                client.table("pm_tasks")
                .select("id, title, status, milestone_id")
                .eq("id", tid)
                .limit(1)
                .execute()
            )
            row = res.data[0] if res.data else None
            return (row, False)
        raise
    row = res.data[0] if res.data else None
    return (row, True)


def complete_pm_task_for_agent(
    task_id: str,
    agent_name: str,
    completion_note: str | None = None,
) -> dict[str, Any]:
    """
    Like :func:`complete_pm_task`, but only after verifying the task is for
    ``agent_name`` when ``target_agent`` is present and non-empty.

    Refuses completion when the task is ``blocked`` (unless already ``done``).

    Raises:
        ValueError: invalid task UUID or empty ``agent_name``.
        LookupError: task not found.
        PmTaskCompletionRefused: wrong agent or blocked task (HTTP 409 by default).
    """
    from uuid import UUID

    raw_id = str(task_id or "").strip()
    try:
        tid = str(UUID(raw_id))
    except ValueError as e:
        raise ValueError("Invalid task_id format") from e

    agent_norm = str(agent_name or "").strip()
    if not agent_norm:
        raise ValueError("agent_name is empty")

    client = get_client()
    row, ta_column_ok = _fetch_pm_task_row_with_target_agent(client, tid)
    if not row:
        raise LookupError(f"Task not found: {tid}")

    st = (row.get("status") or "").strip()
    assigned = (
        str(row.get("target_agent") or "").strip() if ta_column_ok else ""
    )

    if ta_column_ok and assigned and assigned != agent_norm:
        raise PmTaskCompletionRefused(
            f"Task is assigned to {assigned}, not {agent_norm}",
            status_code=409,
        )

    if st == "blocked":
        raise PmTaskCompletionRefused(
            "Cannot complete a blocked task",
            status_code=409,
        )

    result = complete_pm_task(
        tid,
        completion_note,
        activity_action="completed_for_agent",
        activity_agent_name=agent_norm,
    )
    out: dict[str, Any] = dict(result)
    out["agent_name"] = agent_norm

    if not ta_column_ok:
        out["target_agent_validation"] = "skipped_column_unavailable"
        out["warning"] = (
            "target_agent column unavailable; agent ownership was not verified"
        )
    elif not assigned:
        out["target_agent_validation"] = "skipped_unassigned"
        out["warning"] = (
            "Task has no target_agent; completion allowed for any agent"
        )
    else:
        out["target_agent_validation"] = "ok"

    return out


def complete_pm_task(
    task_id: str,
    completion_note: str | None = None,
    *,
    activity_action: str = "completed",
    activity_agent_name: str | None = None,
) -> dict[str, Any]:
    """
    Mark a PM task ``done``, sync dependency blocked flags, reprioritize with
    ``trigger_event='task_completed'``, and roll up milestone completion when
    every task in that milestone is done.

    ``activity_action`` / ``activity_agent_name`` control the pm_task_activity row
    (best-effort; failures are ignored).

    Raises:
        ValueError: invalid UUID string (message ``Invalid task_id format``).
        LookupError: no row in ``pm_tasks`` for the id.
    """
    from uuid import UUID

    raw_id = str(task_id or "").strip()
    try:
        tid = str(UUID(raw_id))
    except ValueError as e:
        raise ValueError("Invalid task_id format") from e

    client = get_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    sel = (
        client.table("pm_tasks")
        .select("id, title, status, milestone_id")
        .eq("id", tid)
        .limit(1)
        .execute()
    )
    if not sel.data:
        raise LookupError(f"Task not found: {tid}")

    row = sel.data[0]
    title = row.get("title") or ""
    st = row.get("status")
    milestone_id = row.get("milestone_id")

    note = (completion_note or "").strip() or None

    def _slim_dep(d: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tasks_blocked": int(d.get("tasks_blocked") or 0),
            "tasks_unblocked": int(d.get("tasks_unblocked") or 0),
        }
        if d.get("dependency_sync_skipped"):
            out["skipped"] = True
        return out

    def _slim_rep(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "top_3_changed": bool(r.get("top_3_changed")),
            "history_written": bool(r.get("history_written")),
        }

    if st == "done":
        out: dict[str, Any] = {
            "task": {"id": tid, "title": title, "status": "done"},
            "already_done": True,
            "dependency_sync": None,
            "reprioritize": None,
            "milestone_completed": None,
        }
        if note:
            out["completion_note"] = note
        return out

    upd = (
        client.table("pm_tasks")
        .update({"status": "done", "completed_at": now_iso})
        .eq("id", tid)
        .execute()
    )
    if getattr(upd, "error", None):
        raise RuntimeError(f"Failed to update pm_tasks: {upd.error}")

    log_pm_task_activity(
        task_id=tid,
        action_type=(activity_action or "completed").strip() or "completed",
        milestone_id=str(milestone_id) if milestone_id else None,
        agent_name=activity_agent_name,
        old_status=st,
        new_status="done",
        note=note,
    )

    dep_raw = sync_task_blocked_statuses()
    dep = _slim_dep(dep_raw)

    rep_raw = reprioritize_backlog(trigger_event="task_completed")
    rep = _slim_rep(rep_raw)

    milestone_completed: dict[str, str] | None = None
    if milestone_id:
        try:
            milestone_completed = _try_complete_milestone_if_all_tasks_done(
                client, str(milestone_id), now_iso
            )
        except Exception:
            milestone_completed = None

    result: dict[str, Any] = {
        "task": {"id": tid, "title": title, "status": "done"},
        "already_done": False,
        "dependency_sync": dep,
        "reprioritize": rep,
        "milestone_completed": milestone_completed,
    }
    if note:
        result["completion_note"] = note
    return result
