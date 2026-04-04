"""
agents/marketing/agent.py — MarketingAgent stub.

Creates and schedules content across channels:
  - Drafts posts using brand_voice from global context
  - Posts to Reddit, X (Twitter), LinkedIn (with approval gate)
  - Tracks engagement metrics
  - Emits: marketing.post_published, marketing.engagement_spike
  - Reacts to research.trend_found to capitalize on timely content opportunities

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class MarketingAgent(BaseAgent):
    name = "marketing"
    description = "Creates and publishes content across social channels"
