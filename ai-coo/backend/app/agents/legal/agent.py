"""
agents/legal/agent.py — LegalAgent

"Tell Me What I'm Forgetting" — generates compliance checklists, drafts
legal documents, tracks deadlines, and reacts to business events that create
new legal obligations.

AUTONOMY RULES
  Generate checklist        → Autonomous
  Draft documents           → Autonomous (creates draft + approval request)
  Mark document final       → APPROVAL REQUIRED
  Send deadline reminders   → Autonomous
  Add checklist items from events → Notify (adds item, does not act further)

TRIGGER HANDLING
  USER_REQUEST
    user_input="generate_checklist"  → _generate_checklist(trigger.parameters)
    user_input="draft_document"      → _draft_document(trigger.parameters)
    user_input="deadline_check"      → _run_deadline_check()
    user_input="execute_approved:*"  → _handle_approval_callback(trigger.parameters)

  SCHEDULED
    task_name="deadline_check"       → _run_deadline_check()

  EVENT
    lead_converted                   → _handle_lead_converted(event)
    revenue_recorded                 → _handle_revenue_recorded(event)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.core.base_agent import BaseAgent
from app.db.supabase_client import get_client
from app.schemas.triggers import AgentTrigger, TriggerType

from app.agents.legal.tools import (
    build_checklist_prompt,
    build_document_prompt,
    days_until,
    document_type_for_item,
    get_existing_documents,
    get_pending_checklist_items,
    parse_checklist_json,
    resolve_due_date,
    urgency_from_days,
)

logger = logging.getLogger(__name__)


class LegalAgent(BaseAgent):
    name = "legal"
    description = (
        "Generates compliance checklists, drafts legal documents, tracks deadlines, "
        "ensures nothing falls through the cracks"
    )
    subscribed_events = ["lead_converted", "revenue_recorded"]
    writable_global_fields = []

    # ── System prompt injected into every LLM call ────────────────────────────
    _SYSTEM_PROMPT = (
        "You are an experienced startup legal advisor with expertise in corporate law, "
        "compliance, intellectual property, and contracts. You give clear, actionable "
        "advice tailored to early-stage companies. You are thorough but practical — "
        "you flag what actually matters at each stage, not every theoretical risk."
    )

    # ── BaseAgent abstract methods ────────────────────────────────────────────

    def load_domain_context(self) -> dict[str, Any]:
        """Load checklist summary counts and recent documents for situational awareness."""
        client = get_client()

        # Count items by status
        checklist_resp = (
            client.table("legal_checklist")
            .select("status")
            .execute()
        )
        rows = checklist_resp.data or []
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

        # Most recent document drafts
        docs_resp = (
            client.table("legal_documents")
            .select("id, document_type, title, status, created_at")
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        return {
            "checklist_status_counts": status_counts,
            "total_checklist_items": len(rows),
            "recent_documents": docs_resp.data or [],
        }

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        """
        Main dispatch method. Routes to private helpers based on trigger type
        and user_input / task_name values.
        """
        # ── Scheduled ─────────────────────────────────────────────────────────
        if trigger.type == TriggerType.SCHEDULED:
            if trigger.task_name == "deadline_check":
                return self._run_deadline_check()
            # Unknown scheduled task — log and skip
            self.logger.warning("LegalAgent: unknown scheduled task '%s'", trigger.task_name)
            return {"status": "skipped", "reason": f"unknown task: {trigger.task_name}"}

        # ── Event-driven ──────────────────────────────────────────────────────
        if trigger.type == TriggerType.EVENT:
            from app.schemas.events import Event as EventSchema
            results = []
            raw = trigger.events or ([trigger.event] if trigger.event else [])
            # Events arriving from Celery are serialised to dicts via model_dump();
            # coerce them back to Event objects so we can use attribute access.
            events = [
                EventSchema(**e) if isinstance(e, dict) else e
                for e in raw
            ]
            for event in events:
                if event.event_type == "lead_converted":
                    results.append(self._handle_lead_converted(event))
                elif event.event_type == "revenue_recorded":
                    results.append(self._handle_revenue_recorded(event))
                else:
                    self.logger.debug("LegalAgent: ignoring event type '%s'", event.event_type)
                # Only mark consumed when we have a real persisted id
                if event.id:
                    self.mark_consumed(event.id)
            return {"status": "ok", "events_processed": len(results), "results": results}

        # ── User request ──────────────────────────────────────────────────────
        if trigger.type == TriggerType.USER_REQUEST:
            user_input = (trigger.user_input or "").lower()
            params = trigger.parameters or {}

            if user_input == "generate_checklist":
                return self._generate_checklist(params)

            if user_input == "draft_document":
                return self._draft_document(params.get("checklist_item_id", ""), params)

            if user_input in ("deadline_check", "manual run"):
                return self._run_deadline_check()

            # Approval callback: "execute_approved:mark_document_final"
            if user_input.startswith("execute_approved:"):
                return self._handle_approval_callback(params)

            self.logger.warning("LegalAgent: unrecognised user_input '%s'", trigger.user_input)
            return {"status": "skipped", "reason": f"unknown user_input: {trigger.user_input}"}

        return {"status": "skipped", "reason": "unhandled trigger type"}

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        """Legal agent has no single domain state row — all state is in DB tables."""
        pass

    # ── Feature 1: Checklist generation ──────────────────────────────────────

    def _generate_checklist(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate a tailored compliance checklist via LLM and store it in DB.

        Expected params keys: entity_type, jurisdiction, stage, product_type.
        Returns the list of created checklist item dicts.
        """
        entity_type  = params.get("entity_type", "C-Corp")
        jurisdiction = params.get("jurisdiction", "Delaware, USA")
        stage        = params.get("stage", "pre_launch")
        product_type = params.get("product_type", "SaaS")

        self.logger.info(
            "LegalAgent: generating checklist for %s/%s/%s/%s",
            entity_type, jurisdiction, stage, product_type,
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        user_msg = build_checklist_prompt(entity_type, jurisdiction, stage, product_type)
        raw_response = self.llm_chat(
            system_prompt=self._SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.3,        # low temp for structured factual output
            inject_context=False,   # checklist generation doesn't need business context header
        )

        # ── Parse ──────────────────────────────────────────────────────────────
        try:
            items = parse_checklist_json(raw_response)
        except ValueError as exc:
            self.logger.error("LegalAgent: checklist JSON parse failed: %s", exc)
            raise RuntimeError(f"Failed to parse checklist from LLM response: {exc}")

        # ── Resolve dates and insert ───────────────────────────────────────────
        client = get_client()
        today = date.today()
        inserted: list[dict[str, Any]] = []
        already_overdue: list[dict[str, Any]] = []

        for raw_item in items:
            due_date = resolve_due_date(raw_item.get("deadline_rule", ""), today)
            typically_overdue = raw_item.get("typically_overdue", False)

            # Determine DB status
            if due_date and due_date < today:
                status = "overdue"
            elif typically_overdue and due_date is None:
                status = "pending"
            else:
                status = "pending"

            row = {
                "item":        raw_item.get("item", "")[:255],
                "description": raw_item.get("description", ""),
                "category":    raw_item.get("category", "compliance"),
                "priority":    raw_item.get("priority", "medium"),
                "due_date":    due_date.isoformat() if due_date else None,
                "status":      status,
                "notes":       f"Deadline rule: {raw_item.get('deadline_rule', 'none')}",
            }

            resp = client.table("legal_checklist").insert(row).execute()
            created = resp.data[0]
            inserted.append(created)

            # Flag already-overdue items for event emission
            if status == "overdue" or (typically_overdue and due_date and due_date < today):
                already_overdue.append(created)

        # ── Emit events for pre-existing overdue items ─────────────────────────
        for item in already_overdue:
            d = days_until(date.fromisoformat(item["due_date"])) if item.get("due_date") else -1
            self.emit_event(
                event_type="legal.deadline_approaching",
                payload={
                    "item_name":      item["item"],
                    "due_date":       item.get("due_date"),
                    "days_remaining": d,
                    "urgency":        "urgent",
                    "description":    item.get("description", ""),
                    "checklist_id":   str(item["id"]),
                },
                summary=f"{item['item']} is already overdue — action required",
                priority="urgent",
            )
            self.send_notification(
                title=f"Overdue: {item['item']}",
                body=item.get("description", "This compliance item requires immediate attention."),
                priority="urgent",
            )

        self.logger.info("LegalAgent: inserted %d checklist items (%d overdue)", len(inserted), len(already_overdue))
        return {
            "status": "ok",
            "items_created": len(inserted),
            "overdue_count": len(already_overdue),
            "checklist": inserted,
        }

    # ── Feature 2: Document drafting ──────────────────────────────────────────

    def _draft_document(
        self,
        checklist_item_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Draft a legal document for a specific checklist item.

        Steps:
          1. Load checklist item from DB
          2. Read global context for company/product details
          3. Call LLM to produce full document draft
          4. Store in legal_documents with status "draft"
          5. Create approval request (required before marking final)
          6. Emit document_drafted event
          7. Update checklist item status to "in_progress"
        """
        if not checklist_item_id:
            raise ValueError("checklist_item_id is required to draft a document")

        client = get_client()

        # Load checklist item
        item_resp = (
            client.table("legal_checklist")
            .select("*")
            .eq("id", checklist_item_id)
            .maybe_single()
            .execute()
        )
        if not item_resp.data:
            raise ValueError(f"Checklist item '{checklist_item_id}' not found")

        item = item_resp.data
        doc_type = document_type_for_item(item["item"])

        # Company details from global context
        ctx = self._global_context
        cp  = ctx.company_profile
        bs  = ctx.business_state
        extra_context = (params or {}).get("context", "")

        self.logger.info(
            "LegalAgent: drafting %s for checklist item '%s'", doc_type, item["item"]
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        user_msg = build_document_prompt(
            document_type=doc_type,
            company_name=cp.name or "the Company",
            product_name=cp.product_name or "the Product",
            product_description=cp.product_description or "",
            jurisdiction=cp.jurisdiction or "the applicable jurisdiction",
            stage=bs.phase,
            product_type=", ".join(cp.tech_stack) if cp.tech_stack else "software",
            extra_context=extra_context,
        )

        document_text = self.llm_chat(
            system_prompt=self._SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.4,
            inject_context=False,   # document prompt already has full company context
        )

        title = f"{doc_type.replace('_', ' ').title()} — {cp.name or 'Draft'}"

        # ── Store document ─────────────────────────────────────────────────────
        doc_resp = client.table("legal_documents").insert({
            "document_type":      doc_type,
            "title":              title,
            "content":            document_text,
            "status":             "draft",
            "checklist_item_id":  checklist_item_id,
        }).execute()
        document = doc_resp.data[0]
        document_id = str(document["id"])

        # ── Approval request (required before marking final) ───────────────────
        approval = self.request_approval(
            action_type="mark_document_final",
            content={
                "document_id":       document_id,
                "document_type":     doc_type,
                "title":             title,
                "checklist_item_id": checklist_item_id,
                "preview":           document_text[:500] + ("..." if len(document_text) > 500 else ""),
            },
        )

        # Attach approval_id to the document row
        client.table("legal_documents").update({
            "approval_id": str(approval.id),
        }).eq("id", document_id).execute()

        # ── Update checklist item status ───────────────────────────────────────
        client.table("legal_checklist").update({
            "status": "in_progress",
        }).eq("id", checklist_item_id).execute()

        # ── Emit event ─────────────────────────────────────────────────────────
        self.emit_event(
            event_type="legal.document_drafted",
            payload={
                "document_type":     doc_type,
                "document_id":       document_id,
                "status":            "draft",
                "checklist_item_id": checklist_item_id,
            },
            summary=f"Drafted {title} — awaiting review",
            priority="medium",
        )

        # ── Notify ─────────────────────────────────────────────────────────────
        self.send_notification(
            title=f"Document ready for review: {title}",
            body=(
                f"A draft {doc_type.replace('_', ' ')} has been prepared. "
                "Please review and approve before it is marked as final."
            ),
            priority="medium",
        )

        self.logger.info("LegalAgent: drafted document %s (approval=%s)", document_id, approval.id)
        return {
            "status":        "ok",
            "document_id":   document_id,
            "document_type": doc_type,
            "title":         title,
            "approval_id":   str(approval.id),
            "checklist_item_updated": True,
        }

    # ── Feature 3: Approval callback (mark document final) ────────────────────

    def _handle_approval_callback(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Called by the approval route's background task when the user approves
        a "mark_document_final" action.

        Updates legal_documents.status to "final" and the linked checklist
        item to "done".
        """
        # approval_routes.py stores the original approval content nested under "content":
        # params = {"approval_id": ..., "action_type": ..., "content": {"document_id": ..., ...}}
        content           = params.get("content", {})
        document_id       = content.get("document_id") or params.get("document_id")
        checklist_item_id = content.get("checklist_item_id") or params.get("checklist_item_id")

        if not document_id:
            return {"status": "skipped", "reason": "no document_id in approval params"}

        client = get_client()

        # Apply any user edits to the document content
        update_payload: dict[str, Any] = {"status": "final"}
        if content.get("content"):
            update_payload["content"] = content["content"]

        client.table("legal_documents").update(update_payload).eq("id", document_id).execute()

        if checklist_item_id:
            client.table("legal_checklist").update({
                "status": "done",
            }).eq("id", checklist_item_id).execute()

        self.send_notification(
            title="Legal document finalised",
            body=f"Document '{params.get('title', document_id)}' has been marked as final.",
            priority="low",
        )

        self.logger.info("LegalAgent: document %s marked final", document_id)
        return {"status": "ok", "document_id": document_id, "document_status": "final"}

    # ── Feature 4: Deadline check (scheduled daily at 8 AM) ──────────────────

    def _run_deadline_check(self) -> dict[str, Any]:
        """
        Query all non-done checklist items due within 14 days or already overdue.
        Emit deadline_approaching events and notifications for each.
        """
        items = get_pending_checklist_items(days_window=14)
        if not items:
            self.logger.info("LegalAgent: deadline check — no upcoming deadlines")
            return {"status": "ok", "deadlines_found": 0}

        emitted = 0
        for item in items:
            due_str = item.get("due_date")
            if not due_str:
                continue

            due = date.fromisoformat(due_str)
            days = days_until(due)
            urgency = urgency_from_days(days)

            if days < 0:
                days_label = f"{abs(days)} days overdue"
                summary = f"{item['item']} is {abs(days)} days overdue — action required"
            elif days == 0:
                days_label = "due today"
                summary = f"{item['item']} is due today"
            else:
                days_label = f"{days} days remaining"
                summary = f"{item['item']} is due in {days} days"

            self.emit_event(
                event_type="legal.deadline_approaching",
                payload={
                    "item_name":      item["item"],
                    "due_date":       due_str,
                    "days_remaining": days,
                    "urgency":        urgency,
                    "description":    item.get("description", ""),
                    "checklist_id":   str(item["id"]),
                },
                summary=summary,
                priority=urgency,
            )

            # Update status to "overdue" in DB if past due
            if days < 0 and item.get("status") != "overdue":
                client = get_client()
                client.table("legal_checklist").update(
                    {"status": "overdue"}
                ).eq("id", item["id"]).execute()

            notif_priority = urgency if urgency in ("urgent", "high") else "medium"
            self.send_notification(
                title=f"Legal deadline: {item['item']}",
                body=f"{item.get('description', '')} ({days_label})",
                priority=notif_priority,
            )
            emitted += 1

        self.logger.info("LegalAgent: deadline check — %d reminders sent", emitted)
        return {"status": "ok", "deadlines_found": len(items), "reminders_sent": emitted}

    # ── Feature 5: Event handlers ─────────────────────────────────────────────

    def _handle_lead_converted(self, event: Any) -> dict[str, Any]:
        """
        Triggered when a lead is converted (outreach.lead_converted or lead_converted).

        If conversion_type is "customer": check whether a Terms of Service exists.
        If no ToS found: create a checklist item and notify.
        """
        payload = event.payload or {}
        conversion_type = payload.get("conversion_type", "customer")

        if conversion_type != "customer":
            return {"skipped": True, "reason": "non-customer conversion"}

        existing_tos = get_existing_documents("tos")
        if existing_tos:
            self.logger.info("LegalAgent: ToS already exists, no action needed")
            return {"status": "ok", "tos_exists": True}

        # No ToS — create a high-priority checklist item
        client = get_client()
        resp = client.table("legal_checklist").insert({
            "item":        "Draft Terms of Service",
            "description": (
                "You have converted your first customer. A Terms of Service is required "
                "to define usage rights, liability limits, and dispute resolution."
            ),
            "category": "contracts",
            "priority": "high",
            "status":   "pending",
            "due_date": None,   # no fixed deadline — should be done ASAP
            "notes":    "Auto-created on first customer conversion",
        }).execute()
        new_item = resp.data[0]

        self.emit_event(
            event_type="legal.compliance_gap_found",
            payload={
                "requirement":         "Terms of Service",
                "risk_level":          "high",
                "recommended_action":  "Draft and publish a Terms of Service before onboarding more customers",
                "checklist_item_id":   str(new_item["id"]),
            },
            summary="Compliance gap: no Terms of Service — customer just converted",
            priority="high",
        )

        self.send_notification(
            title="Action needed: Draft Terms of Service",
            body=(
                "Your first customer has converted but you don't have a Terms of Service. "
                "Use POST /api/legal/draft to generate one now."
            ),
            priority="high",
        )

        return {"status": "ok", "checklist_item_created": str(new_item["id"]), "tos_exists": False}

    def _handle_revenue_recorded(self, event: Any) -> dict[str, Any]:
        """
        Triggered when revenue is recorded (finance.revenue_recorded or revenue_recorded).

        If this is the first revenue: add tax-related checklist items
        (sales tax registration, revenue reporting obligations).
        """
        payload = event.payload or {}
        is_first_revenue = payload.get("is_first_revenue", False)

        if not is_first_revenue:
            return {"status": "ok", "skipped": True, "reason": "not first revenue"}

        client = get_client()

        # Check if tax items already exist
        existing_tax = (
            client.table("legal_checklist")
            .select("id")
            .eq("category", "tax")
            .limit(1)
            .execute()
        )
        if existing_tax.data:
            return {"status": "ok", "skipped": True, "reason": "tax items already exist"}

        ctx = self._global_context
        jurisdiction = ctx.company_profile.jurisdiction or "your jurisdiction"

        tax_items = [
            {
                "item":        "Register for Sales Tax / VAT",
                "description": (
                    f"You have recorded first revenue. Check whether sales tax (US) or VAT "
                    f"registration is required in {jurisdiction} and customer locations."
                ),
                "category": "tax",
                "priority": "high",
                "status":   "pending",
                "notes":    "Auto-created on first revenue event",
            },
            {
                "item":        "Set Up Revenue Recognition Policy",
                "description": (
                    "Document how and when revenue is recognised. Required for clean books "
                    "and future fundraising due diligence."
                ),
                "category": "tax",
                "priority": "medium",
                "status":   "pending",
                "notes":    "Auto-created on first revenue event",
            },
            {
                "item":        "Open Dedicated Business Bank Account",
                "description": (
                    "Ensure revenue flows through a dedicated business account, not a "
                    "personal account. Required for clean financial records and liability protection."
                ),
                "category": "tax",
                "priority": "high",
                "status":   "pending",
                "notes":    "Auto-created on first revenue event",
            },
        ]

        created_ids: list[str] = []
        for tax_item in tax_items:
            resp = client.table("legal_checklist").insert(tax_item).execute()
            created_ids.append(str(resp.data[0]["id"]))

            self.emit_event(
                event_type="legal.deadline_approaching",
                payload={
                    "item_name":      tax_item["item"],
                    "due_date":       None,
                    "days_remaining": 0,
                    "urgency":        tax_item["priority"],
                    "description":    tax_item["description"],
                },
                summary=f"New tax obligation: {tax_item['item']}",
                priority=tax_item["priority"],
            )

        self.send_notification(
            title="New legal obligations from first revenue",
            body=(
                f"{len(tax_items)} tax and compliance items have been added to your checklist. "
                "Review them at /api/legal/checklist."
            ),
            priority="high",
        )

        self.logger.info(
            "LegalAgent: added %d tax checklist items for first revenue", len(tax_items)
        )
        return {
            "status":        "ok",
            "items_created": len(tax_items),
            "item_ids":      created_ids,
        }
