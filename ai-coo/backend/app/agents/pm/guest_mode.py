"""
Deterministic guest-mode PM responses: no LLM, no Supabase.

Classifies user text as informational vs planning/action and returns a small
JSON-shaped dict for /api/public/pm-chat and anonymous PM voice responses.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.public_context import PUBLIC_PM_CONTEXT

# Voice + UI copy when guest tries a protected action (post-listen redirect flow).
LOGIN_REQUIRED_SPOKEN_REPLY = (
    "You need to sign in to continue. Redirecting you to the login page."
)


def _starters() -> list[str]:
    return list(PUBLIC_PM_CONTEXT.get("starter_prompts") or [])


def _assistant_name() -> str:
    return str(PUBLIC_PM_CONTEXT.get("assistant_name") or "PM Agent")


def _product_description() -> str:
    return str(
        PUBLIC_PM_CONTEXT.get("product_description")
        or "A planning agent that turns startup goals into executable tasks."
    )


def _login_payload(spoken: str) -> dict[str, Any]:
    return {
        "status": "login_required",
        "spoken_reply": spoken,
        "starter_prompts": _starters(),
        "redirect_to": "/login",
    }


def _guest_answer_payload(spoken: str) -> dict[str, Any]:
    return {
        "status": "guest_answer",
        "spoken_reply": spoken,
        "starter_prompts": _starters(),
        "redirect_to": None,
    }


# Informational: user wants to understand the product, not execute planning.
_INFO_RES = [
    re.compile(
        r"\b(what\s+(does|do|is)|who\s+are\s+you|tell\s+me\s+about)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(what\s+can\s+you\s+do|how\s+can\s+you\s+help|how\s+do\s+you\s+help)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(show\s+(me\s+)?starter\s+prompts?|starter\s+prompts?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(what\s+is\s+(the\s+)?pm\s+agent)\b", re.IGNORECASE),
]

# Planning / persistence / concrete execution — require login.
_ACTION_RES = [
    re.compile(r"\bcreate\s+(a\s+)?tasks?\b", re.IGNORECASE),
    re.compile(r"\b(save|persist)\s+(my\s+)?(plan|tasks?|milestones?)\b", re.IGNORECASE),
    re.compile(r"\b(build|make|create)\s+(me\s+)?(a\s+)?roadmap\b", re.IGNORECASE),
    re.compile(r"\bplan\s+my\b", re.IGNORECASE),
    re.compile(r"\bnext\s+(2|two)\s+weeks\b", re.IGNORECASE),
    re.compile(r"\bbreak\s+.{0,40}\s+into\s+tasks?\b", re.IGNORECASE),
    re.compile(r"\bbreak\s+down\s+my\b", re.IGNORECASE),
    re.compile(r"\bdecompose\b", re.IGNORECASE),
    re.compile(r"\bassign\s+.{0,20}\s+tasks?\b", re.IGNORECASE),
    re.compile(r"\b(add\s+to\s+)?backlog\b", re.IGNORECASE),
    re.compile(r"\bmilestones?\s+for\s+me\b", re.IGNORECASE),
    re.compile(
        r"\b(launch|ship|release|build)\s+.{0,30}(paid\s+tier|pricing)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bexecutable\s+tasks?\b", re.IGNORECASE),
    re.compile(r"\bturn\s+.{0,40}\s+into\s+tasks?\b", re.IGNORECASE),
    re.compile(
        r"\bhelp\s+me\s+.{0,40}\b(launch|ship|plan|build|organize|prioritize)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI\s+need\s+.{0,30}\b(plan|roadmap|tasks?|milestones?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(startup|founder)\s+.{0,20}\b(goals?|roadmap|plan)\b", re.IGNORECASE),
]


def _is_informational(text: str) -> bool:
    return any(p.search(text) for p in _INFO_RES)


# If action phrase is preceded by a question cue, treat as meta-question not a command.
_QUESTION_CUE = re.compile(
    r"\b(how|why|what|when|where|could\s+you|can\s+you|do\s+you|"
    r"explain|tell\s+me|describe|show\s+me)\b",
    re.IGNORECASE,
)


def _is_action_or_planning(text: str) -> bool:
    tail_window = 55
    for pat in _ACTION_RES:
        m = pat.search(text)
        if not m:
            continue
        prefix = text[: m.start()]
        tail = prefix[-tail_window:] if len(prefix) > tail_window else prefix
        if _QUESTION_CUE.search(tail):
            continue
        return True
    return False


def handle_guest_pm_input(message: str) -> dict[str, Any]:
    """
    Classify ``message`` and return guest_answer or login_required payload.

    No side effects. Deterministic only.
    """
    text = (message or "").strip()
    if not text:
        name = _assistant_name()
        desc = _product_description()
        spoken = (
            f"Hi! I'm {name}. {desc} "
            "Before you log in, I can explain how I work and show starter ideas. "
            "Log in when you're ready so I can save context and create real tasks."
        )
        return _guest_answer_payload(spoken)

    # Meta-questions first so "how do you create tasks?" stays guest-safe.
    if _is_informational(text):
        prompts = _starters()
        examples = "; ".join(f'"{p}"' for p in prompts[:3]) if prompts else "your goals"
        spoken = (
            f"I'm {_assistant_name()}. {_product_description()} "
            f"Here are some ways people start: {examples}. "
            "Log in when you want me to turn a real goal into saved tasks."
        )
        return _guest_answer_payload(spoken)

    if _is_action_or_planning(text):
        return _login_payload(LOGIN_REQUIRED_SPOKEN_REPLY)

    # Default: short onboarding nudge (ambiguous short utterances stay guest-safe).
    spoken = (
        f"I'm {_assistant_name()}. {_product_description()} "
        "Ask what I can do, or log in to plan and save tasks."
    )
    return _guest_answer_payload(spoken)


def build_guest_pm_voice_payload(
    transcript: str,
    *,
    include_tts_audio: bool,
) -> dict[str, Any]:
    """
    Shape a PM voice ``result`` dict compatible with the authenticated endpoint,
    plus optional ``tts`` from ElevenLabs (same as private flow).

    Caller supplies ``include_tts_audio``; this function runs ``maybe_generate_tts``.
    """
    from app.agents.pm.voice import maybe_generate_tts

    guest = handle_guest_pm_input(transcript)
    spoken = str(guest.get("spoken_reply") or "").strip()
    out: dict[str, Any] = {
        "status": guest["status"],
        "goal": None,
        "deadline": None,
        "constraints": [],
        "success_criteria": [],
        "priority_hint": "medium",
        "notes": None,
        "clarification_questions": [],
        "spoken_reply": spoken,
        "starter_prompts": guest.get("starter_prompts") or [],
        "redirect_to": guest.get("redirect_to"),
        "guest_mode": True,
    }
    tts = maybe_generate_tts(spoken, include_audio_base64=include_tts_audio)
    if tts is not None:
        out["tts"] = tts
    return out
