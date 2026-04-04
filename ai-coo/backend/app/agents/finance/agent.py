"""
agents/finance/agent.py — FinanceAgent stub.

Tracks financial health:
  - Emits: finance.mrr_changed, finance.runway_updated, finance.expense_spike
  - Writes: business_state.runway_months, business_state.monthly_burn, business_state.key_metrics

Full implementation in Prompt 4.
"""

from __future__ import annotations
from typing import Any
from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger


class FinanceAgent(BaseAgent):
    name = "finance"
    description = "Tracks MRR, expenses, runway and financial health"
    subscribed_events = []
    writable_global_fields = [
        "business_state.runway_months",
        "business_state.monthly_burn",
        "business_state.key_metrics",
    ]

    def load_domain_context(self) -> dict[str, Any]:
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        raise NotImplementedError("FinanceAgent.execute() — implemented in Prompt 4")

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass
