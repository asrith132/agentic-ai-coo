"""
End-to-end workflow tests for the marketing agent.

These tests verify complete multi-step workflows with all internal
coordination (agent -> tools -> DB -> events -> approvals) mocked
at the boundary layer.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.marketing.agent import MarketingAgent
from app.schemas.context import GlobalContext
from tests.conftest import make_global_context


def _ctx(**kw: Any) -> GlobalContext:
    return GlobalContext(**make_global_context(**kw))


# ============================================================================
# Workflow 1: Full scan → score → store → notify cycle
# ============================================================================

class TestScanToNotifyWorkflow:
    """
    Simulates: search platforms → LLM scores posts → high-score stored →
    event emitted → notification sent.
    """

    @pytest.mark.asyncio
    async def test_full_scan_workflow(
        self,
        mock_get_global_context,
        mock_search_all_platforms,
        mock_llm,
        mock_store_trend,
        mock_emit_event,
        mock_notify,
    ):
        mock_get_global_context.return_value = _ctx()

        # Simulate 3 posts: one low, one medium, one high relevance
        mock_search_all_platforms.return_value = [
            {"platform": "reddit", "content": "irrelevant meme", "url": "https://r.com/1"},
            {"platform": "x", "content": "code review discussion", "url": "https://x.com/2"},
            {"platform": "linkedin", "content": "AI code tools are amazing", "url": "https://li.com/3"},
        ]

        mock_llm.side_effect = [
            json.dumps({"relevance_score": 20, "reason": "Off topic", "topic": "memes", "suggested_action": "none"}),
            json.dumps({"relevance_score": 70, "reason": "Related", "topic": "code reviews", "suggested_action": "reply"}),
            json.dumps({"relevance_score": 92, "reason": "Direct match", "topic": "AI code tools", "suggested_action": "quote"}),
        ]

        agent = MarketingAgent()
        trends = await agent.scan_trends()

        # Post 1 (score 20): filtered out — not stored
        # Post 2 (score 70): stored, no event/notification
        # Post 3 (score 92): stored + event + notification
        assert len(trends) == 2
        assert mock_store_trend.call_count == 2

        # Only score >= 80 triggers event + notification
        mock_emit_event.assert_called_once()
        assert mock_emit_event.call_args.kwargs["priority"] == "high"  # >90

        mock_notify.assert_called_once()
        assert "AI code tools" in mock_notify.call_args.kwargs["title"]


# ============================================================================
# Workflow 2: Draft → approve → publish cycle
# ============================================================================

class TestDraftToPublishWorkflow:
    """
    Simulates: draft content → store draft → create approval →
    (approval granted) → publish to platform → emit event.
    """

    @pytest.mark.asyncio
    async def test_full_draft_approve_publish(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
        mock_get_content,
        mock_publish_to_platform,
        mock_emit_event,
    ):
        content_id = str(uuid.uuid4())
        approval_id = uuid.uuid4()

        mock_get_global_context.return_value = _ctx()
        mock_llm.return_value = "Check out our blazing fast code review tool!"
        mock_request_approval.return_value = MagicMock(id=approval_id)

        # Override store_content to return a row with known id
        async def fake_store(content: dict) -> dict:
            return {"id": content_id, **content}
        mock_store_content.side_effect = fake_store

        agent = MarketingAgent()

        # Step 1: Draft
        draft = await agent.draft_content("announcement", "x", topic="Product launch")
        assert draft["status"] == "pending_approval"
        assert draft["id"] == content_id

        # Step 2: Simulate approval has been granted, now publish
        mock_get_content.return_value = {
            "id": content_id,
            "platform": "x",
            "content": "Check out our blazing fast code review tool!",
            "topic": "Product launch",
            "content_type": "announcement",
        }
        mock_publish_to_platform.return_value = {
            "platform_post_id": "tw-999",
            "url": "https://x.com/status/tw-999",
        }

        published = await agent.publish(content_id)

        mock_publish_to_platform.assert_called_once_with(
            "x", "Check out our blazing fast code review tool!"
        )
        mock_emit_event.assert_called_once()
        assert mock_emit_event.call_args.kwargs["event_type"] == "marketing.content_published"
        assert mock_emit_event.call_args.kwargs["payload"]["url"] == "https://x.com/status/tw-999"


# ============================================================================
# Workflow 3: feature_shipped event → auto-draft for all channels
# ============================================================================

class TestFeatureShippedWorkflow:
    @pytest.mark.asyncio
    async def test_auto_drafts_all_channels(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
        mock_get_unconsumed_events,
        mock_mark_consumed,
    ):
        ctx = _ctx()
        mock_get_global_context.return_value = ctx
        mock_llm.return_value = "Exciting new feature announcement!"

        event = MagicMock()
        event.id = uuid.uuid4()
        event.event_type = "feature_shipped"
        event.payload = {"feature": "Dark Mode"}
        mock_get_unconsumed_events.return_value = [event]

        agent = MarketingAgent()
        await agent.execute()

        # 3 channels → 3 drafts, each with approval
        assert mock_store_content.call_count == 3
        assert mock_request_approval.call_count == 3
        mock_mark_consumed.assert_called_once_with(str(event.id), "marketing")

        # Verify topics mention the feature
        for call in mock_store_content.call_args_list:
            stored = call[0][0]
            assert "Dark Mode" in stored.get("topic", "")


# ============================================================================
# Workflow 4: Mixed event batch processing
# ============================================================================

class TestMixedEventBatch:
    @pytest.mark.asyncio
    async def test_processes_mixed_events(
        self,
        mock_get_global_context,
        mock_get_trend,
        mock_llm,
        mock_store_content,
        mock_request_approval,
        mock_update_content_status,
        mock_get_unconsumed_events,
        mock_mark_consumed,
        mock_notify,
    ):
        mock_get_global_context.return_value = _ctx()
        mock_llm.return_value = "Draft content"

        e1 = MagicMock()
        e1.id = uuid.uuid4()
        e1.event_type = "feature_shipped"
        e1.payload = {"feature": "SSO"}

        e2 = MagicMock()
        e2.id = uuid.uuid4()
        e2.event_type = "research_completed"
        e2.payload = {"finding_type": "competitor", "summary": "Rival launched SSO too"}

        e3 = MagicMock()
        e3.id = uuid.uuid4()
        e3.event_type = "reply_received"
        e3.payload = {"sentiment": "negative", "source_agent": "marketing", "platform": "x", "reply_text": "Not great"}

        mock_get_unconsumed_events.return_value = [e1, e2, e3]

        agent = MarketingAgent()
        await agent.execute()

        # All 3 events consumed
        assert mock_mark_consumed.call_count == 3

        # e1: feature_shipped → 3 drafts
        assert mock_store_content.call_count == 3

        # e2: research_completed → 1 notification (insight)
        # e3: reply_received → 1 notification (negative)
        # Total notify calls: 2
        assert mock_notify.call_count == 2
