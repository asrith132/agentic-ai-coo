"""
agents/legal/agent.py — LegalAgent stub.

Monitors legal and compliance signals:
  - Emits: legal.contract_flagged, legal.compliance_alert
  - Always requires approval before any outward communication

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class LegalAgent(BaseAgent):
    name = "legal"
    description = "Monitors contracts, compliance, and legal risk signals"
    subscribed_events = []
    writable_global_fields = []

    def load_domain_context(self) -> dict[str, Any]:
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        raise NotImplementedError("LegalAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass
