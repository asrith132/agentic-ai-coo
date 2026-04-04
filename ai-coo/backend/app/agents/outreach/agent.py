"""
agents/outreach/agent.py — OutreachAgent implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.base_agent import BaseAgent
from app.db.supabase_client import get_client
from app.schemas.events import Event
from app.schemas.triggers import AgentTrigger, TriggerType

from app.agents.outreach import tools


class OutreachAgent(BaseAgent):
    name = "outreach"
    description = "Handles all one-to-one external communication — customers, investors, partners, press"
    subscribed_events = ["feature_shipped", "trend_found", "research_completed"]
    writable_global_fields: list[str] = []

    def _ensure_context(self) -> None:
        if not hasattr(self, "_global_context"):
            self._global_context = self.load_global_context()
        if not hasattr(self, "_domain_context"):
            self._domain_context = self.load_domain_context()

    def load_domain_context(self) -> dict[str, Any]:
        client = get_client()
        contacts = client.table("outreach_contacts").select("id", count="exact").limit(1).execute()
        messages = client.table("outreach_messages").select("id", count="exact").limit(1).execute()
        templates = client.table("outreach_templates").select("id", count="exact").limit(1).execute()
        return {
            "contact_count": contacts.count or 0,
            "message_count": messages.count or 0,
            "template_count": templates.count or 0,
            "last_loaded_at": datetime.now(timezone.utc).isoformat(),
        }

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        self._domain_context = {**getattr(self, "_domain_context", {}), **updates}

    def research_contact(
        self,
        *,
        name: str,
        company: str,
        context: str | None = None,
        source: str = "manual",
        status: str = "cold",
        contact_type: str = "customer",
    ) -> dict[str, Any]:
        self._ensure_context()
        research_cache = tools.build_research_cache(name=name, company=company, context=context)
        contact = tools.upsert_contact(
            name=name,
            company=company,
            role=research_cache.get("role"),
            email=research_cache.get("email"),
            contact_type=contact_type,
            status=status,
            source=source,
            research_cache=research_cache,
            notes=context,
        )

        brief = self.llm_chat(
            system_prompt=(
                "You are an expert startup outreach researcher. "
                "Write a concise actionable brief with the headings: "
                "'Who they are', 'What they care about', and 'Recommended angle'. "
                "If contact information is missing, say it is unknown. Do not invent email addresses, company names, or titles."
            ),
            user_message=(
                f"Based on this research on {name} at {company}, summarize: who they are, "
                f"what they care about, and what angle we should use to reach out given that "
                f"our product is {self._global_context.company_profile.product_description or 'an AI operations platform'}.\n\n"
                f"Research cache:\n{research_cache}"
            ),
            temperature=0.3,
        )

        updated_cache = {**(contact.get("research_cache") or {}), "brief": brief}
        contact = tools.update_contact(contact["id"], {"research_cache": updated_cache})
        return {"contact": contact, "research_brief": brief}

    def draft_email(
        self,
        *,
        contact_id: str,
        email_type: str,
        custom_notes: str | None = None,
        event_context: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_context()
        contact = tools.get_contact(contact_id)
        if contact is None:
            raise ValueError(f"Contact '{contact_id}' not found")

        ctx = self._global_context
        recent_relevant_events = [
            evt for evt in ctx.recent_events
            if evt.get("source_agent") in {"dev_activity", "marketing", "research", "outreach"}
        ][-5:]

        founder_name = ctx.company_profile.name or "the founder"
        prompt = (
            f"You are writing an email on behalf of {founder_name} who built "
            f"{ctx.company_profile.product_name or 'the product'}.\n"
            f"Brand voice: {ctx.brand_voice.model_dump()}.\n"
            f"Recipient: {contact.get('name')} at {contact.get('company')}.\n"
            f"Here's what we know about them: {contact.get('research_cache') or {}}.\n"
            f"Recent product updates: {recent_relevant_events}.\n"
            f"Extra context: {custom_notes or '(none)'}.\n"
            f"Event context: {event_context or '(none)'}.\n\n"
            f"Write a {email_type} email that:\n"
            f"- References something specific about them\n"
            f"- Clearly explains what {ctx.company_profile.product_name or 'the product'} does\n"
            f"- Has a specific, low-friction ask\n"
            f"- Sounds like a real person, not a template\n"
            f"Keep it under 150 words.\n\n"
            "Return only valid JSON with keys 'subject', 'body', 'template_used'."
        )
        raw = self.llm_chat(
            system_prompt="You write high-conviction founder outreach emails. Output JSON only.",
            user_message=prompt,
            temperature=0.6,
        )

        parsed = self._parse_draft_json(raw)
        message = tools.create_message(
            contact_id=contact_id,
            subject=parsed["subject"],
            body=parsed["body"],
            direction="sent",
            status="draft",
            template_used=parsed.get("template_used") or email_type,
        )
        approval = self.request_approval(
            action_type="send_email",
            content={
                "message_id": message["id"],
                "contact_id": contact_id,
                "contact_name": contact.get("name"),
                "contact_email": contact.get("email"),
                "email_type": email_type,
                "subject": parsed["subject"],
                "body": parsed["body"],
                "template_used": parsed.get("template_used") or email_type,
            },
        )
        message = tools.update_message(
            message["id"],
            {"approval_id": approval.id, "status": "pending_approval"},
        )
        return {"message": message, "approval": approval.model_dump()}

    def discover_contacts(
        self,
        *,
        focus: str | None = None,
        limit: int = 5,
        contact_type: str = "customer",
        auto_research: bool = True,
    ) -> dict[str, Any]:
        self._ensure_context()
        ctx = self._global_context
        query_plan = tools.build_contextual_discovery_queries(
            product_name=ctx.company_profile.product_name,
            product_description=ctx.company_profile.product_description,
            key_features=ctx.company_profile.key_features,
            persona=ctx.target_customer.persona,
            industry=ctx.target_customer.industry,
            company_size=ctx.target_customer.company_size,
            pain_points=ctx.target_customer.pain_points,
            active_priorities=ctx.business_state.active_priorities,
            market_position=ctx.competitive_landscape.market_position,
            focus=focus,
        )

        reddit_results: list[dict[str, str]] = []
        for query in query_plan["reddit"]:
            reddit_results.extend(tools.search_reddit_posts(query, max_results=5))

        profile_results: list[dict[str, str]] = []
        for query in query_plan["profiles"]:
            profile_results.extend(tools.search_google_profiles(query, max_results=5))

        company_results: list[dict[str, str]] = []
        for query in query_plan["company"]:
            company_results.extend(tools.search_web(query, max_results=4))

        search_results: list[dict[str, str]] = [
            *reddit_results,
            *profile_results,
            *company_results,
        ]

        if not search_results:
            raise ValueError("No search results found for prospect discovery")

        prospect_prompt = f"""
You are the autonomous prospecting engine for {ctx.company_profile.name or 'this company'}.

Your job:
Find the best people to reach out to for {ctx.company_profile.product_name or 'the product'}.

Company context:
- Product: {ctx.company_profile.product_name}
- Product description: {ctx.company_profile.product_description}
- Key features: {ctx.company_profile.key_features}
- Target persona: {ctx.target_customer.persona}
- Target industry: {ctx.target_customer.industry}
- Target company size: {ctx.target_customer.company_size}
- Pain points: {ctx.target_customer.pain_points}
- Active priorities: {ctx.business_state.active_priorities}
- Competitive position: {ctx.competitive_landscape.market_position}
- Recent events: {ctx.recent_events[-5:]}
- Discovery focus: {focus or 'best near-term outreach targets'}

Rules:
- Pick only prospects supported by the search evidence.
- Prefer named people with real evidence.
- Never invent an email address.
- Never invent a company name. If company is unclear, set it to "Unknown".
- Never use synthetic placeholders like "Head of Operations at YC Seed-Stage SaaS Startup" as the stored name.
- If a real person is not supported by evidence, skip them instead of fabricating identity fields.
- Favor people who plausibly own the pain point and could buy, pilot, or partner.
- Use Reddit evidence aggressively when someone is publicly describing the exact pain this company solves.
- If the evidence only proves a Reddit username or social handle, keep the name as that real handle and do not invent a real name.
- Explain exactly why this prospect is a fit for THIS company.
- Do not output vague generic prospects.
- Include the best reachable channel supported by evidence: email, reddit_dm, linkedin_dm, x_dm, or unknown.
- If a profile URL is visible in the evidence, include it.

Return valid JSON only with this shape:
{{
  "prospects": [
    {{
      "name": "string",
      "company": "string",
      "role": "string",
      "contact_type": "{contact_type}",
      "email": null,
      "reachable_via": "unknown",
      "profile_url": null,
      "why_fit": "string",
      "outreach_angle": "string",
      "evidence": ["string"],
      "priority_score": 0
    }}
  ]
}}
Limit to {limit} prospects.
"""
        raw = self.llm_chat(
            system_prompt=prospect_prompt,
            user_message=f"Search evidence:\n{search_results}",
            temperature=0.4,
        )
        prospects = self._parse_prospects_json(raw, limit=limit)

        saved_contacts: list[dict[str, Any]] = []
        enriched_prospects: list[dict[str, Any]] = []
        for prospect in prospects:
            notes = (
                f"Discovery focus: {focus or 'general'}\n"
                f"Why fit: {prospect['why_fit']}\n"
                f"Angle: {prospect['outreach_angle']}"
            )
            contact = tools.upsert_contact(
                name=prospect["name"],
                company=prospect["company"],
                role=prospect.get("role"),
                email=prospect.get("email"),
                contact_type=prospect.get("contact_type", contact_type),
                status="cold",
                source="autonomous_discovery",
                research_cache={
                    "discovery": {
                        "why_fit": prospect["why_fit"],
                        "outreach_angle": prospect["outreach_angle"],
                        "priority_score": prospect["priority_score"],
                        "reachable_via": prospect.get("reachable_via", "unknown"),
                        "profile_url": prospect.get("profile_url"),
                        "evidence": prospect.get("evidence", []),
                        "search_results": search_results,
                    }
                },
                notes=notes,
            )
            saved_contacts.append(contact)
            if auto_research:
                researched = self.research_contact(
                    name=contact["name"],
                    company=contact["company"],
                    context=notes,
                    source="autonomous_discovery",
                    status=contact.get("status", "cold"),
                    contact_type=contact.get("contact_type", contact_type),
                )
                enriched_prospects.append(
                    {
                        **prospect,
                        "contact_id": researched["contact"]["id"],
                        "research_brief": researched["research_brief"],
                    }
                )
            else:
                enriched_prospects.append({**prospect, "contact_id": contact["id"]})

        return {
            "queries": query_plan,
            "search_results": search_results,
            "reddit_results": reddit_results,
            "profile_results": profile_results,
            "company_results": company_results,
            "prospects": enriched_prospects,
            "saved_contacts": saved_contacts,
        }

    def send_message(self, *, message_id: str) -> dict[str, Any]:
        self._ensure_context()
        message = tools.get_message(message_id)
        if message is None:
            raise ValueError(f"Message '{message_id}' not found")
        if message.get("status") == "sent":
            raise ValueError(f"Message '{message_id}' has already been sent")
        approval = tools.ensure_approval_is_approved(message.get("approval_id"))
        content = approval.get("final_content") or {}
        contact = tools.get_contact(message["contact_id"])
        if contact is None:
            raise ValueError(f"Contact '{message['contact_id']}' not found")

        send_result = tools.send_via_gmail(
            to_email=contact.get("email") or content.get("contact_email"),
            subject=content.get("subject") or message.get("subject") or "",
            body=content.get("body") or message.get("body") or "",
        )
        updated = tools.update_message(
            message_id,
            {
                "status": "sent",
                "subject": content.get("subject") or message.get("subject"),
                "body": content.get("body") or message.get("body"),
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        tools.update_contact(
            contact["id"],
            {
                "last_contacted_at": datetime.now(timezone.utc).isoformat(),
                "status": "warm" if contact.get("status") == "cold" else contact.get("status"),
            },
        )

        self.emit_event(
            event_type="outreach_sent",
            payload={
                "contact_name": contact.get("name"),
                "message_type": content.get("email_type", message.get("template_used")),
                "template_used": content.get("template_used", message.get("template_used")),
            },
            summary=f"Sent {content.get('email_type', message.get('template_used', 'outreach'))} email to {contact.get('name')}",
            priority="low",
        )

        template = tools.get_template(content.get("template_used") or message.get("template_used"))
        tools.schedule_next_followup(contact["id"], (template or {}).get("follow_up_sequence"))
        return {"message": updated, "send_result": send_result}

    def process_replies(self) -> dict[str, Any]:
        self._ensure_context()
        replies = tools.fetch_recent_replies()
        processed = 0

        for reply in replies:
            contact_email = reply.get("contact_email")
            if not contact_email:
                continue
            response = (
                get_client()
                .table("outreach_contacts")
                .select("*")
                .eq("email", contact_email)
                .maybe_single()
                .execute()
            )
            contact = response.data if response.data else None
            if not contact:
                continue

            sentiment = self._classify_reply_sentiment(reply["body"])
            status = "responded" if sentiment != "positive" else "converted"
            tools.update_contact(contact["id"], {"status": status})
            message = tools.create_message(
                contact_id=contact["id"],
                subject=reply.get("subject") or "",
                body=reply.get("body") or "",
                direction="received",
                status="replied",
            )

            summary = self.llm_chat(
                system_prompt="Summarize the reply in one or two sentences. Output plain text only.",
                user_message=reply.get("body") or "",
                temperature=0.2,
            )

            self.emit_event(
                event_type="reply_received",
                payload={
                    "contact_name": contact.get("name"),
                    "contact_email": contact_email,
                    "sentiment": sentiment,
                    "summary": summary,
                    "original_message_id": message["id"],
                },
                summary=f"{contact.get('name')} replied to your outreach email — sentiment: {sentiment}",
                priority="high",
            )
            self.send_notification(
                title=f"Reply from {contact.get('name')}",
                body=summary,
                priority="high",
            )

            if status == "converted":
                self.emit_event(
                    event_type="lead_converted",
                    payload={
                        "contact_name": contact.get("name"),
                        "contact_type": contact.get("contact_type"),
                        "details": summary,
                    },
                    summary=f"{contact.get('name')} converted from responded to converted",
                    priority="high",
                )

            objection = self._extract_objection(summary)
            if objection:
                self.emit_event(
                    event_type="objection_heard",
                    payload={
                        "objection_text": objection,
                        "contact_name": contact.get("name"),
                        "frequency_count": self._count_objection_frequency(objection),
                    },
                    summary=f"Objection from {contact.get('name')}: '{objection}'. Heard {self._count_objection_frequency(objection)} times total.",
                    priority="medium",
                )

            processed += 1

        return {"processed_replies": processed}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        self._ensure_context()

        if (
            trigger.type == TriggerType.USER_REQUEST
            and trigger.user_input == "execute_approved:send_email"
            and trigger.parameters
        ):
            return self.send_message(message_id=trigger.parameters["content"]["message_id"])

        if trigger.type == TriggerType.SCHEDULED and trigger.task_name == "check_replies":
            return self.process_replies()

        if trigger.type == TriggerType.EVENT and trigger.events:
            drafted = 0
            researched = 0
            for event in trigger.events:
                if event.event_type == "feature_shipped":
                    drafted += self._handle_feature_shipped(event)
                elif event.event_type == "trend_found":
                    researched += self._handle_trend_found(event)
                elif event.event_type == "research_completed":
                    self._handle_research_completed(event)
                if getattr(event, "id", None):
                    self.mark_consumed(event.id)
            return {"status": "processed_events", "drafted": drafted, "researched": researched}

        if trigger.type == TriggerType.USER_REQUEST and trigger.parameters:
            action = trigger.parameters.get("action")
            if action == "research_contact":
                return self.research_contact(**trigger.parameters["payload"])
            if action == "discover_contacts":
                return self.discover_contacts(**trigger.parameters["payload"])
            if action == "draft_email":
                return self.draft_email(**trigger.parameters["payload"])
            if action == "send_message":
                return self.send_message(**trigger.parameters["payload"])

        return {"status": "idle", "reason": "no matching trigger"}

    def _handle_feature_shipped(self, event: Event) -> int:
        response = (
            get_client()
            .table("outreach_contacts")
            .select("*")
            .in_("status", ["warm", "responded"])
            .limit(10)
            .execute()
        )
        drafted = 0
        for contact in response.data:
            self.draft_email(
                contact_id=contact["id"],
                email_type="follow_up",
                custom_notes=f"Reference shipped feature: {event.payload.get('feature_name')}",
                event_context=event.summary,
            )
            drafted += 1
        return drafted

    def _handle_trend_found(self, event: Event) -> int:
        persona = (self._global_context.target_customer.persona or "").lower()
        topic = str(event.payload.get("topic") or event.summary or "")
        if persona and persona not in topic.lower():
            return 0

        people = event.payload.get("people") or []
        drafted = 0
        for person in people[:5]:
            researched = self.research_contact(
                name=person.get("name", "Unknown Contact"),
                company=person.get("company", "Unknown Company"),
                context=f"Found in trend: {topic}",
                source="marketing_agent",
                status="warm",
            )
            self.draft_email(
                contact_id=researched["contact"]["id"],
                email_type="cold",
                custom_notes=f"Reference this conversation: {event.payload.get('url') or event.summary}",
                event_context=event.summary,
            )
            drafted += 1
        return drafted

    def _handle_research_completed(self, event: Event) -> None:
        payload = event.payload or {}
        if payload.get("requesting_agent") != self.name:
            return
        contact_id = payload.get("contact_id")
        if not contact_id:
            return
        contact = tools.get_contact(contact_id)
        if not contact:
            return
        tools.update_contact(
            contact_id,
            {"research_cache": {**(contact.get("research_cache") or {}), "external_findings": payload.get("findings", [])}},
        )

    def _parse_draft_json(self, raw: str) -> dict[str, str]:
        import json
        import re

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError("LLM did not return parseable JSON draft output")
            parsed = json.loads(match.group(0))

        if not parsed.get("subject") or not parsed.get("body"):
            raise ValueError("Draft output is missing subject or body")
        return parsed

    def _parse_prospects_json(self, raw: str, *, limit: int) -> list[dict[str, Any]]:
        import json
        import re

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError("LLM did not return parseable JSON for prospects")
            parsed = json.loads(match.group(0))

        prospects = parsed.get("prospects")
        if not isinstance(prospects, list) or not prospects:
            raise ValueError("No prospects returned from discovery prompt")

        cleaned: list[dict[str, Any]] = []
        for prospect in prospects[:limit]:
            if not prospect.get("name") or not prospect.get("company"):
                continue
            if self._looks_like_placeholder_identity(prospect["name"], prospect["company"]):
                continue
            cleaned.append(
                {
                    "name": prospect["name"],
                    "company": prospect["company"],
                    "role": prospect.get("role", ""),
                    "contact_type": prospect.get("contact_type", "customer"),
                    "email": prospect.get("email"),
                    "reachable_via": prospect.get("reachable_via", "unknown"),
                    "profile_url": prospect.get("profile_url"),
                    "why_fit": prospect.get("why_fit", ""),
                    "outreach_angle": prospect.get("outreach_angle", ""),
                    "evidence": prospect.get("evidence", []),
                    "priority_score": int(prospect.get("priority_score", 50)),
                }
            )
        if not cleaned:
            raise ValueError("Prospect discovery returned no valid prospects")
        return cleaned

    def _looks_like_placeholder_identity(self, name: str, company: str) -> bool:
        lowered_name = name.lower()
        lowered_company = company.lower()
        bad_name_markers = [
            "head of ",
            "founder at ",
            "operator at ",
            "unknown (",
            "unknown linkedin",
        ]
        bad_company_markers = [
            "unknown (",
            "y combinator portfolio",
            "seed-stage",
            "1–10 employees",
            "1-10 employees",
        ]
        if lowered_name.startswith("u/") or lowered_name.startswith("@"):
            return False
        return any(marker in lowered_name for marker in bad_name_markers) or any(
            marker in lowered_company for marker in bad_company_markers
        )

    def _classify_reply_sentiment(self, reply_body: str) -> str:
        result = self.llm_chat(
            system_prompt=(
                "Classify the sentiment of this outreach reply as exactly one of: "
                "positive, neutral, negative. Output the label only."
            ),
            user_message=reply_body[:3000],
            temperature=0.1,
        ).strip().lower().strip(".! ")
        return result if result in {"positive", "neutral", "negative"} else "neutral"

    def _extract_objection(self, summary: str) -> str | None:
        objection = self.llm_chat(
            system_prompt=(
                "If the reply contains a concrete objection, extract it in one short phrase. "
                "If there is no objection, output NONE."
            ),
            user_message=summary,
            temperature=0.1,
        ).strip()
        return None if objection.upper() == "NONE" else objection

    def _count_objection_frequency(self, objection_text: str) -> int:
        messages = tools.list_messages(limit=200)
        needle = objection_text.lower()
        return sum(1 for msg in messages if needle in (msg.get("body") or "").lower()) or 1
