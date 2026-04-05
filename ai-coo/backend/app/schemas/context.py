"""
schemas/context.py — Typed Pydantic models for Global Context.

GlobalContext mirrors the `global_context` Supabase table. Each top-level
field maps to a JSONB column. Agents read this at the start of every run to
understand the business they are operating for.

Write access is controlled in core/context.py — not every agent can write
every field. See the WRITE_PERMISSIONS map there.
"""

from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """Static company identity. Updated by user only — no agent can write this."""
    name: str = ""
    description: str = ""
    product_name: str = ""
    product_description: str = ""
    key_features: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    founded_date: Optional[str] = None
    entity_type: str = ""               # e.g. "LLC", "C-Corp", "Ltd"
    jurisdiction: str = ""              # e.g. "Delaware, USA"


class TargetCustomer(BaseModel):
    """
    Ideal Customer Profile (ICP). Research agent can propose updates;
    user approves. Outreach and marketing agents read this for every campaign.
    """
    persona: str = ""
    industry: str = ""
    company_size: str = ""              # e.g. "1-10 employees", "Series A startup"
    pain_points: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)
    language_patterns: List[str] = Field(default_factory=list)  # phrases the ICP uses


class BusinessState(BaseModel):
    """
    Live operational state. Updated by finance and pm agents.
    Agents read this to calibrate urgency (e.g. if runway is low, act faster).
    """
    phase: str = "pre_launch"           # pre_launch | launched | growing | fundraising | pivoting
    active_priorities: List[str] = Field(default_factory=list)  # pm agent writes this
    runway_months: Optional[float] = None   # finance agent writes
    monthly_burn: Optional[float] = None    # finance agent writes
    team_size: int = 1
    key_metrics: dict[str, Any] = Field(default_factory=dict)  # pm + finance write
    last_updated: Optional[str] = None  # ISO timestamp of last write


class BrandVoice(BaseModel):
    """
    Tone and style guide. Marketing agent can propose; user approves.
    Every agent that produces user-facing text reads this.
    """
    tone: str = ""                      # e.g. "Direct, witty, no fluff"
    formality: str = "balanced"         # casual | balanced | formal
    personality_traits: List[str] = Field(default_factory=list)
    words_to_use: List[str] = Field(default_factory=list)
    words_to_avoid: List[str] = Field(default_factory=list)
    example_good_copy: str = ""


class CompetitiveLandscape(BaseModel):
    """Research agent writes this. All agents read for positioning context."""
    competitors: List[dict[str, Any]] = Field(default_factory=list)
    market_position: str = ""


class GlobalContext(BaseModel):
    """
    The full global context object returned from the DB and injected into agents.

    `recent_events` is a rolling list (max 50) of event summaries automatically
    prepended to agent LLM prompts for situational awareness.
    """
    company_profile: CompanyProfile = Field(default_factory=CompanyProfile)
    target_customer: TargetCustomer = Field(default_factory=TargetCustomer)
    business_state: BusinessState = Field(default_factory=BusinessState)
    brand_voice: BrandVoice = Field(default_factory=BrandVoice)
    competitive_landscape: CompetitiveLandscape = Field(default_factory=CompetitiveLandscape)
    recent_events: List[dict[str, Any]] = Field(default_factory=list)
    # PM voice structured intake (brief, state, generated tasks); pm agent writes via update_global_context.
    pm_voice_intake: dict[str, Any] = Field(default_factory=dict)
    version: int = 1


class GlobalContextPatch(BaseModel):
    """Request body for PATCH /api/context/global (user-facing API)."""
    company_profile: Optional[dict[str, Any]] = None
    target_customer: Optional[dict[str, Any]] = None
    business_state: Optional[dict[str, Any]] = None
    brand_voice: Optional[dict[str, Any]] = None
    competitive_landscape: Optional[dict[str, Any]] = None
    recent_events: Optional[List[dict[str, Any]]] = None
