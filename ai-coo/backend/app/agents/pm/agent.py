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
from app.core.approvals import create_approval
from app.schemas.triggers import AgentTrigger, TriggerType
from app.agents.pm import tools
from app.agents.pm.registry import AGENT_REGISTRY, registry_summary_for_llm

logger = logging.getLogger(__name__)


class PMAgent(BaseAgent):
    name = "pm"
    description = (
        "Maintains task backlog, tracks milestones, dynamically reprioritizes "
        "based on cross-agent signals"
    )
    subscribed_events = [
        "commit_pushed",
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

        # ── Approval callback: user accepted a task ───────────────────────────
        if (
            trigger.type == TriggerType.USER_REQUEST
            and trigger.parameters
            and trigger.parameters.get("action_type") == "start_task"
        ):
            content = trigger.parameters.get("content", {})
            task_id = content.get("task_id")
            if task_id:
                results["task_execution"] = self._execute_approved_task(task_id, content)
            return results

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
            "commit_pushed":       self._on_commit_pushed,
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

    def _on_commit_pushed(self, event: Any, p: dict) -> dict | None:
        """
        PM reviews every new commit and decides if any action is needed.
        Uses LLM to suggest a task (e.g. draft a marketing post, update docs, etc.)
        Only creates a task if the LLM deems action worthwhile.
        """
        commit_type  = p.get("commit_type", "maintenance")
        summary      = p.get("summary", p.get("message", ""))
        author       = p.get("author", "unknown")
        branch       = p.get("branch", "main")
        feature_name = p.get("feature_name") or ""
        notify_teams = p.get("notify_teams", False)

        # Skip pure maintenance / chore commits unless they're flagged
        if commit_type in ("maintenance", "refactor", "chore", "docs") and not notify_teams:
            return None

        # Feature commits are handled by _on_feature_shipped — avoid duplicate tasks
        if p.get("is_new_feature"):
            return None

        registry_text = registry_summary_for_llm()

        try:
            raw = self.llm_chat(
                system_prompt=(
                    "You are a startup project manager reviewing a new code commit. "
                    "Decide if any business action is warranted — marketing post, "
                    "customer outreach, documentation update, etc. "
                    "Available agents:\n" + registry_text + "\n\n"
                    "Respond with valid JSON only — no markdown, no explanation:\n"
                    '{"needs_action": <bool>, '
                    '"task_title": "<short action title>", '
                    '"task_description": "<1-2 sentences of context>", '
                    '"assigned_agent": "<marketing|outreach|legal|finance|dev_activity|pm|null>", '
                    '"priority_score": <int 0-100>, '
                    '"reason": "<one sentence why>"}'
                ),
                user_message=(
                    f"Commit by {author} on branch '{branch}':\n"
                    f"Type: {commit_type}\n"
                    f"Summary: {summary}\n"
                    f"{'Feature: ' + feature_name if feature_name else ''}\n"
                    f"{'Note: ' + p.get('notify_reason', '') if p.get('notify_reason') else ''}"
                ).strip(),
                temperature=0.2,
            )
            data = json.loads(_extract_json(raw))
        except Exception:
            logger.exception("PMAgent: LLM call failed for commit_pushed event")
            return None

        if not data.get("needs_action"):
            return None

        assigned = data.get("assigned_agent") or "pm"
        if assigned == "null":
            assigned = "pm"

        task = tools.create_task(
            title=data.get("task_title", f"Review commit: {summary[:60]}"),
            description=data.get("task_description", summary),
            priority_score=float(data.get("priority_score", 60)),
            status="pending_approval",
            source_agent=event.source_agent or "dev_activity",
            source_event_id=str(event.id),
            assigned_agent=assigned,
        )
        self._emit_task_created(task, event.source_agent or "dev_activity")
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    def _on_feature_shipped(self, event: Any, p: dict) -> dict | None:
        feature_name = p.get("feature_name") or p.get("feature") or p.get("name", "")
        summary      = p.get("description") or p.get("summary", "")
        author       = p.get("author", "")
        branch       = p.get("branch", "main")

        # Mark any existing task for this feature as done
        for task in self._domain_context.get("active_tasks", []):
            if feature_name and feature_name.lower() in task["title"].lower():
                tools.update_task(str(task["id"]), status="done")
                logger.info("Marked task done via feature_shipped: %s", task["title"])

        if not feature_name:
            return None

        # Ask PM if they want to post about this feature on LinkedIn
        task = tools.create_task(
            title=f"Post about new feature on LinkedIn: {feature_name}",
            description=(
                f"New feature shipped by {author} on {branch}.\n\n"
                f"{summary}\n\n"
                "Approve to have the Marketing agent draft a LinkedIn post about this."
            ),
            priority_score=72.0,
            status="pending_approval",
            source_agent=event.source_agent or "dev_activity",
            source_event_id=str(event.id),
            assigned_agent="marketing",
        )
        self._emit_task_created(task, event.source_agent or "dev_activity")
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

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
            status="pending_approval",
            source_agent=event.source_agent,
            source_event_id=str(event.id),
            assigned_agent="finance",
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
            status="pending_approval",
            source_agent=event.source_agent,
            source_event_id=str(event.id),
            assigned_agent="outreach",
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
            status="pending_approval",
            source_agent=event.source_agent,
            source_event_id=str(event.id),
            assigned_agent="legal",
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
            status="pending_approval",
            source_agent=event.source_agent,
            source_event_id=str(event.id),
            assigned_agent="marketing",
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
            status="pending_approval",
            source_agent=event.source_agent,
            source_event_id=str(event.id),
            assigned_agent="marketing",
        )
        self._emit_task_created(task, event.source_agent)
        self._domain_context.setdefault("active_tasks", []).append(task)
        return task

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _execute_approved_task(self, task_id: str, content: dict[str, Any]) -> dict[str, Any]:
        """
        Run after the user approves a task.
          1. Mark task in_progress
          2. Route to the assigned_agent (or fall back to a PM-level LLM summary)
          3. Mark task done
          4. Send completion notification
        """
        title = content.get("title", "task")
        tools.update_task(task_id, status="in_progress")

        # Fetch the full task row to get assigned_agent
        task_row = tools.get_task(task_id) or {}
        assigned_agent = task_row.get("assigned_agent") or content.get("assigned_agent")

        try:
            outcome = self._dispatch_to_agent(assigned_agent, task_id, task_row, content)
        except Exception:
            logger.exception(
                "PMAgent task execution failed for task %s (agent=%s)", task_id, assigned_agent
            )
            tools.update_task(task_id, status="blocked")
            self.send_notification(
                title=f"Task failed: {title}",
                body="The agent encountered an error. Check logs for details.",
                priority="high",
            )
            return {"task_id": task_id, "status": "blocked", "assigned_agent": assigned_agent}

        tools.update_task(task_id, status="done")

        agent_label = AGENT_REGISTRY.get(assigned_agent or "", {}).get("display_name", "PM") if assigned_agent else "PM"

        # For marketing drafts, the real work happens after a second approval —
        # use a more accurate notification so user knows to check approvals panel
        if assigned_agent == "marketing":
            self.send_notification(
                title=f"LinkedIn post drafted: {title}",
                body="Check the Approvals panel to review and publish the post.",
                priority="medium",
            )
        else:
            self.send_notification(
                title=f"Task complete: {title}",
                body=f"[{agent_label}] {outcome}",
                priority="high",
            )

        return {
            "task_id": task_id,
            "status": "done",
            "assigned_agent": assigned_agent,
            "outcome": outcome,
        }

    def _dispatch_to_agent(
        self,
        assigned_agent: str | None,
        task_id: str,
        task_row: dict[str, Any],
        content: dict[str, Any],
    ) -> str:
        """
        Route to the right specialist agent and return an outcome string.
        Falls back to an LLM summary if no routing is possible.
        """
        title = content.get("title") or task_row.get("title", "task")
        description = content.get("description") or task_row.get("description") or ""

        if assigned_agent == "finance":
            from app.agents.finance.agent import FinanceAgent
            agent = FinanceAgent()
            result = agent.run(AgentTrigger(
                type=TriggerType.USER_REQUEST,
                user_input="summarize",
                parameters={"task_id": task_id, "task_title": title},
            ))
            return str(result.get("summary") or f"Finance analysis complete for: {title}")

        if assigned_agent == "outreach":
            from app.agents.outreach.agent import OutreachAgent
            agent = OutreachAgent()

            # Detect contact_type and email_type from task wording
            combined = f"{title} {description or ''}".lower()
            if any(k in combined for k in ("investor", "funding", "raise", "vc", "angel", "seed")):
                contact_type = "investor"
                email_type   = "investor"
            elif any(k in combined for k in ("partner", "founder", "collaborate", "partnership", "integrate")):
                contact_type = "partner"
                email_type   = "partnership"
            else:
                contact_type = "customer"
                email_type   = "cold"

            # First: check if there are already pre-seeded contacts of this type in the DB
            from app.agents.outreach import tools as outreach_tools
            existing = [
                c for c in outreach_tools.list_contacts(limit=50)
                if c.get("contact_type") == contact_type and c.get("status") in ("cold", "warm")
            ]
            if existing:
                drafted = 0
                for contact in existing[:3]:
                    try:
                        agent.draft_email(
                            contact_id=contact["id"],
                            email_type=email_type,
                            custom_notes=description or title,
                        )
                        drafted += 1
                    except Exception:
                        logger.warning("Outreach: failed to draft email for existing contact %s", contact.get("id"))
                if drafted:
                    return (
                        f"Drafted {drafted} {email_type} email(s) for existing {contact_type} contacts. "
                        "Check Approvals panel to review before sending."
                    )

            # Check if the task names a specific person ("Name at Company" or "Name, Company")
            import re as _re
            named_match = _re.search(
                r'([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s+(?:at|@|from|,)\s+([A-Z][A-Za-z0-9 &]+)',
                f"{title} {description or ''}"
            )

            if named_match:
                # Direct research path — faster and more reliable than discovery
                name    = named_match.group(1).strip()
                company = named_match.group(2).strip()
                try:
                    researched = agent.research_contact(
                        name=name,
                        company=company,
                        context=description or title,
                        contact_type=contact_type,
                        source="pm_task",
                    )
                    contact = researched["contact"]
                    agent.draft_email(
                        contact_id=contact["id"],
                        email_type=email_type,
                        custom_notes=description or title,
                    )
                    return (
                        f"Researched {name} at {company} and drafted a {email_type} email. "
                        "Check Approvals panel to review before sending."
                    )
                except Exception as exc:
                    logger.warning("Outreach named-person research failed: %s", exc)
                    return f"Could not research {name} at {company}: {exc}"

            # Discovery path — web scraping
            try:
                discovered = agent.discover_contacts(
                    focus=description or title,
                    contact_type=contact_type,
                    limit=3,
                    auto_research=True,
                )
            except ValueError as exc:
                logger.warning("Outreach discover_contacts found nothing: %s", exc)
                self.send_notification(
                    title="Outreach: no contacts found",
                    body=(
                        f"Could not find {contact_type}s for: {title}.\n"
                        "Try specifying a name: e.g. 'Research John Smith at Acme Golf'"
                    ),
                    priority="medium",
                )
                return (
                    f"No {contact_type}s found via web research for: {title}. "
                    "Tip: specify a name in the task, e.g. 'Research Jane Doe at TechCorp'."
                )

            contacts = discovered.get("saved_contacts", [])
            drafted = 0
            for contact in contacts:
                try:
                    agent.draft_email(
                        contact_id=contact["id"],
                        email_type=email_type,
                        custom_notes=description or title,
                    )
                    drafted += 1
                except Exception:
                    logger.warning("Outreach: failed to draft email for contact %s", contact.get("id"))

            return (
                f"Found {len(contacts)} {contact_type}(s). "
                f"Drafted {drafted} email(s) — check Approvals panel to review before sending."
            )

        if assigned_agent == "legal":
            from app.agents.legal.agent import LegalAgent
            agent = LegalAgent()
            result = agent.run(AgentTrigger(
                type=TriggerType.USER_REQUEST,
                user_input="deadline_check",
                parameters={"task_id": task_id, "task_title": title},
            ))
            return str(result.get("summary") or f"Legal review complete for: {title}")

        if assigned_agent == "marketing":
            from app.agents.marketing.agent import MarketingAgent
            agent = MarketingAgent()
            result = agent.run(AgentTrigger(
                type=TriggerType.USER_REQUEST,
                user_input=title,
                parameters={"task_id": task_id, "description": description},
            ))
            return str(result.get("summary") or f"Marketing agent actioned: {title}")

        if assigned_agent == "dev_activity":
            from app.agents.dev_activity.agent import DevActivityAgent
            agent = DevActivityAgent()
            result = agent.run(AgentTrigger(
                type=TriggerType.USER_REQUEST,
                user_input="summarize",
                parameters={"task_id": task_id, "task_title": title},
            ))
            return str(result.get("summary") or f"Dev activity review complete for: {title}")

        # Fallback: PM-level LLM outcome summary
        raw = self.llm_chat(
            system_prompt=(
                "You are a senior project manager recording task completion. "
                "Write a concise 2-3 sentence outcome summary for the completed task. "
                "Focus on what was accomplished and any immediate next steps."
            ),
            user_message=(
                f"Task: {title}\n"
                f"Description: {description or 'n/a'}\n"
                f"Priority score: {content.get('priority_score', 50)}/100"
            ),
            temperature=0.3,
        )
        return raw.strip()

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

        # Create an approval so the user can accept/decline before the task runs
        try:
            create_approval(
                agent="pm",
                action_type="start_task",
                content={
                    "task_id": str(task["id"]),
                    "title": task["title"],
                    "description": task.get("description") or "",
                    "priority_score": task.get("priority_score", 50),
                    "priority_reason": task.get("priority_reason") or "",
                    "source_agent": source_agent,
                },
            )
        except Exception:
            logger.exception("PMAgent failed to create approval for task %s", task.get("id"))

        self.send_notification(
            title="New task awaiting approval",
            body=f"{task['title']}  —  priority {task.get('priority_score', 50):.0f}/100",
            priority="medium",
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
