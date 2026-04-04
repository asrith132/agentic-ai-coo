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
        description="Append-only history of {at, task_count} for debugging",
    )
    updated_at: str = ""

    def brief_nonempty_keys(self) -> set[str]:
        return {k for k, v in self.brief.items() if str(v or "").strip()}


def empty_brief() -> dict[str, str]:
    return {k: "" for k in PROJECT_BRIEF_FIELD_KEYS}
