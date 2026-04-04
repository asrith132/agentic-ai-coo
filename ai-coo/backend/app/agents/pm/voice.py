"""
agents/pm/voice.py — PM voice intake: Claude interprets transcripts; optional ElevenLabs TTS.

Supports multi-turn sessions: the client sends prior user/assistant turns plus each new
STT segment. Realtime STT uses ElevenLabs Scribe (browser) with a server-minted token.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Mapping

import httpx

from app.agents.pm.tools import decompose_founder_goal, parse_founder_goal
from app.config import settings
from app.core.llm import llm
from app.schemas.pm import FounderGoalInput, PmVoiceTranscriptResult

logger = logging.getLogger(__name__)

# Built-in ElevenLabs premade voice (Rachel). Used for TTS only — Scribe/STT does not use this.
# Ignores ELEVENLABS_VOICE_ID in .env so you get a stable default (remove that line if unused).
ELEVENLABS_DEFAULT_TTS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

PM_VOICE_SYSTEM_PROMPT = """You are the planning intake assistant for an AI COO "PM Agent".
The conversation may include prior turns: user messages are speech-to-text transcripts from the founder; assistant messages are your own earlier short spoken replies (what they heard). Use that context so follow-up answers make sense.

The latest user message is always labeled as the current voice turn and includes the reference date.

Your job:
1. Decide if you have enough information to plan, or if you need clarification.
2. Normalize what you know into structured fields.
3. Produce a short, natural `spoken_reply` suitable for text-to-speech (one or two sentences, conversational).

Output rules — CRITICAL:
- Respond with a single JSON object only. No markdown fences, no commentary before or after.
- `status` must be exactly `"needs_clarification"` OR `"ready_to_plan"`.
- Use `"needs_clarification"` when the goal, scope, or success criteria are too vague to plan safely.
- When `needs_clarification`, set `clarification_questions` to at most 3 concise questions (strings). Leave other fields null or empty arrays when unknown.
- When `ready_to_plan`, set `clarification_questions` to [] and fill `goal` and as much else as the transcript supports.
- `deadline` must be an ISO date string `YYYY-MM-DD` or null. Never invent a deadline; infer only if the transcript clearly implies a date (use the reference date provided in the user message for relative phrases like "in two weeks").
- `priority_hint` must be one of: "low", "medium", "high", "critical".
- `constraints` and `success_criteria` are arrays of strings; use [] if none stated.
- `notes` is optional freeform; null if nothing extra.
- Do not invent company-specific facts, metrics, or stakeholders not mentioned.
- Prefer null and [] over guessing.

JSON shape (all keys must be present):
{
  "status": "needs_clarification" | "ready_to_plan",
  "goal": string | null,
  "deadline": string | null,
  "constraints": string[],
  "success_criteria": string[],
  "priority_hint": "low" | "medium" | "high" | "critical",
  "notes": string | null,
  "clarification_questions": string[],
  "spoken_reply": string
}
"""


_JSON_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    m = _JSON_FENCE_RE.match(t)
    if m:
        return m.group(1).strip()
    return t


def create_scribe_single_use_token() -> dict[str, Any]:
    """
    Mint a single-use ElevenLabs token for browser Scribe WebSocket (realtime STT).

    Raises:
        ValueError: API key not configured.
        httpx.HTTPStatusError: ElevenLabs API error.
    """
    key = (settings.elevenlabs_api_key or "").strip()
    if not key:
        raise ValueError("ELEVENLABS_API_KEY is not configured")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe",
            headers={"xi-api-key": key},
        )
        resp.raise_for_status()
        return resp.json()


def _build_claude_messages(
    conversation: list[dict[str, str]],
    final_user_content: str,
    *,
    max_turns: int = 40,
) -> list[dict[str, str]]:
    """Merge prior turns with the latest user content; enforce Anthropic user-first."""
    rows: list[dict[str, str]] = []
    for t in conversation[-max_turns:]:
        role = t.get("role")
        content = (t.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if rows and rows[-1]["role"] == role:
            rows[-1]["content"] = f'{rows[-1]["content"]}\n\n{content}'
        else:
            rows.append({"role": role, "content": content})

    final_user_content = final_user_content.strip()
    if not final_user_content:
        raise ValueError("empty final user content")

    if rows and rows[-1]["role"] == "user":
        rows[-1]["content"] = f'{rows[-1]["content"]}\n\n{final_user_content}'
    else:
        rows.append({"role": "user", "content": final_user_content})

    if rows and rows[0]["role"] == "assistant":
        rows.insert(0, {"role": "user", "content": "(Continuing the planning conversation.)"})
    return rows


def _parse_claude_json(text: str) -> dict[str, Any]:
    raw = _strip_json_fences(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude did not return valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Claude JSON root must be an object")
    return data


def _coerce_voice_result(data: dict[str, Any]) -> PmVoiceTranscriptResult:
    """Validate and normalize Claude output into the API contract."""
    status = data.get("status")
    if status not in ("needs_clarification", "ready_to_plan"):
        raise ValueError('status must be "needs_clarification" or "ready_to_plan"')

    ph = data.get("priority_hint") or "medium"
    if ph not in ("low", "medium", "high", "critical"):
        ph = "medium"

    deadline_raw = data.get("deadline")
    deadline: date | None = None
    if deadline_raw is not None and str(deadline_raw).strip():
        ds = str(deadline_raw).strip()[:10]
        try:
            deadline = date.fromisoformat(ds)
        except ValueError:
            deadline = None

    qs = data.get("clarification_questions") or []
    if not isinstance(qs, list):
        qs = []
    qs = [str(q).strip() for q in qs if str(q).strip()][:3]

    constraints = data.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = []
    constraints = [str(c).strip() for c in constraints if str(c).strip()]

    success = data.get("success_criteria") or []
    if not isinstance(success, list):
        success = []
    success = [str(s).strip() for s in success if str(s).strip()]

    goal = data.get("goal")
    goal_s = str(goal).strip() if goal is not None else None
    if goal_s == "":
        goal_s = None

    notes = data.get("notes")
    notes_s = str(notes).strip() if notes is not None else None
    if notes_s == "":
        notes_s = None

    spoken = str(data.get("spoken_reply") or "").strip()
    if not spoken:
        spoken = (
            "Could you share a bit more about what you want to accomplish?"
            if status == "needs_clarification"
            else "I have enough to work with. We can build the plan next."
        )

    if status == "ready_to_plan":
        qs = []

    return PmVoiceTranscriptResult(
        status=status,
        goal=goal_s,
        deadline=deadline,
        constraints=constraints,
        success_criteria=success,
        priority_hint=ph,
        notes=notes_s,
        clarification_questions=qs,
        spoken_reply=spoken,
    )


def generate_pm_voice_reply_text(*, structured_result: Mapping[str, Any]) -> str:
    """
    Return the voice line from a processed PM voice result (for TTS or display).
    """
    sr = structured_result.get("spoken_reply")
    return str(sr).strip() if sr else ""


def maybe_generate_tts(
    reply_text: str,
    *,
    include_audio_base64: bool = False,
) -> dict[str, Any] | None:
    """
    Optional ElevenLabs TTS. Never raises.

    Returns None when ``reply_text`` is empty. Otherwise returns a dict with at least
    ``tts_enabled`` and ``text``. On success with ``include_audio_base64``, may
    include ``audio_base64`` and ``content_type``. Voice is fixed server-side.
    """
    text = (reply_text or "").strip()
    if not text:
        return None

    key = (settings.elevenlabs_api_key or "").strip()
    voice_id = ELEVENLABS_DEFAULT_TTS_VOICE_ID

    if not key:
        return {
            "tts_enabled": False,
            "text": text,
            "message": "Set ELEVENLABS_API_KEY for synthesized audio.",
        }

    model_id = (settings.elevenlabs_tts_model_id or "").strip()
    if not model_id:
        model_id = "eleven_multilingual_v2"

    logger.info(
        "TTS requested model_id=%s include_audio=%s",
        model_id,
        include_audio_base64,
    )

    out: dict[str, Any] = {
        "tts_enabled": True,
        "text": text,
    }

    if not include_audio_base64:
        out["message"] = "Pass include_tts_audio=true on the API to receive audio_base64."
        return out

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                url,
                headers={
                    "xi-api-key": key,
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": model_id,
                },
            )
            resp.raise_for_status()
            audio = resp.content
        if not audio or len(audio) < 16:
            out["error"] = "ElevenLabs returned empty audio body"
            return out
        out["content_type"] = "audio/mpeg"
        out["audio_base64"] = base64.standard_b64encode(audio).decode("ascii")
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = (exc.response.text or "")[:400]
        except Exception:
            pass
        logger.warning(
            "ElevenLabs TTS HTTP %s: %s",
            exc.response.status_code if exc.response else "?",
            detail or exc,
        )
        out["error"] = (
            f"HTTP {exc.response.status_code}: {detail or exc}"
        ).strip()[:500]
    except Exception as exc:
        logger.warning("ElevenLabs TTS failed: %s", exc, exc_info=True)
        out["error"] = (str(exc).strip() or repr(exc))[:500]
    return out


def get_pm_tts_debug_info() -> dict[str, Any]:
    """
    TTS model + optional ElevenLabs voice name (no voice id exposed in the payload).
    """
    key = (settings.elevenlabs_api_key or "").strip()
    voice_id = ELEVENLABS_DEFAULT_TTS_VOICE_ID
    tts_model = (settings.elevenlabs_tts_model_id or "").strip()
    if not tts_model:
        tts_model = "eleven_multilingual_v2"
    scribe_model = (settings.elevenlabs_scribe_model_id or "scribe_v2_realtime").strip()

    out: dict[str, Any] = {
        "api_key_configured": bool(key),
        "tts_voice": "default",
        "tts_model_id": tts_model,
        "scribe_model_id": scribe_model,
    }

    if not key:
        out["message"] = "Set ELEVENLABS_API_KEY to enable TTS."
        return out

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"https://api.elevenlabs.io/v1/voices/{voice_id}",
                headers={"xi-api-key": key},
            )
        if resp.is_success:
            data = resp.json()
            out["elevenlabs_voice"] = {
                "name": data.get("name"),
                "category": data.get("category"),
            }
        else:
            snippet = (resp.text or "")[:400]
            missing_voices_read = False
            try:
                body = resp.json()
                detail = body.get("detail") if isinstance(body, dict) else None
                if isinstance(detail, dict) and detail.get("status") == "missing_permissions":
                    msg = str(detail.get("message", ""))
                    missing_voices_read = "voices_read" in msg
            except Exception:
                pass
            if missing_voices_read:
                out["elevenlabs_voice_lookup"] = "failed_missing_voices_read"
                out["hint"] = (
                    "Voice lookup needs the voices_read scope on your API key. "
                    "TTS still uses the built-in default voice; add voices_read in "
                    "ElevenLabs (Developers → API keys) if you want the name here."
                )
            else:
                out["elevenlabs_error"] = f"HTTP {resp.status_code}: {snippet}".strip()
    except Exception as exc:
        out["elevenlabs_error"] = (str(exc).strip() or repr(exc))[:300]

    return out


def _maybe_decomposed_plan(result: PmVoiceTranscriptResult) -> dict[str, Any] | None:
    """Build in-memory decomposed plan when status is ready_to_plan."""
    if result.status != "ready_to_plan":
        return None
    goal_text = (result.goal or "").strip() or "Voice planning request"
    if len(goal_text) < 3:
        goal_text = "Voice planning request"

    try:
        fg = FounderGoalInput(
            goal=goal_text,
            deadline=result.deadline,
            constraints=list(result.constraints),
            success_criteria=list(result.success_criteria),
            priority_hint=result.priority_hint,
            notes=result.notes,
            force_new=False,
        )
        parsed = parse_founder_goal(fg)
        plan = decompose_founder_goal(parsed)
        return {
            "parsed_goal": parsed.model_dump(mode="json"),
            "decomposed_plan": plan.model_dump(mode="json"),
        }
    except Exception as exc:
        logger.warning("PM voice decomposed plan skipped: %s", exc, exc_info=True)
        return {"decomposed_plan_error": (str(exc).strip() or repr(exc))[:500]}


def process_pm_voice_transcript(
    transcript: str,
    *,
    conversation: list[dict[str, str]] | None = None,
    include_decomposed_plan: bool = False,
    include_tts_audio: bool = False,
) -> dict[str, Any]:
    """
    Run Claude on the transcript, normalize fields, optionally attach deterministic
    decomposition, and optional TTS metadata/audio.

    ``conversation`` holds prior ``user`` / ``assistant`` turns (e.g. STT lines and
    prior ``spoken_reply`` values) for multi-turn clarification.

    Raises:
        ValueError: empty transcript or unparseable / invalid Claude output.
    """
    t = (transcript or "").strip()
    if not t:
        raise ValueError("transcript is empty")

    today = datetime.now(timezone.utc).date().isoformat()
    final_user = (
        f"Reference today's date for interpreting relative deadlines: {today}.\n\n"
        f"Latest voice transcript (current user turn):\n\"\"\"\n{t}\n\"\"\""
    )

    conv = conversation or []
    if conv:
        messages = _build_claude_messages(conv, final_user)
    else:
        messages = [{"role": "user", "content": final_user}]

    raw = llm.chat_conversation(
        system_prompt=PM_VOICE_SYSTEM_PROMPT,
        messages=messages,
        temperature=0.2,
        max_tokens=2048,
    )
    data = _parse_claude_json(raw)
    validated = _coerce_voice_result(data)

    payload = validated.model_dump(mode="json")

    if include_decomposed_plan:
        extra = _maybe_decomposed_plan(validated)
        if extra:
            payload.update(extra)

    tts = maybe_generate_tts(
        validated.spoken_reply,
        include_audio_base64=include_tts_audio,
    )
    if tts is not None:
        payload["tts"] = tts

    return payload
