"""
Integration tests for app.api.agents.marketing — FastAPI routes.

Uses httpx AsyncClient with the FastAPI TestClient pattern.
All agent/DB/LLM calls are mocked at the agent or tools layer.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# We need to build a minimal FastAPI app that includes the marketing router.
from fastapi import FastAPI

from app.api.agents.marketing import router

# Build test app
_app = FastAPI()
_app.include_router(router)


@pytest.fixture
def client():
    """Return an httpx AsyncClient bound to the test app."""
    transport = ASGITransport(app=_app)
    return AsyncClient(transport=transport, base_url="http://test")


# ============================================================================
# GET /api/marketing/status
# ============================================================================

class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_returns_agent_metadata(self, client: AsyncClient):
        resp = await client.get("/api/marketing/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "marketing"
        assert data["status"] == "ready"
        assert "feature_shipped" in data["subscribed_events"]


# ============================================================================
# POST /api/marketing/run
# ============================================================================

class TestRunEndpoint:
    @pytest.mark.asyncio
    async def test_run_returns_completed(self, client: AsyncClient):
        with patch("app.api.agents.marketing._agent") as mock_agent:
            mock_agent.run = AsyncMock(return_value={
                "agent": "marketing",
                "trigger": "manual",
                "trends_found": 0,
                "status": "completed",
            })
            resp = await client.post("/api/marketing/run", json={"type": "manual"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_with_no_body(self, client: AsyncClient):
        with patch("app.api.agents.marketing._agent") as mock_agent:
            mock_agent.run = AsyncMock(return_value={"status": "completed"})
            resp = await client.post("/api/marketing/run")

        assert resp.status_code == 200


# ============================================================================
# POST /api/marketing/scan
# ============================================================================

class TestScanEndpoint:
    @pytest.mark.asyncio
    async def test_scan_returns_trends(self, client: AsyncClient):
        fake_trends = [
            {"id": str(uuid.uuid4()), "platform": "x", "relevance_score": 85},
        ]
        with patch("app.api.agents.marketing._agent") as mock_agent:
            mock_agent.scan_trends = AsyncMock(return_value=fake_trends)
            resp = await client.post("/api/marketing/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["trends_found"] == 1
        assert len(data["trends"]) == 1

    @pytest.mark.asyncio
    async def test_scan_returns_empty(self, client: AsyncClient):
        with patch("app.api.agents.marketing._agent") as mock_agent:
            mock_agent.scan_trends = AsyncMock(return_value=[])
            resp = await client.post("/api/marketing/scan")

        assert resp.status_code == 200
        assert resp.json()["trends_found"] == 0


# ============================================================================
# POST /api/marketing/draft
# ============================================================================

class TestDraftEndpoint:
    @pytest.mark.asyncio
    async def test_draft_with_topic(self, client: AsyncClient):
        with patch("app.api.agents.marketing._agent") as mock_agent:
            mock_agent.draft_content = AsyncMock(return_value={
                "id": str(uuid.uuid4()),
                "platform": "x",
                "content": "draft tweet",
                "status": "pending_approval",
            })
            resp = await client.post("/api/marketing/draft", json={
                "content_type": "announcement",
                "platform": "x",
                "topic": "New feature launch",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft_created"
        assert data["content"]["platform"] == "x"

    @pytest.mark.asyncio
    async def test_draft_with_trend_id(self, client: AsyncClient):
        tid = str(uuid.uuid4())
        with patch("app.api.agents.marketing._agent") as mock_agent:
            mock_agent.draft_content = AsyncMock(return_value={
                "id": str(uuid.uuid4()),
                "platform": "reddit",
                "content": "reply draft",
                "status": "pending_approval",
            })
            resp = await client.post("/api/marketing/draft", json={
                "content_type": "reply",
                "platform": "reddit",
                "trend_id": tid,
            })

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_draft_rejects_unsupported_platform(self, client: AsyncClient):
        resp = await client.post("/api/marketing/draft", json={
            "content_type": "announcement",
            "platform": "tiktok",
            "topic": "test",
        })
        assert resp.status_code == 400
        assert "Unsupported platform" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_draft_requires_trend_or_topic(self, client: AsyncClient):
        resp = await client.post("/api/marketing/draft", json={
            "content_type": "announcement",
            "platform": "x",
        })
        assert resp.status_code == 400
        assert "trend_id or topic" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_draft_missing_content_type(self, client: AsyncClient):
        resp = await client.post("/api/marketing/draft", json={
            "platform": "x",
            "topic": "test",
        })
        # Pydantic validation error
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_draft_missing_platform(self, client: AsyncClient):
        resp = await client.post("/api/marketing/draft", json={
            "content_type": "announcement",
            "topic": "test",
        })
        assert resp.status_code == 422


# ============================================================================
# POST /api/marketing/publish
# ============================================================================

class TestPublishEndpoint:
    @pytest.mark.asyncio
    async def test_publish_approved_content(self, client: AsyncClient):
        cid = str(uuid.uuid4())
        aid = str(uuid.uuid4())

        with patch("app.agents.marketing.tools.get_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": cid,
                "platform": "x",
                "content": "tweet",
                "approval_id": aid,
            }
            with patch("app.core.approvals.get_approval_status", new_callable=AsyncMock) as mock_approval:
                mock_approval.return_value = MagicMock(status="approved")
                with patch("app.api.agents.marketing._agent") as mock_agent:
                    mock_agent.publish = AsyncMock(return_value={"id": cid, "status": "published"})
                    resp = await client.post("/api/marketing/publish", json={"content_id": cid})

        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    @pytest.mark.asyncio
    async def test_publish_rejects_unapproved_content(self, client: AsyncClient):
        cid = str(uuid.uuid4())
        aid = str(uuid.uuid4())

        with patch("app.agents.marketing.tools.get_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": cid, "approval_id": aid}
            with patch("app.core.approvals.get_approval_status", new_callable=AsyncMock) as mock_approval:
                mock_approval.return_value = MagicMock(status="pending")
                resp = await client.post("/api/marketing/publish", json={"content_id": cid})

        assert resp.status_code == 403
        assert "not been approved" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_publish_404_when_content_not_found(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            resp = await client.post("/api/marketing/publish", json={"content_id": "nope"})

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_content_without_approval_id(self, client: AsyncClient):
        """Content without approval_id can be published (no gate check)."""
        cid = str(uuid.uuid4())
        with patch("app.agents.marketing.tools.get_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": cid, "platform": "x", "content": "text"}
            with patch("app.api.agents.marketing._agent") as mock_agent:
                mock_agent.publish = AsyncMock(return_value={"id": cid, "status": "published"})
                resp = await client.post("/api/marketing/publish", json={"content_id": cid})

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_publish_rejected_content(self, client: AsyncClient):
        cid = str(uuid.uuid4())
        aid = str(uuid.uuid4())

        with patch("app.agents.marketing.tools.get_content", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": cid, "approval_id": aid}
            with patch("app.core.approvals.get_approval_status", new_callable=AsyncMock) as mock_approval:
                mock_approval.return_value = MagicMock(status="rejected")
                resp = await client.post("/api/marketing/publish", json={"content_id": cid})

        assert resp.status_code == 403


# ============================================================================
# GET /api/marketing/trends
# ============================================================================

class TestTrendsEndpoint:
    @pytest.mark.asyncio
    async def test_list_trends(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_recent_trends", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                {"id": "1", "platform": "x", "relevance_score": 90},
                {"id": "2", "platform": "reddit", "relevance_score": 75},
            ]
            resp = await client.get("/api/marketing/trends")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["trends"]) == 2

    @pytest.mark.asyncio
    async def test_list_trends_with_limit(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_recent_trends", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            resp = await client.get("/api/marketing/trends?limit=5")

        assert resp.status_code == 200
        mock_get.assert_called_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_list_trends_empty(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_recent_trends", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            resp = await client.get("/api/marketing/trends")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ============================================================================
# GET /api/marketing/content
# ============================================================================

class TestContentEndpoint:
    @pytest.mark.asyncio
    async def test_list_content_default_status(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_content_by_status", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [{"id": "1", "status": "draft"}]
            resp = await client.get("/api/marketing/content")

        assert resp.status_code == 200
        mock_get.assert_called_once_with("draft", limit=20)

    @pytest.mark.asyncio
    async def test_list_content_published(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_content_by_status", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            resp = await client.get("/api/marketing/content?status=published")

        assert resp.status_code == 200
        mock_get.assert_called_once_with("published", limit=20)

    @pytest.mark.asyncio
    async def test_list_content_invalid_status(self, client: AsyncClient):
        resp = await client.get("/api/marketing/content?status=deleted")
        assert resp.status_code == 400
        assert "Invalid status" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_content_pending_approval(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_content_by_status", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            resp = await client.get("/api/marketing/content?status=pending_approval")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_content_with_custom_limit(self, client: AsyncClient):
        with patch("app.agents.marketing.tools.get_content_by_status", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            resp = await client.get("/api/marketing/content?status=draft&limit=3")

        assert resp.status_code == 200
        mock_get.assert_called_once_with("draft", limit=3)
