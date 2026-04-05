"""
agents/pm/agent.py — PMAgent

The central nervous system of the task layer. Subscribes to more events
than any other agent, maintaining a living task backlog that reprioritizes
itself as the business evolves.

FLAGSHIP FEATURE: Smart To-Do List That Reprioritizes Itself

Subscribed events:
    feature_shipped, bug_fixed, runway_warning, spending_anomaly,
    objection_heard, deadline_approaching, research_completed,
    trend_found, milestone_completed

Emitted events:
    priority_reshuffled, task_created

Writes to global context:
    business_state.active_priorities
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger, TriggerType
from app.agents.pm import tools

logger = logging.getLogger(__name__)


class PMAgent(BaseAgent):
    name = "pm"
    description = (
        "Maintains task backlog, tracks milestones, dynamically reprioritizes "
        "based on cross-agent signals"
    )
    subscribed_events = [
        "feature_shipped",
        "bug_fixed",
        "runway_warning",
        "spending_anomaly",
        "objection_heard",
        "deadline_approaching",
        "research_completed",
        "trend_found",
        "milestone_completed",
    ]
    writable_global_fields = [
        "business_state.active_priorities",
        "business_state.key_metrics",
        "business_state.phase",
    ]

    # ── BaseAgent contract ────────────────────────────────────────────────────

    def load_domain_context(self) -> dict[str, Any]:
        """Load active tasks and milestones once per run."""
        try:
            return {
                "active_tasks": tools.get_active_tasks(),
                "milestones": tools.get_milestones(),
            }
        except Exception:
            logger.exception("PMAgent failed to load domain context")
            return {"active_tasks": [], "milestones": []}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        results: dict[str, Any] = {"agent": self.name, "trigger": trigger.type}

        if trigger.type == TriggerType.EVENT:
            tasks_created: list[dict] = []
            event_types: list[str] = []

            for event in (trigger.events or []):
                event_types.append(event.event_type)
                try:
                    task = self._handle_event(event)
                    if task:
                        tasks_created.append(task)
                except Exception:
                    logger.exception("PMAgent error handling event %s", event.event_type)
                finally:
                    self.mark_consumed(str(event.id))

            results["tasks_created"] = tasks_created
            results["reprioritize"] = self._reprioritize(
                f"events: {event_types}" if event_types else "events"
            )
        else:
            # USER_REQUEST or SCHEDULED — just reprioritize
            results["reprioritize"] = self._reprioritize("manual")

        return results

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        # Tools write directly to DB per operation; no separate flush needed
        pass

    # ── Reprioritization Engine ───────────────────────────────────────────────

    def _reprioritize(self, trigger_event: str) -> dict[str, Any]:
        """
        Core reprioritization loop:
          1. Build task list from domain context (already loaded)
          2. Call LLM — business context is auto-injected by BaseAgent
          3. Update all task scores in DB
          4. Emit priority_reshuffled if top 3 changed
          5. Update global context active_priorities
          6. Save to pm_priority_history
        """
        active_tasks = self._domain_context.get("active_tasks") or []
        if not active_tasks:
            return {"status": "no_tasks"}

        task_lines = "\n".join(
            f'- id:{t["id"]} | "{t["title"]}" | current_score:{t.get("priority_score", 50)}'
            for t in active_tasks
        )

        prompt = (
            f"Here are the current open tasks:\n\n{task_lines}\n\n"
            "Rescore each task 0–100 based on:\n"
            "- Alignment with the current business phase and active priorities\n"
            "- Urgency (financial pressure, customer demand, deadlines)\n"
            "- Revenue and retention impact\n"
            "- Risk reduction value\n\n"
            "Return ONLY valid JSON — no markdown, no explanation outside the JSON:\n"
            "{\n"
            '  "scores": [{"id": "<uuid>", "score": <int>, "reason": "<one sentence>"}],\n'
            '  "top_3": [{"id": "<uuid>", "title": "<title>", "score": <int>, "reason": "<why top>"}],\n'
            '  "summary": "<2-3 sentence summary of current priorities and why>"\n'
            "}"
        )

        try:
            raw = self.llm_chat(
                system_prompt=(
                    "You are a senior project manager. Prioritize tasks based on "
                    "the business context provided. Respond with valid JSON only."
                ),
                user_message=prompt,
                temperature=0.2,
            )
            data = json.loads(_extract_json(raw))
        except Exception:
            logger.exception("PMAgent reprioritization LLM call failed")
            return {"status": "llm_error"}

        # Snapshot previous top 3 before updating scores
        prev_top_3 = [
            {"id": str(t["id"]), "title": t["title"], "score": t.get("priority_score", 50)}
            for t in sorted(active_tasks, key=lambda x: x.get("priority_score", 0), reverse=True)[:3]
        ]

        # Update scores in DB
        updated = 0
        for item in data.get("scores", []):
            try:
                tools.update_task(item["id"], priority_score=float(item["score"]))
                updated += 1
            except Exception:
                logger.warning("PMAgent failed to update score for task %s", item["id"])

        new_top_3 = data.get("top_3", [])
        prev_ids = [t["id"] for t in prev_top_3]
        new_ids = [t.get("id") for t in new_top_3]
        top_3_changed = prev_ids != new_ids and bool(new_top_3)

        if top_3_changed:
            titles = [t.get("title", "?") for t in new_top_3]
            self.emit_event(
                event_type="priority_reshuffled",
                payload={
                    "new_top_3": new_top_3,
                    "trigger_event": trigger_event,
                    "changes_summary": data.get("summary", ""),
                },
                summary=(
                    "Priorities reshuffled. New top 3: "
                    f"1. {titles[0] if len(titles) > 0 else '?'} "
                    f"2. {titles[1] if len(titles) > 1 else '?'} "
                    f"3. {titles[2] if len(titles) > 2 else '?'}. "
                    f"Triggered by: {trigger_event}"
                ),
                priority="medium",
            )
            try:
                self.update_global_context(
                    "business_state.active_priorities",
                    [t.get("title", "") for t in new_top_3],
                )
            except Exception:
                logger.warning("PMAgent failed to update active_priorities in global context")

        try:
            tools.save_priority_history(
                previous_top_3=prev_top_3,
                new_top_3=new_top_3,
                reasoning=data.get("summary", ""),
                trigger_event=trigger_event,
            )
        except Exception:
            logger.warning("PMAgent failed to save priority history")

        return {
            "status": "ok",
            "tasks_rescored": updated,
            "new_top_3": new_top_3,
            "summary": data.get("summary", ""),
            "top_3_changed": top_3_changed,
        }

    # ── Event Handlers ────────────────────────────────────────────────────────

    def _handle_event(self, event: Any) -> dict[str, Any] | None:
        """Route a single event to its handler. Returns a new task dict or None."""
        handlers = {
            "feature_shipped":     self._on_feature_shipped,
            "bug_fixed":           self._on_bug_fixed,
            "runway_warning":      self._on_runway_warning,
            "spending_anomaly":    self._on_spending_anomaly,
            "objection_heard":     self._on_objection_heard,
            "deadline_approaching": self._on_deadline_approaching,
            "research_completed":  self._on_research_completed,
            "trend_found":         self._on_trend_found,
        }
        handler = handlers.get(event.event_type)
        return handler(event, event.payload or {}) if handler else None

    def _on_feature_shipped(self, event: Any, p: dict) -> None:
        feature = p.get("feature") or p.get("name", "")
        if not feature:
            return None
        for task in self._domain_context.get("active_tasks", []):
            if feature.lower() in task["title"].lower():
                tools.update_task(str(task["id"]), status="done")
                logger.info("Marked task done via feature_shipped: %s", task["title"])
                return None
        return None

    def _on_bug_fixed(self, event: Any, p: dict) -> None:
        bug = p.get("bug") or p.get("title", "")
        if not bug:
            return None
        for task in self._domain_context.get("active_tasks", []):
            title_lower = task["title"].lower()
            if bug.lower() in title_lower or ("bug" in title_lower and "fix" in title_lower):
                tools.update_task(str(task["id"]), status="done")
                return None
        return None

    def _on_runway_warning(self, event: Any, p: dict) -> None:
        months = p.get("months_remaining", "?")
        self.send_notification(
            title="Runway Warning — Tasks Reprioritized",
            body=(
                f"Runway is {months} months. PM agent is reprioritizing to "
                "surface revenue-generating work."
            ),
            priority="high",
        )
        return None

    def _on_spending_anomaly(self, event: Any, p: dict) -> dict:
        category = p.get("category", "unknown category")
        task = tools.create_task(
            title=f"Investigate {category} spending spike",
            description=p.get("description", ""),
            priority_score=75.0,
            source_agent=event.source_agent,
            source_event_id=str(event.id),
        )
        self._emit_task_created(task, event.source_agent)
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    def _on_objection_heard(self, event: Any, p: dict) -> dict:
        objection = p.get("objection_text") or p.get("summary", "customer objection")
        freq = int(p.get("frequency_count", 1))
        score = min(50.0 + freq * 10, 90.0)
        task = tools.create_task(
            title=f"Address customer objection: {str(objection)[:80]}",
            description=str(objection),
            priority_score=score,
            source_agent=event.source_agent,
            source_event_id=str(event.id),
        )
        self._emit_task_created(task, event.source_agent)
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    def _on_deadline_approaching(self, event: Any, p: dict) -> dict | None:
        name = p.get("deadline_name") or p.get("title", "Compliance deadline")
        days = int(p.get("days_remaining", 0))
        score = 95.0 if days <= 7 else 80.0
        # Boost existing task if found
        for task in self._domain_context.get("active_tasks", []):
            if name.lower() in task["title"].lower():
                tools.update_task(str(task["id"]), priority_score=score)
                return None
        # Otherwise create it
        task = tools.create_task(
            title=f"Complete: {name}",
            description=f"{days} days remaining.",
            priority_score=score,
            source_agent=event.source_agent,
            source_event_id=str(event.id),
        )
        self._emit_task_created(task, event.source_agent)
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    def _on_research_completed(self, event: Any, p: dict) -> dict | None:
        findings = p.get("insights") or p.get("summary", "")
        finding_type = p.get("finding_type", "")
        if not findings or finding_type not in ("competitor", "market", "opportunity"):
            return None
        task = tools.create_task(
            title=f"Act on {finding_type} finding: {str(findings)[:80]}",
            description=str(findings),
            priority_score=55.0,
            source_agent=event.source_agent,
            source_event_id=str(event.id),
        )
        self._emit_task_created(task, event.source_agent)
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    def _on_trend_found(self, event: Any, p: dict) -> dict | None:
        topic = p.get("topic", "market trend")
        platform = p.get("platform", "")
        score = int(p.get("relevance_score", 60))
        if score < 70:
            return None
        task = tools.create_task(
            title=f"Evaluate opportunity: {topic}",
            description=f"Trend found on {platform}. Relevance: {score}/100.",
            priority_score=float(score) * 0.6,  # dampen — not every trend needs action
            source_agent=event.source_agent,
            source_event_id=str(event.id),
        )
        self.send_notification(
            title=f"Trending opportunity: {topic}",
            body=(
                f"Marketing spotted a trend on {platform} (relevance {score}/100). "
                "A task has been added to the backlog."
            ),
            priority="low",
        )
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _emit_task_created(self, task: dict[str, Any], source_agent: str) -> None:
        self.emit_event(
            event_type="task_created",
            payload={
                "task_title": task["title"],
                "source_agent": source_agent,
                "priority_score": task.get("priority_score", 50),
            },
            summary=(
                f"New task created: {task['title']} "
                f"(from {source_agent}, priority: {task.get('priority_score', 50):.0f}/100)"
            ),
            priority="low",
        )
        self.send_notification(
            title="New task created",
            body=f"{task['title']}  —  priority {task.get('priority_score', 50):.0f}/100",
            priority="low",
        )


# ── Module-level JSON helper ──────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Strip markdown fences if present and return the raw JSON string."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text
