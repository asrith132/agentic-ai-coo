"""
agents/pm/agent.py — PMAgent stub.

Manages sprint health and velocity:
  - Emits: pm.sprint_started, pm.blocker_detected, pm.sprint_completed
  - Writes: business_state.active_priorities, business_state.key_metrics
  - Reacts to: dev.build_failed

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class PMAgent(BaseAgent):
    name = "pm"
    description = "Tracks sprint health, velocity, and surfaces blockers"
    subscribed_events = ["dev.build_failed", "dev.pr_merged"]
    writable_global_fields = [
        "business_state.active_priorities",
        "business_state.key_metrics",
        "business_state.phase",
    ]

    def load_domain_context(self) -> dict[str, Any]:
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        raise NotImplementedError("PMAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass
