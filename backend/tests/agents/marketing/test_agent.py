"""
Unit tests for app.agents.marketing.agent.MarketingAgent.

All external dependencies (LLM, DB, events, notifications, approvals)
are mocked so tests are deterministic and fast.

Tests cover:
  1. Trend scanning — scoring, thresholds, event emission, notification
  2. Content drafting — LLM call, approval creation, status update
  3. Publishing — platform delegation, dry-run fallback, event emission
  4. Event consumption — feature_shipped, research_completed, reply_received
  5. run() entry point — trigger routing
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.marketing.agent import (
    MarketingAgent,
    RELEVANCE_STORE_THRESHOLD,
    RELEVANCE_NOTIFY_THRESHOLD,
)
from app.schemas.context import GlobalContext
from tests.conftest import make_global_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(**overrides: Any) -> GlobalContext:
    """Build a GlobalContext object from make_global_context dict."""
    return GlobalContext(**make_global_context(**overrides))


def _make_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> MagicMock:
    """Build a fake Event object."""
    e = MagicMock()
    e.id = uuid.UUID(event_id) if event_id else uuid.uuid4()
    e.event_type = event_type
    e.payload = payload or {}
    e.summary = f"Test event: {event_type}"
    e.source_agent = "test"
    return e


# ---------------------------------------------------------------------------
# MarketingAgent class-level attributes
# ---------------------------------------------------------------------------

class TestAgentMetadata:
    def test_name(self):
        agent = MarketingAgent()
        assert agent.name == "marketing"

    def test_description_is_nonempty(self):
        agent = MarketingAgent()
        assert len(agent.description) > 10

    def test_subscribed_events(self):
        agent = MarketingAgent()
        assert "feature_shipped" in agent.subscribed_events
        assert "research_completed" in agent.subscribed_events
        assert "reply_received" in agent.subscribed_events


# ============================================================================
# 1. Trend Scanning
# ============================================================================

class TestScanTrends:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_context(self, mock_get_global_context):
        """If global context isn't seeded, return empty."""
        mock_get_global_context.return_value = None
        agent = MarketingAgent()
        result = await agent.scan_trends()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_search_results(
        self, mock_get_global_context, mock_search_all_platforms
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = []

        agent = MarketingAgent()
        result = await agent.scan_trends()
        assert result == []
        mock_search_all_platforms.assert_called_once()

    @pytest.mark.asyncio
    async def test_filters_below_threshold(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
        mock_store_trend,
        mock_emit_event,
        mock_notify,
    ):
        """Posts scoring below 60 should not be stored."""
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = [
            {"platform": "x", "content": "irrelevant post", "url": "https://x.com/1"}
        ]
        mock_llm.return_value = json.dumps({
            "relevance_score": 30,
            "reason": "Not relevant",
            "topic": "unrelated",
            "suggested_action": "none",
        })

        agent = MarketingAgent()
        result = await agent.scan_trends()
        assert result == []
        mock_store_trend.assert_not_called()
        mock_emit_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_trend_above_threshold(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
        mock_store_trend,
        mock_emit_event,
        mock_notify,
    ):
        """Posts scoring 60-79 are stored but no event/notification."""
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = [
            {"platform": "reddit", "content": "relevant post", "url": "https://reddit.com/1"}
        ]
        mock_llm.return_value = json.dumps({
            "relevance_score": 65,
            "reason": "Somewhat relevant",
            "topic": "code reviews",
            "suggested_action": "reply",
        })

        agent = MarketingAgent()
        result = await agent.scan_trends()
        assert len(result) == 1
        mock_store_trend.assert_called_once()
        mock_emit_event.assert_not_called()
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_emits_event_and_notifies_above_80(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
        mock_store_trend,
        mock_emit_event,
        mock_notify,
    ):
        """Posts scoring >= 80 trigger event + notification."""
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = [
            {"platform": "x", "content": "great post", "url": "https://x.com/hot"}
        ]
        mock_llm.return_value = json.dumps({
            "relevance_score": 85,
            "reason": "Highly relevant",
            "topic": "AI code review",
            "suggested_action": "reply",
        })

        agent = MarketingAgent()
        result = await agent.scan_trends()
        assert len(result) == 1

        mock_emit_event.assert_called_once()
        call_kwargs = mock_emit_event.call_args.kwargs
        assert call_kwargs["event_type"] == "marketing.trend_found"
        assert call_kwargs["payload"]["relevance_score"] == 85
        assert call_kwargs["priority"] == "medium"

        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_priority_for_score_above_90(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
        mock_store_trend,
        mock_emit_event,
        mock_notify,
    ):
        """Scores > 90 should get 'high' priority."""
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = [
            {"platform": "x", "content": "viral post", "url": "https://x.com/viral"}
        ]
        mock_llm.return_value = json.dumps({
            "relevance_score": 95,
            "reason": "Extremely relevant",
            "topic": "AI code review revolution",
            "suggested_action": "quote",
        })

        agent = MarketingAgent()
        await agent.scan_trends()

        call_kwargs = mock_emit_event.call_args.kwargs
        assert call_kwargs["priority"] == "high"

    @pytest.mark.asyncio
    async def test_continues_on_scoring_error(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
        mock_store_trend,
        mock_emit_event,
        mock_notify,
    ):
        """If LLM scoring fails for one post, others still get processed."""
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = [
            {"platform": "x", "content": "bad post", "url": "https://x.com/1"},
            {"platform": "x", "content": "good post", "url": "https://x.com/2"},
        ]
        # First call raises, second returns valid JSON
        mock_llm.side_effect = [
            Exception("LLM error"),
            json.dumps({
                "relevance_score": 70,
                "reason": "Relevant",
                "topic": "testing",
                "suggested_action": "reply",
            }),
        ]

        agent = MarketingAgent()
        result = await agent.scan_trends()
        assert len(result) == 1
        mock_store_trend.assert_called_once()

    @pytest.mark.asyncio
    async def test_keywords_include_pain_points_and_company_name(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
    ):
        """Keywords should be built from pain_points + company name."""
        mock_get_global_context.return_value = _make_ctx()
        mock_search_all_platforms.return_value = []

        agent = MarketingAgent()
        await agent.scan_trends()

        call_args = mock_search_all_platforms.call_args
        keywords = call_args[0][0]  # first positional arg
        assert "TestCo" in keywords
        assert "slow code reviews" in keywords


# ============================================================================
# 2. _score_relevance
# ============================================================================

class TestScoreRelevance:
    @pytest.mark.asyncio
    async def test_returns_parsed_json(self, mock_llm):
        mock_llm.return_value = json.dumps({
            "relevance_score": 75,
            "reason": "test",
            "topic": "topic",
            "suggested_action": "reply",
        })
        agent = MarketingAgent()
        result = await agent._score_relevance(
            {"content": "post text"},
            "product desc",
            ["pain1"],
        )
        assert result["relevance_score"] == 75
        assert result["suggested_action"] == "reply"

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json(self, mock_llm):
        mock_llm.return_value = "not valid json"
        agent = MarketingAgent()
        with pytest.raises(json.JSONDecodeError):
            await agent._score_relevance({"content": "test"}, "desc", [])

    @pytest.mark.asyncio
    async def test_calls_llm_with_low_temperature(self, mock_llm):
        mock_llm.return_value = json.dumps({"relevance_score": 50, "reason": "", "topic": "", "suggested_action": "none"})
        agent = MarketingAgent()
        await agent._score_relevance({"content": "test"}, "desc", ["pain"])
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["temperature"] == 0.3


# ============================================================================
# 3. Content Drafting
# ============================================================================

class TestDraftContent:
    @pytest.mark.asyncio
    async def test_raises_when_no_context(self, mock_get_global_context):
        mock_get_global_context.return_value = None
        agent = MarketingAgent()
        with pytest.raises(RuntimeError, match="Global context not seeded"):
            await agent.draft_content("announcement", "x", topic="test")

    @pytest.mark.asyncio
    async def test_drafts_with_topic(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_llm.return_value = "Here is a great tweet about AI code review!"

        agent = MarketingAgent()
        result = await agent.draft_content("announcement", "x", topic="AI code review")

        assert result["status"] == "pending_approval"
        assert "approval_id" in result
        mock_llm.assert_called_once()
        mock_store_content.assert_called_once()
        mock_request_approval.assert_called_once()

        # Verify approval content includes the draft
        approval_content = mock_request_approval.call_args.kwargs["content"]
        assert approval_content["draft"] == "Here is a great tweet about AI code review!"
        assert approval_content["platform"] == "x"

    @pytest.mark.asyncio
    async def test_drafts_with_trend_id(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_get_trend.return_value = {
            "id": "trend-1",
            "post_content": "Original post about code review tools",
            "platform": "reddit",
        }
        mock_llm.return_value = "Natural reply to the conversation"

        agent = MarketingAgent()
        result = await agent.draft_content("reply", "reddit", trend_id="trend-1")

        mock_get_trend.assert_called_once_with("trend-1")
        # LLM prompt should include the trend content
        llm_messages = mock_llm.call_args.kwargs["messages"]
        assert "Original post about code review tools" in llm_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_uses_correct_char_limit_for_x(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_llm.return_value = "short tweet"

        agent = MarketingAgent()
        await agent.draft_content("engagement", "x", topic="test")

        llm_messages = mock_llm.call_args.kwargs["messages"]
        assert "280" in llm_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_uses_correct_char_limit_for_linkedin(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_llm.return_value = "linkedin post"

        agent = MarketingAgent()
        await agent.draft_content("thought_leadership", "linkedin", topic="test")

        llm_messages = mock_llm.call_args.kwargs["messages"]
        assert "3000" in llm_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_brand_voice_in_system_prompt(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_llm.return_value = "branded content"

        agent = MarketingAgent()
        await agent.draft_content("announcement", "x", topic="test")

        system_prompt = mock_llm.call_args.kwargs["system"]
        assert "friendly, technical, no-BS" in system_prompt
        assert "TestCo" in system_prompt


# ============================================================================
# 4. Publishing
# ============================================================================

class TestPublish:
    @pytest.mark.asyncio
    async def test_raises_when_content_not_found(self, mock_get_content, mock_emit_event):
        mock_get_content.return_value = None
        agent = MarketingAgent()
        with pytest.raises(ValueError, match="not found"):
            await agent.publish("nonexistent-id")

    @pytest.mark.asyncio
    async def test_dry_run_on_not_implemented(
        self,
        mock_get_content,
        mock_publish_to_platform,
        mock_update_content_status,
        mock_emit_event,
    ):
        """When platform posting raises NotImplementedError, uses dry-run fallback."""
        mock_get_content.return_value = {
            "id": "c1",
            "platform": "x",
            "content": "tweet text",
            "topic": "test topic",
            "content_type": "announcement",
        }
        mock_publish_to_platform.side_effect = NotImplementedError("not configured")

        agent = MarketingAgent()
        result = await agent.publish("c1")

        mock_update_content_status.assert_called_once()
        call_args = mock_update_content_status.call_args
        assert call_args[0][1] == "published"  # status arg

        mock_emit_event.assert_called_once()
        assert mock_emit_event.call_args.kwargs["event_type"] == "marketing.content_published"

    @pytest.mark.asyncio
    async def test_successful_publish(
        self,
        mock_get_content,
        mock_publish_to_platform,
        mock_update_content_status,
        mock_emit_event,
    ):
        mock_get_content.return_value = {
            "id": "c2",
            "platform": "linkedin",
            "content": "post text",
            "topic": "launch",
            "content_type": "announcement",
        }
        mock_publish_to_platform.return_value = {
            "platform_post_id": "li-123",
            "url": "https://linkedin.com/post/li-123",
        }

        agent = MarketingAgent()
        result = await agent.publish("c2")

        mock_publish_to_platform.assert_called_once_with("linkedin", "post text")
        mock_emit_event.assert_called_once()
        payload = mock_emit_event.call_args.kwargs["payload"]
        assert payload["url"] == "https://linkedin.com/post/li-123"
        assert payload["platform"] == "linkedin"

    @pytest.mark.asyncio
    async def test_raises_on_generic_publish_error(
        self,
        mock_get_content,
        mock_publish_to_platform,
        mock_update_content_status,
        mock_emit_event,
    ):
        """Generic exceptions (not NotImplementedError) should propagate."""
        mock_get_content.return_value = {
            "id": "c3",
            "platform": "x",
            "content": "text",
            "topic": "test",
            "content_type": "post",
        }
        mock_publish_to_platform.side_effect = RuntimeError("API down")

        agent = MarketingAgent()
        with pytest.raises(RuntimeError, match="API down"):
            await agent.publish("c3")


# ============================================================================
# 5. Event Consumption
# ============================================================================

class TestExecute:
    @pytest.mark.asyncio
    async def test_processes_no_events(self, mock_get_unconsumed_events, mock_mark_consumed):
        mock_get_unconsumed_events.return_value = []
        agent = MarketingAgent()
        await agent.execute()
        mock_mark_consumed.assert_not_called()

    @pytest.mark.asyncio
    async def test_marks_events_consumed_even_on_error(
        self, mock_get_unconsumed_events, mock_mark_consumed
    ):
        """Events should be marked consumed even if handler raises."""
        bad_event = _make_event("feature_shipped", {"feature": "test"})
        mock_get_unconsumed_events.return_value = [bad_event]

        agent = MarketingAgent()
        # Patch _handle_event to raise
        with patch.object(agent, "_handle_event", new_callable=AsyncMock, side_effect=Exception("boom")):
            await agent.execute()

        mock_mark_consumed.assert_called_once_with(str(bad_event.id), "marketing")

    @pytest.mark.asyncio
    async def test_routes_to_correct_handler(
        self, mock_get_unconsumed_events, mock_mark_consumed
    ):
        events = [
            _make_event("feature_shipped", {"feature": "auth"}),
            _make_event("research_completed", {"finding_type": "competitor", "summary": "x"}),
            _make_event("reply_received", {"sentiment": "positive", "source_agent": "marketing"}),
        ]
        mock_get_unconsumed_events.return_value = events

        agent = MarketingAgent()
        with patch.object(agent, "_on_feature_shipped", new_callable=AsyncMock) as m1:
            with patch.object(agent, "_on_research_completed", new_callable=AsyncMock) as m2:
                with patch.object(agent, "_on_reply_received", new_callable=AsyncMock) as m3:
                    await agent.execute()

        m1.assert_called_once()
        m2.assert_called_once()
        m3.assert_called_once()
        assert mock_mark_consumed.call_count == 3


class TestOnFeatureShipped:
    @pytest.mark.asyncio
    async def test_drafts_for_each_channel(
        self, mock_get_global_context, mock_get_trend, mock_llm,
        mock_store_content, mock_request_approval, mock_update_content_status,
    ):
        ctx = _make_ctx()
        mock_get_global_context.return_value = ctx
        mock_llm.return_value = "Feature announcement draft"

        event = _make_event("feature_shipped", {"feature": "Dark Mode"})
        agent = MarketingAgent()
        await agent._on_feature_shipped(event)

        # Should draft for reddit, x, linkedin (3 channels from default context)
        assert mock_store_content.call_count == 3
        assert mock_request_approval.call_count == 3

    @pytest.mark.asyncio
    async def test_uses_feature_name_from_payload(
        self, mock_get_global_context, mock_get_trend, mock_llm,
        mock_store_content, mock_request_approval, mock_update_content_status,
    ):
        mock_get_global_context.return_value = _make_ctx()
        mock_llm.return_value = "Announcement"

        event = _make_event("feature_shipped", {"name": "SSO Support"})
        agent = MarketingAgent()
        await agent._on_feature_shipped(event)

        # Check that topic includes the feature name
        first_call = mock_store_content.call_args_list[0]
        stored = first_call[0][0]  # first positional arg (dict)
        assert "SSO Support" in stored.get("topic", "")

    @pytest.mark.asyncio
    async def test_skips_unsupported_channels(
        self, mock_get_global_context, mock_get_trend, mock_llm,
        mock_store_content, mock_request_approval, mock_update_content_status,
    ):
        ctx = _make_ctx(target_customer={
            "channels": ["x", "tiktok", "mastodon"],
            "pain_points": [],
        })
        mock_get_global_context.return_value = ctx
        mock_llm.return_value = "Draft"

        event = _make_event("feature_shipped", {"feature": "test"})
        agent = MarketingAgent()
        await agent._on_feature_shipped(event)

        # Only "x" is supported, tiktok/mastodon should be skipped
        assert mock_store_content.call_count == 1


class TestOnResearchCompleted:
    @pytest.mark.asyncio
    async def test_notifies_for_competitor_insight(self, mock_notify):
        event = _make_event("research_completed", {
            "finding_type": "competitor",
            "summary": "CompetitorX launched a new feature",
        })
        agent = MarketingAgent()
        await agent._on_research_completed(event)
        mock_notify.assert_called_once()
        assert "Research insight" in mock_notify.call_args.kwargs["title"]

    @pytest.mark.asyncio
    async def test_ignores_non_marketing_finding_types(self, mock_notify):
        event = _make_event("research_completed", {
            "finding_type": "lead",
            "summary": "Found a new lead",
        })
        agent = MarketingAgent()
        await agent._on_research_completed(event)
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_insights(self, mock_notify):
        event = _make_event("research_completed", {
            "finding_type": "competitor",
            "summary": "",
        })
        agent = MarketingAgent()
        await agent._on_research_completed(event)
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_trend_finding_type(self, mock_notify):
        event = _make_event("research_completed", {
            "finding_type": "trend",
            "insights": "Growing interest in AI linting tools",
        })
        agent = MarketingAgent()
        await agent._on_research_completed(event)
        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_market_finding_type(self, mock_notify):
        event = _make_event("research_completed", {
            "finding_type": "market",
            "insights": "TAM estimated at $2B",
        })
        agent = MarketingAgent()
        await agent._on_research_completed(event)
        mock_notify.assert_called_once()


class TestOnReplyReceived:
    @pytest.mark.asyncio
    async def test_flags_negative_reply_from_marketing(self, mock_notify):
        event = _make_event("reply_received", {
            "sentiment": "negative",
            "source_agent": "marketing",
            "platform": "x",
            "reply_text": "This product is terrible",
        })
        agent = MarketingAgent()
        await agent._on_reply_received(event)

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["priority"] == "high"
        assert "Negative reply" in mock_notify.call_args.kwargs["title"]

    @pytest.mark.asyncio
    async def test_ignores_positive_reply(self, mock_notify):
        event = _make_event("reply_received", {
            "sentiment": "positive",
            "source_agent": "marketing",
        })
        agent = MarketingAgent()
        await agent._on_reply_received(event)
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_reply_from_other_agent(self, mock_notify):
        event = _make_event("reply_received", {
            "sentiment": "negative",
            "source_agent": "outreach",
        })
        agent = MarketingAgent()
        await agent._on_reply_received(event)
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_neutral_reply(self, mock_notify):
        event = _make_event("reply_received", {
            "sentiment": "neutral",
            "source_agent": "marketing",
        })
        agent = MarketingAgent()
        await agent._on_reply_received(event)
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_source_agent(self, mock_notify):
        event = _make_event("reply_received", {
            "sentiment": "negative",
        })
        agent = MarketingAgent()
        await agent._on_reply_received(event)
        mock_notify.assert_not_called()


# ============================================================================
# 6. run() entry point
# ============================================================================

class TestRun:
    @pytest.mark.asyncio
    async def test_scheduled_trigger_runs_scan_and_execute(self):
        agent = MarketingAgent()
        with patch.object(agent, "scan_trends", new_callable=AsyncMock, return_value=[]) as scan:
            with patch.object(agent, "execute", new_callable=AsyncMock) as execute:
                result = await agent.run({"type": "scheduled", "agent": "marketing"})

        scan.assert_called_once()
        execute.assert_called_once()
        assert result["status"] == "completed"
        assert result["trends_found"] == 0

    @pytest.mark.asyncio
    async def test_manual_trigger_runs_scan_and_execute(self):
        agent = MarketingAgent()
        with patch.object(agent, "scan_trends", new_callable=AsyncMock, return_value=[{"id": "1"}]) as scan:
            with patch.object(agent, "execute", new_callable=AsyncMock) as execute:
                result = await agent.run({"type": "manual"})

        scan.assert_called_once()
        execute.assert_called_once()
        assert result["trends_found"] == 1

    @pytest.mark.asyncio
    async def test_user_trigger_runs_scan_and_execute(self):
        agent = MarketingAgent()
        with patch.object(agent, "scan_trends", new_callable=AsyncMock, return_value=[]) as scan:
            with patch.object(agent, "execute", new_callable=AsyncMock) as execute:
                result = await agent.run({"type": "user"})

        scan.assert_called_once()
        execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_trigger_skips_scan(self):
        agent = MarketingAgent()
        with patch.object(agent, "scan_trends", new_callable=AsyncMock) as scan:
            with patch.object(agent, "execute", new_callable=AsyncMock) as execute:
                result = await agent.run({"type": "event"})

        scan.assert_not_called()
        execute.assert_called_once()
        assert "trends_found" not in result

    @pytest.mark.asyncio
    async def test_none_trigger_defaults_to_manual(self):
        agent = MarketingAgent()
        with patch.object(agent, "scan_trends", new_callable=AsyncMock, return_value=[]) as scan:
            with patch.object(agent, "execute", new_callable=AsyncMock):
                result = await agent.run(None)

        scan.assert_called_once()
        assert result["trigger"] == "manual"

    @pytest.mark.asyncio
    async def test_empty_trigger_defaults_to_manual(self):
        agent = MarketingAgent()
        with patch.object(agent, "scan_trends", new_callable=AsyncMock, return_value=[]) as scan:
            with patch.object(agent, "execute", new_callable=AsyncMock):
                result = await agent.run({})

        scan.assert_called_once()
        assert result["trigger"] == "manual"
