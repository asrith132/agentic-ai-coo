"""
Shared test fixtures for the marketing agent test suite.

All external dependencies (Supabase, LLM, platform APIs) are mocked here
so tests are deterministic and run without credentials.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Patch pydantic-settings so `Settings()` never reads real env / .env files
# This MUST happen before any app module is imported.
# ---------------------------------------------------------------------------

_FAKE_SETTINGS = {
    "supabase_url": "https://fake.supabase.co",
    "supabase_anon_key": "fake-anon",
    "supabase_service_role_key": "fake-service",
    "anthropic_api_key": "fake-anthropic-key",
    "redis_url": "redis://localhost:6379/0",
    "github_webhook_secret": "",
    "gmail_client_id": "",
    "gmail_client_secret": "",
    "gmail_refresh_token": "",
    "twilio_account_sid": "",
    "twilio_auth_token": "",
    "twilio_phone_from": "",
    "twilio_phone_to": "",
    "reddit_client_id": "",
    "reddit_client_secret": "",
    "reddit_username": "",
    "reddit_password": "",
    "reddit_user_agent": "test-bot",
    "reddit_subreddits": "",
    "x_api_key": "",
    "x_api_secret": "",
    "x_access_token": "",
    "x_access_token_secret": "",
    "linkedin_access_token": "",
    "linkedin_person_id": "",
    "linkedin_organization_id": "",
    "environment": "test",
    "log_level": "DEBUG",
}

# Build a fake Settings object before any other app import
import os

for k, v in _FAKE_SETTINGS.items():
    os.environ.setdefault(k.upper(), v)


# ---------------------------------------------------------------------------
# Supabase mock helpers
# ---------------------------------------------------------------------------


class FakeQueryBuilder:
    """Chainable mock that mimics the Supabase query builder pattern."""

    def __init__(self, data: list[dict[str, Any]] | dict[str, Any] | None = None):
        self._data = data if data is not None else []

    # Every chainable method returns self
    def select(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def insert(self, payload: Any) -> "FakeQueryBuilder":
        # Simulate an insert: add an id and created_at if missing
        if isinstance(payload, dict):
            row = {**payload}
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            self._data = [row]
        return self

    def update(self, payload: Any) -> "FakeQueryBuilder":
        if isinstance(self._data, list) and self._data:
            self._data = [{**self._data[0], **payload}]
        elif isinstance(payload, dict):
            self._data = [payload]
        return self

    def eq(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def in_(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def not_(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def order(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def limit(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def maybe_single(self) -> "FakeQueryBuilder":
        if isinstance(self._data, list):
            self._data = self._data[0] if self._data else None
        return self

    def single(self) -> "FakeQueryBuilder":
        if isinstance(self._data, list):
            self._data = self._data[0] if self._data else {}
        return self

    # Also support .contains and .not_ used by events
    def contains(self, *a: Any, **kw: Any) -> "FakeQueryBuilder":
        return self

    def execute(self) -> MagicMock:
        resp = MagicMock()
        resp.data = self._data
        return resp


class FakeSupabaseClient:
    """Minimal Supabase client mock that returns FakeQueryBuilders."""

    def __init__(self, default_data: list[dict[str, Any]] | None = None):
        self._default_data = default_data or []
        self._table_data: dict[str, list[dict[str, Any]]] = {}

    def set_table_data(self, table: str, data: list[dict[str, Any]]) -> None:
        self._table_data[table] = data

    def table(self, name: str) -> FakeQueryBuilder:
        data = self._table_data.get(name, self._default_data)
        return FakeQueryBuilder(list(data))


@pytest.fixture
def fake_supabase():
    """Return a FakeSupabaseClient and patch get_client to return it."""
    client = FakeSupabaseClient()
    with patch("app.db.supabase_client.get_client", return_value=client):
        # Also patch in tools and other modules that import get_client
        with patch("app.agents.marketing.tools.get_client", return_value=client):
            with patch("app.core.context.get_client", return_value=client):
                with patch("app.core.events.get_client", return_value=client):
                    with patch("app.core.approvals.get_client", return_value=client):
                        with patch("app.core.notifications.get_client", return_value=client):
                            yield client


# ---------------------------------------------------------------------------
# Global context fixtures
# ---------------------------------------------------------------------------

def make_global_context(**overrides: Any) -> dict[str, Any]:
    """Build a realistic global context dict."""
    base = {
        "id": str(uuid.uuid4()),
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "company_profile": {
            "name": "TestCo",
            "website": "https://testco.io",
            "industry": "developer tools",
            "stage": "seed",
            "description": "TestCo helps developers ship faster with AI-powered code review.",
        },
        "target_customer": {
            "persona": "Senior backend engineer",
            "pain_points": ["slow code reviews", "context switching", "CI flakiness"],
            "channels": ["reddit", "x", "linkedin"],
            "company_size": "10-200",
            "geography": "US",
        },
        "business_state": {"mrr": 5000, "runway_months": 18},
        "brand_voice": {
            "tone": "friendly, technical, no-BS",
            "values": ["transparency", "developer empathy"],
            "avoid": ["corporate jargon", "clickbait"],
            "example_copy": "We built this because code reviews shouldn't take longer than writing the code.",
        },
        "competitive_landscape": {
            "competitors": [{"name": "CompetitorX"}],
            "positioning": "fastest AI code reviewer",
            "differentiators": ["speed", "accuracy"],
        },
        "recent_events": [],
    }
    base.update(overrides)
    return base


@pytest.fixture
def global_context_data() -> dict[str, Any]:
    return make_global_context()


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Patch call_llm_text to return canned responses."""
    with patch("app.agents.marketing.agent.call_llm_text", new_callable=AsyncMock) as m:
        yield m


# ---------------------------------------------------------------------------
# Event / notification / approval mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_emit_event():
    with patch("app.agents.marketing.agent.emit_event", new_callable=AsyncMock) as m:
        m.return_value = MagicMock(id=uuid.uuid4())
        yield m


@pytest.fixture
def mock_notify():
    with patch("app.agents.marketing.agent.notify", new_callable=AsyncMock) as m:
        m.return_value = MagicMock(id=uuid.uuid4())
        yield m


@pytest.fixture
def mock_request_approval():
    with patch("app.agents.marketing.agent.request_approval", new_callable=AsyncMock) as m:
        m.return_value = MagicMock(id=uuid.uuid4())
        yield m


@pytest.fixture
def mock_get_unconsumed_events():
    with patch("app.agents.marketing.agent.get_unconsumed_events", new_callable=AsyncMock) as m:
        m.return_value = []
        yield m


@pytest.fixture
def mock_mark_consumed():
    with patch("app.agents.marketing.agent.mark_consumed", new_callable=AsyncMock) as m:
        yield m


# ---------------------------------------------------------------------------
# Tools-layer mocks (for agent tests that shouldn't hit DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_search_all_platforms():
    with patch("app.agents.marketing.agent.search_all_platforms", new_callable=AsyncMock) as m:
        m.return_value = []
        yield m


@pytest.fixture
def mock_store_trend():
    with patch("app.agents.marketing.agent.store_trend", new_callable=AsyncMock) as m:
        async def _store(trend: dict) -> dict:
            return {"id": str(uuid.uuid4()), **trend}
        m.side_effect = _store
        yield m


@pytest.fixture
def mock_store_content():
    with patch("app.agents.marketing.agent.store_content", new_callable=AsyncMock) as m:
        async def _store(content: dict) -> dict:
            return {"id": str(uuid.uuid4()), **content}
        m.side_effect = _store
        yield m


@pytest.fixture
def mock_update_content_status():
    with patch("app.agents.marketing.agent.update_content_status", new_callable=AsyncMock) as m:
        async def _update(content_id: str, status: str, **extra: Any) -> dict:
            return {"id": content_id, "status": status, **extra}
        m.side_effect = _update
        yield m


@pytest.fixture
def mock_get_content():
    with patch("app.agents.marketing.agent.get_content", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_get_trend():
    with patch("app.agents.marketing.agent.get_trend", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_publish_to_platform():
    with patch("app.agents.marketing.agent.publish_to_platform", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_get_global_context():
    with patch("app.agents.marketing.agent.get_global_context", new_callable=AsyncMock) as m:
        yield m
