"""
agents/outreach/agent.py — OutreachAgent stub.

Manages personalized outreach campaigns:
  - Emits: outreach.email_sent, outreach.reply_received, outreach.meeting_booked
  - Reacts to: research.lead_found
  - Always requests approval before sending emails

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class OutreachAgent(BaseAgent):
    name = "outreach"
    description = "Manages personalized outreach campaigns and tracks replies"
    subscribed_events = ["research.lead_found"]
    writable_global_fields = []

    def load_domain_context(self) -> dict[str, Any]:
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        raise NotImplementedError("OutreachAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass
