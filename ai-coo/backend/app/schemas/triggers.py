"""
schemas/triggers.py — Agent trigger type definitions.

Agents can be activated by three trigger types:
  USER_REQUEST — user explicitly asked an agent to run (via API/frontend)
  SCHEDULED    — Celery Beat cron timer fired
  EVENT        — another agent emitted an event this agent subscribes to

The trigger is passed to BaseAgent.execute() so agents can tailor their
behavior based on WHY they were activated.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Optional, List
from pydantic import BaseModel

# Import here to avoid circular — Event is defined in events.py
# We use TYPE_CHECKING to allow forward reference in the type hint
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.schemas.events import Event


class TriggerType(str, Enum):
    USER_REQUEST = "user_request"   # user explicitly asked agent to do something
    SCHEDULED    = "scheduled"      # Celery Beat timer fired
    EVENT        = "event"          # another agent emitted an event we care about


class AgentTrigger(BaseModel):
    """
    Unified trigger envelope passed to every agent's execute() method.

    Only the fields relevant to the trigger type will be populated:
      USER_REQUEST  → user_input, parameters
      SCHEDULED     → task_name
      EVENT         → event (single) or events (batch of pending events)
    """
    type: TriggerType

    # ── USER_REQUEST fields ───────────────────────────────────────────────────
    user_input: Optional[str] = None        # free-text instruction from the user
    parameters: Optional[dict[str, Any]] = None  # structured params from frontend

    # ── SCHEDULED fields ──────────────────────────────────────────────────────
    task_name: Optional[str] = None         # human label e.g. "every_30m"

    # ── EVENT fields ──────────────────────────────────────────────────────────
    # Use event for a single trigger event; events for a batch poll
    event: Optional[Any] = None             # Event (typed as Any to avoid circular import)
    events: Optional[List[Any]] = None      # List[Event] batch

    class Config:
        # Allow Event objects (not just dicts) in event/events fields
        arbitrary_types_allowed = True


# ── Convenience constructors ─────────────────────────────────────────────────

def user_trigger(user_input: str = "", parameters: dict | None = None) -> AgentTrigger:
    return AgentTrigger(
        type=TriggerType.USER_REQUEST,
        user_input=user_input,
        parameters=parameters or {},
    )


def scheduled_trigger(task_name: str) -> AgentTrigger:
    return AgentTrigger(type=TriggerType.SCHEDULED, task_name=task_name)


def event_trigger(event: Any = None, events: list | None = None) -> AgentTrigger:
    return AgentTrigger(type=TriggerType.EVENT, event=event, events=events)
