"""
agents/research/agent.py — ResearchAgent stub.

Continuous competitive and market intelligence:
  - Web search for competitors, trends, and industry news
  - Updates competitive_landscape in global context
  - Emits: research.competitor_found, research.trend_found, research.lead_found
  - Reacts to finance.mrr_changed to research pricing benchmarks

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Researches competitors, trends, and surfaces leads"
