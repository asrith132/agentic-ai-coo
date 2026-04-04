"""
agents/research/agent.py — ResearchAgent stub.

Competitive and market intelligence:
  - Emits: research.competitor_found, research.trend_found, research.lead_found
  - Writes: competitive_landscape
  - Reacts to: finance.mrr_changed

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Researches competitors, trends, and surfaces leads"
    subscribed_events = ["finance.mrr_changed"]
    writable_global_fields = ["competitive_landscape"]

    def load_domain_context(self) -> dict[str, Any]:
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        raise NotImplementedError("ResearchAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass
