"""
agents/dev_activity/agent.py — DevActivityAgent stub.

Monitors GitHub activity (PRs, commits, issues, CI status) and:
  - Updates business_state in global context (open_issues, last_deploy)
  - Emits events: dev.pr_merged, dev.build_failed, dev.issue_opened
  - Notifies on critical build failures or deployment events
  - Reacts to pm.sprint_started events to align tracking

Full implementation in Prompt 4.
"""

from app.core.base_agent import BaseAgent


class DevActivityAgent(BaseAgent):
    """Stub — implemented in Prompt 4."""
    name = "dev_activity"
    description = "Monitors GitHub activity and surfaces engineering insights"
