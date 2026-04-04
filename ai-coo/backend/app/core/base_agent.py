"""
core/base_agent.py — BaseAgent: the foundation every agent inherits from.

ARCHITECTURE CONTRACT
─────────────────────
Agent builders implement ONLY THREE methods:
  1. load_domain_context()   — read the agent's private DB table(s)
  2. execute(trigger)        — all agent logic lives here; returns a result dict
  3. update_domain_context() — write back to the agent's private DB table(s)

Everything else (context loading, event fetching, LLM context injection,
approvals, notifications, error handling, logging) is handled by BaseAgent.

ENTRY POINT
───────────
API routes and Celery tasks call:
    result = agent.run(trigger)

NEVER call agent.execute() directly from outside the class.

LLM CONTEXT INJECTION
──────────────────────
Every llm_chat() call automatically prepends a business context header to
the system prompt so the model understands who it is working for. Agent
builders should NOT manually inject company info — it is done here.
"""

from __future__ import annotations
import logging
import traceback
from typing import Any, List, Optional

from app.core import context as context_module
from app.core import events as events_module
from app.core import approvals as approvals_module
from app.core import notifications as notifications_module
from app.core.llm import llm
from app.schemas.context import GlobalContext
from app.schemas.events import Event
from app.schemas.approvals import Approval
from app.schemas.notifications import Notification
from app.schemas.triggers import AgentTrigger, TriggerType

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Abstract base class for all AI COO agents.

    Class-level attributes to set on every subclass:
        name               (str)        Unique agent identifier used as source_agent in events
        description        (str)        What this agent does (shown in dashboard)
        subscribed_events  (List[str])  event_type values this agent wants to consume
        writable_global_fields (List[str])  global context fields this agent may write
    """

    name: str = "base"
    description: str = ""
    subscribed_events: List[str] = []
    writable_global_fields: List[str] = []

    def __init__(self) -> None:
        # Each agent instance gets its own logger tagged with the agent name
        self.logger = logging.getLogger(f"agent.{self.name}")

    # ── Context loading ───────────────────────────────────────────────────────

    def load_global_context(self) -> GlobalContext:
        """
        Read the current global context row and return a typed GlobalContext.
        Called automatically at the start of run() — agent builders can also
        call this inside execute() to refresh context mid-run.
        """
        return context_module.get_global_context()

    def load_domain_context(self) -> dict[str, Any]:
        """
        ABSTRACT — each agent overrides this to read its private DB tables.

        Return a dict of any domain-specific data the agent needs during execute().
        This is stored on self._domain_context by run() before calling execute().
        """
        raise NotImplementedError(
            f"Agent '{self.name}' must implement load_domain_context()"
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self, trigger: AgentTrigger) -> dict[str, Any]:
        """
        THE MAIN ENTRY POINT — called by API routes and Celery tasks.

        Orchestration steps:
          1. Load global context → stored on self._global_context
          2. Load domain context → stored on self._domain_context
          3. If trigger type is EVENT, fetch pending unconsumed events
             and attach them to the trigger
          4. Call self.execute(trigger)
          5. Log result and return it

        Never call execute() directly from outside the class.
        All exceptions are caught, logged, and re-raised so Celery can retry.
        """
        self.logger.info("Agent '%s' starting run (trigger=%s)", self.name, trigger.type)

        try:
            # Step 1 — load shared business context
            self._global_context: GlobalContext = self.load_global_context()

            # Step 2 — load agent-specific domain context
            self._domain_context: dict[str, Any] = self.load_domain_context()

            # Step 3 — if event-triggered, hydrate the trigger with pending events
            if trigger.type == TriggerType.EVENT and trigger.events is None and trigger.event is None:
                pending = self.get_pending_events()
                trigger = trigger.model_copy(update={"events": pending})

            # Step 4 — run agent logic
            result = self.execute(trigger)

            self.logger.info(
                "Agent '%s' completed run. Result keys: %s",
                self.name,
                list(result.keys()) if isinstance(result, dict) else type(result),
            )
            return result if isinstance(result, dict) else {"result": result}

        except PermissionError as exc:
            self.logger.error("Agent '%s' permission error: %s", self.name, exc)
            raise
        except Exception as exc:
            self.logger.error(
                "Agent '%s' run failed: %s\n%s",
                self.name,
                exc,
                traceback.format_exc(),
            )
            raise

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        """
        ABSTRACT — agent logic lives here. Override in every subclass.

        Receives the typed AgentTrigger (which may carry pending events).
        Returns a dict result that is logged and returned from run().

        Available on self when execute() is called:
          self._global_context  — GlobalContext (already loaded)
          self._domain_context  — dict (agent-specific, already loaded)
        """
        raise NotImplementedError(
            f"Agent '{self.name}' must implement execute(trigger)"
        )

    # ── Event helpers ─────────────────────────────────────────────────────────

    def get_pending_events(self) -> List[Event]:
        """
        Return unconsumed events that match this agent's subscribed_events list.
        Call this inside execute() when you need to re-fetch mid-run.
        """
        return events_module.get_pending_events(
            agent_name=self.name,
            event_types=self.subscribed_events if self.subscribed_events else None,
        )

    def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        summary: str,
        priority: str = "medium",
    ) -> Event:
        """
        Emit an event to the bus and append its summary to recent_events in
        global context so other agents and the LLM have situational awareness.

        Args:
            event_type: Namespaced string e.g. "dev.pr_merged"
            payload:    Structured data for consuming agents
            summary:    Human-readable one-liner
            priority:   low | medium | high | urgent
        """
        event = events_module.emit_event(
            source_agent=self.name,
            event_type=event_type,
            payload=payload,
            summary=summary,
            priority=priority,
        )

        # Keep global context's recent_events list up to date
        context_module.append_recent_event({
            "event_type": event_type,
            "source_agent": self.name,
            "summary": summary,
            "timestamp": str(event.timestamp),
            "priority": priority,
        })

        return event

    def mark_consumed(self, event_id: str) -> None:
        """
        Mark an event as consumed by this agent.
        Call this after processing each event inside execute().
        """
        events_module.mark_event_consumed(event_id, self.name)

    # ── Global context write ──────────────────────────────────────────────────

    def update_global_context(self, field: str, value: Any) -> None:
        """
        Write a value to a global context field — permission-checked.

        Only fields listed in the WRITE_PERMISSIONS map in core/context.py
        are writable by agents. Raises PermissionError if not allowed.

        Usage:
            self.update_global_context("business_state.runway_months", 14.5)
            self.update_global_context("competitive_landscape", {...})
        """
        context_module.update_global_context(field, value, self.name)

    # ── Domain context write ──────────────────────────────────────────────────

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        """
        ABSTRACT — each agent overrides this to write its private DB tables.

        Called by execute() when the agent wants to persist its own state.
        """
        raise NotImplementedError(
            f"Agent '{self.name}' must implement update_domain_context(updates)"
        )

    # ── Approval helpers ──────────────────────────────────────────────────────

    def request_approval(
        self,
        action_type: str,
        content: dict[str, Any],
    ) -> Approval:
        """
        Create a pending approval request and return it immediately.
        The agent should then poll get_approval_status() or use a Celery chord.

        Args:
            action_type: Short label e.g. "send_email", "publish_post"
            content:     The exact payload the agent will act on (shown to user)
        """
        return approvals_module.create_approval(
            agent=self.name,
            action_type=action_type,
            content=content,
        )

    def get_approval_status(self, approval_id: str) -> Optional[Approval]:
        """Poll the status of an approval request. Returns None if not found."""
        return approvals_module.get_approval(approval_id)

    # ── Notification helpers ──────────────────────────────────────────────────

    def send_notification(
        self,
        title: str,
        body: str,
        priority: str = "medium",
    ) -> Notification:
        """
        Push a notification to the user.
        "high" and "urgent" also trigger an SMS via Twilio if configured.
        """
        return notifications_module.send_notification(
            agent=self.name,
            title=title,
            body=body,
            priority=priority,
        )

    # ── LLM helpers ──────────────────────────────────────────────────────────

    def _build_context_header(self) -> str:
        """
        Build the business context block automatically prepended to every
        llm_chat() system prompt.

        Includes: company name, product, current phase, brand voice tone,
        and active priorities — the minimum an LLM needs to produce contextually
        grounded outputs without further agent-level prompting.
        """
        ctx = self._global_context
        cp = ctx.company_profile
        bs = ctx.business_state
        bv = ctx.brand_voice

        priorities_str = (
            "\n".join(f"  - {p}" for p in bs.active_priorities)
            if bs.active_priorities else "  (none set)"
        )

        recent_str = ""
        if ctx.recent_events:
            last5 = ctx.recent_events[-5:]
            recent_str = "\n\nRECENT SYSTEM EVENTS (last 5):\n" + "\n".join(
                f"  [{e.get('source_agent','?')}] {e.get('summary','')}"
                for e in last5
            )

        return f"""=== BUSINESS CONTEXT ===
Company:     {cp.name}
Product:     {cp.product_name} — {cp.product_description}
Phase:       {bs.phase}
Team size:   {bs.team_size}
Brand voice: {bv.tone or '(not set)'}
Formality:   {bv.formality}

Active priorities:
{priorities_str}{recent_str}
========================

You are operating as the {self.name.replace('_', ' ').title()} agent for {cp.name or 'this company'}.
{self.description}

"""

    def llm_chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        inject_context: bool = True,
    ) -> str:
        """
        Convenience wrapper around llm.chat() that automatically injects
        the business context header into the system prompt.

        Args:
            system_prompt:   Agent-specific instructions (appended after context header)
            user_message:    The task or question for the model
            temperature:     Sampling temperature (default 0.7)
            inject_context:  Set False to skip context header (e.g. for pure summarization)

        Returns:
            Plain text response string.
        """
        if inject_context and hasattr(self, "_global_context"):
            full_system = self._build_context_header() + system_prompt
        else:
            full_system = system_prompt

        return llm.chat(
            system_prompt=full_system,
            user_message=user_message,
            temperature=temperature,
        )

    def llm_chat_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: List[dict[str, Any]],
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Tool-use variant of llm_chat(). Injects the same context header.
        Returns {"text": str|None, "tool_calls": list[dict], "stop_reason": str}.
        """
        if hasattr(self, "_global_context"):
            full_system = self._build_context_header() + system_prompt
        else:
            full_system = system_prompt

        return llm.chat_with_tools(
            system_prompt=full_system,
            user_message=user_message,
            tools=tools,
            temperature=temperature,
        )


# ── Example agent ─────────────────────────────────────────────────────────────
# Copy this pattern to build a new agent. Only implement the three abstract methods.

class ExampleAgent(BaseAgent):
    """
    Minimal example showing the exact pattern agent builders follow.
    Delete or move to a separate file when building a real agent.
    """

    name = "example"
    description = "Example agent for testing the BaseAgent framework"
    subscribed_events = ["dev.pr_merged"]           # listen for PR merge events

    def load_domain_context(self) -> dict[str, Any]:
        """
        Read from the agent's private DB table.
        Return whatever structured data execute() needs.
        """
        # In a real agent:
        # client = get_client()
        # row = client.table("example_state").select("*").limit(1).execute()
        # return row.data[0] if row.data else {}
        return {"last_run": None, "items_processed": 0}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        """
        All agent logic lives here. This is the ONLY method that varies per agent.
        """
        # Access pre-loaded context (no extra DB call needed)
        ctx = self._global_context
        domain = self._domain_context

        self.logger.info("ExampleAgent running for company: %s", ctx.company_profile.name)

        # React to events if event-triggered
        if trigger.type == TriggerType.EVENT and trigger.events:
            for event in trigger.events:
                self.logger.info("Processing event: %s — %s", event.event_type, event.summary)
                self.mark_consumed(event.id)

        # Call the LLM (context header is injected automatically)
        response = self.llm_chat(
            system_prompt="You are a helpful assistant. Be brief.",
            user_message="Summarize what an example agent does in one sentence.",
        )

        # Emit an event for other agents
        self.emit_event(
            event_type="example.run_completed",
            payload={"response_length": len(response)},
            summary="ExampleAgent completed a test run",
            priority="low",
        )

        # Notify the user
        self.send_notification(
            title="Example agent ran",
            body=f"Test response: {response[:100]}",
            priority="low",
        )

        return {"status": "done", "response_preview": response[:200]}

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        """Write back to the agent's private table."""
        # In a real agent:
        # client = get_client()
        # client.table("example_state").upsert(updates).execute()
        pass
