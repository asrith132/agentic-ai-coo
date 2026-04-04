"""
Public (no-auth) routes for guest PM onboarding.

Routes:
  GET  /api/public/pm-context — Static guest context for UI copy
  POST /api/public/pm-chat   — Deterministic guest replies (no LLM / no DB)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.agents.pm.guest_mode import handle_guest_pm_input
from app.core.public_context import PUBLIC_PM_CONTEXT
from app.schemas.pm import PublicPmChatRequest

router = APIRouter(prefix="/api/public", tags=["Public"])


@router.get(
    "/pm-context",
    summary="Guest PM context (assistant copy, rules, starter prompts)",
)
def get_public_pm_context() -> dict[str, Any]:
    return {
        "assistant_name": PUBLIC_PM_CONTEXT["assistant_name"],
        "product_description": PUBLIC_PM_CONTEXT["product_description"],
        "guest_mode_rules": list(PUBLIC_PM_CONTEXT["guest_mode_rules"]),
        "starter_prompts": list(PUBLIC_PM_CONTEXT["starter_prompts"]),
    }


@router.post(
    "/pm-chat",
    summary="Guest PM chat (deterministic; no persistence)",
)
def post_public_pm_chat(body: PublicPmChatRequest) -> dict[str, Any]:
    return handle_guest_pm_input(body.message)
