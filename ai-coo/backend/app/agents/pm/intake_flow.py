"""
Logged-in PM voice: structured project intake, conditional follow-ups, task generation.

Persists session in global_context.pm_voice_intake. Reuses Claude via core.llm and
message shaping from voice.py.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.agents.pm.voice import (
    _build_claude_messages,
    _maybe_decomposed_plan,
    _parse_claude_json,
    maybe_generate_tts,
)
from app.core.context import (
    format_global_context_for_prompt,
    get_global_context,
    update_global_context,
)
from app.core.llm import llm
from app.schemas.pm import PmVoiceTranscriptResult
from app.schemas.pm_intake import (
    GeneratedIntakeTask,
    PROJECT_BRIEF_FIELD_KEYS,
    PmVoiceIntakeSession,
    empty_brief,
)

logger = logging.getLogger(__name__)

STANDARD_QUESTIONS: dict[str, str] = {
    "project_name": "What would you like to call this project?",
    "project_summary": "Can you summarize the project in one or two sentences?",
    "problem_statement": "What problem are you trying to solve?",
    "target_users": "Who is this for?",
    "primary_goal": "What is the main outcome you want from this project?",
    "success_metrics": "How will you know this is successful?",
    "scope_included": "What should definitely be included in version one?",
    "scope_excluded": "What is explicitly out of scope for now?",
    "timeline": "What timeline or target date are you working toward?",
    "priority_level": "How urgent is this compared with your other work?",
    "constraints": "Are there any major constraints like budget, time, team, or technical limitations?",
    "assumptions": "What are you assuming to be true for this plan?",
    "stakeholders": "Who needs to be involved or kept informed?",
    "dependencies": "Does this depend on any people, approvals, systems, or other work?",
    "risks": "What do you think could block or derail this?",
    "launch_or_delivery_type": (
        "Are you aiming for a prototype, internal launch, beta, or full public release?"
    ),
    "platform_or_channel": "Where will this live or ship (web, mobile, internal tool, etc.)?",
    "monetization_model": "How do you plan to monetize or fund this, if at all?",
    "technical_complexity": "How complex is the technical build from your perspective?",
    "content_or_assets_needed": "What content or assets will you need prepared?",
    "team_capacity": "What capacity does the team have to work on this?",
    "existing_progress": "What progress or assets do you already have?",
    "desired_milestones": "Are there milestone dates or checkpoints you care about?",
    "project_summary_or_problem_statement": (
        "What problem are you solving, or can you summarize the project in a sentence or two?"
    ),
}

INTAKE_SYSTEM_PROMPT = """You are an expert product manager assistant for an AI COO. The user speaks via voice; messages may be STT transcripts. Prior turns in the conversation are real user/assistant history.

## Your job this turn
1. Decide if the user is discussing a **new or ongoing product/project idea** (project intake). If they are only chatting, asking unrelated questions, or not starting/continuing a project, set `project_intake_relevant` to false and give a short helpful `spoken_reply` without fabricating a project.
2. If `project_intake_relevant` is true, **extract** every project parameter you can infer from the **entire** conversation and especially the latest user message into `brief_updates`. Use concise plain text. Only include keys you have evidence for; omit keys you are guessing without support.
3. If the user **corrects** earlier information, put overrides in `field_corrections` (same key names as brief fields).
4. If the user clearly starts a **new** project while a previous one was finished (`session_state` is tasks_generated), set `reset_intake` to true and extract into `brief_updates` (fresh start).
5. If `session_state` is tasks_generated and the user is **refining** the same plan (not starting over), set `ready_for_task_generation` to false unless they **explicitly** ask to regenerate the task list; in that case set `regenerate_tasks` to true.
6. Never put values in `brief_updates` for fields that are **already confidently filled** in CURRENT_BRIEF unless the user clearly changes them (use `field_corrections` instead).
7. **Blocking gaps** (BLOCKING_MISSING_JSON) must be resolved before task generation. Ask **only** about those blocking gaps (or the most important remaining ones if several exist). Do not ask about fields already present in CURRENT_BRIEF with a substantive value.
8. You may ask **one** focused question OR a **small grouped** question (at most 3 strings in `clarification_questions`) that only targets missing blocking fields. Do not repeat questions the user already answered in earlier messages or in CURRENT_BRIEF.
9. Set `ready_for_task_generation` to true only when BLOCKING_MISSING_JSON is empty **after** applying your proposed `brief_updates` and `field_corrections` mentally to CURRENT_BRIEF — i.e. all blocking fields would be filled (and see rule 5 if tasks were already generated).
10. `voice_status`: use `"needs_clarification"` while you still need blocking info or `project_intake_relevant` is false with a clarifying nudge; use `"ready_to_plan"` when `ready_for_task_generation` is true and the server will generate tasks this turn **or** when `session_state` is tasks_generated, blocking is satisfied, and you are only acknowledging an update without new questions.
11. `spoken_reply`: conversational, concise, suitable for TTS when possible (do not read long lists in spoken_reply; the server will attach task lists separately when needed).

## Brief field keys (strings)
""" + ", ".join(PROJECT_BRIEF_FIELD_KEYS) + """

## Standard questions (use only for missing fields; paraphrase naturally)
""" + "\n".join(
    f"- {k}: {v}" for k, v in sorted(STANDARD_QUESTIONS.items(), key=lambda kv: kv[0])
) + """

{global_context_block}

## Current session
- session_state: {session_state}
- CURRENT_BRIEF (JSON): {current_brief}
- BLOCKING_MISSING_JSON (computed server; empty list means ready): {blocking_missing}

## Output rules — CRITICAL
Respond with a **single JSON object** only. No markdown fences, no commentary.

Keys (all required):
- `project_intake_relevant`: boolean
- `reset_intake`: boolean
- `brief_updates`: object (string keys from brief field list, string values)
- `field_corrections`: object (same; explicit corrections)
- `ready_for_task_generation`: boolean
- `voice_status`: `"needs_clarification"` | `"ready_to_plan"`
- `clarification_questions`: string[] (max 3 items; empty if none needed or not relevant)
- `spoken_reply`: string
- `regenerate_tasks`: boolean (true only if user explicitly wants a fresh task list while `session_state` is tasks_generated)

Reference date for timelines: {today}
"""


TASK_GEN_SYSTEM_PROMPT = """You are a senior PM. Given a structured project brief (JSON), produce an **initial practical task breakdown** for the team.

Rules:
- Return a single JSON object with key `tasks` (array).
- Each task: `id` (short slug like "intake-1"), `title`, `description` (1-3 sentences), `priority` ("low"|"medium"|"high"|"urgent"), `status` always "todo", `owner` null or a placeholder role string, `depends_on` array of other task ids or [].
- 6–14 tasks typical. Cover: clarify requirements, MVP scope, stakeholders, timeline/milestones, metrics, dependencies/risks, content/assets, testing, launch readiness where relevant.
- Do not invent confidential facts; stay grounded in the brief and the workspace context below.

{global_context_block}

Brief JSON:
{brief_json}
"""


def _filled(v: Any) -> bool:
    return bool(v is not None and str(v).strip())


def merge_brief(
    existing: dict[str, str],
    updates: dict[str, Any] | None,
    corrections: dict[str, Any] | None,
) -> dict[str, str]:
    base = {k: (existing.get(k) or "").strip() for k in PROJECT_BRIEF_FIELD_KEYS}
    for k in PROJECT_BRIEF_FIELD_KEYS:
        if k not in base:
            base[k] = ""
    upd = updates or {}
    cor = corrections or {}
    for src in (upd, cor):
        for key, val in src.items():
            if key not in PROJECT_BRIEF_FIELD_KEYS:
                continue
            if val is None:
                continue
            s = str(val).strip()
            if s:
                base[key] = s
    return base


def blocking_missing_for_brief(brief: dict[str, str]) -> list[str]:
    """Return human/machine field ids still blocking task generation."""
    missing: list[str] = []
    if not _filled(brief.get("primary_goal")):
        missing.append("primary_goal")
    if not _filled(brief.get("target_users")):
        missing.append("target_users")
    if not _filled(brief.get("timeline")):
        missing.append("timeline")
    if not _filled(brief.get("project_summary")) and not _filled(brief.get("problem_statement")):
        missing.append("project_summary_or_problem_statement")
    if not _filled(brief.get("scope_included")):
        missing.append("scope_included")
    return missing


def _coerce_intake_llm(data: dict[str, Any]) -> dict[str, Any]:
    rel = bool(data.get("project_intake_relevant", True))
    reset = bool(data.get("reset_intake"))
    brief_updates = data.get("brief_updates")
    if brief_updates is not None and not isinstance(brief_updates, dict):
        brief_updates = {}
    field_corrections = data.get("field_corrections")
    if field_corrections is not None and not isinstance(field_corrections, dict):
        field_corrections = {}
    ready = bool(data.get("ready_for_task_generation"))
    vs = data.get("voice_status")
    if vs not in ("needs_clarification", "ready_to_plan"):
        vs = "needs_clarification"
    qs = data.get("clarification_questions") or []
    if not isinstance(qs, list):
        qs = []
    qs = [str(q).strip() for q in qs if str(q).strip()][:3]
    spoken = str(data.get("spoken_reply") or "").strip()
    regen = bool(data.get("regenerate_tasks"))
    return {
        "project_intake_relevant": rel,
        "reset_intake": reset,
        "brief_updates": brief_updates or {},
        "field_corrections": field_corrections or {},
        "ready_for_task_generation": ready,
        "voice_status": vs,
        "clarification_questions": qs,
        "spoken_reply": spoken,
        "regenerate_tasks": regen,
    }


def _generate_tasks_from_brief(
    brief: dict[str, str],
    *,
    global_context_block: str = "",
) -> list[dict[str, Any]]:
    brief_json = json.dumps(brief, ensure_ascii=False, indent=2)
    gc_block = global_context_block.strip() or "(No global workspace context attached.)"
    raw = llm.chat_conversation(
        system_prompt=TASK_GEN_SYSTEM_PROMPT.format(
            brief_json=brief_json,
            global_context_block=gc_block,
        ),
        messages=[{"role": "user", "content": "Generate the initial task list as JSON."}],
        temperature=0.35,
        max_tokens=4096,
    )
    data = _parse_claude_json(raw)
    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, list):
        raise ValueError("task generation: expected tasks array")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(tasks_raw):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or "").strip() or f"intake-{i + 1}"
        title = str(item.get("title") or "").strip() or f"Task {i + 1}"
        desc = str(item.get("description") or "").strip()
        pr = str(item.get("priority") or "medium").strip().lower()
        if pr not in ("low", "medium", "high", "urgent"):
            pr = "medium"
        st = str(item.get("status") or "todo").strip().lower()
        if st not in ("todo", "in_progress", "blocked", "done"):
            st = "todo"
        owner = item.get("owner")
        owner_s = str(owner).strip() if owner is not None else ""
        dep = item.get("depends_on")
        deps: list[str] = []
        if isinstance(dep, list):
            deps = [str(x).strip() for x in dep if str(x).strip()]
        try:
            gt = GeneratedIntakeTask(
                id=tid,
                title=title,
                description=desc,
                priority=pr,  # type: ignore[arg-type]
                status=st,  # type: ignore[arg-type]
                owner=owner_s or None,
                depends_on=deps,
            )
            out.append(gt.model_dump(mode="json"))
        except Exception:
            out.append(
                {
                    "id": tid,
                    "title": title,
                    "description": desc,
                    "priority": pr,
                    "status": st,
                    "owner": owner_s or None,
                    "depends_on": deps,
                }
            )
    if not out:
        raise ValueError("task generation produced no tasks")
    return out


def brief_from_legacy_pm_voice(result: PmVoiceTranscriptResult) -> dict[str, str]:
    """Map classic PM voice JSON (goal, deadline, …) into a project brief for task-generation LLM."""
    b = merge_brief(empty_brief(), {}, {})
    goal = (result.goal or "").strip()
    if goal:
        b["primary_goal"] = goal
        b["project_summary"] = goal
        b["problem_statement"] = goal[:1200] if len(goal) > 1200 else goal
    if result.deadline is not None:
        b["timeline"] = result.deadline.isoformat()
    if not _filled(b.get("timeline")):
        b["timeline"] = "As discussed in the voice planning session"
    if result.constraints:
        b["constraints"] = "; ".join(str(c).strip() for c in result.constraints if str(c).strip())
    if result.success_criteria:
        b["success_metrics"] = "; ".join(
            str(s).strip() for s in result.success_criteria if str(s).strip()
        )
    if result.notes:
        b["assumptions"] = str(result.notes).strip()[:2000]
    b["target_users"] = "Founder / team as described in the voice session"
    b["scope_included"] = "Work implied by the stated goal, MVP, and launch preparation"
    ph = getattr(result, "priority_hint", None)
    if ph:
        b["priority_level"] = str(ph)
    return b


def attach_tasks_to_legacy_voice_result(result: PmVoiceTranscriptResult) -> dict[str, Any]:
    """
    When classic ``process_pm_voice_transcript`` returns ``ready_to_plan``, generate the same
    style of initial task list as structured intake (no global_context required). Does not
    persist to ``pm_tasks`` — that remains a separate API.
    """
    from app.core.context import format_global_context_for_prompt, try_get_global_context

    brief = brief_from_legacy_pm_voice(result)
    gc_block = format_global_context_for_prompt(try_get_global_context())
    tasks = _generate_tasks_from_brief(brief, global_context_block=gc_block)
    logger.info(
        "PM_LEGACY_VOICE_GENERATED_TASKS count=%s tasks=%s",
        len(tasks),
        json.dumps(tasks, ensure_ascii=False),
    )
    tasks_text = _format_tasks_for_ui(tasks)
    spoken = _spoken_with_task_summary(str(result.spoken_reply or ""), tasks)
    return {
        "generated_tasks": tasks,
        "tasks_display_text": tasks_text,
        "spoken_reply": spoken,
        "legacy_voice_with_tasks": True,
    }


def _format_tasks_for_ui(tasks: list[dict[str, Any]]) -> str:
    lines = ["--- Generated initial tasks ---", ""]
    for t in tasks:
        tid = t.get("id", "")
        title = t.get("title", "")
        desc = (t.get("description") or "").strip()
        pr = t.get("priority", "medium")
        deps = t.get("depends_on") or []
        dep_s = ", ".join(deps) if deps else "—"
        lines.append(f"**[{tid}]** {title} _(priority: {pr})_")
        if desc:
            lines.append(f"  {desc}")
        lines.append(f"  Depends on: {dep_s}")
        lines.append("")
    return "\n".join(lines).strip()


def _spoken_with_task_summary(spoken: str, tasks: list[dict[str, Any]]) -> str:
    spoken = (spoken or "").strip()
    n = len(tasks)
    titles = [str(t.get("title") or "") for t in tasks[:6]]
    bullet = "\n".join(f"- {x}" for x in titles if x)
    more = f"\n… and {n - len(titles)} more (see tasks_display_text)." if n > len(titles) else ""
    block = f"\n\n--- Generated initial tasks ({n}) ---\n{bullet}{more}"
    return (spoken + block).strip()


def _fallback_questions_for_blocking(missing: list[str]) -> list[str]:
    out: list[str] = []
    for m in missing:
        q = STANDARD_QUESTIONS.get(m)
        if q and q not in out:
            out.append(q)
        if len(out) >= 3:
            break
    return out


def _pm_result_from_intake(
    *,
    status: str,
    spoken_reply: str,
    brief: dict[str, str],
    clarification_questions: list[str],
    priority_hint: str = "medium",
) -> PmVoiceTranscriptResult:
    goal = (brief.get("primary_goal") or brief.get("project_summary") or "").strip() or None
    deadline: date | None = None
    tl = (brief.get("timeline") or "").strip()
    if tl:
        m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", tl)
        if m:
            try:
                deadline = date.fromisoformat(m.group(0)[:10])
            except ValueError:
                deadline = None
    constraints: list[str] = []
    if _filled(brief.get("constraints")):
        constraints = [brief["constraints"]]
    success: list[str] = []
    if _filled(brief.get("success_metrics")):
        success = [brief["success_metrics"]]
    notes_parts = []
    if _filled(brief.get("project_name")):
        notes_parts.append(f"Project: {brief['project_name']}")
    if _filled(brief.get("problem_statement")):
        notes_parts.append(f"Problem: {brief['problem_statement'][:500]}")
    notes = "\n".join(notes_parts) if notes_parts else None
    ph = priority_hint
    if ph not in ("low", "medium", "high", "critical"):
        pl = (brief.get("priority_level") or "").lower()
        if "critical" in pl or "urgent" in pl:
            ph = "critical"
        elif "high" in pl:
            ph = "high"
        elif "low" in pl:
            ph = "low"
        else:
            ph = "medium"
    if status == "ready_to_plan":
        clarification_questions = []
    return PmVoiceTranscriptResult(
        status=status,  # type: ignore[arg-type]
        goal=goal,
        deadline=deadline,
        constraints=constraints,
        success_criteria=success,
        priority_hint=ph,  # type: ignore[arg-type]
        notes=notes,
        clarification_questions=clarification_questions,
        spoken_reply=spoken_reply,
    )


def process_logged_in_pm_voice_with_intake(
    transcript: str,
    *,
    conversation: list[dict[str, str]] | None = None,
    include_decomposed_plan: bool = False,
    include_tts_audio: bool = False,
) -> dict[str, Any]:
    """
    Structured intake + task generation for authenticated PM voice.
    Persists ``pm_voice_intake`` on global_context.
    """
    t = (transcript or "").strip()
    if not t:
        raise ValueError("transcript is empty")

    today = datetime.now(timezone.utc).date().isoformat()
    final_user = (
        f"Reference today's date for interpreting relative timelines: {today}.\n\n"
        f"Latest voice transcript (current user turn):\n\"\"\"\n{t}\n\"\"\""
    )
    conv = conversation or []
    messages = (
        _build_claude_messages(conv, final_user)
        if conv
        else [{"role": "user", "content": final_user}]
    )

    ctx = get_global_context()
    raw_session = getattr(ctx, "pm_voice_intake", None) or {}
    if not isinstance(raw_session, dict):
        raw_session = {}
    session = PmVoiceIntakeSession.model_validate(raw_session)

    # Ensure brief has all keys for stable merge/display
    session.brief = merge_brief(session.brief, {}, {})

    blocking_before = blocking_missing_for_brief(session.brief)
    gc_block = format_global_context_for_prompt(ctx)
    system = INTAKE_SYSTEM_PROMPT.format(
        global_context_block=gc_block
        if gc_block.strip()
        else "\n## Global workspace context\n(No database row or empty context.)\n",
        session_state=session.state,
        current_brief=json.dumps(session.brief, ensure_ascii=False),
        blocking_missing=json.dumps(blocking_before),
        today=today,
    )

    raw = llm.chat_conversation(
        system_prompt=system,
        messages=messages,
        temperature=0.2,
        max_tokens=3072,
    )
    data = _coerce_intake_llm(_parse_claude_json(raw))

    if not data["project_intake_relevant"]:
        session.state = "idle"
        session.missing_blocking = []
        session.last_asked_fields = []
        session.updated_at = datetime.now(timezone.utc).isoformat()
        update_global_context("pm_voice_intake", session.model_dump(mode="json"), "pm")
        spoken = data["spoken_reply"] or "Tell me about a project you have in mind when you are ready."
        vr = _pm_result_from_intake(
            status="needs_clarification",
            spoken_reply=spoken,
            brief=session.brief,
            clarification_questions=[],
        )
        payload = vr.model_dump(mode="json")
        payload["pm_intake_state"] = session.state
        payload["project_brief"] = session.brief
        payload["generated_tasks"] = []
        payload["tasks_display_text"] = ""
        payload["intake_flow"] = True
        tts = maybe_generate_tts(spoken, include_audio_base64=include_tts_audio)
        if tts is not None:
            payload["tts"] = tts
        return payload

    if data["reset_intake"]:
        session = PmVoiceIntakeSession(
            state="intake_in_progress",
            brief=merge_brief(empty_brief(), data["brief_updates"], data["field_corrections"]),
        )
    else:
        session.brief = merge_brief(
            session.brief,
            data["brief_updates"],
            data["field_corrections"],
        )

    blocking_after = blocking_missing_for_brief(session.brief)
    session.missing_blocking = blocking_after
    regenerate = bool(data["regenerate_tasks"])

    may_generate_tasks = session.state != "tasks_generated" or regenerate
    ready = (
        data["ready_for_task_generation"]
        and len(blocking_after) == 0
        and may_generate_tasks
    )
    if data["ready_for_task_generation"] and blocking_after:
        logger.info(
            "PM intake: model claimed ready but blocking remains: %s",
            blocking_after,
        )

    def _persist_and_return(
        *,
        vr: PmVoiceTranscriptResult,
        tasks_display_text: str,
    ) -> dict[str, Any]:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        update_global_context("pm_voice_intake", session.model_dump(mode="json"), "pm")
        payload = vr.model_dump(mode="json")
        payload["pm_intake_state"] = session.state
        payload["project_brief"] = session.brief
        payload["generated_tasks"] = list(session.generated_tasks)
        payload["tasks_display_text"] = tasks_display_text
        payload["intake_flow"] = True
        if include_decomposed_plan:
            extra = _maybe_decomposed_plan(vr)
            if extra:
                payload.update(extra)
        tts = maybe_generate_tts(vr.spoken_reply, include_audio_base64=include_tts_audio)
        if tts is not None:
            payload["tts"] = tts
        return payload

    if session.state == "tasks_generated" and not regenerate:
        clarification = list(data["clarification_questions"])
        if blocking_after:
            if not clarification:
                clarification = _fallback_questions_for_blocking(blocking_after)
            session.state = "awaiting_fields"
            session.last_asked_fields = blocking_after[:5]
            spoken = data["spoken_reply"] or (
                " ".join(clarification) if clarification else "What else should we clarify?"
            )
            vr = _pm_result_from_intake(
                status="needs_clarification",
                spoken_reply=spoken,
                brief=session.brief,
                clarification_questions=clarification,
            )
            td = _format_tasks_for_ui(session.generated_tasks) if session.generated_tasks else ""
            return _persist_and_return(vr=vr, tasks_display_text=td)

        session.state = "tasks_generated"
        session.last_asked_fields = []
        spoken = data["spoken_reply"] or (
            "I've noted that update. Your earlier task list is still available in the response."
        )
        vs = data["voice_status"]
        st = vs if vs in ("needs_clarification", "ready_to_plan") else "ready_to_plan"
        clar_out: list[str] = []
        if st == "needs_clarification":
            clar_out = clarification[:3]
        if st == "needs_clarification" and not clar_out:
            st = "ready_to_plan"
        vr = _pm_result_from_intake(
            status=st,
            spoken_reply=spoken,
            brief=session.brief,
            clarification_questions=clar_out,
        )
        td = _format_tasks_for_ui(session.generated_tasks) if session.generated_tasks else ""
        return _persist_and_return(vr=vr, tasks_display_text=td)

    clarification = list(data["clarification_questions"])
    if not ready:
        if not clarification and blocking_after:
            clarification = _fallback_questions_for_blocking(blocking_after)
        session.state = "awaiting_fields" if clarification else "intake_in_progress"
        session.last_asked_fields = blocking_after[:5]
        spoken = data["spoken_reply"] or " ".join(clarification) if clarification else (
            "Could you add a bit more detail so we can plan?"
        )
        vr = _pm_result_from_intake(
            status="needs_clarification",
            spoken_reply=spoken,
            brief=session.brief,
            clarification_questions=clarification,
        )
        return _persist_and_return(vr=vr, tasks_display_text="")

    # Generate tasks
    session.state = "intake_complete"
    session.updated_at = datetime.now(timezone.utc).isoformat()
    update_global_context("pm_voice_intake", session.model_dump(mode="json"), "pm")

    try:
        ctx_for_tasks = get_global_context()
        gc_for_tasks = format_global_context_for_prompt(ctx_for_tasks)
        new_tasks = _generate_tasks_from_brief(
            session.brief,
            global_context_block=gc_for_tasks
            if gc_for_tasks.strip()
            else "\n## Global workspace context\n(Context empty.)\n",
        )
    except Exception as exc:
        logger.exception("PM intake task generation failed: %s", exc)
        session.state = "awaiting_fields"
        session.updated_at = datetime.now(timezone.utc).isoformat()
        update_global_context("pm_voice_intake", session.model_dump(mode="json"), "pm")
        raise ValueError(f"Task generation failed: {exc}") from exc

    logger.info(
        "PM_INTAKE_GENERATED_TASKS count=%s tasks=%s",
        len(new_tasks),
        json.dumps(new_tasks, ensure_ascii=False),
    )

    session.generated_tasks = new_tasks
    session.tasks_runs.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "task_count": len(new_tasks),
            "run_id": str(uuid.uuid4()),
        }
    )
    session.state = "tasks_generated"
    session.last_asked_fields = []
    session.missing_blocking = []
    session.updated_at = datetime.now(timezone.utc).isoformat()
    update_global_context("pm_voice_intake", session.model_dump(mode="json"), "pm")

    tasks_text = _format_tasks_for_ui(new_tasks)
    spoken_base = data["spoken_reply"] or "Here is an initial task breakdown based on what we captured."
    spoken_full = _spoken_with_task_summary(spoken_base, new_tasks)

    vr = _pm_result_from_intake(
        status="ready_to_plan",
        spoken_reply=spoken_full,
        brief=session.brief,
        clarification_questions=[],
    )
    payload = vr.model_dump(mode="json")
    payload["pm_intake_state"] = session.state
    payload["project_brief"] = session.brief
    payload["generated_tasks"] = new_tasks
    payload["tasks_display_text"] = tasks_text
    payload["intake_flow"] = True

    if include_decomposed_plan:
        extra = _maybe_decomposed_plan(vr)
        if extra:
            payload.update(extra)

    tts = maybe_generate_tts(spoken_full, include_audio_base64=include_tts_audio)
    if tts is not None:
        payload["tts"] = tts

    return payload
