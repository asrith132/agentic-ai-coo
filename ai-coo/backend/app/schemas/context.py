"""
schemas/context.py — Pydantic models for Global Context.

GlobalContext mirrors the `global_context` table. Every JSONB column is typed
as a dict so callers get IDE completion while still being flexible for schema
evolution. Agents cast to stricter sub-models in their own domain code.
"""

from __future__ import annotations
from typing import Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """Identifies the company being operated by the AI COO."""
    name: str = ""
    website: str = ""
    industry: str = ""
    stage: str = ""           # e.g. "pre-seed", "seed", "series-a"
    founded_year: int | None = None
    team_size: int | None = None
    description: str = ""


class TargetCustomer(BaseModel):
    """ICP definition used by outreach, marketing, and research agents."""
    persona: str = ""
    pain_points: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    company_size: str = ""
    geography: str = ""


class BusinessState(BaseModel):
    """Live business metrics — updated by finance and dev agents."""
    mrr: float | None = None
    runway_months: float | None = None
    active_users: int | None = None
    open_issues: int | None = None
    last_deploy: str | None = None  # ISO timestamp
    current_sprint_goal: str = ""


class BrandVoice(BaseModel):
    """Tone and style guide used by marketing and outreach agents."""
    tone: str = ""
    values: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    example_copy: str = ""


class CompetitiveLandscape(BaseModel):
    """Known competitors — updated by research agent."""
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    positioning: str = ""
    differentiators: list[str] = Field(default_factory=list)


class GlobalContext(BaseModel):
    """
    Full global context row. Agents read this at the start of every run.

    The `recent_events` field is a rolling list of the last ~20 event summaries
    injected into agent system prompts so they have situational awareness.
    """
    id: UUID
    company_profile: dict[str, Any] = Field(default_factory=dict)
    target_customer: dict[str, Any] = Field(default_factory=dict)
    business_state: dict[str, Any] = Field(default_factory=dict)
    brand_voice: dict[str, Any] = Field(default_factory=dict)
    competitive_landscape: dict[str, Any] = Field(default_factory=dict)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    version: int = 1
    updated_at: datetime


class GlobalContextPatch(BaseModel):
    """Request body for PATCH /api/context/global."""
    company_profile: dict[str, Any] | None = None
    target_customer: dict[str, Any] | None = None
    business_state: dict[str, Any] | None = None
    brand_voice: dict[str, Any] | None = None
    competitive_landscape: dict[str, Any] | None = None
    recent_events: list[dict[str, Any]] | None = None
