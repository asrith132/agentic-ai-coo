"""
api/agents/pm.py — /api/pm/* routes

Routes:
  POST  /api/pm/plan-goal         — Validate, parse, and decompose founder goal (no persistence)
  POST  /api/pm/plan-goal/save    — Parse, decompose, and persist milestone + tasks (+ deps)
  POST  /api/pm/apply-feature-shipped — Apply feature_shipped-style payload (mark tasks / milestones)
  POST  /api/pm/reprioritize       — Deterministic backlog reprioritization + optional history row
  POST  /api/pm/sync-dependencies  — Align todo/blocked from pm_task_dependencies
  GET   /api/pm/backlog           — Read-back tasks for verification (priority desc)
  GET   /api/pm/tasks/assigned/{agent_name} — Tasks routed to a target agent (incl. done opt)
  GET   /api/pm/tasks/pickup/{agent_name} — Open execution queue for an agent
  POST  /api/pm/tasks/{task_id}/start — todo → in_progress
  POST  /api/pm/tasks/{task_id}/complete — done + dependency sync + reprioritize + milestone rollup
  POST  /api/pm/tasks/{task_id}/complete-for/{agent_name} — same, with target_agent validation
  GET   /api/pm/tasks/{task_id}/activity — Task lifecycle activity log (newest first)
  POST  /api/pm/voice/transcript — Voice: Claude when Bearer valid; else guest assistant (no 401 for anonymous)
  GET   /api/pm/voice/scribe-token — Single-use token for browser ElevenLabs realtime STT
  GET   /api/pm/voice/tts-debug — TTS model + optional ElevenLabs voice name (debug)
  GET   /api/pm/tasks              — Task backlog sorted by priority
  POST  /api/pm/tasks              — Create a task manually
  PATCH /api/pm/tasks/{id}         — Update task status or fields
  GET   /api/pm/milestones         — Milestones and progress
  POST  /api/pm/run                — Manually trigger the PM agent
  GET   /api/pm/status             — Last run status
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.agents.pm.repository import (
    fetch_backlog_tasks,
    save_decomposed_plan_to_supabase,
    start_pm_task,
)
from app.agents.pm.intake_flow import process_logged_in_pm_voice_with_intake
from app.agents.pm.pm_memory import (
    ensure_global_context_row_exists,
    maybe_extract_and_persist_decisions,
    persist_tasks_from_decomposed_plan,
)
from app.agents.pm.voice import (
    create_scribe_single_use_token,
    get_pm_tts_debug_info,
    process_guest_pm_voice_transcript,
    process_pm_voice_transcript,
)
from app.config import settings
from app.core.auth import get_voice_user_optional, require_pm_user
from app.core.context import record_pm_voice_turn
from app.agents.pm.tools import (
    PmTaskCompletionRefused,
    apply_feature_shipped_event,
    complete_pm_task,
    complete_pm_task_for_agent,
    decompose_founder_goal,
    get_open_tasks_for_agent,
    get_pm_task_activity,
    get_tasks_assigned_to_agent,
    parse_founder_goal,
    reprioritize_backlog,
    sync_task_blocked_statuses,
)
from app.schemas.pm import (
    CompletePmTaskRequest,
    FeatureShippedPayload,
    FounderGoalInput,
    PmVoiceTranscriptRequest,
    ReprioritizeRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pm", tags=["Project Management"])

_NOT_IMPLEMENTED = {"status": "not_implemented", "message": "Implemented in Prompt 4"}


def _parse_pm_task_uuid_param(task_id: str) -> str:
    """Return canonical UUID string or raise 400 for malformed ids."""
    from uuid import UUID

    raw = str(task_id or "").strip()
    try:
        return str(UUID(raw))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid task_id format",
        ) from None


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


@router.post(
    "/plan-goal",
    summary="Submit a founder goal for future PM planning",
)
def plan_goal(body: FounderGoalInput) -> dict[str, Any]:
    """
    Validate founder goal, parse workstreams, then deterministic task decomposition.
    Does not write to Supabase, emit events, or enqueue Celery work.
    """
    parsed = parse_founder_goal(body)
    plan = decompose_founder_goal(parsed)
    return {
        "message": "Goal decomposed",
        "goal": body.model_dump(mode="json"),
        "parsed": parsed.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }


@router.post(
    "/plan-goal/save",
    summary="Parse, decompose, and persist founder goal to Supabase",
)
def plan_goal_save(
    body: FounderGoalInput,
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """
    Same pipeline as /plan-goal, then writes pm_milestones, pm_tasks, and
    pm_task_dependencies when the schema supports it.
    """
    parsed = parse_founder_goal(body)
    plan = decompose_founder_goal(parsed)
    try:
        saved = save_decomposed_plan_to_supabase(
            parsed, plan, force_new=body.force_new
        )
    except Exception as exc:
        logger.exception("PM save failed")
        detail = str(exc).strip() or repr(exc)
        # Surface PostgREST / network errors in the API for local debugging
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    msg = (
        "Goal already exists"
        if saved.get("deduped")
        else "Goal decomposed and saved"
    )
    dependency_sync = sync_task_blocked_statuses()
    if not dependency_sync.get("dependency_sync_skipped"):
        dependency_sync.pop("skip_reason", None)

    out: dict[str, Any] = {
        "message": msg,
        "goal": body.model_dump(mode="json"),
        "parsed": parsed.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "saved": saved,
        "dependency_sync": dependency_sync,
    }

    if (
        not saved.get("deduped")
        and int(saved.get("tasks_created") or 0) > 0
    ):
        try:
            persist_tasks_from_decomposed_plan(plan, source="plan_goal_save")
        except Exception as exc:
            logger.warning(
                "pm memory: plan_goal_save task mirror to pm_voice_intake failed: %s",
                exc,
                exc_info=True,
            )
        try:
            rp = reprioritize_backlog(trigger_event="plan_saved")
            if rp.get("history_warning") is None:
                rp.pop("history_warning", None)
            out["reprioritize"] = rp
        except Exception as exc:
            logger.exception("reprioritize after plan save failed")
            out["reprioritize"] = {
                "error": (str(exc).strip() or repr(exc))[:2000],
            }

    return out


@router.get(
    "/backlog",
    summary="List persisted PM tasks (verification)",
)
def pm_backlog(
    include_done: bool = Query(
        default=False,
        description="If true, include completed tasks",
    ),
    limit: int = Query(default=200, le=500),
) -> dict[str, Any]:
    """Compact task list from pm_tasks, ordered by priority then created_at."""
    try:
        tasks = fetch_backlog_tasks(include_done=include_done, limit=limit)
    except Exception as exc:
        logger.exception("PM backlog fetch failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc
    return {"tasks": tasks}


@router.get(
    "/tasks/assigned/{agent_name}",
    summary="Tasks assigned to a target agent (decomposition routing)",
)
def pm_tasks_assigned_to_agent(
    agent_name: str,
    include_done: bool = Query(
        default=False,
        description="If true, include completed tasks (still sorted open-first)",
    ),
    limit: int = Query(default=200, le=500),
) -> dict[str, Any]:
    """
    Fetch persisted PM tasks for ``target_agent`` (e.g. marketing, dev_activity),
    priority order with milestone context when columns exist.
    """
    try:
        payload = get_tasks_assigned_to_agent(
            agent_name,
            include_done=include_done,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("assigned tasks fetch failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    return payload


@router.get(
    "/tasks/pickup/{agent_name}",
    summary="Open PM task queue for an agent (execution-ready)",
)
def pm_tasks_pickup(
    agent_name: str,
    limit: int = Query(default=10, ge=1, le=100),
    include_blocked: bool = Query(
        default=False,
        description="If true, include blocked tasks (still excludes done)",
    ),
) -> dict[str, Any]:
    """
    Non-done tasks for ``target_agent``, priority order. Excludes ``blocked`` by default.
    """
    try:
        return get_open_tasks_for_agent(
            agent_name,
            limit=limit,
            include_blocked=include_blocked,
        )
    except Exception as exc:
        logger.exception("PM task pickup failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc


@router.post(
    "/tasks/{task_id}/start",
    summary="Mark a PM task in progress (todo → in_progress)",
)
def pm_task_start(
    task_id: str,
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """Idempotent-friendly: only transitions from ``todo``."""
    tid = _parse_pm_task_uuid_param(task_id)
    try:
        result = start_pm_task(tid)
    except LookupError:
        raise HTTPException(status_code=404, detail="Task not found") from None
    except Exception as exc:
        logger.exception("PM task start failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc
    return result


@router.post(
    "/tasks/{task_id}/complete",
    summary="Mark PM task done; sync deps, reprioritize, complete milestone if applicable",
)
def pm_task_complete(
    task_id: str,
    body: CompletePmTaskRequest = CompletePmTaskRequest(),
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """
    Sets ``status=done`` and ``completed_at``, runs dependency sync and backlog
    reprioritization with ``trigger_event=task_completed``, then marks the parent
    milestone completed when every task in that milestone is done.
    """
    try:
        result = complete_pm_task(task_id, body.completion_note)
    except ValueError as exc:
        if str(exc) == "Invalid task_id format":
            raise HTTPException(
                status_code=400,
                detail="Invalid task_id format",
            ) from exc
        logger.exception("PM task complete validation failed")
        raise HTTPException(
            status_code=500,
            detail=(str(exc).strip() or repr(exc))[:4000],
        ) from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Task not found") from None
    except Exception as exc:
        logger.exception("PM task complete failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    return {
        "message": "Task completed",
        "result": result,
    }


@router.post(
    "/tasks/{task_id}/complete-for/{agent_name}",
    summary="Complete PM task with target_agent check for the calling agent",
)
def pm_task_complete_for_agent_route(
    task_id: str,
    agent_name: str,
    body: CompletePmTaskRequest = CompletePmTaskRequest(),
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """
    Validates UUID, ensures the task is routed to ``agent_name`` when
    ``target_agent`` is set, and refuses ``blocked`` tasks. Then runs the same
    completion pipeline as ``/complete``.
    """
    try:
        result = complete_pm_task_for_agent(
            task_id,
            agent_name,
            body.completion_note,
        )
    except PmTaskCompletionRefused as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
    except ValueError as exc:
        msg = str(exc)
        if msg == "Invalid task_id format":
            raise HTTPException(
                status_code=400,
                detail="Invalid task_id format",
            ) from exc
        if msg == "agent_name is empty":
            raise HTTPException(
                status_code=400,
                detail="agent_name is empty",
            ) from exc
        logger.exception("PM task complete-for-agent validation failed")
        raise HTTPException(
            status_code=500,
            detail=msg[:4000],
        ) from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Task not found") from None
    except Exception as exc:
        logger.exception("PM task complete-for-agent failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    agent_key = (result.get("agent_name") or str(agent_name).strip() or agent_name)
    return {
        "message": "Task completed for agent",
        "agent": agent_key,
        "result": result,
    }


@router.get(
    "/tasks/{task_id}/activity",
    summary="Read pm_task_activity rows for a task (newest first)",
)
def pm_task_activity_list(
    task_id: str,
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    tid = _parse_pm_task_uuid_param(task_id)
    return get_pm_task_activity(tid, limit=limit)


@router.get(
    "/voice/scribe-token",
    summary="Mint ElevenLabs single-use token for browser Scribe (realtime STT)",
)
def pm_voice_scribe_token() -> dict[str, Any]:
    """
    Never expose ``ELEVENLABS_API_KEY`` to the client. The browser connects to
    ``wss://api.elevenlabs.io/v1/speech-to-text/realtime`` with ``token`` + ``model_id``.
    """
    try:
        data = create_scribe_single_use_token()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc).strip()[:500],
        ) from exc
    except Exception as exc:
        logger.exception("ElevenLabs scribe token failed")
        raise HTTPException(
            status_code=502,
            detail=(str(exc).strip() or repr(exc))[:500],
        ) from exc

    token = data.get("token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="ElevenLabs token response missing token",
        )

    return {
        "token": token,
        "model_id": (settings.elevenlabs_scribe_model_id or "scribe_v2_realtime").strip(),
    }


@router.get(
    "/voice/tts-debug",
    summary="TTS debug: model + optional ElevenLabs voice name (no voice id in response)",
)
def pm_voice_tts_debug() -> dict[str, Any]:
    """
    Returns ``tts_model_id`` and, when the API key can call the voices API, the
    premade voice ``name``. Voice identifier is not included in the JSON.
    """
    return get_pm_tts_debug_info()


@router.post(
    "/voice/transcript",
    summary="Turn-based PM voice: transcript text, Claude intake, optional TTS",
)
def pm_voice_transcript(
    body: PmVoiceTranscriptRequest,
    user: dict | None = Depends(get_voice_user_optional),
    include_decomposed_plan: bool = Query(
        default=False,
        description=(
            "When true and status is ready_to_plan, attach deterministic "
            "parsed_goal + decomposed_plan (no auto-save)."
        ),
    ),
    include_tts_audio: bool = Query(
        default=False,
        description=(
            "When true and ElevenLabs env is set, include MP3 as audio_base64 in result.tts."
        ),
    ),
) -> dict[str, Any]:
    """
    Client sends each STT segment as ``transcript`` and prior turns in ``conversation``
    (user = committed STT, assistant = prior ``spoken_reply``) so Claude can clarify
    across turns. Optional ElevenLabs TTS does not affect success if it fails.

    Valid ``Authorization: Bearer`` (Supabase access token) → full Claude PM pipeline
    (intake + global context when available).

    Missing or invalid Bearer → Claude guest pipeline: model reads ``PUBLIC_PM_CONTEXT``,
    answers within guest rules, and returns ``login_required`` + ``redirect_to`` ``/login``
    when the user needs sign-in for saved planning. Falls back to rule-based guest mode
    if Claude fails (no 401).
    """
    if user is not None:
        conv = [t.model_dump(mode="python") for t in body.conversation]
        ensure_global_context_row_exists()
        try:
            result = process_logged_in_pm_voice_with_intake(
                body.transcript,
                conversation=conv,
                include_decomposed_plan=include_decomposed_plan,
                include_tts_audio=include_tts_audio,
            )
        except RuntimeError:
            logger.warning(
                "PM intake skipped: global context unavailable; falling back to legacy voice pipeline",
            )
            try:
                result = process_pm_voice_transcript(
                    body.transcript,
                    conversation=conv,
                    include_decomposed_plan=include_decomposed_plan,
                    include_tts_audio=include_tts_audio,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=str(exc).strip()[:2000],
                ) from exc
            except Exception as exc:
                logger.exception("PM voice transcript failed")
                raise HTTPException(
                    status_code=502,
                    detail=(str(exc).strip() or repr(exc))[:2000],
                ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail=str(exc).strip()[:2000],
            ) from exc
        except Exception as exc:
            logger.exception("PM voice transcript failed")
            raise HTTPException(
                status_code=502,
                detail=(str(exc).strip() or repr(exc))[:2000],
            ) from exc

        record_pm_voice_turn(body.transcript, result)
        maybe_extract_and_persist_decisions(
            user_text=body.transcript,
            assistant_text=str(result.get("spoken_reply") or ""),
        )
        return {
            "message": "Voice transcript processed",
            "result": result,
        }

    conv = [t.model_dump(mode="python") for t in body.conversation]
    try:
        result = process_guest_pm_voice_transcript(
            body.transcript,
            conversation=conv,
            include_tts_audio=include_tts_audio,
        )
    except Exception as exc:
        logger.exception("Guest PM voice transcript failed")
        raise HTTPException(
            status_code=502,
            detail=(str(exc).strip() or repr(exc))[:2000],
        ) from exc

    return {
        "message": "Voice transcript processed (guest mode)",
        "result": result,
    }


@router.post(
    "/apply-feature-shipped",
    summary="Apply feature_shipped: mark matching tasks done and roll up milestones",
)
def apply_feature_shipped(
    body: FeatureShippedPayload,
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """
    Deterministic substring match on open PM tasks, then complete milestones when
    all of their tasks are done. For manual testing; not wired to the event bus yet.
    """
    payload = body.model_dump(mode="python")
    try:
        result = apply_feature_shipped_event(payload)
    except Exception as exc:
        logger.exception("apply_feature_shipped failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    dependency_sync = sync_task_blocked_statuses()
    if not dependency_sync.get("dependency_sync_skipped"):
        dependency_sync.pop("skip_reason", None)
    result["dependency_sync"] = dependency_sync

    if result.get("tasks_marked_done", 0) > 0:
        try:
            rp = reprioritize_backlog(trigger_event="feature_shipped")
            if rp.get("history_warning") is None:
                rp.pop("history_warning", None)
            result["reprioritize"] = rp
        except Exception as exc:
            logger.exception("reprioritize after feature_shipped failed")
            result["reprioritize"] = {
                "error": (str(exc).strip() or repr(exc))[:2000],
            }

    return {
        "message": "feature_shipped applied",
        "result": result,
    }


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
def create_task(
    body: CreateTaskRequest,
    _user: dict = Depends(require_pm_user),
):
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
def update_task(
    task_id: str,
    body: PatchTaskRequest,
    _user: dict = Depends(require_pm_user),
):
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
    summary="Deterministic backlog reprioritization (scores + optional history)",
)
def pm_reprioritize(
    body: ReprioritizeRequest = ReprioritizeRequest(),
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """
    Recompute priority_score for open tasks, update Supabase, and append
    pm_priority_history when the top 3 tasks change. No LLM / Celery.
    """
    dependency_sync = sync_task_blocked_statuses()
    if not dependency_sync.get("dependency_sync_skipped"):
        dependency_sync.pop("skip_reason", None)

    try:
        result = reprioritize_backlog(trigger_event=body.trigger_event)
    except Exception as exc:
        logger.exception("PM reprioritize failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    if result.get("history_warning") is None:
        result.pop("history_warning", None)

    return {
        "message": "Backlog reprioritized",
        "dependency_sync": dependency_sync,
        "result": result,
    }


@router.post(
    "/sync-dependencies",
    summary="Sync todo/blocked from pm_task_dependencies",
)
def pm_sync_dependencies(
    _user: dict = Depends(require_pm_user),
) -> dict[str, Any]:
    """Deterministic dependency-aware status updates for manual testing."""
    try:
        sync_result = sync_task_blocked_statuses()
    except Exception as exc:
        logger.exception("dependency sync failed")
        detail = str(exc).strip() or repr(exc)
        raise HTTPException(status_code=500, detail=detail[:4000]) from exc

    if not sync_result.get("dependency_sync_skipped"):
        sync_result.pop("skip_reason", None)

    return {
        "message": "Dependency statuses synchronized",
        "result": sync_result,
    }


@router.post("/run", summary="Manually trigger the PM agent")
def run_pm(_user: dict = Depends(require_pm_user)):
    """Enqueue a manual run of the PM agent via Celery."""
    from app.api.agents._task_dispatch import dispatch_agent_run
    return dispatch_agent_run("pm", {"type": "user_request", "user_input": "manual run"})


@router.get("/status", summary="PM agent last run status")
def pm_status():
    """Return last run timestamp and current sprint summary."""
    return {"agent": "pm", "status": "idle", "last_run": None}
