"""
agents/legal/agent.py — LegalAgent stub.

Monitors legal and compliance signals:
  - Scans uploaded contracts/docs for risk clauses
  - Tracks regulatory changes relevant to the company's industry
  - Emits: legal.contract_flagged, legal.compliance_alert
  - Always requires approval before any outward communication

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class LegalAgent(BaseAgent):
    name = "legal"
    description = "Monitors contracts, compliance, and legal risk signals"
