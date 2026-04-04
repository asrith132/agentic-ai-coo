"""
agents/marketing/agent.py — MarketingAgent stub.

Creates and publishes content:
  - Emits: marketing.post_published, marketing.engagement_spike
  - Reacts to: research.trend_found
  - Requests approval before publishing

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class MarketingAgent(BaseAgent):
    name = "marketing"
    description = "Creates and publishes content across social channels"
    subscribed_events = ["research.trend_found"]
    writable_global_fields = []   # brand_voice changes require user approval

    def load_domain_context(self) -> dict[str, Any]:
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        raise NotImplementedError("MarketingAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass
