"""
agents/finance/agent.py — FinanceAgent stub.

Tracks financial health:
  - Parses uploaded CSV/statements to extract MRR, expenses, runway
  - Updates business_state in global context (mrr, runway_months)
  - Emits: finance.runway_updated, finance.mrr_changed, finance.expense_spike
  - Notifies urgently if runway drops below 3 months

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class FinanceAgent(BaseAgent):
    name = "finance"
    description = "Tracks MRR, expenses, runway and financial health"
