"""
agents/outreach/agent.py — OutreachAgent stub.

Manages personalized outreach campaigns:
  - Reads ICP from global context (target_customer)
  - Drafts and sends cold emails via Gmail (with approval gate)
  - Tracks reply rates and updates domain context
  - Emits: outreach.email_sent, outreach.reply_received, outreach.meeting_booked
  - Reacts to research.lead_found events to auto-add leads to sequences

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class OutreachAgent(BaseAgent):
    name = "outreach"
    description = "Manages personalized outreach campaigns and tracks replies"
