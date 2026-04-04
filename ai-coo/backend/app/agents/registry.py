"""
agents/registry.py — Central agent registry.

Maps agent name strings to their agent classes. Used by the approval callback
in approval_routes.py to instantiate the correct agent after a user approves
an action, so the agent can immediately execute it.

To register a new agent: add its class to AGENT_REGISTRY below.
Agents are imported lazily here to avoid circular imports at startup.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.base_agent import BaseAgent


def get_agent(name: str) -> "BaseAgent":
    """
    Instantiate and return the agent with the given name.

    Raises KeyError if the name is not registered.
    Raises NotImplementedError if the agent's __init__ is not yet implemented
    (stubs from Prompt 1 — will be resolved in Prompt 4).
    """
    # Import lazily to avoid circular module loading
    from app.agents.dev_activity.agent import DevActivityAgent
    from app.agents.outreach.agent import OutreachAgent
    from app.agents.marketing.agent import MarketingAgent
    from app.agents.finance.agent import FinanceAgent
    from app.agents.pm.agent import PMAgent
    from app.agents.research.agent import ResearchAgent
    from app.agents.legal.agent import LegalAgent

    registry: dict[str, type] = {
        "dev_activity": DevActivityAgent,
        "outreach":     OutreachAgent,
        "marketing":    MarketingAgent,
        "finance":      FinanceAgent,
        "pm":           PMAgent,
        "research":     ResearchAgent,
        "legal":        LegalAgent,
    }

    if name not in registry:
        raise KeyError(f"No agent registered with name '{name}'. Known agents: {list(registry)}")

    return registry[name]()


def list_agents() -> list[str]:
    """Return all registered agent names."""
    return [
        "dev_activity", "outreach", "marketing",
        "finance", "pm", "research", "legal",
    ]
