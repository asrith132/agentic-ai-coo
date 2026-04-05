"""
Tests for app.agents.marketing.tasks — Celery task wrapper.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest


class TestRunMarketingTask:
    def test_task_is_registered(self):
        """The Celery task should be importable and have the correct name."""
        from app.agents.marketing.tasks import run_marketing_task
        assert run_marketing_task.name == "app.agents.marketing.tasks.run_marketing_task"

    def test_task_calls_agent_run(self):
        """The task should instantiate MarketingAgent and call run()."""
        from app.agents.marketing.tasks import run_marketing_task

        fake_result = {"agent": "marketing", "status": "completed", "trends_found": 0}

        with patch("app.agents.marketing.tasks.MarketingAgent") as MockAgent:
            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=fake_result)

            with patch("app.agents.marketing.tasks.asyncio") as mock_asyncio:
                mock_loop = MagicMock()
                mock_loop.run_until_complete.return_value = fake_result
                mock_asyncio.get_event_loop.return_value = mock_loop

                # __wrapped__ on a bind=True task has signature (self, trigger)
                # where self is the Celery task instance
                result = run_marketing_task.__wrapped__(
                    trigger={"type": "scheduled"},
                    # Celery injects `self` — we skip it via keyword arg
                )

            assert result == fake_result

    def test_task_max_retries(self):
        """Task should have max_retries=3."""
        from app.agents.marketing.tasks import run_marketing_task
        assert run_marketing_task.max_retries == 3
