"""
agents/pm/agent.py — PMAgent stub.

Manages project velocity and sprint health:
  - Synthesizes GitHub issues + PRs into sprint status
  - Detects blockers and surface them to the user
  - Emits: pm.sprint_started, pm.blocker_detected, pm.sprint_completed
  - Reacts to dev.build_failed to flag as potential blocker

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class PMAgent(BaseAgent):
    name = "pm"
    description = "Tracks sprint health, velocity, and surfaces blockers"
