"""
agents/marketing/agent.py — MarketingAgent

Scans LinkedIn for relevant conversations, drafts content in brand voice,
maintains public presence.

Flagship feature: LinkedIn Trend Hunter + Content Drafter

Subscribed events: feature_shipped, research_completed, reply_received
Emitted events:    marketing.trend_found, marketing.content_published

Autonomy rules:
  - Trend scanning:   Autonomous
  - Drafting content: Autonomous (queued as pending_approval)
  - Publishing:       APPROVAL REQUIRED
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.base_agent import BaseAgent
from app.core.approvals import create_approval
from app.schemas.triggers import AgentTrigger, TriggerType
from app.agents.marketing import tools

logger = logging.getLogger(__name__)

RELEVANCE_STORE_THRESHOLD = 60
RELEVANCE_NOTIFY_THRESHOLD = 80


class MarketingAgent(BaseAgent):
    name = "marketing"
    description = (
        "Scans LinkedIn for relevant conversations, drafts content in brand voice, "
        "manages LinkedIn presence"
    )
    subscribed_events = ["feature_shipped", "research_completed", "reply_received"]
    writable_global_fields: list[str] = []

    # ── BaseAgent contract ────────────────────────────────────────────────────

    def load_domain_context(self) -> dict[str, Any]:
        try:
            return {
                "recent_posts":  tools.get_content_by_status("pending_approval", limit=10)
                                 + tools.get_content_by_status("draft", limit=5),
                "recent_trends": tools.get_recent_trends(limit=10),
            }
        except Exception:
            logger.exception("MarketingAgent failed to load domain context")
            return {"recent_posts": [], "recent_trends": []}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        results: dict[str, Any] = {"agent": self.name, "trigger": trigger.type}

        # Approval callback: user approved a post for publishing
        if (
            trigger.type == TriggerType.USER_REQUEST
            and trigger.parameters
            and trigger.parameters.get("action_type") == "publish_post"
        ):
            content = trigger.parameters.get("content", {})
            content_id = content.get("content_id")
            if content_id:
                results["publish"] = self._execute_approved_publish(content_id, content)
            return results

        # PM task dispatch: draft content for a given topic
        if (
            trigger.type == TriggerType.USER_REQUEST
            and trigger.parameters
            and trigger.parameters.get("task_id")
        ):
            topic = (
                trigger.parameters.get("description")
                or trigger.user_input
                or "our product"
            )
            draft = self.draft_content(
                content_type="thought_leadership",
                platform="linkedin",
                topic=topic,
            )
            results["draft"] = draft
            results["summary"] = f"Drafted LinkedIn post about: {topic}"
            return results

        # Event trigger
        if trigger.type == TriggerType.EVENT:
            created: list[dict] = []
            for event in (trigger.events or []):
                try:
                    result = self._handle_event(event)
                    if result:
                        created.append(result)
                except Exception:
                    logger.exception("MarketingAgent error handling event %s", event.event_type)
                finally:
                    self.mark_consumed(str(event.id))
            results["drafts_created"] = created

        # Scheduled / manual: scan LinkedIn trends
        if trigger.type in (TriggerType.SCHEDULED, TriggerType.USER_REQUEST):
            trends = self.scan_trends()
            results["trends_found"] = len(trends)

        return results

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        pass  # writes go directly to DB per operation

    # ── Trend Scanning ──────────────────────────────��─────────────────────────

    def scan_trends(self) -> list[dict[str, Any]]:
        """
        Search LinkedIn for posts relevant to our product and audience.
        Score each with LLM, store high-relevance hits, emit events for top ones.
        """
        ctx = self._global_context
        if not ctx:
            logger.warning("MarketingAgent: no global context — skipping trend scan")
            return []

        cp = ctx.company_profile
        tc = ctx.target_customer
        pain_points = list(tc.pain_points) if tc.pain_points else []
        keywords = pain_points[:]
        if cp.name:
            keywords.append(cp.name)
        if cp.product_name:
            keywords.append(cp.product_name)

        if not keywords:
            logger.info("MarketingAgent: no keywords to scan — add product name/pain points to context")
            return []

        raw_results = tools.search_linkedin(keywords, hours=24)
        if not raw_results:
            logger.info("MarketingAgent: LinkedIn trend scan found 0 results")
            return []

        product_description = cp.product_description or cp.product_name or "our product"
        stored_trends: list[dict[str, Any]] = []

        for post in raw_results:
            try:
                scored = self._score_relevance(post, product_description, pain_points)
            except Exception:
                logger.exception("Failed to score post: %s", post.get("url", "?"))
                continue

            score = scored.get("relevance_score", 0)
            if score < RELEVANCE_STORE_THRESHOLD:
                continue

            trend_row = tools.store_trend({
                "platform":         post.get("platform", "linkedin"),
                "url":              post.get("url"),
                "author":           post.get("author"),
                "content":          post.get("content", ""),
                "topic":            scored.get("topic", ""),
                "relevance_score":  score,
                "relevance_reason": scored.get("reason", ""),
                "suggested_action": scored.get("suggested_action"),
            })
            stored_trends.append(trend_row)

            if score >= RELEVANCE_NOTIFY_THRESHOLD:
                priority = "high" if score > 90 else "medium"
                topic = scored.get("topic", "relevant conversation")
                self.emit_event(
                    event_type="marketing.trend_found",
                    payload={
                        "platform":         "linkedin",
                        "topic":            topic,
                        "url":              post.get("url"),
                        "relevance_score":  score,
                        "suggested_action": scored.get("suggested_action"),
                    },
                    summary=f"LinkedIn trend found: '{topic}' (relevance: {score})",
                    priority=priority,
                )
                self.send_notification(
                    title=f"LinkedIn trend: {topic}",
                    body=(
                        f"Relevance {score}/100. "
                        f"Suggested action: {scored.get('suggested_action', 'engage')}. "
                        f"URL: {post.get('url', 'N/A')}"
                    ),
                    priority=priority,
                )

        logger.info("MarketingAgent trend scan complete — stored %d trends", len(stored_trends))
        return stored_trends

    def _score_relevance(
        self,
        post: dict[str, Any],
        product_description: str,
        pain_points: list[str],
    ) -> dict[str, Any]:
        raw = self.llm_chat(
            system_prompt=(
                "You are a marketing analyst. Score social media posts for relevance "
                "to our product. Respond ONLY with valid JSON."
            ),
            user_message=(
                f"Our product: {product_description}.\n"
                f"Target pain points: {', '.join(pain_points)}.\n\n"
                f"Post: {post.get('content', '')}\n\n"
                f'Respond as JSON: {{"relevance_score": <int 0-100>, "reason": "<str>", '
                f'"topic": "<short topic>", "suggested_action": "<reply|quote|new_post|none>"}}'
            ),
            temperature=0.2,
        )
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group()) if match else {"relevance_score": 0}

    # ── Content Drafting ─────���─────────────────────────────────────────��──────

    def draft_content(
        self,
        content_type: str,
        platform: str = "linkedin",
        trend_id: str | None = None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """
        Draft a LinkedIn post and queue it for approval.
        Returns the stored draft row with approval_id.
        """
        ctx = self._global_context
        cp = ctx.company_profile if ctx else None
        bv = ctx.brand_voice if ctx else None

        product_name   = (cp.product_name or cp.name or "our product") if cp else "our product"
        brand_voice    = (bv.tone or "professional and approachable") if bv else "professional and approachable"
        product_desc   = (cp.product_description or "") if cp else ""
        char_limit     = tools.PLATFORM_CHAR_LIMITS.get(platform, 3000)

        trend_context = ""
        if trend_id:
            trend = tools.get_trend(trend_id)
            if trend:
                trend_context = (
                    f"Respond to this LinkedIn post naturally (don't be promotional): "
                    f"{trend.get('original_content', '')}"
                )

        draft_text = self.llm_chat(
            system_prompt=(
                f"You are the LinkedIn voice for {product_name}. "
                f"Brand voice: {brand_voice}. "
                f"Sound human, never overly promotional. "
                f"Product: {product_desc}\n\n"
                "CRITICAL FORMATTING RULES — follow exactly:\n"
                "- Output ONLY the post text, nothing else\n"
                "- NO markdown: no **, no *, no ---, no backticks, no headers\n"
                "- Use plain text and blank lines for structure\n"
                "- Hashtags use # prefix (e.g. #golf not hashtag#golf)\n"
                "- NO meta-commentary, word counts, suggestions, or labels\n"
                "- The output is pasted directly into LinkedIn as-is"
            ),
            user_message=(
                f"Platform: LinkedIn. Content type: {content_type}.\n"
                f"{trend_context}\n"
                f"{'Topic: ' + topic if topic else ''}\n"
                f"Keep it under {char_limit} characters. Sound human and genuine."
            ),
            temperature=0.8,
        )

        row = tools.store_content({
            "platform":     platform,
            "content":      draft_text,   # maps to 'body' column in store_content
            "content_type": content_type,
        })

        try:
            create_approval(
                agent=self.name,
                action_type="publish_post",
                content={
                    "content_id":   str(row["id"]),
                    "platform":     platform,
                    "content_type": content_type,
                    "draft":        draft_text,
                    "topic":        topic or "",
                    "trend_id":     trend_id or "",
                },
            )
            tools.update_content_status(row["id"], "pending_approval")
            row["status"] = "pending_approval"
        except Exception:
            logger.warning("MarketingAgent: failed to create approval for post %s", row.get("id"))

        self.send_notification(
            title=f"LinkedIn draft ready for review",
            body=f"{content_type} post about: {topic or 'product update'}",
            priority="medium",
        )

        return row

    # ── Publishing ──────────���─────────────────────────────────────────────────

    def _execute_approved_publish(self, content_id: str, content: dict[str, Any]) -> dict[str, Any]:
        """Called when user approves a post. Publishes to LinkedIn."""
        content_row = tools.get_content(content_id)
        if not content_row:
            logger.error("MarketingAgent: content %s not found for publishing", content_id)
            return {"error": "content not found"}

        platform = content_row.get("platform", "linkedin")
        text = content_row.get("body", "")

        try:
            result = tools.post_to_linkedin(text)
        except NotImplementedError:
            logger.warning("LinkedIn not configured — dry run")
            result = {"platform_post_id": "dry-run", "url": ""}
        except Exception:
            logger.exception("Failed to publish content %s", content_id)
            tools.update_content_status(content_id, "rejected")
            return {"error": "publish failed"}

        published_url = result.get("url", "")
        tools.update_content_status(
            content_id,
            "published",
            published_url=published_url,
            published_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        )

        topic = content_row.get("topic", "content")
        self.emit_event(
            event_type="marketing.content_published",
            payload={"platform": platform, "topic": topic, "url": published_url},
            summary=f"Published LinkedIn post: {topic}",
            priority="low",
        )
        self.send_notification(
            title="LinkedIn post published",
            body=f"'{topic}' is now live. {published_url}",
            priority="medium",
        )

        return {"content_id": content_id, "status": "published", "url": published_url}

    # ── Event Handlers ──────────���─────────────────────────────────────────────

    def _handle_event(self, event: Any) -> dict[str, Any] | None:
        handlers = {
            "feature_shipped":    self._on_feature_shipped,
            "research_completed": self._on_research_completed,
        }
        handler = handlers.get(event.event_type)
        return handler(event, event.payload or {}) if handler else None

    def _on_feature_shipped(self, event: Any, p: dict) -> dict | None:
        feature_name = p.get("feature") or p.get("name", "new feature")
        try:
            return self.draft_content(
                content_type="announcement",
                platform="linkedin",
                topic=f"New feature shipped: {feature_name}",
            )
        except Exception:
            logger.exception("MarketingAgent: failed to draft announcement for %s", feature_name)
            return None

    def _on_research_completed(self, event: Any, p: dict) -> None:
        finding_type = p.get("finding_type", "")
        if finding_type not in ("competitor", "trend", "market"):
            return None
        insights = p.get("insights") or p.get("summary", "")
        if insights:
            self.send_notification(
                title="Research insight for LinkedIn messaging",
                body=f"Type: {finding_type}. {str(insights)[:300]}",
                priority="low",
            )
        return None
