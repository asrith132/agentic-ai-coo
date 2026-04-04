"""
agents/dev_activity/agent.py — DevActivityAgent stub.

Monitors GitHub activity (PRs, commits, issues, CI status):
  - Emits: dev.pr_merged, dev.build_failed, dev.issue_opened
  - Writes: business_state.key_metrics (open issues, last deploy)
  - Reacts to: pm.sprint_started

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class DevActivityAgent(BaseAgent):
    name = "dev_activity"
    description = "Monitors GitHub activity and surfaces engineering insights"
    subscribed_events = ["pm.sprint_started"]
    writable_global_fields = ["business_state.key_metrics", "business_state.last_updated"]

    def load_domain_context(self) -> dict[str, Any]:
        # TODO (Prompt 4): query dev_agent_state table
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        # TODO (Prompt 4): implement GitHub polling and event emission
        raise NotImplementedError("DevActivityAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        # TODO (Prompt 4): upsert dev_agent_state table
        pass
