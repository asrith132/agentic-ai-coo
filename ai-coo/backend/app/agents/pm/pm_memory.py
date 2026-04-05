"""
Central PM durable memory in ``global_context.pm_voice_intake``.

- Ensures a ``global_context`` row exists (minimal auto-seed).
- Merges generated tasks (by stable ``id``) instead of blind overwrite.
- Extracts and stores important decisions from PM voice turns (LLM).
- Builds a digest string for Claude system prompts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.context import get_global_context, update_global_context
from app.core.llm import llm
from app.db.supabase_client import get_client
from app.schemas.context import GlobalContext
from app.schemas.pm_intake import PmVoiceIntakeSession, merge_brief

logger = logging.getLogger(__name__)

_MINIMAL_GLOBAL_INSERT: dict[str, Any] = {
    "company_profile": {},
    "target_customer": {},
    "business_state": {},
    "brand_voice": {},
    "competitive_landscape": {},
    "recent_events": [],
    "pm_voice_intake": {},
    "version": 1,
}

_DECISIONS_PROMPT = """You analyze PM / founder voice turns to find **important project decisions** worth saving for future sessions.

Latest user message (STT transcript):
\"\"\"
{user_text}
\"\"\"

Latest assistant reply (what the user heard):
\"\"\"
{assistant_text}
\"\"\"

Existing decision summaries already stored (do not repeat these):
{existing_summaries}

Return a **single JSON object** only. No markdown fences.

Keys:
- `decisions`: array of 0–5 objects, each with:
  - `category`: short snake_case label (e.g. scope, timeline, audience, success_metrics, priority, budget, tech, stakeholders, launch_type, dependencies)
  - `decision`: one clear sentence stating what was decided or committed
  - `rationale`: one short sentence or null if unknown
  - `confidence`: "high" | "medium" | "low"
  - `related_fields`: array of brief field names this touches (e.g. target_users, scope_excluded) or []

**Include** concrete commitments, scope cuts, timelines, audiences, success metrics, launch sequencing, prioritization.
**Exclude** greetings, filler, vague brainstorming with no commitment, or exact repeats of existing summaries.

If nothing important: `"decisions": []`.
"""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_global_context_row_exists() -> bool:
    """
    If ``global_context`` has no row, insert a minimal workspace row so PM memory can persist.

    Returns True if a row exists or was created; False only on insert failure.
    """
    client = get_client()
    try:
        res = client.table("global_context").select("id").limit(1).execute()
        if res.data:
            return True
    except Exception as exc:
        logger.warning("pm memory: could not probe global_context: %s", exc, exc_info=True)
        return False

    try:
        client.table("global_context").insert(_MINIMAL_GLOBAL_INSERT).execute()
        logger.info("pm memory initialized in global_context (auto-seeded minimal row)")
        return True
    except Exception as exc:
        logger.exception("pm memory: global_context auto-seed failed: %s", exc)
        return False


def load_pm_intake_session() -> PmVoiceIntakeSession:
    ctx = get_global_context()
    raw = getattr(ctx, "pm_voice_intake", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    return PmVoiceIntakeSession.model_validate(raw)


def save_pm_intake_session(session: PmVoiceIntakeSession) -> None:
    session.updated_at = _iso_now()
    session.last_updated_at = session.updated_at
    update_global_context("pm_voice_intake", session.model_dump(mode="json"), "pm")


def _normalize_decision_key(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip().lower())
    s = re.sub(r"[^\w\s,.-]", "", s)
    return s[:400]


def merge_tasks(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    run_id: str,
    replace_all: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Merge ``incoming`` tasks into ``existing`` by ``id``.

    - Same ``id``: shallow merge; preserve ``created_at``; set ``updated_at`` and ``source_run_id``.
    - New ``id``: append with timestamps.
    - ``replace_all``: drop prior tasks and use only enriched incoming (explicit full replace).
    """
    now = _iso_now()
    stats = {"added": 0, "updated": 0, "replaced": 0}

    def enrich(t: dict[str, Any], tid: str, *, is_new: bool) -> dict[str, Any]:
        out = dict(t)
        out["id"] = tid
        out["source_run_id"] = run_id
        out["updated_at"] = now
        if is_new:
            out.setdefault("created_at", now)
        return out

    if replace_all:
        stats["replaced"] = len(existing)
        merged: list[dict[str, Any]] = []
        for i, t in enumerate(incoming):
            tid = str(t.get("id") or "").strip() or f"task-{uuid.uuid4().hex[:10]}"
            merged.append(enrich(t, tid, is_new=True))
        stats["added"] = len(merged)
        return merged, stats

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for t in existing:
        tid = str(t.get("id") or "").strip()
        if not tid:
            tid = f"legacy-{uuid.uuid4().hex[:8]}"
            t = {**t, "id": tid}
        if tid not in by_id:
            order.append(tid)
        by_id[tid] = dict(t)

    for t in incoming:
        tid = str(t.get("id") or "").strip() or f"task-{uuid.uuid4().hex[:10]}"
        if tid in by_id:
            old = by_id[tid]
            merged_task = {**old}
            for k, v in t.items():
                if k == "created_at":
                    continue
                if v is None:
                    continue
                if k == "depends_on" and v == [] and old.get("depends_on"):
                    continue
                merged_task[k] = v
            merged_task["updated_at"] = now
            merged_task["source_run_id"] = run_id
            merged_task.setdefault("created_at", old.get("created_at") or now)
            by_id[tid] = merged_task
            stats["updated"] += 1
        else:
            by_id[tid] = enrich(t, tid, is_new=True)
            order.append(tid)
            stats["added"] += 1

    return [by_id[i] for i in order], stats


def merge_decisions(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Append incoming decisions that are not near-duplicates of existing."""
    seen = {_normalize_decision_key(str(d.get("decision") or "")) for d in existing}
    seen = {s for s in seen if len(s) >= 8}
    added = 0
    out = list(existing)
    now = _iso_now()
    for d in incoming:
        dec = str(d.get("decision") or "").strip()
        if len(dec) < 12:
            continue
        key = _normalize_decision_key(dec)
        if not key or key in seen:
            continue
        seen.add(key)
        did = str(d.get("id") or "").strip() or f"dec-{uuid.uuid4().hex[:12]}"
        conf_raw = str(d.get("confidence") or "medium").strip().lower()
        conf = conf_raw if conf_raw in ("high", "medium", "low") else "medium"
        row = {
            "id": did,
            "timestamp": d.get("timestamp") or now,
            "category": str(d.get("category") or "general").strip()[:80],
            "decision": dec[:2000],
            "rationale": (str(d.get("rationale")).strip()[:2000] if d.get("rationale") else None),
            "source": str(d.get("source") or "pm_agent_turn").strip()[:80],
            "confidence": conf,
            "related_fields": d.get("related_fields")
            if isinstance(d.get("related_fields"), list)
            else [],
            "related_task_ids": d.get("related_task_ids")
            if isinstance(d.get("related_task_ids"), list)
            else [],
        }
        out.append(row)
        added += 1
    return out, added


def persist_generated_tasks(
    *,
    new_tasks: list[dict[str, Any]],
    source: str,
    brief_delta: dict[str, str] | None = None,
    replace_all_tasks: bool = False,
    brief_merge_updates: dict[str, Any] | None = None,
    brief_merge_corrections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Load PM memory, merge tasks, optional brief merge, append ``tasks_runs``, save.

    ``brief_delta`` is merged into ``brief`` via merge_brief if provided (flat string map).
    """
    if not new_tasks:
        logger.info("pm memory: persist_generated_tasks skipped (empty list) source=%s", source)
        return {"ok": True, "skipped": True}

    if not ensure_global_context_row_exists():
        logger.error(
            "pm memory persistence failed: global_context row could not be created",
        )
        return {"ok": False, "error": "no_global_context_row"}

    try:
        session = load_pm_intake_session()
    except Exception as exc:
        logger.exception("pm memory: load failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    run_id = str(uuid.uuid4())
    merged_tasks, stats = merge_tasks(
        session.generated_tasks,
        new_tasks,
        run_id=run_id,
        replace_all=replace_all_tasks,
    )
    session.generated_tasks = merged_tasks
    session.state = "tasks_generated"
    session.missing_blocking = []
    session.last_asked_fields = []

    brief_fingerprint = ""
    if brief_delta:
        session.brief = merge_brief(session.brief, brief_delta, {})
        brief_fingerprint = hashlib.sha256(
            json.dumps(brief_delta, sort_keys=True).encode()
        ).hexdigest()[:16]
    if brief_merge_updates is not None or brief_merge_corrections is not None:
        session.brief = merge_brief(
            session.brief,
            brief_merge_updates or {},
            brief_merge_corrections or {},
        )

    session.tasks_runs.append(
        {
            "run_id": run_id,
            "created_at": _iso_now(),
            "source": source,
            "task_count": len(new_tasks),
            "merged_added": stats.get("added", 0),
            "merged_updated": stats.get("updated", 0),
            "replaced_all": bool(stats.get("replaced")),
            "brief_fingerprint": brief_fingerprint or None,
        }
    )

    try:
        save_pm_intake_session(session)
    except PermissionError as exc:
        logger.warning("pm memory persistence skipped (permission): %s", exc)
        return {"ok": False, "error": str(exc)}

    if replace_all_tasks:
        logger.info(
            "stored %s generated tasks in global_context.pm_voice_intake (source=%s; full replace)",
            len(new_tasks),
            source,
        )
    else:
        logger.info(
            "stored %s generated tasks in global_context.pm_voice_intake (source=%s); "
            "merged: added=%s updated=%s",
            len(new_tasks),
            source,
            stats.get("added", 0),
            stats.get("updated", 0),
        )
    return {"ok": True, "run_id": run_id, "merge_stats": stats}


def persist_tasks_from_decomposed_plan(plan: Any, *, source: str = "plan_goal_save") -> None:
    """Map deterministic plan tasks into memory task dicts and persist (merge)."""
    tasks_out: list[dict[str, Any]] = []
    for t in getattr(plan, "tasks", []) or []:
        title = str(getattr(t, "title", "") or "").strip()
        if not title:
            continue
        tid = f"plan-{hashlib.sha256(title.encode()).hexdigest()[:16]}"
        desc = str(getattr(t, "description", "") or "").strip()
        deps = list(getattr(t, "depends_on_titles", []) or [])
        tasks_out.append(
            {
                "id": tid,
                "title": title,
                "description": desc,
                "priority": "medium",
                "status": "todo",
                "owner": None,
                "depends_on": deps,
            }
        )
    if tasks_out:
        persist_generated_tasks(new_tasks=tasks_out, source=source, replace_all_tasks=False)


def build_pm_memory_context_block(gc: GlobalContext | None) -> str:
    """Compact digest for Claude: brief highlights, tasks, decisions, last runs."""
    if gc is None:
        return "\n## PM persistent memory\n(global context unavailable)\n"
    raw = getattr(gc, "pm_voice_intake", None) or {}
    if not isinstance(raw, dict) or not raw:
        return "\n## PM persistent memory\n(empty — no prior PM voice memory in DB)\n"

    try:
        s = PmVoiceIntakeSession.model_validate(raw)
    except Exception:
        return "\n## PM persistent memory\n(unparseable session JSON)\n"

    lines: list[str] = [
        "\n## PM persistent memory (from database — reuse; do not re-ask settled items)",
        f"- state: {s.state}",
        f"- last_updated_at: {s.last_updated_at or s.updated_at or 'unknown'}",
    ]
    filled_brief = [(k, v) for k, v in s.brief.items() if str(v or "").strip()]
    if filled_brief:
        lines.append("- brief (filled fields):")
        for k, v in filled_brief[:20]:
            lines.append(f"  - {k}: {str(v)[:240]}{'…' if len(str(v)) > 240 else ''}")
    if s.generated_tasks:
        lines.append(f"- saved tasks ({len(s.generated_tasks)}):")
        for t in s.generated_tasks[:25]:
            tid = t.get("id", "")
            title = t.get("title", "")
            st = t.get("status", "")
            lines.append(f"  - [{tid}] {title} ({st})")
        if len(s.generated_tasks) > 25:
            lines.append(f"  … and {len(s.generated_tasks) - 25} more tasks")
    if s.important_decisions:
        lines.append(f"- important decisions ({len(s.important_decisions)}):")
        for d in s.important_decisions[-15:]:
            lines.append(
                f"  - [{d.get('category', '')}] {d.get('decision', '')[:200]}"
            )
    if s.tasks_runs:
        last = s.tasks_runs[-3:]
        lines.append("- recent task-generation runs:")
        for r in last:
            lines.append(
                f"  - {r.get('source')} @ {r.get('created_at') or r.get('at')}: "
                f"{r.get('task_count')} tasks"
            )
    return "\n".join(lines) + "\n"


def extract_decisions_llm(
    *,
    user_text: str,
    assistant_text: str,
    existing_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries = [
        str(d.get("decision") or "")[:120]
        for d in existing_decisions[-12:]
        if d.get("decision")
    ]
    existing_summaries = json.dumps(summaries, ensure_ascii=False) if summaries else "[]"
    system = _DECISIONS_PROMPT.format(
        user_text=(user_text or "").strip()[:8000],
        assistant_text=(assistant_text or "").strip()[:4000],
        existing_summaries=existing_summaries,
    )
    raw = llm.chat_conversation(
        system_prompt=system,
        messages=[{"role": "user", "content": "Extract decisions as JSON."}],
        temperature=0.1,
        max_tokens=1200,
    )
    from app.agents.pm.voice import _parse_claude_json

    data = _parse_claude_json(raw)
    decs = data.get("decisions")
    if not isinstance(decs, list):
        return []
    out: list[dict[str, Any]] = []
    for d in decs:
        if isinstance(d, dict) and d.get("decision"):
            out.append(d)
    return out


def persist_decisions(
    new_decisions: list[dict[str, Any]],
    *,
    source: str = "pm_voice_turn",
) -> dict[str, Any]:
    if not new_decisions:
        return {"ok": True, "added": 0}
    if not ensure_global_context_row_exists():
        logger.error("pm memory: decision persistence failed — no global_context row")
        return {"ok": False, "error": "no_global_context_row"}
    try:
        session = load_pm_intake_session()
    except Exception as exc:
        logger.exception("pm memory: load for decisions failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    for d in new_decisions:
        if isinstance(d, dict) and "source" not in d:
            d["source"] = source

    merged, added = merge_decisions(session.important_decisions, new_decisions)
    if added == 0:
        logger.info("pm memory: no new important decisions to store (deduped)")
        return {"ok": True, "added": 0}

    session.important_decisions = merged
    save_pm_intake_session(session)
    logger.info("stored %s important decision(s) in global_context.pm_voice_intake", added)
    return {"ok": True, "added": added}


def maybe_extract_and_persist_decisions(
    *,
    user_text: str,
    assistant_text: str,
) -> None:
    """Best-effort LLM extraction after a logged-in PM voice turn."""
    ut = (user_text or "").strip()
    if len(ut) < 8:
        return
    if not ensure_global_context_row_exists():
        logger.warning(
            "pm memory: decision extraction skipped — global_context row missing",
        )
        return
    try:
        session = load_pm_intake_session()
        extracted = extract_decisions_llm(
            user_text=ut,
            assistant_text=assistant_text or "",
            existing_decisions=session.important_decisions,
        )
        if extracted:
            persist_decisions(extracted, source="pm_voice_turn")
    except Exception as exc:
        logger.warning(
            "pm memory: decision extraction/persist failed: %s",
            exc,
            exc_info=True,
        )
