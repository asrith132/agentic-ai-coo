"""
schemas/pm.py — Pydantic models for PM agent API inputs.

Founder-facing payloads accepted by /api/pm/* before decomposition or persistence.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FounderGoalInput(BaseModel):
    """High-level goal and planning hints from a founder (Task 1.1 input contract)."""

    goal: str = Field(
        ...,
        min_length=3,
        description="High-level founder instruction",
    )
    deadline: date | None = Field(
        default=None,
        description="Optional deadline for completing the goal",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints the PM Agent should respect",
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description="Conditions that define success",
    )
    priority_hint: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description="Founder-provided urgency hint",
    )
    notes: str | None = Field(
        default=None,
        description="Additional planning context",
    )
    force_new: bool = Field(
        default=False,
        description="If true, always create a new milestone even when an active/planned goal with the same title exists",
    )


class FeatureShippedPayload(BaseModel):
    """Normalized contract for feature_shipped-style matching and APIs."""

    model_config = ConfigDict(extra="ignore")

    feature_name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    changelog_entry: str | None = Field(default=None)


class ParsedFounderGoal(BaseModel):
    """Deterministic parse of a founder goal for planning (no LLM, no persistence)."""

    objective: str = Field(description="Condensed objective, usually derived from goal text")
    deadline: date | None = Field(
        default=None,
        description="Deadline from input, unchanged",
    )
    priority_hint: Literal["low", "medium", "high", "critical"] = Field(
        description="Echo of founder urgency hint",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints passed through from input",
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description="Success criteria passed through from input",
    )
    workstreams: list[str] = Field(
        default_factory=list,
        description="Inferred workstream tags (deterministic keyword rules)",
    )
    planning_summary: str = Field(
        description="One-line summary of goal and likely workstreams",
    )


TargetAgentLiteral = Literal[
    "dev_activity",
    "outreach",
    "marketing",
    "finance",
    "pm",
    "research",
    "legal",
]

TaskTypeLiteral = Literal[
    "research",
    "implementation",
    "content",
    "outreach",
    "compliance",
    "analysis",
    "planning",
]

ImpactAreaLiteral = Literal[
    "revenue",
    "growth",
    "compliance",
    "product",
    "cost",
    "retention",
]

UrgencyLiteral = Literal["low", "medium", "high", "critical"]


class DecomposedTask(BaseModel):
    """A single generated subtask from deterministic decomposition (not persisted)."""

    title: str
    description: str
    target_agent: TargetAgentLiteral
    task_type: TaskTypeLiteral
    impact_area: ImpactAreaLiteral
    urgency: UrgencyLiteral
    effort_points: int
    depends_on_titles: list[str] = Field(default_factory=list)


class DecomposedGoalPlan(BaseModel):
    """Parent plan plus decomposed tasks and notes (in-memory only until persistence exists)."""

    parent_title: str
    parent_description: str | None = None
    tasks: list[DecomposedTask] = Field(default_factory=list)
    planning_notes: list[str] = Field(default_factory=list)


class ReprioritizeRequest(BaseModel):
    """Optional body for deterministic backlog reprioritization."""

    trigger_event: str | None = Field(
        default=None,
        description="Label stored in pm_priority_history.trigger_event (default: manual_reprioritize)",
    )


class CompletePmTaskRequest(BaseModel):
    """Optional body when an agent reports a PM task as complete."""

    completion_note: str | None = Field(
        default=None,
        description="Optional note echoed in the response (not persisted unless a column is added later).",
    )
