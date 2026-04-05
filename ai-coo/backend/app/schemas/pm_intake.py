"""
Structured PM voice project intake (brief) and session state stored in global_context.pm_voice_intake.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

IntakeStateLiteral = Literal[
    "idle",
    "intake_in_progress",
    "awaiting_fields",
    "intake_complete",
    "ready_to_plan",
    "tasks_generated",
]

# All brief field keys the extractor and UI care about (string values; empty = unknown).
PROJECT_BRIEF_FIELD_KEYS: tuple[str, ...] = (
    "project_name",
    "project_summary",
    "problem_statement",
    "target_users",
    "primary_goal",
    "success_metrics",
    "scope_included",
    "scope_excluded",
    "timeline",
    "priority_level",
    "constraints",
    "assumptions",
    "stakeholders",
    "dependencies",
    "risks",
    "launch_or_delivery_type",
    "platform_or_channel",
    "monetization_model",
    "technical_complexity",
    "content_or_assets_needed",
    "team_capacity",
    "existing_progress",
    "desired_milestones",
)


def merge_brief(
    existing: dict[str, str],
    updates: dict[str, Any] | None,
    corrections: dict[str, Any] | None,
) -> dict[str, str]:
    """Merge string brief fields; non-empty updates and corrections win."""
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


class GeneratedIntakeTask(BaseModel):
    """One PM-style task emitted after intake is complete enough."""

    model_config = {"extra": "ignore"}

    id: str
    title: str
    description: str = ""
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    status: Literal["todo", "in_progress", "blocked", "done"] = "todo"
    owner: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class PmVoiceIntakeSession(BaseModel):
    """Persisted under global_context.pm_voice_intake."""

    model_config = {"extra": "ignore"}

    state: IntakeStateLiteral = "idle"
    brief: dict[str, str] = Field(default_factory=dict)
    missing_blocking: list[str] = Field(default_factory=list)
    last_asked_fields: list[str] = Field(default_factory=list)
    generated_tasks: list[dict[str, Any]] = Field(default_factory=list)
    tasks_runs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Append-only history of task-generation runs",
    )
    important_decisions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured decisions extracted from PM conversations",
    )
    updated_at: str = ""
    last_updated_at: str = ""

    def brief_nonempty_keys(self) -> set[str]:
        return {k for k, v in self.brief.items() if str(v or "").strip()}


def empty_brief() -> dict[str, str]:
    return {k: "" for k in PROJECT_BRIEF_FIELD_KEYS}
