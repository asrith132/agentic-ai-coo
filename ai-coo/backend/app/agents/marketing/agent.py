"""
agents/marketing/agent.py — MarketingAgent.

Scans social platforms for relevant conversations, drafts content in brand voice,
maintains public presence.

Flagship feature: Live Trend Hunter + Auto-Reply Generator

Subscribed events: feature_shipped, research_completed, reply_received
Emitted events:    marketing.trend_found, marketing.content_published, marketing.engagement_spike

Autonomy rules:
  - Trend scanning: Autonomous
  - Drafting content: Autonomous
  - Publishing: APPROVAL REQUIRED
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.base_agent import BaseAgent
from app.core.context import get_global_context
from app.core.events import emit_event, get_unconsumed_events, mark_consumed
from app.core.approvals import request_approval, get_approval_status
from app.core.notifications import notify
from app.core.llm import call_llm_text
from app.agents.marketing.tools import (
    PLATFORM_CHAR_LIMITS,
    SUPPORTED_PLATFORMS,
    search_all_platforms,
    store_trend,
    get_trend,
    store_content,
    update_content_status,
    get_content,
    publish_to_platform,
)

logger = logging.getLogger(__name__)

RELEVANCE_STORE_THRESHOLD = 60
RELEVANCE_NOTIFY_THRESHOLD = 80


class MarketingAgent:
    """
    Marketing / Content agent for the AI COO system.

    NOTE: BaseAgent.__init__ raises NotImplementedError (stub). This class
    implements its own methods and will inherit from BaseAgent once that is
    wired up in the base-agent prompt. For now it operates standalone.
    """

    name = "marketing"
    description = (
        "Scans social platforms for relevant conversations, "
        "drafts content in brand voice, maintains public presence"
    )
    subscribed_events = ["feature_shipped", "research_completed", "reply_received"]

    # ── 1. Trend Scanning ────────────────────────────────────────────────────

    async def scan_trends(self) -> list[dict[str, Any]]:
        """
        Search all platforms for posts relevant to our product and audience.
        Score each with LLM, store high-relevance hits, emit events for top ones.
        """
        ctx = await get_global_context()
        if ctx is None:
            logger.error("Global context not seeded — cannot scan trends")
            return []

        target = ctx.target_customer or {}
        company = ctx.company_profile or {}
        pain_points = target.get("pain_points", [])
        channels = target.get("channels", SUPPORTED_PLATFORMS)
        product_description = company.get("description", company.get("name", "our product"))

        # Build keyword list from pain points + product name
        keywords = list(pain_points)
        if company.get("name"):
            keywords.append(company["name"])

        raw_results = await search_all_platforms(keywords, hours=24)
        if not raw_results:
            logger.info("Trend scan found 0 raw results")
            return []

        stored_trends: list[dict[str, Any]] = []

        for post in raw_results:
            try:
                scored = await self._score_relevance(post, product_description, pain_points)
            except Exception:
                logger.exception("Failed to score post: %s", post.get("url", "?"))
                continue

            score = scored.get("relevance_score", 0)
            if score < RELEVANCE_STORE_THRESHOLD:
                continue

            trend_row = await store_trend({
                "platform": post.get("platform", "unknown"),
                "url": post.get("url"),
                "author": post.get("author"),
                "content": post.get("content", ""),
                "topic": scored.get("topic", ""),
                "relevance_score": score,
                "relevance_reason": scored.get("reason", ""),
                "suggested_action": scored.get("suggested_action"),
            })
            stored_trends.append(trend_row)

            if score >= RELEVANCE_NOTIFY_THRESHOLD:
                priority = "high" if score > 90 else "medium"
                topic = scored.get("topic", "relevant conversation")

                await emit_event(
                    source_agent=self.name,
                    event_type="marketing.trend_found",
                    payload={
                        "platform": post.get("platform"),
                        "topic": topic,
                        "url": post.get("url"),
                        "relevance_score": score,
                        "suggested_action": scored.get("suggested_action"),
                    },
                    summary=(
                        f"Found relevant conversation on {post.get('platform')}: "
                        f"'{topic}' (relevance: {score})"
                    ),
                    priority=priority,
                )

                await notify(
                    agent=self.name,
                    title=f"Trending: {topic}",
                    body=(
                        f"Relevance {score}/100 on {post.get('platform')}. "
                        f"Suggested action: {scored.get('suggested_action', 'engage')}. "
                        f"URL: {post.get('url', 'N/A')}"
                    ),
                    priority=priority,
                )

        logger.info("Trend scan complete — stored %d trends", len(stored_trends))
        return stored_trends

    async def _score_relevance(
        self,
        post: dict[str, Any],
        product_description: str,
        pain_points: list[str],
    ) -> dict[str, Any]:
        """Ask LLM to score a post's relevance and suggest engagement type."""
        system = (
            "You are a marketing analyst. Evaluate social media posts for relevance "
            "to our product and audience. Respond ONLY with valid JSON."
        )
        prompt = (
            f"Our product is {product_description}. "
            f"Our target customer's pain points are: {', '.join(pain_points)}.\n\n"
            f"Score this post's relevance (0-100) and explain why:\n"
            f"Post: {post.get('content', '')}\n\n"
            f"Should we engage? If yes, what type of engagement "
            f"(reply, quote, new_post referencing this)?\n\n"
            f"Respond as JSON: "
            f'{{"relevance_score": <int>, "reason": "<str>", '
            f'"topic": "<short topic>", "suggested_action": "<reply|quote|new_post|none>"}}'
        )
        raw = await call_llm_text(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        return json.loads(raw)

    # ── 2. Content Drafting ──────────────────────────────────────────────────

    async def draft_content(
        self,
        content_type: str,
        platform: str,
        trend_id: str | None = None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """
        Draft content for a given platform and content type.
        Optionally based on a trend or a free-form topic.
        Returns the stored draft row (with approval request created).
        """
        ctx = await get_global_context()
        if ctx is None:
            raise RuntimeError("Global context not seeded")

        company = ctx.company_profile or {}
        brand = ctx.brand_voice or {}
        product_name = company.get("name", "our product")
        brand_voice = brand.get("tone", "professional and approachable")
        key_features = company.get("description", "")
        char_limit = PLATFORM_CHAR_LIMITS.get(platform, 3000)

        trend_context = ""
        if trend_id:
            trend = await get_trend(trend_id)
            if trend:
                trend_context = (
                    f"Respond to this conversation: {trend.get('post_content', '')}. "
                    f"Make it feel natural, not promotional."
                )

        topic_context = ""
        if topic:
            topic_context = f"Write about: {topic}"

        system = (
            f"You are the social media voice for {product_name}. "
            f"Brand voice: {brand_voice}. "
            f"Sound human. Never be overly promotional."
        )
        prompt = (
            f"Platform: {platform}. Content type: {content_type}.\n"
            f"{trend_context}\n"
            f"{topic_context}\n"
            f"Current product features: {key_features}.\n"
            f"Keep it under {char_limit} characters. Sound human."
        )

        draft_text = await call_llm_text(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1024,
        )

        # Store as draft
        row = await store_content({
            "platform": platform,
            "content": draft_text,
            "content_type": content_type,
            "topic": topic or (trend_context[:100] if trend_context else ""),
            "trend_id": trend_id,
        })

        # Create approval request for publishing
        approval = await request_approval(
            agent=self.name,
            action_type="publish_post",
            content={
                "content_id": row["id"],
                "platform": platform,
                "content_type": content_type,
                "draft": draft_text,
                "topic": topic,
                "trend_id": trend_id,
            },
        )

        # Link approval to content row
        await update_content_status(
            row["id"],
            "pending_approval",
            approval_id=str(approval.id),
        )

        row["approval_id"] = str(approval.id)
        row["status"] = "pending_approval"
        return row

    # ── 3. Publishing (triggered on approval) ────────────────────────────────

    async def publish(self, content_id: str) -> dict[str, Any]:
        """
        Publish an approved content piece to its platform.
        Called when an approval is approved.
        """
        content_row = await get_content(content_id)
        if not content_row:
            raise ValueError(f"Content {content_id} not found")

        platform = content_row["platform"]
        text = content_row["content"]

        try:
            result = await publish_to_platform(platform, text)
        except NotImplementedError:
            logger.warning(
                "Publishing to %s not yet configured — marking as published (dry run)",
                platform,
            )
            result = {"platform_post_id": "dry-run", "url": ""}
        except Exception:
            logger.exception("Failed to publish content %s to %s", content_id, platform)
            raise

        published_url = result.get("url", "")
        updated = await update_content_status(
            content_id,
            "published",
            platform_post_id=result.get("platform_post_id", ""),
            published_url=published_url,
            published_at="now()",
        )

        topic = content_row.get("topic", "content")
        content_type = content_row.get("content_type", "post")

        await emit_event(
            source_agent=self.name,
            event_type="marketing.content_published",
            payload={
                "platform": platform,
                "content_type": content_type,
                "topic": topic,
                "url": published_url,
            },
            summary=f"Published {content_type} on {platform}: {topic}",
            priority="low",
        )

        return updated

    # ── 4. Event Consumption ─────────────────────────────────────────────────

    async def execute(self) -> None:
        """
        Main event-consumption loop. Process unconsumed events this agent
        subscribes to.
        """
        events = await get_unconsumed_events(
            consumer_agent=self.name,
            event_types=self.subscribed_events,
        )

        for event in events:
            try:
                await self._handle_event(event)
            except Exception:
                logger.exception("Error handling event %s (%s)", event.id, event.event_type)
            finally:
                await mark_consumed(str(event.id), self.name)

    async def _handle_event(self, event: Any) -> None:
        """Route an event to the appropriate handler."""
        if event.event_type == "feature_shipped":
            await self._on_feature_shipped(event)
        elif event.event_type == "research_completed":
            await self._on_research_completed(event)
        elif event.event_type == "reply_received":
            await self._on_reply_received(event)
        else:
            logger.debug("Ignoring unhandled event type: %s", event.event_type)

    async def _on_feature_shipped(self, event: Any) -> None:
        """Auto-draft announcement posts for each active platform."""
        payload = event.payload or {}
        feature_name = payload.get("feature", payload.get("name", "new feature"))

        ctx = await get_global_context()
        channels = (ctx.target_customer or {}).get("channels", SUPPORTED_PLATFORMS) if ctx else SUPPORTED_PLATFORMS

        for platform in channels:
            if platform not in SUPPORTED_PLATFORMS:
                continue
            try:
                await self.draft_content(
                    content_type="announcement",
                    platform=platform,
                    topic=f"New feature shipped: {feature_name}",
                )
                logger.info("Drafted announcement for %s on %s", feature_name, platform)
            except Exception:
                logger.exception("Failed to draft announcement on %s", platform)

    async def _on_research_completed(self, event: Any) -> None:
        """If research contains market/competitor insights, store for messaging."""
        payload = event.payload or {}
        finding_type = payload.get("finding_type", "")

        if finding_type not in ("competitor", "trend", "market"):
            return

        insights = payload.get("insights") or payload.get("summary", "")
        if not insights:
            return

        logger.info(
            "Storing research insight for marketing messaging: %s",
            str(insights)[:100],
        )

        # Store insight in a notification for the marketing operator to review
        await notify(
            agent=self.name,
            title="Research insight for messaging",
            body=f"Type: {finding_type}. {str(insights)[:500]}",
            priority="low",
        )

    async def _on_reply_received(self, event: Any) -> None:
        """Flag negative replies on marketing-originated contacts for review."""
        payload = event.payload or {}
        sentiment = payload.get("sentiment", "neutral")
        source = payload.get("source_agent", "")

        if source != self.name:
            return

        if sentiment == "negative":
            await notify(
                agent=self.name,
                title="Negative reply on marketing content",
                body=(
                    f"Platform: {payload.get('platform', '?')}. "
                    f"Content: {str(payload.get('reply_text', ''))[:300]}"
                ),
                priority="high",
            )

    # ── Celery-compatible run entry point ────────────────────────────────────

    async def run(self, trigger: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Main entry point called by Celery task or API.

        On scheduled/manual trigger: runs trend scan + event consumption.
        On event trigger: processes the specific event.
        """
        trigger = trigger or {}
        trigger_type = trigger.get("type", "manual")

        results: dict[str, Any] = {"agent": self.name, "trigger": trigger_type}

        if trigger_type in ("scheduled", "manual", "user"):
            trends = await self.scan_trends()
            results["trends_found"] = len(trends)

        # Always consume pending events
        await self.execute()
        results["status"] = "completed"

        return results
