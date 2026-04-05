"""
core/base_agent.py — BaseAgent class.

⚠️  NOT IMPLEMENTED YET — this is a placeholder stub.
    Full implementation comes in Prompt 2.

Every domain agent (DevActivityAgent, OutreachAgent, etc.) will inherit from
BaseAgent. The base class will provide:
  - run() lifecycle: plan → execute → emit_events → notify
  - Access to global context (read/write)
  - Event emission helpers
  - Approval request + wait pattern
  - Notification shortcuts
  - LLM call wrapper with automatic system prompt injection
  - Agent-specific domain context (private Supabase table per agent)
  - Error handling and structured logging
"""

from __future__ import annotations


class BaseAgent:
    """
    Placeholder stub — implemented in Prompt 2.

    Subclass pattern (to be filled in):

        class DevActivityAgent(BaseAgent):
            name = "dev_activity"
            description = "Monitors GitHub activity and surfaces engineering insights"

            async def run(self, trigger: dict) -> None:
                ctx = await self.get_context()
                # ... agent logic ...
                await self.emit("dev.pr_merged", payload={...}, summary="PR #42 merged")
                await self.notify("New PR merged", body="...")
    """

    name: str = "base"
    description: str = ""

    def __init__(self) -> None:
        raise NotImplementedError("BaseAgent will be implemented in Prompt 2")
