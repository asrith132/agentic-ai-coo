"""
agents/marketing/tasks.py — Celery tasks for MarketingAgent.

Registered in celery_app.py include list. Beat schedule triggers
run_marketing_task every 30 minutes for trend scanning.
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery_app import celery_app
from app.agents.marketing.agent import MarketingAgent


@celery_app.task(name="app.agents.marketing.tasks.run_marketing_task", bind=True, max_retries=3)
def run_marketing_task(self, trigger: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the marketing agent — called by Celery Beat or on-demand."""
    agent = MarketingAgent()
    try:
        return asyncio.get_event_loop().run_until_complete(agent.run(trigger))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
